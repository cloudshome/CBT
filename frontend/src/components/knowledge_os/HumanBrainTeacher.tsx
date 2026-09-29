import React, { useState } from 'react';
import {
  Sparkles,
  BookOpen,
  FlaskConical,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Brain,
  Layers,
  ArrowRight,
  Target,
} from 'lucide-react';
import { api } from '../../services/api';
import {
  HumanQuestionMode,
  HumanAnswerData,
  QuizItem,
  QuizSubmissionResult,
} from '../../types';

interface HumanBrainTeacherProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
}

const MODES: Array<{ mode: HumanQuestionMode; label: string; icon: string }> = [
  { mode: 'EXPLAIN', label: 'Explain', icon: '💡' },
  { mode: 'TEACH', label: 'Teach Step-by-Step', icon: '🎓' },
  { mode: 'COMPARE', label: 'Compare Perspect.', icon: '⚖️' },
  { mode: 'CHALLENGE_ME', label: 'Challenge Me', icon: '🥊' },
  { mode: 'QUIZ_ME', label: 'Quiz Me', icon: '🧪' },
  { mode: 'PRACTICAL_EXERCISE', label: 'Practical Drill', icon: '🎯' },
  { mode: 'RESEARCH_DEEP_DIVE', label: 'Deep Dive', icon: '🔬' },
  { mode: 'WHAT_SHOULD_I_LEARN_NEXT', label: 'What Next?', icon: '🧭' },
];

const SUGGESTIONS = [
  'Teach me liquidity sweeps',
  'What do books say about stop losses?',
  'Explain Fair Value Gaps like a professional',
  'Compare ICT with traditional technical analysis',
  'Why does mathematical expectancy matter more than win rate?',
  'What are the failure reasons for retail breakout strategies?',
];

export const HumanBrainTeacher: React.FC<HumanBrainTeacherProps> = ({ onNotify }) => {
  const [question, setQuestion] = useState<string>('Teach me liquidity sweeps');
  const [activeMode, setActiveMode] = useState<HumanQuestionMode>('TEACH');
  const [depth, setDepth] = useState<string>('INTERMEDIATE');
  const [loading, setLoading] = useState<boolean>(false);
  const [answerData, setAnswerData] = useState<HumanAnswerData | null>(null);
  const [showSources, setShowSources] = useState<boolean>(false);

  // Quiz State
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [quizResult, setQuizResult] = useState<QuizSubmissionResult | null>(null);
  const [submittingQuiz, setSubmittingQuiz] = useState<boolean>(false);

  const handleAsk = async (customQ?: string, customMode?: HumanQuestionMode) => {
    const q = (customQ || question).trim();
    if (!q) return;

    try {
      setLoading(true);
      setSelectedOption(null);
      setQuizResult(null);

      const m = customMode || activeMode;
      const res = await api.askKnowledgeOS({
        question: q,
        mode: 'HUMAN',
        human_mode: m,
        depth,
      });

      if (res.answer_data) {
        setAnswerData(res.answer_data);
        onNotify?.('success', 'Teacher Response', `Generated educational breakdown for: "${q}"`);
      }
    } catch (err: any) {
      onNotify?.('error', 'Teacher Query Failed', err.message || 'Error generating educational answer');
    } finally {
      setLoading(false);
    }
  };

  const handleQuizSubmit = async (quiz: QuizItem, optionIdx: number) => {
    setSelectedOption(optionIdx);
    try {
      setSubmittingQuiz(true);
      const res = await api.submitQuizAnswer({
        quiz_id: quiz.quiz_id,
        concept_id: quiz.concept_id,
        selected_option_index: optionIdx,
        correct_option_index: quiz.correct_option_index,
        question_text: quiz.question,
        options: quiz.options,
        misconception_trap: quiz.misconception_trap,
      });
      setQuizResult(res);
      if (res.is_correct) {
        onNotify?.('success', 'Quiz Passed', res.feedback);
      } else {
        onNotify?.('warning', 'Concept Calibrated', res.feedback);
      }
    } catch (err: any) {
      onNotify?.('error', 'Quiz Submission Error', err.message || 'Error recording quiz answer');
    } finally {
      setSubmittingQuiz(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Teacher Question Bar */}
      <div className="bg-slate-900/90 border border-emerald-900/50 rounded-xl p-4 shadow-lg flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-emerald-400" />
            <h3 className="font-bold text-sm text-emerald-300">
              SKY RESEARCH TEACHER & ADAPTIVE TUTOR
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">
              HUMAN_ANSWER_PROTOCOL
            </span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={depth}
              onChange={(e) => setDepth(e.target.value)}
              className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-300"
            >
              <option value="BEGINNER">Beginner</option>
              <option value="INTERMEDIATE">Intermediate</option>
              <option value="ADVANCED">Advanced</option>
              <option value="EXPERT">Expert Quant</option>
            </select>
          </div>
        </div>

        {/* Input Bar */}
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
            placeholder="Ask the Research Teacher anything about trading, market mechanics, or risk..."
            className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
          />
          <button
            onClick={() => handleAsk()}
            disabled={loading || !question.trim()}
            className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 disabled:opacity-50 transition-all shadow-md shadow-emerald-600/30"
          >
            {loading ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            <span>Teach Me</span>
          </button>
        </div>

        {/* Mode Selector Buttons */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
          {MODES.map((m) => (
            <button
              key={m.mode}
              onClick={() => {
                setActiveMode(m.mode);
                handleAsk(question, m.mode);
              }}
              className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all whitespace-nowrap ${
                activeMode === m.mode
                  ? 'bg-emerald-600/30 border border-emerald-500 text-emerald-200 shadow-sm'
                  : 'bg-slate-950 text-slate-400 border border-slate-800 hover:bg-slate-800'
              }`}
            >
              <span>{m.icon}</span>
              <span>{m.label}</span>
            </button>
          ))}
        </div>

        {/* Suggested Prompts */}
        <div className="flex items-center gap-1.5 flex-wrap pt-1">
          <span className="text-[10px] text-slate-500 font-semibold uppercase">Quick Prompts:</span>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => {
                setQuestion(s);
                handleAsk(s);
              }}
              className="text-[11px] px-2 py-1 bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-800 rounded transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Answer Output */}
      {answerData && (
        <div className="flex flex-col gap-4">
          {/* Missing Prerequisites Warning (Adaptive Teaching Invariant) */}
          {answerData.missing_prerequisites && answerData.missing_prerequisites.length > 0 && (
            <div className="p-3 bg-indigo-950/60 border border-indigo-700/60 rounded-xl flex items-start gap-3">
              <Brain className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
              <div className="flex flex-col gap-0.5">
                <span className="text-xs font-bold text-indigo-300">
                  Adaptive Teaching Notice: Foundational Prerequisites Recommended
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Before mastering{' '}
                  <strong className="text-indigo-200">{answerData.primary_concept}</strong>, you should
                  strengthen your foundation in:
                </p>
                <div className="flex items-center gap-2 flex-wrap mt-1">
                  {answerData.missing_prerequisites.map((p, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 text-[10px] font-mono bg-indigo-900/80 text-indigo-200 border border-indigo-700 rounded"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Master Answer Breakdown (Human Answer Protocol) */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-4 shadow-sm">
            {/* 1. Simple Plain-Language Explanation */}
            <div className="flex flex-col gap-1 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                <span>💡 Core Concept Explanation</span>
              </div>
              <p className="text-sm text-slate-100 leading-relaxed font-sans font-medium">
                {answerData.answer_breakdown.simple_explanation}
              </p>
            </div>

            {/* 6-Part Structured Protocol Accordion */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
              {/* Box A: Source Knowledge */}
              <div className="p-3.5 bg-slate-950 border border-slate-800/90 rounded-xl flex flex-col gap-2">
                <h4 className="text-xs font-bold text-cyan-400 flex items-center gap-1.5">
                  <BookOpen className="w-3.5 h-3.5" />
                  A. Literature & Book Knowledge
                </h4>
                <ul className="text-xs text-slate-300 flex flex-col gap-2 list-disc pl-4">
                  {answerData.answer_breakdown.source_knowledge.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">{item}</li>
                  ))}
                </ul>
              </div>

              {/* Box B: Cross-Source Synthesis */}
              <div className="p-3.5 bg-slate-950 border border-slate-800/90 rounded-xl flex flex-col gap-2">
                <h4 className="text-xs font-bold text-indigo-400 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  B. Cross-Source Synthesis & Agreements
                </h4>
                <ul className="text-xs text-slate-300 flex flex-col gap-2 list-disc pl-4">
                  {answerData.answer_breakdown.cross_source_synthesis.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">{item}</li>
                  ))}
                </ul>
              </div>

              {/* Box C: Empirical Evidence */}
              <div className="p-3.5 bg-slate-950 border border-emerald-950/80 rounded-xl flex flex-col gap-2">
                <h4 className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                  <FlaskConical className="w-3.5 h-3.5" />
                  C. Empirical Proofs (Evidence Vault)
                </h4>
                <ul className="text-xs text-slate-300 flex flex-col gap-2 list-disc pl-4">
                  {answerData.answer_breakdown.empirical_evidence.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">{item}</li>
                  ))}
                </ul>
              </div>

              {/* Box D: SKY Findings & Autopsy Precedents */}
              <div className="p-3.5 bg-slate-950 border border-amber-950/80 rounded-xl flex flex-col gap-2">
                <h4 className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  D. SKY Project Experiments & Autopsies
                </h4>
                <ul className="text-xs text-slate-300 flex flex-col gap-2 list-disc pl-4">
                  {answerData.answer_breakdown.sky_project_knowledge.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">{item}</li>
                  ))}
                </ul>
              </div>

              {/* Box E: Model Inference */}
              <div className="p-3.5 bg-slate-950 border border-purple-950/80 rounded-xl flex flex-col gap-2">
                <h4 className="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" />
                  E. Model Deductive Inference (AI Reasoning)
                </h4>
                <ul className="text-xs text-slate-300 flex flex-col gap-2 list-disc pl-4">
                  {answerData.answer_breakdown.model_inference.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">{item}</li>
                  ))}
                </ul>
              </div>

              {/* Box F: Unknowns & What Remains Untested */}
              <div className="p-3.5 bg-slate-950 border border-rose-950/80 rounded-xl flex flex-col gap-2">
                <h4 className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5" />
                  F. What Remains Unproven / Unknown
                </h4>
                <ul className="text-xs text-slate-300 flex flex-col gap-2 list-disc pl-4">
                  {answerData.answer_breakdown.unknown_or_unestablished.map((item, idx) => (
                    <li key={idx} className="leading-relaxed">{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Interactive "TEST YOURSELF" Quiz Card */}
          {answerData.quiz && (
            <div className="p-5 bg-gradient-to-br from-slate-900 to-indigo-950/40 border border-indigo-800/50 rounded-xl flex flex-col gap-3 shadow-md">
              <div className="flex items-center justify-between pb-2 border-b border-indigo-900/50">
                <h4 className="text-xs font-bold text-indigo-300 flex items-center gap-2">
                  <Target className="w-4 h-4 text-indigo-400" />
                  TEST YOUR UNDERSTANDING (CALIBRATION DRILL)
                </h4>
                <span className="text-[10px] text-slate-400 font-mono">
                  Concept: {answerData.quiz.concept_id}
                </span>
              </div>

              <p className="text-xs font-semibold text-slate-200">
                {answerData.quiz.question}
              </p>

              <div className="flex flex-col gap-2 pt-1">
                {answerData.quiz.options.map((opt, idx) => {
                  const isChosen = selectedOption === idx;
                  const isSubmitted = quizResult !== null;
                  const isCorrectAnswer = answerData.quiz?.correct_option_index === idx;

                  let btnColor = 'bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800';
                  if (isSubmitted) {
                    if (isCorrectAnswer) {
                      btnColor = 'bg-emerald-950 border-emerald-600 text-emerald-200 font-bold';
                    } else if (isChosen && !isCorrectAnswer) {
                      btnColor = 'bg-rose-950 border-rose-600 text-rose-200';
                    }
                  } else if (isChosen) {
                    btnColor = 'bg-indigo-900 border-indigo-500 text-white';
                  }

                  return (
                    <button
                      key={idx}
                      disabled={isSubmitted || submittingQuiz}
                      onClick={() => handleQuizSubmit(answerData.quiz!, idx)}
                      className={`text-left p-3 rounded-lg border text-xs transition-all flex items-start gap-2.5 ${btnColor}`}
                    >
                      <span className="w-5 h-5 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center text-[10px] shrink-0">
                        {String.fromCharCode(65 + idx)}
                      </span>
                      <span className="leading-relaxed">{opt}</span>
                    </button>
                  );
                })}
              </div>

              {/* Quiz Evaluation Feedback */}
              {quizResult && (
                <div
                  className={`p-3 rounded-lg border text-xs flex flex-col gap-1 mt-1 ${
                    quizResult.is_correct
                      ? 'bg-emerald-950/60 border-emerald-700 text-emerald-200'
                      : 'bg-amber-950/60 border-amber-700 text-amber-200'
                  }`}
                >
                  <div className="flex items-center justify-between font-bold">
                    <span>{quizResult.feedback}</span>
                    <span>Updated Mastery: {(quizResult.updated_mastery * 100).toFixed(0)}%</span>
                  </div>
                  <p className="text-[11px] text-slate-300 pt-1 border-t border-slate-800">
                    <strong className="text-slate-200">Explanation:</strong> {answerData.quiz.explanation}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* "LEARN NEXT" Recommended Concept Path */}
          {answerData.learn_next && answerData.learn_next.length > 0 && (
            <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-2">
              <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <ArrowRight className="w-3.5 h-3.5 text-emerald-400" />
                RECOMMENDED NEXT LEARNING CONCEPTS
              </h4>
              <div className="flex items-center gap-2 flex-wrap pt-1">
                {answerData.learn_next.map((ln) => (
                  <button
                    key={ln.concept_id}
                    onClick={() => {
                      const q = `Explain ${ln.title}`;
                      setQuestion(q);
                      handleAsk(q);
                    }}
                    className="px-3 py-1.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 hover:border-emerald-700 rounded-lg text-xs text-slate-300 transition-colors flex items-center gap-1.5"
                  >
                    <span className="text-emerald-400 font-bold">&rarr;</span>
                    <span>{ln.title}</span>
                    <span className="text-[10px] text-slate-500 font-mono">({ln.domain})</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Expandable Citations Drawer */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowSources(!showSources)}
              className="w-full px-4 py-3 flex items-center justify-between text-xs font-bold text-slate-300 hover:bg-slate-800/60 transition-colors"
            >
              <div className="flex items-center gap-2">
                <ExternalLink className="w-4 h-4 text-emerald-400" />
                <span>WHY AM I SEEING THIS? ({answerData.citations.length} Auditable Citations)</span>
              </div>
              {showSources ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showSources && (
              <div className="p-4 border-t border-slate-800 flex flex-col gap-2">
                {answerData.citations.map((c, i) => (
                  <div key={i} className="p-2.5 bg-slate-950 border border-slate-900 rounded-lg text-xs flex flex-col gap-1 font-mono">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-emerald-400">{c.source}</span>
                      <span className="text-slate-500">{c.location}</span>
                    </div>
                    <p className="text-slate-300 italic text-[11px]">{c.quote}</p>
                    <span className="text-[10px] text-slate-500">Author: {c.author} | Status: {c.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
