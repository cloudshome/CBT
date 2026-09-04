import { OHLCVCandle } from '../../types';
import { WSStateMachine, WSConnectionState } from './wsStateMachine';

export interface OrderBookEntry {
  price: number;
  size: number;
  total: number;
}

export interface OrderBookDepth {
  symbol: string;
  timestamp: number;
  bids: OrderBookEntry[];
  asks: OrderBookEntry[];
}

export interface TickerData {
  symbol: string;
  lastPrice: number;
  high24h: number;
  low24h: number;
  volume24h: number;
  priceChangePct24h: number;
  timestamp: number;
}

export type Unsubscribe = () => void;

export interface IMarketDataProvider {
  fetchHistoricalOHLCV(symbol: string, timeframe: string, limit?: number): Promise<OHLCVCandle[]>;
  subscribeRealtimeCandles(
    symbol: string,
    timeframe: string,
    onCandle: (candle: OHLCVCandle) => void
  ): Unsubscribe;
  subscribeOrderBook(
    symbol: string,
    onDepth: (depth: OrderBookDepth) => void
  ): Unsubscribe;
  subscribeTicker(
    symbol: string,
    onTicker: (ticker: TickerData) => void
  ): Unsubscribe;
  getConnectionState(): WSConnectionState;
  onConnectionStateChange(callback: (state: WSConnectionState, attempt: number) => void): Unsubscribe;
}

/**
 * Universal Market Data Provider connecting to Binance Futures WebSocket via resilient WSStateMachine.
 */
export class BinanceMarketDataProvider implements IMarketDataProvider {
  private stateMachine: WSStateMachine | null = null;
  private subscribers = new Set<(candle: OHLCVCandle) => void>();
  private depthSubscribers = new Set<(depth: OrderBookDepth) => void>();
  private tickerSubscribers = new Set<(ticker: TickerData) => void>();
  private stateListeners = new Set<(state: WSConnectionState, attempt: number) => void>();

  private activeSymbol = '';
  private activeTimeframe = '';

  async fetchHistoricalOHLCV(symbol: string, timeframe: string, limit = 100): Promise<OHLCVCandle[]> {
    const res = await fetch(`/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch historical candles`);
    const data = await res.json();
    return data.candles || [];
  }

  subscribeRealtimeCandles(
    symbol: string,
    timeframe: string,
    onCandle: (candle: OHLCVCandle) => void
  ): Unsubscribe {
    this.subscribers.add(onCandle);
    this.ensureWebSocket(symbol, timeframe);

    return () => {
      this.subscribers.delete(onCandle);
      this.checkCleanup();
    };
  }

  subscribeOrderBook(
    symbol: string,
    onDepth: (depth: OrderBookDepth) => void
  ): Unsubscribe {
    this.depthSubscribers.add(onDepth);
    this.ensureWebSocket(symbol, '15m');

    return () => {
      this.depthSubscribers.delete(onDepth);
      this.checkCleanup();
    };
  }

  subscribeTicker(
    symbol: string,
    onTicker: (ticker: TickerData) => void
  ): Unsubscribe {
    this.tickerSubscribers.add(onTicker);
    this.ensureWebSocket(symbol, '15m');

    return () => {
      this.tickerSubscribers.delete(onTicker);
      this.checkCleanup();
    };
  }

  getConnectionState(): WSConnectionState {
    return this.stateMachine ? this.stateMachine.getState() : 'IDLE';
  }

  onConnectionStateChange(callback: (state: WSConnectionState, attempt: number) => void): Unsubscribe {
    this.stateListeners.add(callback);
    callback(this.getConnectionState(), this.stateMachine?.getAttempt() ?? 0);
    return () => {
      this.stateListeners.delete(callback);
    };
  }

  private buildStreamUrl(cleanSymbol: string, binanceTF: string): string {
    const isGold = cleanSymbol.includes('paxg') || cleanSymbol.includes('xau');
    const streamSymbol = isGold ? 'paxgusdt' : cleanSymbol;
    const host = 'stream.binance.com:9443';
    const streamName = `${streamSymbol}@kline_${binanceTF}/${streamSymbol}@depth20@100ms/${streamSymbol}@ticker`;
    return `wss://${host}/stream?streams=${streamName}`;
  }

  private ensureWebSocket(symbol: string, timeframe: string) {
    const cleanSymbol = symbol.toLowerCase().replace(/[^a-z0-9]/g, '');
    const tfMap: Record<string, string> = {
      '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '1h': '1h', '4h': '4h', '1d': '1d'
    };
    const binanceTF = tfMap[timeframe] || '15m';

    const url = this.buildStreamUrl(cleanSymbol, binanceTF);

    if (this.stateMachine) {
      if (this.activeSymbol === cleanSymbol && this.activeTimeframe === binanceTF) {
        return;
      }
      this.activeSymbol = cleanSymbol;
      this.activeTimeframe = binanceTF;
      this.stateMachine.setUrl(url);
      return;
    }

    this.activeSymbol = cleanSymbol;
    this.activeTimeframe = binanceTF;

    this.stateMachine = new WSStateMachine({
      url,
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      heartbeatTimeoutMs: 20000,
      onStateChange: (state, attempt) => {
        this.stateListeners.forEach((cb) => cb(state, attempt));
      },
      onMessage: (event) => {
        try {
          const payload = JSON.parse(event.data);
          const data = payload.data;
          const stream = payload.stream as string;

          if (stream.includes('@kline')) {
            const k = data.k;
            const candle: OHLCVCandle = [
              k.t,
              parseFloat(k.o),
              parseFloat(k.h),
              parseFloat(k.l),
              parseFloat(k.c),
              parseFloat(k.v),
            ];
            this.subscribers.forEach((cb) => cb(candle));
          } else if (stream.includes('@depth')) {
            const rawBids = (data.bids || data.b || []).slice(0, 15);
            const rawAsks = (data.asks || data.a || []).slice(0, 15);

            let cumBid = 0;
            const bids: OrderBookEntry[] = rawBids.map((b: [string, string]) => {
              const p = parseFloat(b[0]);
              const s = parseFloat(b[1]);
              cumBid += s;
              return { price: p, size: s, total: cumBid };
            });

            let cumAsk = 0;
            const asks: OrderBookEntry[] = rawAsks.map((a: [string, string]) => {
              const p = parseFloat(a[0]);
              const s = parseFloat(a[1]);
              cumAsk += s;
              return { price: p, size: s, total: cumAsk };
            });

            const depth: OrderBookDepth = {
              symbol,
              timestamp: Date.now(),
              bids,
              asks,
            };
            this.depthSubscribers.forEach((cb) => cb(depth));
          } else if (stream.includes('@ticker')) {
            const ticker: TickerData = {
              symbol,
              lastPrice: parseFloat(data.c || data.lastPrice || '0'),
              high24h: parseFloat(data.h || data.highPrice || '0'),
              low24h: parseFloat(data.l || data.lowPrice || '0'),
              volume24h: parseFloat(data.v || data.volume || '0'),
              priceChangePct24h: parseFloat(data.P || data.priceChangePercent || '0'),
              timestamp: data.E || Date.now(),
            };
            this.tickerSubscribers.forEach((cb) => cb(ticker));
          }
        } catch {
          // Ignore parse errors on heartbeat frames
        }
      },
    });

    this.stateMachine.connect();
  }

  private checkCleanup() {
    if (this.subscribers.size === 0 && this.depthSubscribers.size === 0 && this.tickerSubscribers.size === 0) {
      if (this.stateMachine) {
        this.stateMachine.disconnect();
        this.stateMachine = null;
      }
    }
  }
}

export const marketProvider = new BinanceMarketDataProvider();
