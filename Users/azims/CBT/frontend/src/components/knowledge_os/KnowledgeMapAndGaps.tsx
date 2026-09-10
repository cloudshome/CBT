import React, { useState, useEffect } from 'react';
import {
  Compass,
  RotateCcw,
  FlaskConical,
  Sparkles,
} from 'lucide-react';
import { api } from '../../services/api';
import { ResearchGapItem } from '../../types';

interface KnowledgeMapAndGapsProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
  onAskConcept?: (concept: string) => void;
}

export const KnowledgeMapAndGaps: React.FC<KnowledgeMapAndGapsProps> = ({
  onNotify,
  onAskConcept,
}) => {
  const [gaps, setGaps] = useState<ResearchGapItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [filterDomain, setFilterDomain] = useState<string>('ALL');

  const fetchGaps = async () => {
    try {
      setLoading(true);
      const res = await api.getResearchGaps();
      setGaps(res.gaps || []);
    } catch (err: any) {
      onNotify?.('error', 'Failed loading research gaps', err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGaps();
  }, []);

  const domains = ['ALL', ...Array.from(new Set(gaps.map((g) => g.domain)))];

  const filteredGaps = gaps.filter((g) => {
    if (filterDomain !== 'ALL' && g.domain !== filterDomain) return false;
    return true;
  });

  const getGapBadge = (type: string) => {
    if (type === 'HIGH_TALK_ZERO_EVIDENCE') {
      return 'bg-rose-950 text-rose-300 border-rose-700';
    }
    if (type === 'CONFLICTING_DEFINITIONS') {
      return 'bg-amber-950 text-amber-300 border-amber-700';
    }
    return 'bg-purple-950 text-purple-300 border-purple-700';
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Header & Metric Banner */}
      <div className="bg-slate-900/90 border border-amber-900/50 rounded-xl p-4 shadow-lg flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Compass className="w-5 h-5 text-amber-400" />
            <h3 className="font-bold text-sm text-amber-300">
              RESEARCH GAP DETECTOR & EVIDENCE RADAR
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800 rounded">
              EMPIRICAL_DEFICIT_MONITOR
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Surfaces ideas heavily discussed across trading literature that lack empirical verification in SKY's Evidence Vault.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchGaps}
            disabled={loading}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Scan Gaps</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        <span className="text-[10px] text-slate-500 font-semibold uppercase mr-1">Domain Filter:</span>
        {domains.map((d) => (
          <button
            key={d}
            onClick={() => setFilterDomain(d)}
            className={`px-2.5 py-1 rounded text-xs transition-colors ${
              filterDomain === d
                ? 'bg-amber-600/30 border border-amber-500 text-amber-200 font-bold'
                : 'bg-slate-900 text-slate-400 border border-slate-800 hover:bg-slate-800'
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      {/* Gap Radar Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredGaps.map((gap) => (
          <div
            key={gap.gap_id}
            className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col justify-between gap-3 shadow-sm hover:border-slate-700 transition-colors"
          >
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className={`px-2 py-0.5 text-[10px] font-bold rounded border ${getGapBadge(gap.gap_type)}`}>
                  {gap.gap_type.replace(/_/g, ' ')}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">
                  Priority: <strong className="text-amber-400">{gap.priority_score.toFixed(2)}</strong>
                </span>
              </div>

              <h4 className="text-xs font-bold text-slate-200 flex items-center justify-between">
                <span>{gap.concept_title}</span>
                <span className="text-[10px] text-slate-400 font-mono">[{gap.domain}]</span>
              </h4>

              <div className="flex items-center gap-3 text-[11px] text-slate-400 py-1 bg-slate-950 px-2.5 rounded border border-slate-800/80">
                <span>
                  Source Claims: <strong className="text-cyan-400">{gap.claims_count}</strong>
                </span>
                <span>•</span>
                <span>
                  Evidence Proofs: <strong className="text-rose-400">{gap.empirical_tests_count}</strong>
                </span>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed font-sans">
                {gap.description}
              </p>

              <div className="p-2.5 bg-slate-950/80 border border-purple-950/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-purple-400 uppercase">Suggested Hypothesis:</span>
                <p className="text-xs text-slate-300 font-mono italic">{gap.suggested_hypothesis}</p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/80">
              <button
                onClick={() => onAskConcept?.(`Teach me ${gap.concept_title}`)}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs flex items-center gap-1 transition-colors"
              >
                <Sparkles className="w-3 h-3 text-emerald-400" />
                <span>Learn</span>
              </button>
              <button
                onClick={() => {
                  onNotify?.('info', 'Hypothesis Queued', `Created test candidate for ${gap.concept_title}`);
                }}
                className="px-2.5 py-1 bg-purple-900/60 hover:bg-purple-800 text-purple-200 border border-purple-700/60 rounded text-xs flex items-center gap-1 transition-colors"
              >
                <FlaskConical className="w-3 h-3" />
                <span>Test in Lab</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
