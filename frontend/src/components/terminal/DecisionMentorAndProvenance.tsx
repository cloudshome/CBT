import React, { useState, useEffect } from 'react';
import {
  Brain,
  ShieldCheck,
  AlertOctagon,
  GitBranch,
  PlayCircle,
  BookOpen,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import {
  AICoachCockpitData,
  ProvenanceGraphData,
  SMCGlossaryItem,
  ReplaySnapshotData,
} from '../../types';
import { api } from '../../services/api';

interface DecisionMentorAndProvenanceProps {
  coach: AICoachCockpitData;
  provenance: ProvenanceGraphData;
}

export const DecisionMentorAndProvenance: React.FC<DecisionMentorAndProvenanceProps> = ({
  coach,
  provenance,
}) => {
  const [activeSection, setActiveSection] = useState<'COACH' | 'PRE_TRADE_GATE' | 'WHY_NOT_TRADE' | 'PROVENANCE' | 'REPLAY' | 'GLOSSARY'>('COACH');

  // Interactive Checklist State
  const [checklist, setChecklist] = useState(coach.preTradeGateChecklist);

  // Glossary State
  const [glossaryItems, setGlossaryItems] = useState<SMCGlossaryItem[]>([]);
  const [glossaryQuery, setGlossaryQuery] = useState('');

  // Replay State
  const [replayOffset, setReplayOffset] = useState<'NOW' | 'T-10m' | 'T-30m' | 'T-60m'>('NOW');
  const [replayData, setReplayData] = useState<ReplaySnapshotData | null>(null);

  // Load Glossary when tab is selected
  useEffect(() => {
    if (activeSection === 'GLOSSARY' && glossaryItems.length === 0) {
      api.getSMCGlossary(glossaryQuery).then((res) => {
        setGlossaryItems(res.items);
      }).catch(() => null);
    }
  }, [activeSection, glossaryQuery, glossaryItems.length]);

  // Load Replay when tab or offset changes
  useEffect(() => {
    if (activeSection === 'REPLAY') {
      api.getTerminalReplay(replayOffset).then((res) => {
        setReplayData(res);
      }).catch(() => null);
    }
  }, [activeSection, replayOffset]);

  const toggleCheck = (id: string) => {
    setChecklist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, checked: !item.checked } : item))
    );
  };

  const completedCount = checklist.filter((c) => c.checked).length;
  const isGatePassed = completedCount >= 8;

  return (
    <div className="w-full bg-[#080c16] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-300 select-none flex flex-col justify-between">
      {/* Sub-Tab Navigation Header */}
      <div className="flex flex-wrap items-center justify-between pb-2 mb-2.5 border-b border-[#1e293b] gap-2">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-indigo-400" />
          <span className="font-bold text-white text-[11px] tracking-wider">
            AI DECISION MENTOR &amp; RESEARCH PROVENANCE
          </span>
        </div>

        {/* Section Tabs */}
        <div className="flex flex-wrap items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 text-[10px]">
          <button
            onClick={() => setActiveSection('COACH')}
            className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
              activeSection === 'COACH' ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Coach Mentor
          </button>
          <button
            onClick={() => setActiveSection('PRE_TRADE_GATE')}
            className={`px-2.5 py-0.5 rounded font-semibold transition-all flex items-center gap-1 ${
              activeSection === 'PRE_TRADE_GATE' ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>Pre-Trade Gate</span>
            <span className={`text-[8px] px-1 rounded font-bold ${isGatePassed ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
              {completedCount}/10
            </span>
          </button>
          <button
            onClick={() => setActiveSection('WHY_NOT_TRADE')}
            className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
              activeSection === 'WHY_NOT_TRADE' ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Why Not Trade?
          </button>
          <button
            onClick={() => setActiveSection('PROVENANCE')}
            className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
              activeSection === 'PROVENANCE' ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Evidence Provenance
          </button>
          <button
            onClick={() => setActiveSection('REPLAY')}
            className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
              activeSection === 'REPLAY' ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Market Replay
          </button>
          <button
            onClick={() => setActiveSection('GLOSSARY')}
            className={`px-2.5 py-0.5 rounded font-semibold transition-all ${
              activeSection === 'GLOSSARY' ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Glossary
          </button>
        </div>
      </div>

      {/* 1. Coach Mentor Section */}
      {activeSection === 'COACH' && (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-stretch">
          <div className="md:col-span-8 bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <div>
              <div className="text-[10px] text-indigo-300 font-bold uppercase tracking-wider mb-1">
                CURRENT THESIS
              </div>
              <p className="text-[11px] text-white leading-relaxed mb-3 font-semibold">
                {coach.currentThesis}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[10px]">
                <div className="p-2 rounded bg-emerald-950/20 border border-emerald-500/30">
                  <span className="text-emerald-400 font-bold block mb-1">WHAT SUPPORTS IT:</span>
                  <ul className="space-y-1 text-slate-300">
                    {coach.supportingFactors.map((f, i) => (
                      <li key={i} className="flex items-start gap-1">
                        <span className="text-emerald-400 font-bold">✓</span> {f}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="p-2 rounded bg-amber-950/20 border border-amber-500/30">
                  <span className="text-amber-400 font-bold block mb-1">WHAT CAN BREAK IT:</span>
                  <ul className="space-y-1 text-slate-300">
                    {coach.threatFactors.map((t, i) => (
                      <li key={i} className="flex items-start gap-1">
                        <span className="text-amber-400 font-bold">⚠</span> {t}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* Coach Verdict Banner */}
            <div className="mt-3 p-2 rounded bg-indigo-950/60 border border-indigo-500/40 text-[10px] flex items-center justify-between">
              <span className="text-slate-400 font-semibold">COACH VERDICT:</span>
              <span className="text-cyan-300 font-black tracking-wide">{coach.verdict}</span>
            </div>
          </div>

          {/* Behavioral Bias / Tilt Monitor (4 cols) */}
          <div className="md:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-[10px] text-slate-400 mb-2 pb-1 border-b border-[#1e293b]">
                <span className="font-bold text-white uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck size={11} className="text-emerald-400" /> BEHAVIORAL SHIELD
                </span>
                <span className="text-emerald-400 font-bold">DISCIPLINED</span>
              </div>

              <div className="space-y-2 text-[10px]">
                <div className="flex justify-between">
                  <span className="text-slate-400">Consecutive Losses:</span>
                  <span className="text-white font-bold">{coach.behavioralTiltShield.consecutiveLosses}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Trade Frequency:</span>
                  <span className="text-cyan-300 font-bold">{coach.behavioralTiltShield.recentTradeFrequencyPerHour} trades/hr (Nominal)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Revenge Trading Alert:</span>
                  <span className="text-emerald-400 font-bold">None Detected</span>
                </div>
              </div>
            </div>

            <div className="mt-3 p-2 rounded bg-[#070b16] border border-[#1e293b]/70 text-[9px] text-slate-400 leading-tight">
              {coach.behavioralTiltShield.advisoryMessage}
            </div>
          </div>
        </div>
      )}

      {/* 2. Pre-Trade Gate Checklist */}
      {activeSection === 'PRE_TRADE_GATE' && (
        <div className="bg-[#0c1222] border border-[#1e293b] rounded-lg p-3">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]">
            <div>
              <span className="font-bold text-white text-[11px] uppercase tracking-wider">
                10-Point Institutional Pre-Trade Gate
              </span>
              <span className="text-[10px] text-slate-400 block">
                All mandatory gates must be confirmed before executing a live or paper order.
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded font-black text-[10px] border ${
                isGatePassed
                  ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-400'
                  : 'bg-rose-950/80 border-rose-500/50 text-rose-400 animate-pulse'
              }`}>
                STATUS: {isGatePassed ? 'GATE PASSED (READY)' : 'NOT READY (GATES REMAINING)'}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 my-2">
            {checklist.map((item) => (
              <div
                key={item.id}
                onClick={() => toggleCheck(item.id)}
                className={`p-2 rounded border transition-all cursor-pointer flex items-center justify-between ${
                  item.checked
                    ? 'bg-emerald-950/20 border-emerald-500/40 text-slate-200'
                    : 'bg-slate-900/40 border-slate-800 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center gap-2 text-[10px]">
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={() => toggleCheck(item.id)}
                    className="rounded border-slate-700 text-emerald-500 focus:ring-0 cursor-pointer"
                  />
                  <span>{item.label}</span>
                </div>
                {item.checked ? (
                  <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-rose-400 shrink-0" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. Why Not Trade? Rejection Engine */}
      {activeSection === 'WHY_NOT_TRADE' && (
        <div className="bg-[#0c1222] border border-[#1e293b] rounded-lg p-3">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <AlertOctagon size={14} className="text-amber-400" />
              <span className="font-bold text-white text-[11px] uppercase tracking-wider">
                &quot;Why Not Trade?&quot; Capital Preservation Engine
              </span>
            </div>
            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-bold text-[10px]">
              WAIT IS A FIRST-CLASS STATE
            </span>
          </div>

          <div className="space-y-3 text-[11px]">
            <div className="p-2.5 rounded bg-amber-950/20 border border-amber-500/40 text-amber-200">
              <span className="font-bold text-amber-400 block mb-1">PRIMARY BLOCKER / DISCIPLINE ADVISORY:</span>
              <p>{coach.whyNotTradeEngine.primaryBlocker}</p>
            </div>

            {coach.whyNotTradeEngine.activeBlockers.length > 0 && (
              <div className="p-2.5 rounded bg-[#070b16] border border-[#1e293b] space-y-1">
                <span className="text-slate-400 font-bold block mb-1">ACTIVE CAPITAL GATES:</span>
                {coach.whyNotTradeEngine.activeBlockers.map((b, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-slate-300 text-[10px]">
                    <span className="text-amber-400 font-bold">⚠</span> {b}
                  </div>
                ))}
              </div>
            )}

            <div className="p-2 rounded bg-indigo-950/30 border border-indigo-500/30 text-slate-300 text-[10px]">
              <span className="text-cyan-400 font-bold">RECOMMENDATION: </span>
              {coach.whyNotTradeEngine.capitalPreservationAdvice}
            </div>
          </div>
        </div>
      )}

      {/* 4. Evidence Provenance Chain */}
      {activeSection === 'PROVENANCE' && (
        <div className="bg-[#0c1222] border border-[#1e293b] rounded-lg p-3">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <GitBranch size={14} className="text-cyan-400" />
              <span className="font-bold text-white text-[11px] uppercase tracking-wider">
                Evidence Provenance Audit Chain
              </span>
            </div>
            <span className="text-[10px] text-slate-500">
              Thesis ID: {provenance.thesisId}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 my-2">
            {provenance.nodes.map((node, i) => (
              <div key={node.id} className="p-2 rounded bg-[#070b16] border border-[#1e293b] text-[10px] space-y-1 relative">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] text-slate-500 font-mono font-bold">STEP {i + 1}</span>
                  <span className="text-emerald-400 font-bold text-[9px]">{node.status}</span>
                </div>
                <div className="font-bold text-white text-[11px]">{node.step || node.name}</div>
                <div className="text-slate-400 text-[9px]">
                  {node.source || node.algorithm || node.idOrType || node.check || node.model}
                </div>
                <div className="flex justify-between text-[8px] text-slate-500 pt-1 border-t border-[#1e293b]/70">
                  <span>Latency: {node.latencyMs ? `${node.latencyMs}ms` : node.latency || 'N/A'}</span>
                  <span className="text-cyan-400">Conf: {node.confidence}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Market Replay Lab */}
      {activeSection === 'REPLAY' && (
        <div className="bg-[#0c1222] border border-[#1e293b] rounded-lg p-3">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <PlayCircle size={14} className="text-amber-400" />
              <span className="font-bold text-white text-[11px] uppercase tracking-wider">
                Trade &amp; Market Replay Lab
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-[10px]">
              {(['T-60m', 'T-30m', 'T-10m', 'NOW'] as const).map((offset) => (
                <button
                  key={offset}
                  onClick={() => setReplayOffset(offset)}
                  className={`px-2.5 py-0.5 rounded font-bold transition-all ${
                    replayOffset === offset
                      ? 'bg-amber-500 text-slate-950 shadow-sm'
                      : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {offset}
                </button>
              ))}
            </div>
          </div>

          {replayData && (
            <div className="space-y-3 text-[11px] my-2">
              <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                <div className="p-2 rounded bg-[#070b16] border border-[#1e293b]">
                  <span className="text-slate-500 block">REPLAY PRICE</span>
                  <span className="text-white font-bold text-sm">${replayData.replayPrice.toLocaleString()}</span>
                </div>
                <div className="p-2 rounded bg-[#070b16] border border-[#1e293b]">
                  <span className="text-slate-500 block">SCORE AT {replayData.offset}</span>
                  <span className="text-cyan-400 font-bold text-sm">{replayData.replayScore} / 100</span>
                </div>
                <div className="p-2 rounded bg-[#070b16] border border-[#1e293b]">
                  <span className="text-slate-500 block">ALIGNMENT AT {replayData.offset}</span>
                  <span className="text-emerald-400 font-bold text-sm">+{replayData.replayAlignment}</span>
                </div>
              </div>

              <div className="p-2.5 rounded bg-[#070b16] border border-[#1e293b]">
                <span className="text-amber-400 font-bold block mb-1">WHAT THE SYSTEM KNEW AT {replayData.offset}:</span>
                <p className="text-slate-300 leading-relaxed">{replayData.whatChanged}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 6. SMC & Quant Glossary */}
      {activeSection === 'GLOSSARY' && (
        <div className="bg-[#0c1222] border border-[#1e293b] rounded-lg p-3">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <BookOpen size={14} className="text-cyan-400" />
              <span className="font-bold text-white text-[11px] uppercase tracking-wider">
                Searchable SMC &amp; Quantitative Glossary
              </span>
            </div>
            <div className="relative w-48">
              <input
                type="text"
                value={glossaryQuery}
                onChange={(e) => setGlossaryQuery(e.target.value)}
                placeholder="Search term or concept..."
                className="w-full bg-[#070b16] border border-[#1e293b] rounded px-2 py-0.5 text-[10px] text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400"
              />
            </div>
          </div>

          <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
            {glossaryItems.map((item) => (
              <div key={item.term} className="p-2 rounded bg-[#070b16] border border-[#1e293b] text-[10px] space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-cyan-300 text-[11px]">{item.term}</span>
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                    {item.category}
                  </span>
                </div>
                <p className="text-slate-300">{item.definition}</p>
                <div className="flex flex-wrap items-center gap-3 text-[9px] pt-1 border-t border-[#1e293b]/70">
                  <span className="text-emerald-400">Rule: {item.rule}</span>
                  <span className="text-slate-400">Visual Cue: {item.visualCue}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
