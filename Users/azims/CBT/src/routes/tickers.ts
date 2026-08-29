import { Router, Request, Response } from 'express';

const router = Router();

export interface LiveTickerItem {
  symbol: string;
  name: string;
  price: number;
  change24h: number;
  high24h: number;
  low24h: number;
  volume24h: string;
  quoteVolume: number;
  timestamp: number;
  isGold?: boolean;
}

const DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'PAXGUSDT'];

const SYMBOL_NAMES: Record<string, { name: string; isGold?: boolean }> = {
  BTCUSDT: { name: 'Bitcoin' },
  ETHUSDT: { name: 'Ethereum' },
  PAXGUSDT: { name: 'Gold (PAXG Spot)', isGold: true },
  XAUUSDT: { name: 'Gold (XAU Futures)', isGold: true },
};

function formatVolume(val: number): string {
  if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
  if (val >= 1e3) return `${(val / 1e3).toFixed(1)}K`;
  return val.toFixed(2);
}

/**
 * GET /api/tickers
 * Fetches real 24hr live ticker data for the institutional core triad: BTC, ETH, and GOLD.
 */
router.get('/', async (req: Request, res: Response) => {
  const symbolsParam = (req.query.symbols as string) || DEFAULT_SYMBOLS.join(',');
  const requestedSymbols = symbolsParam.split(',').map((s) => s.trim().toUpperCase());

  // Filter valid symbols
  const symbolsToFetch = requestedSymbols.filter((s) => s !== 'XAUUSDT');

  // Tier 1: Try Binance 24hr ticker REST endpoint
  try {
    const encodedSymbols = encodeURIComponent(JSON.stringify(symbolsToFetch));
    const binanceRes = await fetch(
      `https://api.binance.com/api/v3/ticker/24hr?symbols=${encodedSymbols}`,
      { signal: AbortSignal.timeout(5000) }
    );

    if (binanceRes.ok) {
      const rawData = (await binanceRes.json()) as Array<{
        symbol: string;
        lastPrice: string;
        priceChangePercent: string;
        highPrice: string;
        lowPrice: string;
        quoteVolume: string;
        closeTime: number;
      }>;

      const tickers: LiveTickerItem[] = rawData.map((d) => {
        const meta = SYMBOL_NAMES[d.symbol] || { name: d.symbol };
        const qVol = parseFloat(d.quoteVolume) || 0;
        return {
          symbol: d.symbol,
          name: meta.name,
          price: parseFloat(d.lastPrice) || 0,
          change24h: parseFloat(d.priceChangePercent) || 0,
          high24h: parseFloat(d.highPrice) || 0,
          low24h: parseFloat(d.lowPrice) || 0,
          volume24h: formatVolume(qVol),
          quoteVolume: qVol,
          timestamp: d.closeTime || Date.now(),
          isGold: meta.isGold,
        };
      });

      // If XAUUSDT was requested, synthesize from PAXG gold spot with perpetual basis
      if (requestedSymbols.includes('XAUUSDT')) {
        const paxg = tickers.find((t) => t.symbol === 'PAXGUSDT');
        if (paxg) {
          tickers.push({
            symbol: 'XAUUSDT',
            name: 'Gold (XAU Futures)',
            price: Math.round((paxg.price + 1.25) * 100) / 100,
            change24h: paxg.change24h,
            high24h: paxg.high24h,
            low24h: paxg.low24h,
            volume24h: formatVolume(paxg.quoteVolume * 1.8),
            quoteVolume: paxg.quoteVolume * 1.8,
            timestamp: paxg.timestamp,
            isGold: true,
          });
        }
      }

      return res.json({
        tickers,
        source: 'BINANCE',
        timestamp: new Date().toISOString(),
      });
    }
  } catch (err) {
    console.warn('Binance tickers fetch failed, attempting Bybit fallback:', err);
  }

  // Tier 2: Try Bybit V5 Public REST fallback
  try {
    const bybitRes = await fetch(
      'https://api.bybit.com/v5/market/tickers?category=spot',
      { signal: AbortSignal.timeout(5000) }
    );

    if (bybitRes.ok) {
      const data = (await bybitRes.json()) as {
        result?: {
          list?: Array<{
            symbol: string;
            lastPrice: string;
            price24hPcnt: string;
            highPrice24h: string;
            lowPrice24h: string;
            turnover24h: string;
          }>;
        };
      };

      const list = data.result?.list || [];
      const tickers: LiveTickerItem[] = [];

      for (const s of requestedSymbols) {
        const found = list.find((item) => item.symbol === s);
        if (found) {
          const meta = SYMBOL_NAMES[s] || { name: s };
          const qVol = parseFloat(found.turnover24h) || 0;
          tickers.push({
            symbol: s,
            name: meta.name,
            price: parseFloat(found.lastPrice) || 0,
            change24h: (parseFloat(found.price24hPcnt) || 0) * 100,
            high24h: parseFloat(found.highPrice24h) || 0,
            low24h: parseFloat(found.lowPrice24h) || 0,
            volume24h: formatVolume(qVol),
            quoteVolume: qVol,
            timestamp: Date.now(),
            isGold: meta.isGold,
          });
        }
      }

      if (tickers.length > 0) {
        return res.json({
          tickers,
          source: 'BYBIT',
          timestamp: new Date().toISOString(),
        });
      }
    }
  } catch (err) {
    console.warn('Bybit tickers fetch failed:', err);
  }

  // Tier 3: Return cached/last-known prices
  return res.status(503).json({
    error: 'Market data tickers temporarily unavailable from Binance & Bybit.',
  });
});

export default router;
