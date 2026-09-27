import React, { useState } from 'react';
import {
  Brain,
  Search,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  FileText,
  FlaskConical,
  RotateCcw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Layers,
  Sparkles,
  Zap,
} from 'lucide-react';
import { api } from '../../services/api';
import { ProjectKnowledgeContext } from '../../types';

interface ProjectBrainDeskProps {
  selectedSymbol?: string;
  selectedTimeframe?: string;
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
}

const QUICK_PROMPTS = [
  'Volatility regime filter effectiveness',
  'Fair Value Gap (FVG) continuation probability',
  'Order block invalidation rules',
  'Conservative Half-Kelly position sizing',
  'CVD absorption vs price breakout',
  'Macro DXY lead-lag correlation with BTC',
];

export const ProjectBrainDesk: React.FC<ProjectBrainDeskProps> = ({
  selectedSymbol = 'BTC/USDT',
  selectedTimeframe = '15m',
  onNotify,
}) => {
  const [query, setQuery] = useState<string>('Volatility regime filter effectiveness');
  const [symbol, setSymbol] = useState<string>(selectedSymbol);
  const [timeframe, setTimeframe] = useState<string>(selectedTimeframe);
  const [loading, setLoading] = useState<boolean>(false);
  const [context, setContext] = useState<ProjectKnowledgeContext | null>(null);
  const [showCitations, setShowCitations] = useState<boolean>(false);

  const handleQuery = async (customQuery?: string) => {
    const q = (customQuery || query).trim();
    if (!q) return;
    try {
      setLoading(true);
      const res = await api.askKnowledgeOS({
        question: q,
        mode: 'PROJECT',
        target_symbol: symbol,
        timeframe,
      });

      if (res.project_context) {
        setContext(res.project_context);
        onNotify?.('success', 'Project Brain Context', `Synthesized research context for: "${q}"`);
      }
    } catch (err: any) {
      onNotify?.('error', 'Project Brain Query Failed', err.message || 'Error fetching project context');
    } finally {
      setLoading(false);
    }
  };

  const getRecBadge = (rec: string) => {
    if (rec.startsWith('VALIDATED')) return 'bg-emerald-950 text-emerald-300 border-emerald-700';
    if (rec.startsWith('DISPUTED')) return 'bg-amber-950 text-amber-300 border-amber-700';
    if (rec.startsWith('REJECT')) return 'bg-rose-950 text-rose-300 border-rose-700';
    return 'bg-blue-950 text-blue-300 border-blue-700';
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Search Header & Prompt Bar */}
      <div className="bg-slate-900/90 border border-cyan-900/50 rounded-xl p-4 shadow-lg flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-cyan-400" />
            <h3 className="font-bold text-sm text-cyan-300">
              PROJECT BRAIN: QUANTITATIVE CONTEXT ENGINE
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-bold bg-cyan-950 text-cyan-400 border border-cyan-800 rounded">
              PROJECT_BRAIN_POLICY
            </span>
          </div>
          <span className="text-[11px] text-slate-400">
            Authoritative Research Context for Architecture & Strategy
          </span>
        </div>

        {/* Input Bar */}
        <div className="flex flex-col md:flex-row gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
              placeholder="Ask: What does SKY know about [market structure / volatility / FVG]?"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
          </div>

          <div className="flex items-center gap-2">
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-24 bg-slate-950 border border-slate-800 rounded-lg px-2 py-2.5 text-xs text-center text-slate-200"
              title="Target Asset"
            />
            <input
              type="text"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-16 bg-slate-950 border border-slate-800 rounded-lg px-2 py-2.5 text-xs text-center text-slate-200"
              title="Timeframe"
            />
            <button
              onClick={() => handleQuery()}
              disabled={loading || !query.trim()}
              className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 disabled:opacity-50 transition-all shadow-md shadow-cyan-600/30"
            >
              {loading ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              <span>Consult Brain</span>
            </button>
          </div>
        </div>

        {/* Quick Suggested Queries */}
        <div className="flex items-center gap-1.5 flex-wrap pt-1">
          <span className="text-[10px] text-slate-500 font-semibold uppercase">Suggestions:</span>
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => {
                setQuery(p);
                handleQuery(p);
              }}
              className="text-[11px] px-2 py-1 bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded transition-colors"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Safety & Governance Boundary Banner */}
      <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-xl flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-amber-300">Constitutional Safety Boundary</span>
            <span className="text-[10px] bg-amber-900/60 text-amber-200 px-1.5 py-0.2 rounded font-mono">
              ZERO_SILENT_MUTATION
            </span>
          </div>
          <p className="text-[11px] text-slate-300 leading-relaxed">
            Project Brain context informs, suggests, warns, and explains. It has{' '}
            <strong className="text-amber-300">zero execution authority</strong> and cannot bypass
            risk gates, modify capital allocations, activate strategies, or alter live trading perimeters.
          </p>
        </div>
      </div>

      {/* Query Result Presentation */}
      {context && (
        <div className="flex flex-col gap-4">
          {/* Recommendation & Metric Summary Card */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-3 shadow-sm">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-semibold">Synthesis Verdict:</span>
                <span className={`px-2.5 py-1 text-xs font-bold rounded-lg border ${getRecBadge(context.recommendation)}`}>
                  {context.recommendation}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span>
                  Proofs: <strong className="text-emerald-400">{context.epistemic_summary.empirical_proofs_found}</strong>
                </span>
                <span>
                  Autopsies: <strong className="text-rose-400">{context.epistemic_summary.known_failures_autopsied}</strong>
                </span>
                <span>
                  Conflicts: <strong className="text-amber-400">{context.epistemic_summary.active_contradictions}</strong>
                </span>
                <span className="px-2 py-0.5 text-[10px] bg-slate-800 text-cyan-300 rounded font-bold">
                  {context.epistemic_summary.highest_epistemic_tier}
                </span>
              </div>
            </div>

            {/* Current SKY Assumptions & Risk Boundaries */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5 mb-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
                  Active SKY Quantitative Assumptions
                </h4>
                <ul className="text-[11px] text-slate-400 flex flex-col gap-1.5 list-disc pl-4">
                  {context.current_sky_assumptions.map((a, idx) => (
                    <li key={idx}>{a}</li>
                  ))}
                </ul>
              </div>

              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5 mb-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                  Risk Perimeter Constraints
                </h4>
                <ul className="text-[11px] text-slate-400 flex flex-col gap-1.5 list-disc pl-4">
                  {context.risk_boundary_warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Active Macro Cognitive Regime & Dynamic Trade Plans */}
            {(context.macro_intelligence || (context.trade_plans && context.trade_plans.length > 0)) && (
              <div className="p-4 bg-[#0a101d] border border-rose-500/40 rounded-xl flex flex-col gap-3 shadow-md mt-2">
                <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Brain className="w-4 h-4 text-rose-400" />
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                      Macro Cognitive Memory &amp; Confluent Trading Plans
                    </h4>
                    <span className="px-2 py-0.5 text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-800 rounded">
                      ECONOMIC COGNITION
                    </span>
                  </div>
                  {context.macro_intelligence?.macro_regime && (
                    <span className="text-xs font-mono font-bold text-emerald-400">
                      Regime: {context.macro_intelligence.macro_regime.monetary_stance} ({context.macro_intelligence.macro_regime.liquidity_cycle} Liquidity)
                    </span>
                  )}
                </div>

                {context.macro_intelligence?.executive_macro_thesis && (
                  <p className="text-xs text-slate-300 font-mono bg-slate-950/80 p-2.5 rounded-lg border border-slate-800">
                    <strong className="text-amber-400">Active Thesis:</strong> {context.macro_intelligence.executive_macro_thesis}
                  </p>
                )}

                {context.trade_plans && context.trade_plans.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                    {context.trade_plans.map((p, idx) => (
                      <div key={idx} className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex flex-col justify-between gap-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-white font-mono">{p.symbol}</span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${
                            p.macroAlignment === 'CONFLUENT'
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : p.macroAlignment === 'CAUTION_DAMPENED'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                              : 'bg-slate-800 text-slate-300'
                          }`}>
                            <Zap className="w-3 h-3" />
                            {p.macroAlignment} ({p.riskMultiplier}x Sizing)
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-300 font-mono">
                          <div><strong>Bias:</strong> {p.bias} | <strong>Current:</strong> ${p.currentPrice?.toLocaleString()}</div>
                          <div><strong>FVG:</strong> {p.fvgZone} | <strong>OB:</strong> {p.orderBlock}</div>
                        </div>
                        <p className="text-[10px] text-slate-400 italic">
                          <strong>Driver:</strong> {p.macroDriver}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 4-Quadrant Evidence & Autopsy Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Quadrant 1: Empirical Evidence Vault Findings */}
            <div className="p-4 bg-slate-900 border border-emerald-900/30 rounded-xl flex flex-col gap-2.5">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <h4 className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                  <FlaskConical className="w-4 h-4 text-emerald-400" />
                  Empirical Evidence ({context.empirical_evidence.length})
                </h4>
                <span className="text-[10px] text-slate-500">Evidence Vault</span>
              </div>

              {context.empirical_evidence.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-500">
                  Zero verified empirical evidence records found in the Evidence Vault for this topic.
                </div>
              ) : (
                context.empirical_evidence.map((ev, i) => (
                  <div key={i} className="p-2.5 bg-slate-950 border border-emerald-950 rounded-lg flex flex-col gap-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-emerald-400">{ev.title}</span>
                      <span className="text-[10px] text-slate-400">{ev.location_citation}</span>
                    </div>
                    <p className="text-xs text-slate-300">{ev.content}</p>
                  </div>
                ))
              )}
            </div>

            {/* Quadrant 2: Historical Autopsies & Rejected Precedents */}
            <div className="p-4 bg-slate-900 border border-rose-900/30 rounded-xl flex flex-col gap-2.5">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <h4 className="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                  Autopsy & Failure Precedents ({context.autopsy_failures.length})
                </h4>
                <span className="text-[10px] text-slate-500">Rejected Vault</span>
              </div>

              {context.autopsy_failures.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-500">
                  No prior rejected hypotheses or forensic failure autopsies found matching this pattern.
                </div>
              ) : (
                context.autopsy_failures.map((af, i) => (
                  <div key={i} className="p-2.5 bg-slate-950 border border-rose-950 rounded-lg flex flex-col gap-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-rose-400">{af.title}</span>
                      <span className="text-[10px] text-slate-400">{af.location_citation}</span>
                    </div>
                    <p className="text-xs text-slate-300">{af.content}</p>
                  </div>
                ))
              )}
            </div>

            {/* Quadrant 3: Literature Claims & Competing Definitions */}
            <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-2.5">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <h4 className="text-xs font-bold text-cyan-300 flex items-center gap-1.5">
                  <FileText className="w-4 h-4 text-cyan-400" />
                  Source Claims & Definitions ({context.source_claims.length})
                </h4>
                <span className="text-[10px] text-slate-500">Literature Archive</span>
              </div>

              {context.source_claims.map((sc, i) => (
                <div key={i} className="p-2.5 bg-slate-950 border border-slate-800 rounded-lg flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-bold text-cyan-400">{sc.title}</span>
                    <span className="text-[10px] text-slate-500">{sc.location_citation}</span>
                  </div>
                  <p className="text-xs text-slate-300 line-clamp-2">{sc.content}</p>
                </div>
              ))}
            </div>

            {/* Quadrant 4: Proposed Statistical Test Plan */}
            <div className="p-4 bg-slate-900 border border-purple-900/30 rounded-xl flex flex-col gap-2.5">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <h4 className="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-purple-400" />
                  Recommended Empirical Test Plan
                </h4>
                <span className="text-[10px] text-slate-500">Walk-Forward Roadmap</span>
              </div>

              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex flex-col gap-2">
                {context.proposed_test_plan.map((step, idx) => (
                  <p key={idx} className="text-xs text-slate-300 font-mono">
                    {step}
                  </p>
                ))}
              </div>
            </div>
          </div>

          {/* Expandable Line-Item Provenance Citations ("Why am I seeing this?") */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowCitations(!showCitations)}
              className="w-full px-4 py-3 flex items-center justify-between text-xs font-bold text-slate-300 hover:bg-slate-800/60 transition-colors"
            >
              <div className="flex items-center gap-2">
                <ExternalLink className="w-4 h-4 text-cyan-400" />
                <span>WHY AM I SEEING THIS? (Auditable Line-Item Provenance: {context.provenance_citations.length} Sources)</span>
              </div>
              {showCitations ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showCitations && (
              <div className="p-4 border-t border-slate-800 flex flex-col gap-2 max-h-80 overflow-y-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead>
                    <tr className="border-b border-slate-800 text-[11px] text-slate-500">
                      <th className="py-1.5 px-2">ID</th>
                      <th className="py-1.5 px-2">SOURCE / TITLE</th>
                      <th className="py-1.5 px-2">AUTHOR</th>
                      <th className="py-1.5 px-2">SPATIAL CITATION</th>
                      <th className="py-1.5 px-2">EPISTEMIC STATUS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {context.provenance_citations.map((cite, i) => (
                      <tr key={i} className="border-b border-slate-900 hover:bg-slate-950/60 font-mono">
                        <td className="py-1.5 px-2 text-cyan-400 font-bold">{cite.node_id}</td>
                        <td className="py-1.5 px-2 text-slate-200">{cite.title || cite.source}</td>
                        <td className="py-1.5 px-2 text-slate-400">{cite.author}</td>
                        <td className="py-1.5 px-2 text-slate-500">{cite.citation || cite.location}</td>
                        <td className="py-1.5 px-2">
                          <span className="px-1.5 py-0.5 text-[10px] bg-slate-800 text-slate-300 rounded">
                            {cite.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
