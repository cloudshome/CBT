import React from 'react';
import { Star, TrendingUp, TrendingDown, Search } from 'lucide-react';

interface WatchlistVirtualTrackerProps {
  currentSymbol: string;
  onSelectSymbol: (symbol: string) => void;
}

const DEFAULT_WATCHLIST = [
  { symbol: 'BTCUSDT', price: 88450.0, change: 2.45, volume: '1.2B' },
  { symbol: 'ETHUSDT', price: 2940.5, change: -1.15, volume: '650M' },
  { symbol: 'SOLUSDT', price: 184.2, change: 5.80, volume: '420M' },
  { symbol: 'AVAXUSDT', price: 32.8, change: 0.95, volume: '110M' },
  { symbol: 'ADAUSDT', price: 0.74, change: -2.30, volume: '95M' },
  { symbol: 'LINKUSDT', price: 18.5, change: 3.10, volume: '140M' },
];

export const WatchlistVirtualTracker: React.FC<WatchlistVirtualTrackerProps> = ({
  currentSymbol,
  onSelectSymbol,
}) => {
  const [search, setSearch] = React.useState('');

  const filtered = DEFAULT_WATCHLIST.filter((item) =>
    item.symbol.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col h-full font-mono select-none">
      {/* Header & Search */}
      <div className="pb-2 border-b border-border/80 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-slate-300 font-bold">
            <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
            <span>WATCHLIST</span>
          </div>
          <span className="text-[10px] text-slate-500">{filtered.length} ASSETS</span>
        </div>

        {/* Search Input */}
        <div className="relative">
          <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
          <input
            type="text"
            placeholder="Filter symbol..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-900 border border-border rounded pl-7 pr-2 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-terminal-cyan"
          />
        </div>
      </div>

      {/* Asset Items List */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-1 py-1 mt-1">
        {filtered.map((item) => {
          const isSelected = item.symbol === currentSymbol;
          const isPos = item.change >= 0;
          return (
            <button
              key={item.symbol}
              onClick={() => onSelectSymbol(item.symbol)}
              className={`p-2 rounded flex items-center justify-between text-xs transition border ${
                isSelected
                  ? 'bg-terminal-cyan/15 border-terminal-cyan text-slate-100'
                  : 'bg-slate-900/60 border-border/40 hover:bg-slate-900 text-slate-400'
              }`}
            >
              <div className="flex flex-col items-start">
                <span className="font-bold text-slate-200">{item.symbol}</span>
                <span className="text-[10px] text-slate-500">Vol: {item.volume}</span>
              </div>

              <div className="flex flex-col items-end">
                <span className="font-semibold text-slate-200">${item.price.toLocaleString()}</span>
                <span className={`text-[10px] font-bold flex items-center gap-0.5 ${isPos ? 'text-terminal-green' : 'text-terminal-red'}`}>
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
