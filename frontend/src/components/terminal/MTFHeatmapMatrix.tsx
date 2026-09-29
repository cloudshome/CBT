import React from 'react';
import {
  TrendingUp,
  TrendingDown,
  Compass,
  Layers,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
} from 'lucide-react';
import { MTFHeatmapRow, MarketRegimeData, MarketDecisionData } from '../../types';

interface MTFHeatmapMatrixProps {
  matrix: MTFHeatmapRow[];
  regime: MarketRegimeData;
  marketDecision: MarketDecisionData;
  selectedTimeframe: string;
  onSelectTimeframe: (tf: string) => void;
}

export const MTFHeatmapMatrix: React.FC<MTFHeatmapMatrixProps> = ({
  matrix,
  regime,
  marketDecision,
  selectedTimeframe,
  onSelectTimeframe,
}) => {
  const htfRows = matrix.filter((m) => m.isHTF);
  const ltfRows = matrix.filter((m) => !m.isHTF);

  const htfAvgScore = Math.round(
    htfRows.reduce((s, r) => s + r.score, 0) / (htfRows.length || 1)
  );
  const ltfAvgScore = Math.round(
    ltfRows.reduce((s, r) => s + r.score, 0) / (ltfRows.length || 1)
  );

  const bullishCount = matrix.filter((m) => m.score > 20).length;
  const bearishCount = matrix.filter((m) => m.score < -20).length;
  const alignedCount = matrix.filter((m) => (m.score > 0 && htfAvgScore > 0) || (m.score < 0 && htfAvgScore < 0)).length;
  const conflictCount = matrix.length - alignedCount;

  // Alignment Score percentage mapped for visual slider (-100..+100 -> 0..100%)
  const alignmentNormalizedPct = Math.min(100, Math.max(0, ((marketDecision.alignmentScore + 100) / 200) * 100));

  return (
    <div className="w-full bg-[#080c16] border-b border-[#1e293b] p-3 text-xs font-mono text-slate-300">
      {/* Top Row: MTF Heatmap Table & Market Regime Banner */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
        {/* Heatmap Matrix Table (9 cols on xl) */}
        <div className="xl:col-span-8 flex flex-col justify-between bg-[#0b101d] border border-[#1e293b] rounded-lg p-2.5">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]/70">
            <div className="flex items-center gap-2">
              <Layers size={13} className="text-cyan-400" />
              <span className="font-bold text-white text-[11px] tracking-wider">
                9-TIMEFRAME MATRIX HEATMAP
              </span>
              <span className="text-[10px] text-slate-500">
                (Monthly down to 1M)
              </span>
            </div>
            <div className="flex items-center gap-3 text-[10px]">
              <span className="text-emerald-400 font-semibold">
                ● {bullishCount}/9 Bullish
              </span>
              <span className="text-rose-400 font-semibold">
                ● {bearishCount}/9 Bearish
              </span>
              <span className="text-amber-400 font-semibold">
                ⚠ {conflictCount} Conflicts
              </span>
            </div>
          </div>

          {/* Matrix Grid Row */}
          <div className="grid grid-cols-9 gap-1.5 overflow-x-auto select-none">
            {matrix.map((row) => {
              const isSelected = selectedTimeframe.toLowerCase() === row.timeframe.toLowerCase();
              const isBull = row.score > 0;
              return (
                <div
                  key={row.timeframe}
                  onClick={() => onSelectTimeframe(row.timeframe)}
                  className={`flex flex-col p-1.5 rounded border transition-all cursor-pointer text-center ${
                    isSelected
                      ? 'border-cyan-400 bg-cyan-950/40 shadow-sm shadow-cyan-500/20'
                      : row.score > 50
                      ? 'border-emerald-500/30 bg-emerald-950/15 hover:border-emerald-500/60'
                      : row.score > 0
                      ? 'border-cyan-500/20 bg-cyan-950/10 hover:border-cyan-500/50'
                      : row.score > -30
                      ? 'border-amber-500/20 bg-amber-950/10 hover:border-amber-500/50'
                      : 'border-rose-500/30 bg-rose-950/15 hover:border-rose-500/60'
                  }`}
                >
                  {/* Timeframe & HTF/LTF Pill */}
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="font-bold text-white text-[11px]">{row.timeframe}</span>
                    <span className={`text-[8px] px-1 py-0.2 rounded font-bold ${row.isHTF ? 'bg-indigo-900/60 text-indigo-300' : 'bg-slate-800 text-slate-400'}`}>
                      {row.isHTF ? 'HTF' : 'LTF'}
                    </span>
                  </div>

                  {/* Trend & Bias */}
                  <div className="flex items-center justify-center gap-1 my-0.5">
                    {isBull ? (
                      <TrendingUp size={11} className="text-emerald-400" />
                    ) : (
                      <TrendingDown size={11} className="text-rose-400" />
                    )}
                    <span className={`text-[10px] font-bold ${isBull ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {row.structure}
                    </span>
                  </div>

                  {/* Indicator Metrics */}
                  <div className="text-[9px] text-slate-400 space-y-0.5 my-0.5">
                    <div className="flex justify-between">
                      <span>RSI:</span>
                      <span className={`font-semibold ${row.rsi > 70 ? 'text-amber-400' : row.rsi < 30 ? 'text-cyan-400' : 'text-slate-300'}`}>
                        {row.rsi}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>VWAP:</span>
                      <span className="font-semibold text-slate-300">{row.vwapSigma > 0 ? `+${row.vwapSigma}σ` : `${row.vwapSigma}σ`}</span>
                    </div>
                  </div>

                  {/* SMC Tag */}
                  <div className="mt-1 py-0.5 bg-slate-900/80 rounded border border-slate-800 text-[8px] text-cyan-300 truncate px-1">
                    {row.smcPattern}
                  </div>

                  {/* Score Pill */}
                  <div className={`mt-1 text-[10px] font-bold ${isBull ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {row.score > 0 ? `+${row.score}` : row.score}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Lower Alignment Bar & Dual Bias Indicator */}
          <div className="mt-2.5 pt-2 border-t border-[#1e293b]/70 flex flex-wrap items-center justify-between gap-3 text-[11px]">
            {/* HTF vs LTF Bias comparison */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500 font-semibold">HTF BIAS:</span>
                <span className="px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-500/40 text-emerald-400 font-bold">
                  EXPANSION ({htfAvgScore > 0 ? `+${htfAvgScore}` : htfAvgScore})
                </span>
              </div>
              <span className="text-slate-700">➔</span>
              <div className="flex items-center gap-1.5">
                <span className="text-slate-500 font-semibold">LTF EXECUTION:</span>
                <span className={`px-1.5 py-0.5 rounded border font-bold ${
                  ltfAvgScore > 0
                    ? 'bg-emerald-950/80 border-emerald-500/40 text-emerald-400'
                    : 'bg-amber-950/80 border-amber-500/40 text-amber-400'
                }`}>
                  {ltfAvgScore > 0 ? `ALIGNED (+${ltfAvgScore})` : `PULLBACK (${ltfAvgScore})`}
                </span>
              </div>
            </div>

            {/* Alignment Score Slider Bar */}
            <div className="flex-1 max-w-[340px] flex flex-col gap-0.5">
              <div className="flex justify-between text-[10px]">
                <span className="text-slate-500">ALIGNMENT SCORE</span>
                <span className={`font-bold ${marketDecision.alignmentScore > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {marketDecision.alignmentScore > 0 ? `+${marketDecision.alignmentScore}` : marketDecision.alignmentScore} / 100
                </span>
              </div>
              <div className="relative w-full h-2 rounded-full bg-slate-900 border border-slate-800 overflow-hidden">
                <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-slate-700 z-10"></div>
                <div
                  className={`h-full transition-all duration-500 ${
                    marketDecision.alignmentScore > 0
                      ? 'bg-gradient-to-r from-emerald-600 to-cyan-400'
                      : 'bg-gradient-to-r from-rose-600 to-amber-500'
                  }`}
                  style={{ width: `${alignmentNormalizedPct}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>

        {/* Market Regime & Decision Card (4 cols on xl) */}
        <div className="xl:col-span-4 bg-[#0b101d] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between pb-1.5 border-b border-[#1e293b]/70">
            <div className="flex items-center gap-1.5">
              <Compass size={13} className="text-amber-400" />
              <span className="font-bold text-white text-[11px] tracking-wider">
                MARKET REGIME
              </span>
            </div>
            <span className="px-1.5 py-0.5 rounded bg-amber-950/60 border border-amber-500/40 text-amber-300 font-bold text-[10px]">
              {regime.classification.replace(/_/g, ' ')}
            </span>
          </div>

          {/* Regime Radar Metrics */}
          <div className="grid grid-cols-4 gap-1.5 text-center my-2">
            <div className="bg-[#0e1526] p-1 rounded border border-[#1e293b]">
              <span className="text-[9px] text-slate-500 block">TREND</span>
              <span className="font-bold text-emerald-400 text-[10px]">{regime.trendScore}%</span>
            </div>
            <div className="bg-[#0e1526] p-1 rounded border border-[#1e293b]">
              <span className="text-[9px] text-slate-500 block">VOLATILITY</span>
              <span className="font-bold text-cyan-400 text-[10px]">{regime.volatilityScore}%</span>
            </div>
            <div className="bg-[#0e1526] p-1 rounded border border-[#1e293b]">
              <span className="text-[9px] text-slate-500 block">LIQUIDITY</span>
              <span className="font-bold text-indigo-400 text-[10px]">{regime.liquidityScore}%</span>
            </div>
            <div className="bg-[#0e1526] p-1 rounded border border-[#1e293b]">
              <span className="text-[9px] text-slate-500 block">MOMENTUM</span>
              <span className="font-bold text-emerald-400 text-[10px]">{regime.momentumScore}%</span>
            </div>
          </div>

          {/* Market Decision Banner */}
          <div className={`p-2 rounded border flex items-center justify-between gap-2 ${
            marketDecision.primaryAction === 'LONG'
              ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
              : marketDecision.primaryAction === 'SHORT'
              ? 'bg-rose-950/40 border-rose-500/40 text-rose-300'
              : 'bg-amber-950/40 border-amber-500/40 text-amber-300'
          }`}>
            <div className="flex items-center gap-2">
              {marketDecision.primaryAction === 'LONG' ? (
                <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
              ) : marketDecision.primaryAction === 'SHORT' ? (
                <AlertCircle size={16} className="text-rose-400 shrink-0" />
              ) : (
                <ShieldCheck size={16} className="text-amber-400 shrink-0" />
              )}
              <div>
                <span className="font-bold text-white text-[11px] block leading-tight">
                  {marketDecision.stateLabel}
                </span>
                <span className="text-[9px] text-slate-400 leading-tight">
                  {marketDecision.narrative}
                </span>
              </div>
            </div>
            <div className="text-right shrink-0">
              <span className="text-[8px] text-slate-500 block">ACTION</span>
              <span className={`text-[12px] font-black px-2 py-0.5 rounded ${
                marketDecision.primaryAction === 'LONG'
                  ? 'bg-emerald-500 text-slate-950 font-black'
                  : marketDecision.primaryAction === 'SHORT'
                  ? 'bg-rose-500 text-white font-black'
                  : 'bg-amber-500 text-slate-950 font-black'
              }`}>
                {marketDecision.primaryAction}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
