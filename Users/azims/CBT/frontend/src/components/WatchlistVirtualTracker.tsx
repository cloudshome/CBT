import React, { memo } from 'react';
import { Star, TrendingUp, TrendingDown, Search } from 'lucide-react';

interface WatchlistVirtualTrackerProps {
  currentSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}

interface WatchlistItem {
  symbol: string;
  name: string;
  tier: 'FLAGSHIP_CORE' | 'SECONDARY';
  price: number;
  change: number;
  volume: string;
  isGold?: boolean;
}

const CORE_PAIRS: WatchlistItem[] = [
  {
    symbol: 'BTCUSDT',
    name: 'Bitcoin',
    tier: 'FLAGSHIP_CORE',
    price: 88450.0,
    change: 2.45,
    volume: '1.2B',
  },
  {
    symbol: 'ETHUSDT',
    name: 'Ethereum',
    tier: 'FLAGSHIP_CORE',
    price: 2940.5,
    change: -1.15,
    volume: '650M',
  },
  {
    symbol: 'PAXGUSDT',
    name: 'Gold (PAXG Spot)',
    tier: 'FLAGSHIP_CORE',
    price: 2715.4,
    change: 1.12,
    volume: '380M',
    isGold: true,
  },
  {
    symbol: 'XAUUSDT',
    name: 'Gold (XAU Futures)',
    tier: 'FLAGSHIP_CORE',
    price: 2718.2,
    change: 1.08,
    volume: '510M',
    isGold: true,
  },
];

const WatchlistVirtualTrackerComponent: React.FC<WatchlistVirtualTrackerProps> = ({
  currentSymbol,
  onSelectSymbol,
}) => {
  const [search, setSearch] = React.useState('');

  const filtered = CORE_PAIRS.filter((item) => {
    const q = search.toLowerCase();
    const matchesSym = item.symbol.toLowerCase().includes(q);
    const matchesName = item.name.toLowerCase().includes(q);
    const matchesGold = (q === 'gold' || q === 'xau') && (item.isGold || item.symbol.includes('PAXG'));
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
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400 border border-amber-400/20 font-bold">
            BTC • ETH • GOLD
          </span>
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
          const isPos = item.change >= 0;
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
                  {item.name} • Vol: {item.volume}
                </span>
              </div>

              <div className="flex flex-col items-end gap-0.5">
                <span className="font-semibold text-slate-100">${item.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                <span className={`text-[10px] font-bold flex items-center gap-0.5 ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {isPos ? <TrendingUp className="w-2.5 h-2.5" /> : <TrendingDown className="w-2.5 h-2.5" />}
                  {isPos ? '+' : ''}{item.change.toFixed(2)}%
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export const WatchlistVirtualTracker = memo(WatchlistVirtualTrackerComponent);
