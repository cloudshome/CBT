import React from 'react';
import { Target, Zap, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { FVGItem, OrderBlockItem, SetupSuggestion } from '../types';
import { LoadingSkeleton } from './LoadingSkeleton';
import { PairVenueLinks } from './PairVenueLinks';

interface SMCScanPanelProps {
  symbol?: string;
  fvgs?: FVGItem[];
  orderBlocks?: OrderBlockItem[];
  setups?: SetupSuggestion[];
  onSelectSetup: (setup: SetupSuggestion) => void;
  loading?: boolean;
}

export const SMCScanPanel: React.FC<SMCScanPanelProps> = ({
  symbol,
  fvgs = [],
  orderBlocks = [],
  setups = [],
  onSelectSetup,
  loading = false,
}) => {
  const bullishFVGCount = fvgs.filter((f) => f.type === 'bullish').length;
  const bearishFVGCount = fvgs.filter((f) => f.type === 'bearish').length;
  const activeFVGCount = fvgs.filter((f) => !f.mitigated).length;

  const bullishOBCount = orderBlocks.filter((o) => o.type === 'bullish').length;
  const bearishOBCount = orderBlocks.filter((o) => o.type === 'bearish').length;

  return (
    <div className="bg-background-card border border-border rounded-lg p-4 shadow-lg flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-terminal-cyan" />
          <h3 className="text-xs font-mono font-bold text-slate-200 uppercase">
            MARKET STRUCTURE &amp; TRADE SETUPS
          </h3>
          {symbol && <PairVenueLinks symbol={symbol} size="xs" isFutures={true} />}
        </div>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/30">
          AUTO-SCANNER
        </span>
      </div>

      {loading ? (
        <div className="space-y-3">
          <LoadingSkeleton className="h-10 w-full" />
          <LoadingSkeleton className="h-16 w-full" />
        </div>
      ) : (
        <div className="flex flex-col gap-3 flex-1">
          {/* Structure Metrics Ticker */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-background p-2.5 rounded border border-border">
              <div className="text-[10px] font-mono text-slate-400">FAIR VALUE GAPS</div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-sm font-mono font-bold text-terminal-green">+{bullishFVGCount} Bull</span>
                <span className="text-sm font-mono font-bold text-terminal-red">-{bearishFVGCount} Bear</span>
              </div>
              <div className="text-[9px] font-mono text-slate-500 mt-0.5">
                {activeFVGCount} Unmitigated Active
              </div>
            </div>

            <div className="bg-background p-2.5 rounded border border-border">
              <div className="text-[10px] font-mono text-slate-400">ORDER BLOCKS</div>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-sm font-mono font-bold text-terminal-cyan">+{bullishOBCount} Bull</span>
                <span className="text-sm font-mono font-bold text-terminal-purple">-{bearishOBCount} Bear</span>
              </div>
              <div className="text-[9px] font-mono text-slate-500 mt-0.5">Institutional Zones</div>
            </div>
          </div>

          {/* Setup Suggestions Cards */}
          <div className="flex-1 flex flex-col">
            <div className="text-[11px] font-mono text-slate-400 mb-1.5 flex items-center justify-between">
              <span>ALGORITHMIC SETUPS ({setups.length})</span>
              <span className="text-[9px] text-slate-500">1-CLICK EXECUTE</span>
            </div>

            {setups.length === 0 ? (
              <div className="bg-background/50 border border-dashed border-border rounded p-4 text-center font-mono text-xs text-slate-500 flex-1 flex items-center justify-center">
                Scanning for high-probability setups...
              </div>
            ) : (
              <div className="space-y-2 overflow-y-auto max-h-[160px] pr-1">
                {setups.map((setup, idx) => {
                  const isLong = setup.type === 'LONG';

                  return (
                    <div
                      key={idx}
                      className={`p-2.5 rounded border transition-all hover:border-slate-500 cursor-pointer ${
                        isLong
                          ? 'bg-[#0A1612] border-terminal-green/30'
                          : 'bg-[#180F13] border-terminal-red/30'
                      }`}
                      onClick={() => onSelectSetup(setup)}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 font-mono text-xs font-bold">
                          {isLong ? (
                            <span className="flex items-center gap-1 text-terminal-green">
                              <ArrowUpRight className="w-3.5 h-3.5" /> BUY / LONG
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-terminal-red">
                              <ArrowDownRight className="w-3.5 h-3.5" /> SELL / SHORT
                            </span>
                          )}
                          <span className="text-[10px] font-normal text-slate-400">
                            R:R {Number(setup.riskRewardRatio || 0).toFixed(2)}
                          </span>
                        </div>

                        <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                          {symbol && <PairVenueLinks symbol={symbol} size="xs" isFutures={true} />}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectSetup(setup);
                            }}
                            className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600 flex items-center gap-1"
                          >
                            <Zap className="w-2.5 h-2.5 text-terminal-amber" /> Use Setup
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-1 mt-2 text-[11px] font-mono">
                        <div>
                          <span className="text-slate-500 text-[9px] block">ENTRY</span>
                          <span className="text-white font-semibold">${Number(setup.entry || 0).toFixed(2)}</span>
                        </div>
                        <div>
                          <span className="text-slate-500 text-[9px] block">STOP LOSS</span>
                          <span className="text-terminal-red font-semibold">${Number(setup.stopLoss || 0).toFixed(2)}</span>
                        </div>
                        <div>
                          <span className="text-slate-500 text-[9px] block">TARGET (TP)</span>
                          <span className="text-terminal-green font-semibold">${Number(setup.takeProfit || 0).toFixed(2)}</span>
                        </div>
                      </div>

                      <div className="text-[9px] font-mono text-slate-400 mt-1.5 truncate">
                        {setup.trigger}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
