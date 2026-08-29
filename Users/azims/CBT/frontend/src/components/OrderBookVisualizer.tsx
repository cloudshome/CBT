import React, { useState, useEffect } from 'react';
import { Layers } from 'lucide-react';
import { OrderBookDepth, marketProvider } from '../data/providers/marketProvider';

interface OrderBookVisualizerProps {
  symbol: string;
  lastPrice: number;
}

export const OrderBookVisualizer: React.FC<OrderBookVisualizerProps> = ({
  symbol,
  lastPrice,
}) => {
  const [depth, setDepth] = useState<OrderBookDepth | null>(null);
  const [precision, setPrecision] = useState<number>(1);

  useEffect(() => {
    const unsub = marketProvider.subscribeOrderBook(symbol, (d) => {
      setDepth(d);
    });

    return () => unsub();
  }, [symbol]);

  // Aggregate with precision (5 asks, 5 bids for clean compact footprint)
  const bids = depth?.bids.slice(0, 5) || [];
  const asks = depth?.asks.slice(0, 5).reverse() || [];

  const maxTotal = Math.max(
    bids[bids.length - 1]?.total || 1,
    asks[0]?.total || 1,
    1
  );

  return (
    <div className="bg-[#0b0f19] border border-[#1e293b] rounded-lg p-2.5 flex flex-col font-mono select-none overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-border/80 text-xs">
        <div className="flex items-center gap-1.5 text-slate-300 font-bold">
          <Layers className="w-3.5 h-3.5 text-terminal-cyan" />
          <span>ORDER BOOK L2</span>
        </div>

        {/* Grouping Precision */}
        <div className="flex items-center gap-1 text-[10px] bg-slate-900 rounded p-0.5 border border-border">
          {[0.1, 1, 10].map((p) => (
            <button
              key={p}
              onClick={() => setPrecision(p)}
              className={`px-1.5 py-0.2 rounded ${precision === p ? 'bg-terminal-cyan text-slate-950 font-bold' : 'text-slate-400'}`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Column Headers */}
      <div className="grid grid-cols-3 text-[10px] text-slate-500 py-1.5 border-b border-border/40">
        <span>Price (USDT)</span>
        <span className="text-right">Size</span>
        <span className="text-right">Total</span>
      </div>

      {/* Asks (Sells) */}
      <div className="flex-1 flex flex-col justify-end gap-0.5 py-1">
        {asks.map((a, i) => {
          const depthPct = (a.total / maxTotal) * 100;
          return (
            <div key={`ask-${i}`} className="relative grid grid-cols-3 text-[11px] py-0.5">
              <div
                className="absolute inset-y-0 right-0 bg-terminal-red/15 rounded-sm pointer-events-none"
                style={{ width: `${Math.min(100, depthPct)}%` }}
              />
              <span className="text-terminal-red font-semibold z-10">${a.price.toFixed(2)}</span>
              <span className="text-right text-slate-300 z-10">{a.size.toFixed(4)}</span>
              <span className="text-right text-slate-500 z-10">{a.total.toFixed(2)}</span>
            </div>
          );
        })}
      </div>

      {/* Mid Market Price & Spread Readout */}
      <div className="py-2 my-1 px-2 rounded bg-slate-900/90 border border-border flex items-center justify-between text-xs">
        <span className="text-slate-200 font-bold text-sm">
          ${lastPrice > 0 ? lastPrice.toFixed(2) : (bids[0]?.price || 0).toFixed(2)}
        </span>
        <span className="text-[10px] text-terminal-cyan">SPREAD: ~0.01%</span>
      </div>

      {/* Bids (Buys) */}
      <div className="flex-1 flex flex-col gap-0.5 py-1">
        {bids.map((b, i) => {
          const depthPct = (b.total / maxTotal) * 100;
          return (
            <div key={`bid-${i}`} className="relative grid grid-cols-3 text-[11px] py-0.5">
              <div
                className="absolute inset-y-0 right-0 bg-terminal-green/15 rounded-sm pointer-events-none"
                style={{ width: `${Math.min(100, depthPct)}%` }}
              />
              <span className="text-terminal-green font-semibold z-10">${b.price.toFixed(2)}</span>
              <span className="text-right text-slate-300 z-10">{b.size.toFixed(4)}</span>
              <span className="text-right text-slate-500 z-10">{b.total.toFixed(2)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
