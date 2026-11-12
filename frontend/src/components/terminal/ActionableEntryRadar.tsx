import React, { useState } from 'react';
import { ActionableEntryItem } from '../../types';

interface ActionableEntryRadarProps {
  entries: ActionableEntryItem[];
  selectedSymbol: string;
  selectedStyle: string;
  directionFilter: 'AUTO' | 'LONG' | 'SHORT';
  onSelectEntry: (entry: ActionableEntryItem) => void;
  loading?: boolean;
}

export const ActionableEntryRadar: React.FC<ActionableEntryRadarProps> = ({
  entries,
  selectedSymbol,
  selectedStyle,
  directionFilter,
  onSelectEntry,
  loading = false,
}) => {
  const [filterGrade, setFilterGrade] = useState<'ALL' | 'A+' | 'A' | 'B'>('ALL');
  const [isCollapsed, setIsCollapsed] = useState(false);

  const filteredEntries = entries.filter((e) => {
    if (filterGrade === 'ALL') return true;
    return e.readinessGrade === filterGrade;
  });

  const getGradeBadge = (grade: string) => {
    switch (grade) {
      case 'A+':
        return 'bg-emerald-950/80 text-emerald-400 border-emerald-500/60 shadow-[0_0_8px_rgba(16,185,129,0.35)]';
      case 'A':
        return 'bg-cyan-950/80 text-cyan-400 border-cyan-500/50 shadow-[0_0_6px_rgba(6,182,212,0.25)]';
      case 'B':
        return 'bg-indigo-950/80 text-indigo-400 border-indigo-500/40';
      case 'QUARANTINED':
        return 'bg-rose-950/80 text-rose-400 border-rose-500/50';
      default:
        return 'bg-slate-900 text-slate-400 border-slate-700';
    }
  };

  const getStateBadge = (state: string) => {
    switch (state) {
      case 'IN_ZONE_CONFIRMED':
        return { label: '🎯 IN ZONE', color: 'text-emerald-400 bg-emerald-950/60 border-emerald-500/40' };
      case 'PULLBACK_APPROACHING':
        return { label: '⏱️ PULLBACK', color: 'text-cyan-400 bg-cyan-950/60 border-cyan-500/40' };
      case 'AWAITING_RECLAIM':
        return { label: '🛡️ RECLAIM PENDING', color: 'text-amber-400 bg-amber-950/60 border-amber-500/40' };
      case 'STOPPED_OUT':
        return { label: '❌ STOPPED', color: 'text-rose-400 bg-rose-950/60 border-rose-500/40' };
      default:
        return { label: state, color: 'text-slate-400 bg-slate-900 border-slate-700' };
    }
  };

  const getMtfBadge = (mtf: string) => {
    switch (mtf) {
      case 'ALIGNED':
        return { label: 'MTF ALIGNED', color: 'text-emerald-400 bg-emerald-950/50 border-emerald-500/30' };
      case 'COUNTER_TREND':
        return { label: 'COUNTER-TREND', color: 'text-amber-400 bg-amber-950/50 border-amber-500/30' };
      default:
        return { label: 'NEUTRAL', color: 'text-slate-400 bg-slate-900 border-slate-700' };
    }
  };

  return (
    <div className="w-full bg-[#0a0e1a] border border-cyan-900/30 rounded-md p-2.5 shadow-md flex flex-col gap-2">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-950/60 pb-2">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-xs font-bold tracking-wider text-cyan-300 uppercase flex items-center gap-1.5">
            ⚡ Actionable Entry Radar
            <span className="text-[10px] text-slate-400 font-normal">
              ({filteredEntries.length} SMC Setups Active)
            </span>
          </span>
        </div>

        {/* Grade filters & collapse toggle */}
        <div className="flex items-center gap-1.5">
          {(['ALL', 'A+', 'A', 'B'] as const).map((grade) => (
            <button
              key={grade}
              onClick={() => setFilterGrade(grade)}
              className={`px-2 py-0.5 text-[10px] font-semibold rounded border transition-colors ${
                filterGrade === grade
                  ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/60'
                  : 'bg-slate-900/60 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
            >
              {grade}
            </button>
          ))}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="px-2 py-0.5 text-[10px] text-slate-400 hover:text-slate-200 rounded border border-slate-800 bg-slate-900/40 ml-1"
            title={isCollapsed ? 'Expand Radar' : 'Collapse Radar'}
          >
            {isCollapsed ? '▼ SHOW' : '▲ HIDE'}
          </button>
        </div>
      </div>

      {/* Entry Cards / Horizontal Strip */}
      {!isCollapsed && (
        <div className="overflow-x-auto scrollbar-thin scrollbar-thumb-cyan-950 scrollbar-track-transparent">
          {filteredEntries.length === 0 ? (
            <div className="py-3 text-center text-xs text-slate-500 italic">
              {loading ? 'Scanning actionable entries...' : 'No active actionable entries matching grade filter.'}
            </div>
          ) : (
            <div className="flex items-stretch gap-2.5 pb-1 min-w-max">
              {filteredEntries.map((entry) => {
                const isSelected =
                  entry.symbol === selectedSymbol &&
                  entry.style === selectedStyle &&
                  (directionFilter === 'AUTO' || directionFilter === entry.side);

                const stateBadge = getStateBadge(entry.entryTriggerState);
                const mtfBadge = getMtfBadge(entry.mtfAlignment);

                return (
                  <div
                    key={`${entry.symbol}-${entry.style}-${entry.side}-${entry.timestamp}`}
                    onClick={() => onSelectEntry(entry)}
                    className={`cursor-pointer rounded border p-2 flex flex-col justify-between gap-1.5 w-64 transition-all duration-150 select-none ${
                      isSelected
                        ? 'bg-cyan-950/40 border-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.3)] ring-1 ring-cyan-400/50'
                        : 'bg-[#0d1322] border-slate-800/80 hover:border-slate-700 hover:bg-[#11192e]'
                    }`}
                  >
                    {/* Top row: Symbol, Side, Grade */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold text-slate-100">{entry.symbol}</span>
                        <span
                          className={`text-[9px] px-1.5 py-0.2 rounded font-semibold uppercase ${
                            entry.side === 'LONG'
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40'
                              : 'bg-rose-950 text-rose-400 border border-rose-500/40'
                          }`}
                        >
                          {entry.side}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          {entry.style}
                        </span>
                      </div>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded font-bold border ${getGradeBadge(
                          entry.readinessGrade
                        )}`}
                      >
                        {entry.readinessGrade} ({entry.entryReadinessScore.toFixed(0)})
                      </span>
                    </div>

                    {/* Middle row: Trigger State & Distance */}
                    <div className="flex items-center justify-between text-[10px]">
                      <span
                        className={`px-1.5 py-0.5 rounded font-mono border text-[9px] ${stateBadge.color}`}
                      >
                        {stateBadge.label}
                      </span>
                      <span className="font-mono text-slate-300">
                        {entry.distancePct >= 0 ? `+${entry.distancePct.toFixed(2)}%` : `${entry.distancePct.toFixed(2)}%`}
                      </span>
                    </div>

                    {/* Bottom row: R:R, MTF alignment & Origin */}
                    <div className="flex items-center justify-between text-[9px] pt-1 border-t border-slate-800/60 text-slate-400">
                      <span className="font-mono text-cyan-300 font-semibold">
                        R:R {entry.riskRewardRatio.toFixed(1)}:1
                      </span>
                      <span className={`px-1 rounded border text-[8px] ${mtfBadge.color}`}>
                        {mtfBadge.label}
                      </span>
                      <span className="truncate max-w-[80px]" title={entry.zoneOrigin}>
                        {entry.zoneOrigin.replace(/_/g, ' ')}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
