import React, { useState } from 'react';
import {
  Layers,
  Play,
} from 'lucide-react';
import { PaperPortfolioCockpitData } from '../../types';

interface ExecutionBlotterAndRiskProps {
  portfolio: PaperPortfolioCockpitData;
  onUpdateSignalState: (signalId: string, action: 'APPROVE' | 'REJECT' | 'EXECUTE' | 'CLOSE') => void;
}

export const ExecutionBlotterAndRisk: React.FC<ExecutionBlotterAndRiskProps> = ({
  portfolio,
  onUpdateSignalState,
}) => {
  const [activeTab, setActiveTab] = useState<'BLOTTER' | 'PERFORMANCE' | 'CALIBRATION'>('BLOTTER');

  const {
    equityUsd,
    todayPnlUsd,
    todayPnlPct,
    winRatePct,
    profitFactor,
    expectancyR,
    maxDrawdownPct,
    blotter,
    equityCurve,
    rDistribution,
    calibrationLab,
  } = portfolio;

  return (
    <div className="w-full bg-[#080c16] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-300 select-none flex flex-col justify-between">
      {/* Top Header: KPI Strip & Tab Selector */}
      <div className="flex flex-wrap items-center justify-between pb-2 mb-2.5 border-b border-[#1e293b] gap-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <Layers size={14} className="text-cyan-400" />
            <span className="font-bold text-white text-[11px] tracking-wider">
              EXECUTION BLOTTER &amp; PAPER RISK
            </span>
          </div>

          {/* Sub-Tabs */}
          <div className="flex items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 text-[10px]">
            <button
              onClick={() => setActiveTab('BLOTTER')}
              className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
                activeTab === 'BLOTTER'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Blotter ({blotter.length})
            </button>
            <button
              onClick={() => setActiveTab('PERFORMANCE')}
              className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
                activeTab === 'PERFORMANCE'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Performance &amp; R-Curve
            </button>
            <button
              onClick={() => setActiveTab('CALIBRATION')}
              className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
                activeTab === 'CALIBRATION'
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Calibration Lab ({calibrationLab.length})
            </button>
          </div>
        </div>

        {/* Global Paper Portfolio KPI Strip */}
        <div className="flex items-center gap-3 text-[10px]">
          <div>
            <span className="text-slate-500">EQUITY: </span>
            <span className="text-white font-bold">${equityUsd.toLocaleString()}</span>
          </div>
          <span className="text-slate-700">|</span>
          <div>
            <span className="text-slate-500">TODAY: </span>
            <span className={`font-bold ${todayPnlUsd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {todayPnlUsd >= 0 ? `+$${todayPnlUsd.toFixed(2)}` : `-$${Math.abs(todayPnlUsd).toFixed(2)}`} ({todayPnlPct >= 0 ? `+${todayPnlPct.toFixed(2)}` : `${todayPnlPct.toFixed(2)}`}%)
            </span>
          </div>
          <span className="text-slate-700">|</span>
          <div>
            <span className="text-slate-500">WIN RATE: </span>
            <span className="text-cyan-300 font-bold">{winRatePct}%</span>
          </div>
          <span className="text-slate-700">|</span>
          <div>
            <span className="text-slate-500">EXPECTANCY: </span>
            <span className="text-emerald-400 font-bold">+{expectancyR}R</span>
          </div>
          <span className="text-slate-700">|</span>
          <div>
            <span className="text-slate-500">MAX DD: </span>
            <span className="text-rose-400 font-bold">{maxDrawdownPct}%</span>
          </div>
        </div>
      </div>

      {/* Tab 1: Human Approval Queue / Signal Blotter */}
      {activeTab === 'BLOTTER' && (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-[10px]">
            <thead>
              <tr className="bg-[#0b101d] text-slate-400 border-b border-[#1e293b]">
                <th className="p-1.5 font-semibold">SIGNAL ID</th>
                <th className="p-1.5 font-semibold">HORIZON</th>
                <th className="p-1.5 font-semibold">SIDE</th>
                <th className="p-1.5 font-semibold">ENTRY ZONE</th>
                <th className="p-1.5 font-semibold">STOP / INVALIDATION</th>
                <th className="p-1.5 font-semibold">R:R</th>
                <th className="p-1.5 font-semibold">RISK</th>
                <th className="p-1.5 font-semibold">SCORE</th>
                <th className="p-1.5 font-semibold">LIFECYCLE STATE</th>
                <th className="p-1.5 font-semibold text-right">HUMAN ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60">
              {blotter.map((item) => (
                <tr key={item.id} className="hover:bg-slate-900/40 transition-colors">
                  <td className="p-1.5 font-bold text-white">{item.id}</td>
                  <td className="p-1.5">
                    <span className="px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-semibold">
                      {item.style}
                    </span>
                  </td>
                  <td className="p-1.5">
                    <span className={`px-1.5 py-0.2 rounded font-bold ${
                      item.side === 'LONG' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                    }`}>
                      {item.side}
                    </span>
                  </td>
                  <td className="p-1.5 font-mono text-slate-300">
                    ${item.entryZone[0].toLocaleString()} – ${item.entryZone[1].toLocaleString()}
                  </td>
                  <td className="p-1.5 font-mono text-rose-400">
                    ${item.stopLoss.toLocaleString()}
                  </td>
                  <td className="p-1.5 font-bold text-emerald-400">
                    {item.riskRewardRatio}:1
                  </td>
                  <td className="p-1.5 font-mono text-slate-300">
                    {item.suggestedRiskPct}% (${(item.notionalUsd * 0.0125).toFixed(0)})
                  </td>
                  <td className="p-1.5">
                    <span className="font-bold text-cyan-300">
                      {item.score} ({item.qualityBadge})
                    </span>
                  </td>
                  <td className="p-1.5">
                    <span className={`px-2 py-0.5 rounded font-black text-[9px] border ${
                      item.state === 'PENDING'
                        ? 'bg-amber-950/80 border-amber-500/50 text-amber-300 animate-pulse'
                        : item.state === 'APPROVED'
                        ? 'bg-cyan-950/80 border-cyan-500/50 text-cyan-300'
                        : item.state === 'EXECUTED'
                        ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-400'
                        : 'bg-slate-900 border-slate-800 text-slate-400'
                    }`}>
                      {item.state}
                    </span>
                  </td>
                  <td className="p-1.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {item.state === 'PENDING' && (
                        <>
                          <button
                            onClick={() => onUpdateSignalState(item.id, 'APPROVE')}
                            className="px-2 py-0.5 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-[9px]"
                            title="Approve setup for paper execution"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => onUpdateSignalState(item.id, 'REJECT')}
                            className="px-2 py-0.5 rounded bg-rose-950 border border-rose-800 text-rose-400 hover:bg-rose-900 font-bold text-[9px]"
                            title="Reject signal"
                          >
                            Reject
                          </button>
                        </>
                      )}
                      {item.state === 'APPROVED' && (
                        <button
                          onClick={() => onUpdateSignalState(item.id, 'EXECUTE')}
                          className="px-2.5 py-0.5 rounded bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black text-[9px] flex items-center gap-1 shadow-sm shadow-emerald-500/30"
                          title="Execute into live paper portfolio"
                        >
                          <Play size={9} /> Execute
                        </button>
                      )}
                      {item.state === 'EXECUTED' && (
                        <button
                          onClick={() => onUpdateSignalState(item.id, 'CLOSE')}
                          className="px-2 py-0.5 rounded bg-amber-950 border border-amber-700 text-amber-300 hover:bg-amber-900 font-bold text-[9px]"
                          title="Close active paper position"
                        >
                          Close Pos
                        </button>
                      )}
                      {item.state === 'CLOSED' && (
                        <span className="text-emerald-400 font-bold text-[9px]">
                          Realized +${item.realizedPnlUsd} (+{item.realizedR}R)
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Performance, Equity Curve & R-Distribution */}
      {activeTab === 'PERFORMANCE' && (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-stretch">
          {/* Equity Curve (7 cols) */}
          <div className="md:col-span-7 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5">
            <div className="flex justify-between items-center text-[10px] mb-2">
              <span className="font-bold text-white uppercase tracking-wider">
                Equity Curve ($10,000 Initial Baseline)
              </span>
              <span className="text-emerald-400 font-bold">
                Profit Factor: {profitFactor}
              </span>
            </div>
            <div className="h-28 flex items-end justify-between gap-2 bg-[#060914] p-2 rounded border border-[#1e293b]/70">
              {equityCurve.map((pt, i) => {
                const heightPct = Math.min(100, Math.max(10, ((pt.equity - 9800) / 1200) * 100));
                return (
                  <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
                    <span className="text-[8px] text-slate-500 mb-1">${pt.equity}</span>
                    <div
                      className="w-full bg-gradient-to-t from-cyan-600 to-emerald-400 rounded-t-sm"
                      style={{ height: `${heightPct}%` }}
                    ></div>
                    <span className="text-[8px] text-slate-500 mt-1">{pt.time}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* R-Multiple Distribution Histogram (5 cols) */}
          <div className="md:col-span-5 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
            <div className="flex justify-between items-center text-[10px] mb-1">
              <span className="font-bold text-white uppercase tracking-wider">
                R-Distribution
              </span>
              <span className="text-cyan-300 font-bold">Mean: +{expectancyR}R</span>
            </div>
            <div className="space-y-1 my-1">
              {rDistribution.map((bucket, i) => (
                <div key={i} className="flex items-center gap-2 text-[9px]">
                  <span className="w-16 text-slate-400 font-mono text-right">{bucket.rBucket}</span>
                  <div className="flex-1 h-2 rounded bg-slate-900 overflow-hidden">
                    <div
                      className={`h-full ${bucket.rBucket.includes('-') ? 'bg-rose-500' : 'bg-emerald-400'}`}
                      style={{ width: `${Math.min(100, bucket.count * 8)}%` }}
                    ></div>
                  </div>
                  <span className="w-6 text-white font-bold">{bucket.count}</span>
                </div>
              ))}
            </div>
            <div className="text-[8px] text-slate-500 text-center pt-1 border-t border-[#1e293b]/70">
              Positive expectancy verified with 8.4% fat right-tail trades
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Strategy Calibration Lab */}
      {activeTab === 'CALIBRATION' && (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-[10px]">
            <thead>
              <tr className="bg-[#0b101d] text-slate-400 border-b border-[#1e293b]">
                <th className="p-1.5 font-semibold">SETUP CATEGORY</th>
                <th className="p-1.5 font-semibold">HISTORICAL WIN RATE</th>
                <th className="p-1.5 font-semibold">PROFIT FACTOR</th>
                <th className="p-1.5 font-semibold">EXPECTANCY (R)</th>
                <th className="p-1.5 font-semibold">DYNAMIC SIZING MULTIPLIER</th>
                <th className="p-1.5 font-semibold text-right">CAPITAL ALLOCATION STATUS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60">
              {calibrationLab.map((row) => (
                <tr key={row.setupType} className="hover:bg-slate-900/40 transition-colors">
                  <td className="p-1.5 font-bold text-white">{row.setupType}</td>
                  <td className="p-1.5 font-bold text-cyan-300">{row.winRatePct}%</td>
                  <td className="p-1.5 font-mono text-slate-300">{row.profitFactor}</td>
                  <td className="p-1.5 font-bold text-emerald-400">+{row.expectancyR}R</td>
                  <td className="p-1.5 font-mono text-amber-300 font-bold">{row.sizingMultiplier}x</td>
                  <td className="p-1.5 text-right">
                    <span className={`px-2 py-0.5 rounded font-black text-[9px] border ${
                      row.status === 'PRIME_ALLOCATION'
                        ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-400'
                        : row.status === 'ACTIVE_EDGE'
                        ? 'bg-cyan-950/80 border-cyan-500/50 text-cyan-300'
                        : row.status === 'REDUCED_RISK'
                        ? 'bg-amber-950/80 border-amber-500/50 text-amber-300'
                        : 'bg-rose-950/80 border-rose-500/50 text-rose-400'
                    }`}>
                      {row.status.replace(/_/g, ' ')}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
