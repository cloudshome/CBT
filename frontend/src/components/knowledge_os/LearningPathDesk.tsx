import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  Clock,
  Sparkles,
  ArrowRight,
  RotateCcw,
} from 'lucide-react';
import { api } from '../../services/api';
import {
  PersonalLearningGraphResponse,
  ResearchAdvisorResponse,
} from '../../types';

interface LearningPathDeskProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
  onAskConcept?: (concept: string) => void;
}

export const LearningPathDesk: React.FC<LearningPathDeskProps> = ({
  onNotify,
  onAskConcept,
}) => {
  const [graphData, setGraphData] = useState<PersonalLearningGraphResponse | null>(null);
  const [advisorData, setAdvisorData] = useState<ResearchAdvisorResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const fetchLearningState = async () => {
    try {
      setLoading(true);
      const [gRes, aRes] = await Promise.all([
        api.getPersonalLearningGraph(),
        api.getResearchAdvisor(),
      ]);
      setGraphData(gRes);
      setAdvisorData(aRes);
    } catch (err: any) {
      onNotify?.('error', 'Failed loading learning path', err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLearningState();
  }, []);

  const getMasteryColor = (mastery: number) => {
    if (mastery >= 0.70) return 'bg-emerald-500';
    if (mastery >= 0.35) return 'bg-amber-500';
    return 'bg-slate-700';
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Header & Overall Curriculum Progress */}
      <div className="bg-slate-900/90 border border-purple-900/50 rounded-xl p-4 shadow-lg flex flex-col gap-3">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-purple-400" />
              <h3 className="font-bold text-sm text-purple-300">
                PERSONAL LEARNING GRAPH & CURRICULUM
              </h3>
              <span className="px-2 py-0.5 text-[10px] font-bold bg-purple-950 text-purple-400 border border-purple-800 rounded">
                SPACED_REPETITION_ENGINE
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Tracks exposure, calibration accuracy, misconceptions, and prerequisite mastery across 16+ institutional domains.
            </p>
          </div>

          <button
            onClick={fetchLearningState}
            disabled={loading}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Curriculum</span>
          </button>
        </div>

        {/* Overall Curriculum Bar */}
        {graphData && (
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs text-slate-300">
              <span className="font-semibold">Overall Quantitative Mastery:</span>
              <span className="font-bold text-purple-400">
                {graphData.summary.overall_curriculum_progress_pct}%
              </span>
            </div>
            <div className="w-full h-2.5 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
              <div
                className="h-full bg-gradient-to-r from-purple-500 to-emerald-400 transition-all duration-500"
                style={{ width: `${graphData.summary.overall_curriculum_progress_pct}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
              <span>Mastered: <strong className="text-emerald-400">{graphData.summary.mastered_count}</strong></span>
              <span>In Progress: <strong className="text-amber-400">{graphData.summary.in_progress_count}</strong></span>
              <span>Unstarted: <strong className="text-slate-500">{graphData.summary.unstarted_count}</strong></span>
              <span>Total Concepts: <strong className="text-slate-300">{graphData.summary.total_concepts}</strong></span>
            </div>
          </div>
        )}
      </div>

      {/* 'Right Path' Research Advisor Card */}
      {advisorData && (
        <div className="p-4 bg-gradient-to-r from-slate-900 to-purple-950/40 border border-purple-800/60 rounded-xl flex flex-col gap-3 shadow-md">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-purple-300 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-400" />
              RIGHT PATH RESEARCH ADVISOR (NEXT OPTIMAL STEP)
            </h4>
            <span className="text-[10px] font-mono text-slate-400">
              Recommended: {advisorData.recommended_title}
            </span>
          </div>

          <p className="text-xs text-slate-200 leading-relaxed">
            {advisorData.rationale}
          </p>

          <div className="flex flex-col gap-1 text-xs text-slate-300 font-mono bg-slate-950/70 p-2.5 rounded-lg border border-slate-800">
            {advisorData.suggested_actions.map((act, i) => (
              <span key={i}>{act}</span>
            ))}
          </div>

          <div className="flex justify-end">
            <button
              onClick={() => onAskConcept?.(`Teach me ${advisorData.recommended_title}`)}
              className="px-3.5 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm"
            >
              <span>Begin Teaching Module</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Concept Curriculum Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {graphData?.concepts.map((node) => {
          const masteryPct = Math.round(node.mastery_estimate * 100);
          const daysToReview = node.next_review
            ? Math.max(0, Math.round((node.next_review - Date.now()) / 86400000))
            : 1;

          return (
            <div
              key={node.concept_id}
              className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col justify-between gap-3 shadow-sm"
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold px-2 py-0.5 bg-slate-950 text-slate-400 border border-slate-800 rounded">
                    {node.domain}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    ID: {node.concept_id}
                  </span>
                </div>

                <h4 className="text-xs font-bold text-slate-200 flex items-center justify-between">
                  <span>{node.concept_title}</span>
                  <span className="text-xs font-bold font-mono text-purple-300">{masteryPct}%</span>
                </h4>

                {/* Progress Bar */}
                <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${getMasteryColor(node.mastery_estimate)} transition-all duration-300`}
                    style={{ width: `${masteryPct}%` }}
                  />
                </div>

                {/* Stats row */}
                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                  <span>Exposures: <strong className="text-slate-300">{node.exposure_count}</strong></span>
                  <span>Quizzes: <strong className="text-slate-300">{node.quiz_attempts}</strong></span>
                  <span>
                    Accuracy:{' '}
                    <strong className="text-emerald-400">
                      {node.quiz_attempts > 0
                        ? Math.round((node.correct_answers / node.quiz_attempts) * 100)
                        : 0}%
                    </strong>
                  </span>
                </div>

                {/* Prerequisites */}
                {node.prerequisite_concepts.length > 0 && (
                  <div className="text-[10px] text-slate-400 flex items-center gap-1 flex-wrap pt-1">
                    <span className="text-slate-500">Prereqs:</span>
                    {node.prerequisite_concepts.map((p) => (
                      <span key={p} className="px-1.5 py-0.2 bg-slate-950 text-slate-400 rounded border border-slate-800">
                        {p}
                      </span>
                    ))}
                  </div>
                )}

                {/* Misconceptions */}
                {node.misconceptions.length > 0 && (
                  <div className="p-2 bg-rose-950/40 border border-rose-900/40 rounded text-[11px] text-rose-300 flex flex-col gap-0.5">
                    <span className="text-[10px] font-bold text-rose-400 uppercase">Identified Misconception:</span>
                    <span>{node.misconceptions[0]}</span>
                  </div>
                )}
              </div>

              {/* Action Bar */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
                <span className="text-[10px] text-slate-500 flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3" />
                  Next Review: {daysToReview === 0 ? 'Due Today' : `in ${daysToReview}d`}
                </span>
                <button
                  onClick={() => onAskConcept?.(`Teach me ${node.concept_title}`)}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs transition-colors flex items-center gap-1"
                >
                  <Sparkles className="w-3 h-3 text-emerald-400" />
                  <span>Practice</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
