import React from 'react';
import {
  Globe,
  Grid,
  Calendar,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
} from 'lucide-react';
import { MacroCockpitRadarData } from '../../types';

interface MacroRadarStripProps {
  macro: MacroCockpitRadarData;
}

export const MacroRadarStrip: React.FC<MacroRadarStripProps> = ({ macro }) => {
  const {
    fearAndGreed,
    marketDominance,
    crossAssetCorrelation,
    polymarketIntelligence,
    macroCalendar,
    onChainVitals,
  } = macro;

  return (
    <div className="w-full bg-[#080c16] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-300 select-none">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <Globe size={14} className="text-cyan-400" />
          <span className="font-bold text-white text-[11px] tracking-wider">
            MACRO CONTEXT, ON-CHAIN &amp; PREDICTION MARKETS
          </span>
        </div>
        <span className="text-[10px] text-slate-500">
          Cross-Asset Liquidity Beta &amp; Event Horizon
        </span>
      </div>

      {/* 4-Column Grid: Sentiment & Dominance | Cross-Asset Correlation | Polymarket | Macro Calendar & On-Chain */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-12 gap-3 items-stretch">
        {/* Col 1: Fear & Greed + Dominance (3 cols) */}
        <div className="xl:col-span-3 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider">FEAR &amp; GREED</span>
              <span className="text-emerald-400 font-bold">{fearAndGreed.classification}</span>
            </div>

            <div className="flex items-center gap-3 p-2 bg-[#070b16] rounded border border-[#1e293b]/70 mb-2">
              <div className="w-12 h-12 rounded-full bg-emerald-950/70 border border-emerald-500/50 flex flex-col items-center justify-center text-emerald-400 font-black text-base shadow-sm shadow-emerald-500/20">
                {fearAndGreed.score}
              </div>
              <div className="text-[10px] space-y-0.5">
                <div className="text-slate-400">Previous Close: <span className="text-white font-semibold">{fearAndGreed.previousClose}</span></div>
                <div className="text-slate-400">7D Moving Avg: <span className="text-white font-semibold">{fearAndGreed.historicalAvg7d}</span></div>
              </div>
            </div>

            {/* Dominance Bars */}
            <div className="space-y-1 text-[9px]">
              <div className="flex justify-between text-slate-400">
                <span>BTC Dominance:</span>
                <span className="text-amber-400 font-bold">{marketDominance.btcD}%</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden">
                <div className="h-full bg-amber-400" style={{ width: `${marketDominance.btcD}%` }}></div>
              </div>

              <div className="flex justify-between text-slate-400 mt-1">
                <span>ETH Dominance:</span>
                <span className="text-cyan-400 font-bold">{marketDominance.ethD}%</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden">
                <div className="h-full bg-cyan-400" style={{ width: `${marketDominance.ethD * 2.5}%` }}></div>
              </div>

              <div className="flex justify-between text-slate-400 mt-1">
                <span>USDT Dry Powder:</span>
                <span className="text-emerald-400 font-bold">{marketDominance.usdtD}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Col 2: Cross-Asset Correlation Matrix (3 cols) */}
        <div className="xl:col-span-3 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider flex items-center gap-1">
                <Grid size={11} className="text-indigo-400" /> CORRELATION MATRIX
              </span>
              <span className="text-slate-500">30D ROLLING</span>
            </div>

            <div className="overflow-x-auto my-1">
              <table className="w-full text-center text-[9px]">
                <thead>
                  <tr className="text-slate-500 border-b border-[#1e293b]/70">
                    <th className="p-0.5"></th>
                    {crossAssetCorrelation.assets.map((a) => (
                      <th key={a} className="p-0.5 font-bold text-slate-300">{a}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {crossAssetCorrelation.matrix.map((row, i) => (
                    <tr key={i} className="border-b border-[#1e293b]/30">
                      <td className="p-0.5 font-bold text-slate-400 text-left">
                        {crossAssetCorrelation.assets[i]}
                      </td>
                      {row.map((val, j) => {
                        const isPos = val > 0;
                        const opacity = Math.min(1, Math.abs(val) * 0.8 + 0.2);
                        return (
                          <td
                            key={j}
                            className={`p-0.5 font-mono ${
                              i === j
                                ? 'text-slate-500'
                                : isPos
                                ? 'text-cyan-300 font-semibold'
                                : 'text-rose-300 font-semibold'
                            }`}
                            style={{
                              backgroundColor: i !== j ? (isPos ? `rgba(6,182,212,${opacity * 0.15})` : `rgba(244,63,94,${opacity * 0.15})`) : undefined,
                            }}
                          >
                            {val.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="text-[8px] text-slate-500 text-center pt-1 border-t border-[#1e293b]/70">
            DXY Inverse Correlation (-0.41) confirms structural tailwind
          </div>
        </div>

        {/* Col 3: Polymarket Prediction Shifts (3 cols) */}
        <div className="xl:col-span-3 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider flex items-center gap-1">
                <Zap size={11} className="text-amber-400" /> POLYMARKET SHIFTS
              </span>
              <span className="text-slate-500">PREDICTION INTEL</span>
            </div>

            <div className="space-y-1.5 my-1">
              {polymarketIntelligence.map((item, i) => (
                <div key={i} className="p-1.5 rounded bg-[#070b16] border border-[#1e293b]/70 text-[9px] space-y-0.5">
                  <div className="text-white font-semibold truncate leading-tight">
                    {item.question}
                  </div>
                  <div className="flex items-center justify-between text-slate-400">
                    <span>Previous: {item.previousProbPct}%</span>
                    <div className="flex items-center gap-1 font-bold">
                      <span className="text-cyan-300">Now: {item.currentProbPct}%</span>
                      <span className={`flex items-center ${item.deltaPct > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {item.deltaPct > 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                        {item.deltaPct > 0 ? `+${item.deltaPct}%` : `${item.deltaPct}%`}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="text-[8px] text-slate-500 text-center pt-1 border-t border-[#1e293b]/70">
            Prediction data serves as evidence, not trade authorization
          </div>
        </div>

        {/* Col 4: Macro Calendar & On-Chain Vitals (3 cols) */}
        <div className="xl:col-span-3 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5">
              <span className="font-bold text-white uppercase tracking-wider flex items-center gap-1">
                <Calendar size={11} className="text-rose-400" /> EVENT COUNTDOWN
              </span>
              <span className="text-rose-400 font-bold">VOLATILITY ALERTS</span>
            </div>

            {/* Calendar Events */}
            <div className="space-y-1.5 mb-2">
              {macroCalendar.map((ev, i) => (
                <div key={i} className="p-1.5 rounded bg-[#070b16] border border-[#1e293b]/70 text-[9px]">
                  <div className="flex items-center justify-between text-white font-bold">
                    <span className="truncate">{ev.event}</span>
                    <span className="text-amber-400 font-mono">{ev.countdown}</span>
                  </div>
                  <div className="text-rose-400 text-[8px] mt-0.5 truncate">
                    ⚠ {ev.policyWarning}
                  </div>
                </div>
              ))}
            </div>

            {/* On-Chain Vitals */}
            <div className="p-1.5 rounded bg-[#070b16] border border-[#1e293b]/70 text-[9px] space-y-0.5">
              <div className="flex justify-between">
                <span className="text-slate-400">Exchange Net Flow:</span>
                <span className="text-emerald-400 font-bold">-$182M (Outflow Drain)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Whale Moves (&gt;100 BTC):</span>
                <span className="text-white font-bold">{onChainVitals.whaleTransfers24hCount} transfers (14 to Cold Vaults)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Mempool Gas:</span>
                <span className="text-cyan-300 font-bold">{onChainVitals.medianGasSatVb} sat/vB ({onChainVitals.mempoolCongestionPct}% capacity)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
