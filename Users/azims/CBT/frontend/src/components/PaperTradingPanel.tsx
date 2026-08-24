import React, { useState } from 'react';
import { ShieldAlert, ShieldCheck, Play, RefreshCw, Layers } from 'lucide-react';
import { PaperTrade, RiskConfig } from '../types';

interface PaperTradingPanelProps {
  symbol: string;
  lastPrice: number;
  initialEntry?: number;
  initialSL?: number;
  initialTP?: number;
  initialSide?: 'BUY' | 'SELL';
  positions: PaperTrade[];
  riskConfig?: RiskConfig;
  onSubmitTrade: (trade: {
    symbol: string;
    side: 'BUY' | 'SELL';
    entryPrice: number;
    sl: number;
    tp: number;
    size: number;
  }) => Promise<void>;
  onRefreshPositions: () => void;
  loading?: boolean;
}

export const PaperTradingPanel: React.FC<PaperTradingPanelProps> = ({
  symbol,
  lastPrice,
  initialEntry,
  initialSL,
  initialTP,
  initialSide = 'BUY',
  positions,
  riskConfig,
  onSubmitTrade,
  onRefreshPositions,
  loading = false,
}) => {
  const [side, setSide] = useState<'BUY' | 'SELL'>(initialSide);
  const [entryPrice, setEntryPrice] = useState<string>(
    initialEntry ? String(initialEntry) : lastPrice > 0 ? String(lastPrice) : '65000'
  );
  const [sl, setSL] = useState<string>(
    initialSL ? String(initialSL) : lastPrice > 0 ? String(Number((lastPrice * 0.99).toFixed(2))) : '64350'
  );
  const [tp, setTP] = useState<string>(
    initialTP ? String(initialTP) : lastPrice > 0 ? String(Number((lastPrice * 1.02).toFixed(2))) : '66300'
  );
  const [size, setSize] = useState<string>('1.0');
  const [submitting, setSubmitting] = useState(false);

  // Sync external setup selections if provided
  React.useEffect(() => {
    if (initialEntry) setEntryPrice(String(initialEntry));
    if (initialSL) setSL(String(initialSL));
    if (initialTP) setTP(String(initialTP));
    if (initialSide) setSide(initialSide);
  }, [initialEntry, initialSL, initialTP, initialSide]);

  // Risk Gate calculation preview
  const numEntry = parseFloat(entryPrice) || 0;
  const numSL = parseFloat(sl) || 0;
  const numSize = parseFloat(size) || 1.0;

  const accountBalance = riskConfig?.accountBalance || 100000.0;
  const maxRiskDollar = accountBalance * (riskConfig?.maxRiskPerTrade || 0.02); // $2,000

  const dollarRisk = Math.abs(numEntry - numSL) * numSize;
  const riskPct = accountBalance > 0 ? (dollarRisk / accountBalance) * 100 : 0;
  const isRiskBreached = dollarRisk > maxRiskDollar;
  const isOpenTradesLimitReached = (positions.length || 0) >= (riskConfig?.maxOpenTrades || 3);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (numEntry <= 0 || numSL <= 0 || !parseFloat(tp)) return;

    setSubmitting(true);
    try {
      await onSubmitTrade({
        symbol,
        side,
        entryPrice: numEntry,
        sl: numSL,
        tp: parseFloat(tp),
        size: numSize,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-background-card border border-border rounded-lg p-4 shadow-lg flex flex-col h-full">
      {/* Panel Header */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-terminal-cyan" />
          <h3 className="text-xs font-mono font-bold text-slate-200 uppercase">
            PAPER TRADING &amp; RISK GATE
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            BAL: ${accountBalance.toLocaleString()}
          </span>
          <button
            onClick={onRefreshPositions}
            title="Refresh Open Positions"
            className="p-1 rounded text-slate-400 hover:text-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1">
        {/* Left: Order Placement Form (5 cols) */}
        <form onSubmit={handleSubmit} className="lg:col-span-5 flex flex-col justify-between space-y-3">
          {/* Side Selector */}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setSide('BUY')}
              className={`py-1.5 rounded font-mono text-xs font-bold transition-all border ${
                side === 'BUY'
                  ? 'bg-terminal-green/20 border-terminal-green text-terminal-green shadow-sm'
                  : 'bg-background border-border text-slate-400 hover:text-slate-200'
              }`}
            >
              BUY / LONG
            </button>
            <button
              type="button"
              onClick={() => setSide('SELL')}
              className={`py-1.5 rounded font-mono text-xs font-bold transition-all border ${
                side === 'SELL'
                  ? 'bg-terminal-red/20 border-terminal-red text-terminal-red shadow-sm'
                  : 'bg-background border-border text-slate-400 hover:text-slate-200'
              }`}
            >
              SELL / SHORT
            </button>
          </div>

          {/* Form Inputs */}
          <div className="space-y-2 text-xs font-mono">
            <div>
              <label className="text-[10px] text-slate-400 block mb-0.5">SYMBOL</label>
              <input
                type="text"
                disabled
                value={symbol}
                className="w-full bg-background border border-border rounded px-2.5 py-1.5 text-slate-300 font-bold"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-slate-400 block mb-0.5">ENTRY PRICE</label>
                <input
                  type="number"
                  step="any"
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)}
                  className="w-full bg-background border border-border rounded px-2.5 py-1.5 text-white focus:border-terminal-cyan focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400 block mb-0.5">SIZE (UNITS)</label>
                <input
                  type="number"
                  step="any"
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  className="w-full bg-background border border-border rounded px-2.5 py-1.5 text-white focus:border-terminal-cyan focus:outline-none"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-slate-400 block mb-0.5">STOP LOSS (SL)</label>
                <input
                  type="number"
                  step="any"
                  value={sl}
                  onChange={(e) => setSL(e.target.value)}
                  className="w-full bg-background border border-terminal-red/40 rounded px-2.5 py-1.5 text-terminal-red focus:outline-none"
                  required
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400 block mb-0.5">TAKE PROFIT (TP)</label>
                <input
                  type="number"
                  step="any"
                  value={tp}
                  onChange={(e) => setTP(e.target.value)}
                  className="w-full bg-background border border-terminal-green/40 rounded px-2.5 py-1.5 text-terminal-green focus:outline-none"
                  required
                />
              </div>
            </div>
          </div>

          {/* Pre-Execution Risk Gate Preview */}
          <div
            className={`p-2 rounded border text-xs font-mono transition-all ${
              isRiskBreached || isOpenTradesLimitReached
                ? 'bg-[#1D1014] border-terminal-red/40 text-terminal-red'
                : 'bg-[#0E161D] border-terminal-cyan/30 text-terminal-cyan'
            }`}
          >
            <div className="flex items-center justify-between font-bold">
              <span className="flex items-center gap-1">
                {isRiskBreached || isOpenTradesLimitReached ? (
                  <ShieldAlert className="w-3.5 h-3.5" />
                ) : (
                  <ShieldCheck className="w-3.5 h-3.5" />
                )}
                RISK GATE PREVIEW
              </span>
              <span>
                ${dollarRisk.toFixed(2)} ({riskPct.toFixed(2)}%)
              </span>
            </div>

            <div className="text-[10px] mt-1 text-slate-300">
              {isRiskBreached ? (
                <span className="text-terminal-red font-semibold">
                  REJECTION WARNING: Risk exceeds 2% max threshold (${maxRiskDollar.toFixed(0)})!
                </span>
              ) : isOpenTradesLimitReached ? (
                <span className="text-terminal-red font-semibold">
                  REJECTION WARNING: Max open trades (3) limit reached!
                </span>
              ) : (
                <span>Trade risk conforms with institutional risk limits.</span>
              )}
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={submitting}
            className={`w-full py-2 rounded font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all shadow-md ${
              side === 'BUY'
                ? 'bg-terminal-green text-[#0B0E14] hover:bg-terminal-green/90'
                : 'bg-terminal-red text-white hover:bg-terminal-red/90'
            } disabled:opacity-50`}
          >
            <Play className="w-3.5 h-3.5" />
            {submitting ? 'VALIDATING RISK GATE...' : `ROUTE SIMULATED ${side} ORDER`}
          </button>
        </form>

        {/* Right: Active Open Positions Table (7 cols) */}
        <div className="lg:col-span-7 flex flex-col justify-between border-t lg:border-t-0 lg:border-l border-border pt-3 lg:pt-0 lg:pl-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-mono text-slate-400">
                ACTIVE POSITIONS ({positions.length}/3)
              </span>
              <span className="text-[9px] font-mono text-slate-500">REAL-TIME STATE</span>
            </div>

            {positions.length === 0 ? (
              <div className="bg-background/40 border border-dashed border-border rounded p-6 text-center font-mono text-xs text-slate-500">
                No active open paper trades.
              </div>
            ) : (
              <div className="overflow-x-auto max-h-[220px] overflow-y-auto">
                <table className="w-full text-left text-[11px] font-mono">
                  <thead className="bg-background text-slate-400 border-b border-border sticky top-0">
                    <tr>
                      <th className="py-1.5 px-2">ID</th>
                      <th className="py-1.5 px-2">SYMBOL</th>
                      <th className="py-1.5 px-2">SIDE</th>
                      <th className="py-1.5 px-2">ENTRY</th>
                      <th className="py-1.5 px-2">SL</th>
                      <th className="py-1.5 px-2">TP</th>
                      <th className="py-1.5 px-2">STATUS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {positions.map((pos) => {
                      const isLong = pos.side === 'BUY';
                      return (
                        <tr key={pos.id} className="hover:bg-background-hover transition-colors">
                          <td className="py-1.5 px-2 text-slate-400">#{pos.id}</td>
                          <td className="py-1.5 px-2 font-bold text-white">{pos.symbol}</td>
                          <td className="py-1.5 px-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                isLong
                                  ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/30'
                                  : 'bg-terminal-red/10 text-terminal-red border border-terminal-red/30'
                              }`}
                            >
                              {pos.side}
                            </span>
                          </td>
                          <td className="py-1.5 px-2 text-slate-200">${pos.entryPrice.toFixed(2)}</td>
                          <td className="py-1.5 px-2 text-terminal-red">${pos.sl.toFixed(2)}</td>
                          <td className="py-1.5 px-2 text-terminal-green">${pos.tp.toFixed(2)}</td>
                          <td className="py-1.5 px-2">
                            <span className="text-[9px] px-1 py-0.5 rounded bg-slate-800 text-slate-300">
                              {pos.status}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="text-[10px] font-mono text-slate-500 mt-2 flex items-center justify-between">
            <span>Risk Rules: Max 3 Open Orders | 2% Loss Gate</span>
            <span className="text-terminal-cyan">Prisma SQLite State</span>
          </div>
        </div>
      </div>
    </div>
  );
};
