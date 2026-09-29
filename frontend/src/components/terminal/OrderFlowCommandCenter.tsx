import React from 'react';
import {
  Activity,
  Zap,
  Layers,
  ArrowUpRight,
} from 'lucide-react';
import { MasterTerminalTelemetry } from '../../types';

interface OrderFlowCommandCenterProps {
  orderFlow: MasterTerminalTelemetry['orderFlow'];
  candles: any[];
}

export const OrderFlowCommandCenter: React.FC<OrderFlowCommandCenterProps> = ({
  orderFlow,
  candles,
}) => {
  const { currentCvd, cvdDeltaPct, divergenceAlert, derivativesVitals } = orderFlow;

  const isAbsorption = divergenceAlert.type === 'BULLISH_ABSORPTION';

  // Compute a normalized sparkline curve for the last 20 CVD delta points
  const recentCandles = candles.slice(-20);
  let runningCvd = 0;
  const cvdPoints = recentCandles.map((c) => {
    const isGreen = c[4] >= c[1];
    const body = Math.abs(c[4] - c[1]);
    const rng = Math.max(c[2] - c[3], 1e-4);
    runningCvd += c[5] * (isGreen ? body / rng : -(body / rng));
    return runningCvd;
  });

  const minCvd = Math.min(...cvdPoints, 0);
  const maxCvd = Math.max(...cvdPoints, 1);
  const rangeCvd = maxCvd - minCvd || 1;

  return (
    <div className="w-full bg-[#080c16] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-300 select-none">
      {/* Title & Section Header */}
      <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-cyan-400" />
          <span className="font-bold text-white text-[11px] tracking-wider">
            ORDER FLOW &amp; CUMULATIVE VOLUME DELTA (CVD)
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          <span className="text-slate-400">Net Delta:</span>
          <span className={`font-bold ${currentCvd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {currentCvd >= 0 ? `+${currentCvd.toLocaleString()}` : currentCvd.toLocaleString()} ({cvdDeltaPct > 0 ? `+${cvdDeltaPct}` : cvdDeltaPct}%)
          </span>
        </div>
      </div>

      {/* Main Grid: CVD Sparkline + Divergence Banner + Derivatives Vitals + Liquidity Walls */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
        {/* CVD Sub-Chart Sparkline & Divergence Alert (4 cols) */}
        <div className="xl:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-[10px] mb-1.5">
              <span className="text-slate-400 font-semibold">CVD TRAJECTORY (LAST 20 BARS)</span>
              <span className={currentCvd >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                {currentCvd >= 0 ? 'BUY DELTA EXPANSION' : 'SELL DELTA HEAVY'}
              </span>
            </div>

            {/* Sparkline Canvas / SVG */}
            <div className="h-16 w-full bg-[#060914] rounded p-1 border border-[#1e293b]/70 flex items-end justify-between gap-1">
              {cvdPoints.map((pt, i) => {
                const heightPct = Math.min(100, Math.max(8, ((pt - minCvd) / rangeCvd) * 100));
                return (
                  <div
                    key={i}
                    className="flex-1 flex flex-col justify-end items-center h-full"
                    title={`Bar ${i + 1}: ${Math.round(pt)} CVD`}
                  >
                    <div
                      className={`w-full rounded-t-sm transition-all ${
                        pt >= 0 ? 'bg-cyan-400' : 'bg-rose-500'
                      }`}
                      style={{ height: `${heightPct}%` }}
                    ></div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Divergence Alert Box */}
          <div className={`mt-2 p-2 rounded border flex items-start gap-2 ${
            isAbsorption
              ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
              : 'bg-amber-950/40 border-amber-500/40 text-amber-300'
          }`}>
            <Zap size={14} className={isAbsorption ? 'text-emerald-400 shrink-0 mt-0.5' : 'text-amber-400 shrink-0 mt-0.5'} />
            <div className="text-[10px] leading-tight">
              <span className="font-bold text-white block text-[11px]">{divergenceAlert.title}</span>
              <span className="text-slate-400">{divergenceAlert.description}</span>
              <div className="mt-1 flex items-center gap-2 text-[9px]">
                <span className="text-white font-semibold">Strength: {divergenceAlert.strengthScore}/100</span>
                <span>•</span>
                <span className="text-emerald-400 font-bold">Confidence: {divergenceAlert.confidence}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Derivatives Vitals & OI Triad (4 cols) */}
        <div className="xl:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between pb-1.5 border-b border-[#1e293b]/70">
            <span className="font-bold text-white text-[10px] uppercase tracking-wider">
              Derivatives Vitals &amp; OI Triad
            </span>
            <span className="px-1.5 py-0.2 rounded bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 text-[9px] font-bold">
              PERPETUALS
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 my-2 text-[10px]">
            {/* Open Interest */}
            <div className="p-1.5 rounded bg-[#090e1c] border border-[#1e293b]">
              <span className="text-slate-500 text-[9px] block">OPEN INTEREST</span>
              <span className="text-white font-bold text-[11px]">
                ${(derivativesVitals.openInterestUsd / 1e9).toFixed(2)}B
              </span>
              <div className="flex items-center gap-1 text-[9px] text-emerald-400 font-semibold mt-0.5">
                <ArrowUpRight size={10} /> +{derivativesVitals.oiDelta1hPct}% (1h)
              </div>
            </div>

            {/* Funding Rate */}
            <div className="p-1.5 rounded bg-[#090e1c] border border-[#1e293b]">
              <span className="text-slate-500 text-[9px] block">PREDICTED FUNDING</span>
              <span className="text-amber-300 font-bold text-[11px]">
                +{derivativesVitals.predictedFundingRate8hPct}%
              </span>
              <div className="text-[9px] text-slate-400 font-semibold mt-0.5">
                {derivativesVitals.fundingRateAnnualizedPct}% APR
              </div>
            </div>

            {/* Long / Short Ratio */}
            <div className="p-1.5 rounded bg-[#090e1c] border border-[#1e293b]">
              <span className="text-slate-500 text-[9px] block">LONG / SHORT RATIO</span>
              <span className="text-cyan-400 font-bold text-[11px]">
                {derivativesVitals.longShortRatioTopTraders}:1
              </span>
              <div className="text-[9px] text-slate-400 mt-0.5">
                Top Traders (Binance)
              </div>
            </div>

            {/* OI Triad Interpretation */}
            <div className="p-1.5 rounded bg-[#090e1c] border border-[#1e293b]">
              <span className="text-slate-500 text-[9px] block">TRIAD REGIME</span>
              <span className="text-emerald-400 font-bold text-[10px] block truncate">
                LONG ACCUMULATION
              </span>
              <div className="text-[9px] text-slate-400 mt-0.5">
                Price ↑ + OI ↑
              </div>
            </div>
          </div>

          {/* L2 Imbalance Meter */}
          <div className="p-1.5 rounded bg-[#080d1a] border border-[#1e293b]/70">
            <div className="flex justify-between text-[9px] mb-1">
              <span className="text-emerald-400 font-bold">BIDS: {derivativesVitals.bidsPercentage}%</span>
              <span className="text-cyan-300 font-bold">IMBALANCE: +{derivativesVitals.l2DepthImbalancePct}%</span>
              <span className="text-rose-400 font-bold">ASKS: {derivativesVitals.asksPercentage}%</span>
            </div>
            <div className="w-full h-2 rounded-full bg-rose-950/70 overflow-hidden flex">
              <div
                className="h-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${derivativesVitals.bidsPercentage}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* Resting Liquidity Walls & Depth Table (4 cols) */}
        <div className="xl:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between pb-1.5 border-b border-[#1e293b]/70 text-[10px]">
            <span className="font-bold text-white uppercase tracking-wider flex items-center gap-1">
              <Layers size={11} className="text-amber-400" /> RESTING LIQUIDITY WALLS
            </span>
            <span className="text-slate-500">TOP 20 LEVELS</span>
          </div>

          <div className="space-y-1 my-2">
            {derivativesVitals.liquidityWalls.map((wall, i) => (
              <div
                key={i}
                className={`p-1.5 rounded border text-[10px] flex items-center justify-between ${
                  wall.side === 'BID'
                    ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                    : 'bg-rose-950/20 border-rose-500/30 text-rose-300'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`px-1 rounded text-[8px] font-bold ${wall.side === 'BID' ? 'bg-emerald-500 text-slate-950' : 'bg-rose-500 text-white'}`}>
                    {wall.side}
                  </span>
                  <span className="font-bold text-white">${wall.price.toLocaleString()}</span>
                  <span className="text-slate-400 text-[9px] font-mono">
                    ({wall.distancePct > 0 ? `+${wall.distancePct}%` : `${wall.distancePct}%`})
                  </span>
                </div>
                <div className="text-right">
                  <span className="font-bold text-white">${(wall.volumeUsd / 1e6).toFixed(1)}M</span>
                </div>
              </div>
            ))}
          </div>

          <div className="text-[9px] text-slate-500 text-center pt-1 border-t border-[#1e293b]/70">
            Real-time passive limit order book defense
          </div>
        </div>
      </div>
    </div>
  );
};
