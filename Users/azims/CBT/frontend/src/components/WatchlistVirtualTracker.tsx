import React, { useState, useEffect, memo } from 'react';
import { Star, TrendingUp, TrendingDown, Search } from 'lucide-react';
import { api } from '../services/api';

interface WatchlistVirtualTrackerProps {
  currentSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onPriceTick?: (symbol: string, price: number, high?: number, low?: number) => void;
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  high24h: number;
  low24h: number;
  volume: string;
  isGold?: boolean;
  lastUpdated?: number;
}

const INITIAL_CORE_PAIRS: WatchlistItem[] = [
  {
    symbol: 'BTCUSDT',
    name: 'Bitcoin',
    price: 0,
    change: 0,
    high24h: 0,
    low24h: 0,
    volume: '...',
  },
  {
    symbol: 'ETHUSDT',
    name: 'Ethereum',
    price: 0,
    change: 0,
    high24h: 0,
    low24h: 0,
    volume: '...',
  },
  {
    symbol: 'PAXGUSDT',
    name: 'Gold (PAXG Spot)',
    price: 0,
    change: 0,
    high24h: 0,
    low24h: 0,
    volume: '...',
    isGold: true,
  },
  {
    symbol: 'XAUUSDT',
    name: 'Gold (XAU Futures)',
    price: 0,
    change: 0,
    high24h: 0,
    low24h: 0,
    volume: '...',
    isGold: true,
  },
];

const WatchlistVirtualTrackerComponent: React.FC<WatchlistVirtualTrackerProps> = ({
  currentSymbol,
  onSelectSymbol,
  onPriceTick,
}) => {
  const [items, setItems] = useState<WatchlistItem[]>(INITIAL_CORE_PAIRS);
  const [search, setSearch] = useState('');
  const [isLiveConnected, setIsLiveConnected] = useState(false);

  // 1. Initial REST fetch for authentic 24h Ticker statistics
  useEffect(() => {
    let isMounted = true;

    async function loadLiveTickers() {
      try {
        const res = await api.getLiveTickers(['BTCUSDT', 'ETHUSDT', 'PAXGUSDT', 'XAUUSDT']);
        if (isMounted && res.tickers && res.tickers.length > 0) {
          const cleanCur = currentSymbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
          const curMatch = res.tickers.find((t) => String(t.symbol || '').toUpperCase().replace(/[^A-Z0-9]/g, '') === cleanCur);
          if (curMatch && onPriceTick && Number(curMatch.price) > 0) {
            onPriceTick(String(curMatch.symbol), Number(curMatch.price), Number(curMatch.high24h) || 0, Number(curMatch.low24h) || 0);
          }

          setItems(
            res.tickers.map((t) => {
              const sym = String(t.symbol || '').toUpperCase();
              const defaultName =
                sym === 'BTCUSDT'
                  ? 'Bitcoin'
                  : sym === 'ETHUSDT'
                  ? 'Ethereum'
                  : sym.includes('PAXG')
                  ? 'Gold (PAXG Spot)'
                  : sym.includes('XAU')
                  ? 'Gold (XAU Futures)'
                  : sym;
              const rawVol = Number(t.volume24h) || 0;
              const vol =
                rawVol >= 1e6
                  ? `${(rawVol / 1e6).toFixed(1)}M`
                  : rawVol > 0
                  ? `${rawVol.toLocaleString()}`
                  : String(t.volume24h || '...');
              return {
                symbol: sym,
                name: String(t.name || defaultName),
                price: Number(t.price) || 0,
                change: Number(t.change24h) || 0,
                high24h: Number(t.high24h) || 0,
                low24h: Number(t.low24h) || 0,
                volume: vol,
                isGold: Boolean(t.isGold || sym.includes('PAXG') || sym.includes('XAU')),
                lastUpdated: Number(t.timestamp) || Date.now(),
              };
            })
          );
        }
      } catch (err) {
        console.warn('Failed to load initial REST tickers:', err);
      }
    }

    loadLiveTickers();
    const pollInterval = setInterval(loadLiveTickers, 10000); // 10s fallback sync

    return () => {
      isMounted = false;
      clearInterval(pollInterval);
    };
  }, [currentSymbol, onPriceTick]);

  // 2. Real-Time Multi-Stream WebSocket for Sub-Second Price Ticks
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    function connectWs() {
      const streamUrl = 'wss://stream.binance.com:9443/ws/btcusdt@ticker/ethusdt@ticker/paxgusdt@ticker';

      try {
        ws = new WebSocket(streamUrl);

        ws.onopen = () => {
          setIsLiveConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            const sym = (data.s || '').toUpperCase();
            const newPrice = parseFloat(data.c) || 0;
            const newChange = parseFloat(data.P) || 0;
            const qVol = parseFloat(data.q) || 0;

            if (newPrice > 0 && sym) {
              const cleanCur = currentSymbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
              const cleanSym = sym.replace(/[^A-Z0-9]/g, '');
              if (cleanCur === cleanSym && onPriceTick) {
                onPriceTick(sym, newPrice, parseFloat(data.h) || 0, parseFloat(data.l) || 0);
              }

              setItems((prev) =>
                prev.map((item) => {
                  if (item.symbol === sym) {
                    return {
                      ...item,
                      price: newPrice,
                      change: newChange,
                      volume: qVol >= 1e9 ? `${(qVol / 1e9).toFixed(2)}B` : qVol >= 1e6 ? `${(qVol / 1e6).toFixed(1)}M` : `${(qVol / 1e3).toFixed(1)}K`,
                      lastUpdated: Date.now(),
                    };
                  }
                  // Keep XAU in sync with PAXG spot
                  if (item.symbol === 'XAUUSDT' && sym === 'PAXGUSDT') {
                    return {
                      ...item,
                      price: Math.round((newPrice + 1.25) * 100) / 100,
                      change: newChange,
                      lastUpdated: Date.now(),
                    };
                  }
                  return item;
                })
              );
            }
          } catch {
            // Ignore parse errors on ping frames
          }
        };

        ws.onerror = () => {
          setIsLiveConnected(false);
        };

        ws.onclose = () => {
          setIsLiveConnected(false);
          reconnectTimeout = setTimeout(connectWs, 3000);
        };
      } catch {
        setIsLiveConnected(false);
      }
    }

    connectWs();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
    };
  }, []);

  const filtered = items.filter((item) => {
    if (!item) return false;
    const q = (search || '').trim().toLowerCase();
    if (!q) return true;
    const sym = (item.symbol || '').toLowerCase();
    const name = (item.name || '').toLowerCase();
    const matchesSym = sym.includes(q);
    const matchesName = name.includes(q);
    const matchesGold = (q === 'gold' || q === 'xau') && (item.isGold || sym.includes('paxg') || sym.includes('xau'));
    return matchesSym || matchesName || matchesGold;
  });

  return (
    <div className="bg-[#080b11] border border-[#1e293b] rounded-lg p-3 flex flex-col h-full font-mono select-none">
      {/* Header & Search */}
      <div className="pb-2 border-b border-[#1e293b] flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-amber-400 font-bold">
            <Star className="w-3.5 h-3.5 fill-amber-400" />
            <span className="text-slate-100">CORE WATCHLIST</span>
          </div>
          <div className="flex items-center gap-1">
            <span
              className={`w-2 h-2 rounded-full ${
                isLiveConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span className="text-[10px] text-slate-400">
              {isLiveConnected ? 'LIVE FEED' : 'SYNCING'}
            </span>
          </div>
        </div>

        {/* Search Input with Gold/XAU support */}
        <div className="relative">
          <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
          <input
            type="text"
            placeholder="Filter BTC, ETH, GOLD..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#050811] border border-[#1e293b] rounded pl-7 pr-2 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-sky-400"
          />
        </div>
      </div>

      {/* Asset Items List */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-1.5 py-1 mt-1">
        {filtered.map((item) => {
          const isSelected = item.symbol === currentSymbol;
          const isPos = (item.change || 0) >= 0;
          const price = Number(item.price || 0);
          return (
            <button
              key={item.symbol}
              onClick={() => onSelectSymbol(item.symbol)}
              className={`p-2 rounded-lg flex items-center justify-between text-xs transition border ${
                isSelected
                  ? 'bg-sky-500/15 border-sky-400 text-slate-100 shadow-sm shadow-sky-500/20'
                  : 'bg-[#0b101b] border-[#1e293b]/70 hover:bg-[#0f172a] hover:border-slate-700 text-slate-400'
              }`}
            >
              <div className="flex flex-col items-start gap-0.5">
                <div className="flex items-center gap-1.5">
                  <span className={`font-bold ${isSelected ? 'text-white' : 'text-slate-200'}`}>
                    {item.symbol}
                  </span>
                  {item.isGold ? (
                    <span className="text-[9px] px-1 py-0.2 rounded bg-amber-400/20 text-amber-300 font-bold border border-amber-400/40">
                      GOLD
                    </span>
                  ) : (
                    <span className="text-[9px] px-1 py-0.2 rounded bg-sky-500/20 text-sky-300 font-bold border border-sky-500/40">
                      CORE
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-slate-500">
                  {item.name || item.symbol} {item.volume !== '...' && `• Vol: ${item.volume}`}
                </span>
              </div>

              <div className="flex flex-col items-end gap-0.5">
                <span className="font-semibold text-slate-100 font-mono">
                  {price > 0
                    ? `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                    : 'Loading...'}
                </span>
                {price > 0 && (
                  <span
                    className={`text-[10px] font-bold flex items-center gap-0.5 ${
                      isPos ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {isPos ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                    {isPos ? '+' : ''}
                    {Number(item.change || 0).toFixed(2)}%
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export const WatchlistVirtualTracker = memo(WatchlistVirtualTrackerComponent);
