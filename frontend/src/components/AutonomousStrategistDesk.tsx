import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Activity,
  Cpu,
  Shield,
  ShieldCheck,
  GitBranch,
  Layers,
  RefreshCw,
  Play,
  BarChart2,
  CheckCircle,
  AlertTriangle,
  XCircle,
  TrendingUp,
  FileText,
  Send,
  Sliders,
  Check,
  Clock,
  Terminal,
} from 'lucide-react';
import {
  synthesizeStrategy,
  getStrategistJobs,
  getStrategistJobDetail,
  getStrategistLineage,
  getStrategistPolicy,
  toggleStrategistDaemon,
  SynthesisJobReportItem,
  StrategyLineageNodeItem,
  StatisticalPolicyItem,
  ResearchClassification,
} from '../services/api';

interface AutonomousStrategistDeskProps {
  currentSymbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

type ActiveSubTab = 'CPCV' | 'STAT_DEFENSE' | 'PERTURBATION' | 'REGIMES' | 'LINEAGE' | 'TEARSHEET';

export const AutonomousStrategistDesk: React.FC<AutonomousStrategistDeskProps> = ({
  currentSymbol = 'BTC/USDT',
  onNotify,
}) => {
  // Form State
  const [symbol, setSymbol] = useState(currentSymbol);
  const [timeframe, setTimeframe] = useState('15m');
  const [concept, setConcept] = useState(
    'SMC liquidity sweep with order block retest and resting wall absorption'
  );
  const [parentGenomeId, setParentGenomeId] = useState<string>('');
  const [isMutation, setIsMutation] = useState(false);
  const [paramEmaFast, setParamEmaFast] = useState(12);
  const [paramEmaSlow, setParamEmaSlow] = useState(26);

  // Engine & Synthesis State
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveSubTab>('CPCV');
  const [currentJob, setCurrentJob] = useState<SynthesisJobReportItem | null>(null);
  const [pastJobs, setPastJobs] = useState<SynthesisJobReportItem[]>([]);
  const [lineageNodes, setLineageNodes] = useState<StrategyLineageNodeItem[]>([]);
  const [policy, setPolicy] = useState<StatisticalPolicyItem | null>(null);
  const [cumulativeTrials, setCumulativeTrials] = useState<number>(0);
  const [isDaemonActive, setIsDaemonActive] = useState<boolean>(false);
  const [isTogglingDaemon, setIsTogglingDaemon] = useState<boolean>(false);
  const [copiedTearSheet, setCopiedTearSheet] = useState<boolean>(false);

  // Load Policy and Lineage
  const fetchMeta = useCallback(async () => {
    try {
      const [policyRes, lineageRes, jobsRes] = await Promise.all([
        getStrategistPolicy(),
        getStrategistLineage(50),
        getStrategistJobs(10),
      ]);
      if (policyRes?.policy) {
        setPolicy(policyRes.policy);
        setCumulativeTrials(policyRes.cumulative_trials);
        setIsDaemonActive(policyRes.is_daemon_active);
      }
      if (lineageRes?.nodes) {
        setLineageNodes(lineageRes.nodes);
      }
      if (jobsRes?.jobs && jobsRes.jobs.length > 0) {
        setPastJobs(jobsRes.jobs);
        if (!currentJob) {
          setCurrentJob(jobsRes.jobs[0]);
        }
      }
    } catch (err) {
      console.error('Failed to load strategist meta:', err);
    }
  }, [currentJob]);

  useEffect(() => {
    fetchMeta();
    const interval = setInterval(fetchMeta, 15000);
    return () => clearInterval(interval);
  }, [fetchMeta]);

  // Handle Synthesis Run
  const handleRunSynthesis = async () => {
    if (isSynthesizing) return;
    setIsSynthesizing(true);
    onNotify?.('info', 'Quant Strategist Initiated', `Testing hypothesis on ${symbol} (${timeframe})...`);

    try {
      const baseParams: Record<string, number> = {
        ema_fast: Number(paramEmaFast),
        ema_slow: Number(paramEmaSlow),
      };

      const res = await synthesizeStrategy(
        symbol,
        timeframe,
        concept,
        baseParams,
        parentGenomeId || undefined,
        isMutation
      );

      if (res?.job) {
        setCurrentJob(res.job);
        setPastJobs((prev) => [res.job, ...prev.slice(0, 19)]);
        setCumulativeTrials(res.job.cumulative_trials);

        const verdict = res.job.research_dossier.classification;
        if (verdict === 'ROBUST') {
          onNotify?.(
            'success',
            'Research Gate: ROBUST',
            `Strategy ${res.job.strategy_id} admitted to Tier 1 Smoke Quarantine (DSR: ${res.job.research_dossier.dsr_report.deflated_sharpe_ratio}).`
          );
        } else {
          onNotify?.(
            'warning',
            `Research Gate: ${verdict}`,
            `Strategy rejected from quarantine. Reasons: ${res.job.research_dossier.rejection_reasons.join(', ') || 'Statistical hurdles not met'}`
          );
        }
      }
      fetchMeta();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown synthesis error';
      onNotify?.('error', 'Synthesis Failed', msg);
    } finally {
      setIsSynthesizing(false);
    }
  };

  // Toggle Background Exploration Daemon
  const handleToggleDaemon = async () => {
    if (isTogglingDaemon) return;
    setIsTogglingDaemon(true);
    try {
      const nextState = !isDaemonActive;
      const res = await toggleStrategistDaemon(nextState);
      setIsDaemonActive(res.is_daemon_active);
      onNotify?.(
        res.is_daemon_active ? 'success' : 'info',
        'Autonomous Daemon',
        res.is_daemon_active ? 'Background research exploration activated.' : 'Daemon deactivated.'
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Toggle error';
      onNotify?.('error', 'Daemon Error', msg);
    } finally {
      setIsTogglingDaemon(false);
    }
  };

  // Load a past job
  const handleSelectJob = async (jobId: string) => {
    try {
      const res = await getStrategistJobDetail(jobId);
      if (res?.job) {
        setCurrentJob(res.job);
      }
    } catch (err) {
      console.error('Failed to fetch job detail:', err);
    }
  };

  const handleCopyTearSheet = () => {
    if (!currentJob) return;
    navigator.clipboard.writeText(currentJob.tear_sheet_markdown);
    setCopiedTearSheet(true);
    setTimeout(() => setCopiedTearSheet(false), 2000);
  };

  // Helpers for styling classification
  const getClassificationBadge = (classification?: ResearchClassification) => {
    switch (classification) {
      case 'ROBUST':
        return {
          bg: 'bg-emerald-950/80 border-emerald-500/50 text-emerald-400',
          icon: <ShieldCheck className="w-5 h-5 text-emerald-400" />,
          label: 'ROBUST (QUARANTINE CANDIDATE)',
        };
      case 'FRAGILE':
        return {
          bg: 'bg-amber-950/80 border-amber-500/50 text-amber-400',
          icon: <AlertTriangle className="w-5 h-5 text-amber-400" />,
          label: 'FRAGILE (FRICTION / REGIME SENSITIVE)',
        };
      case 'OVERFIT':
        return {
          bg: 'bg-rose-950/80 border-rose-500/50 text-rose-400',
          icon: <XCircle className="w-5 h-5 text-rose-400" />,
          label: 'OVERFIT (REJECTED BY DSR / WRC)',
        };
      case 'INSUFFICIENT_DATA':
        return {
          bg: 'bg-blue-950/80 border-blue-500/50 text-blue-400',
          icon: <Clock className="w-5 h-5 text-blue-400" />,
          label: 'INSUFFICIENT DATA (SAMPLE < 30 TRADES)',
        };
      default:
        return {
          bg: 'bg-zinc-800/80 border-zinc-700 text-zinc-400',
          icon: <Shield className="w-5 h-5 text-zinc-400" />,
          label: 'INCONCLUSIVE',
        };
    }
  };

  const dossier = currentJob?.research_dossier;
  const classificationMeta = useMemo(
    () => getClassificationBadge(dossier?.classification),
    [dossier?.classification]
  );

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-zinc-100 p-4 space-y-4 overflow-y-auto">
      {/* 1. Header & Institutional Telemetry Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-zinc-900/90 border border-zinc-800 backdrop-blur-md shadow-2xl">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-lg bg-cyan-950/80 border border-cyan-500/40 text-cyan-400">
            <Cpu className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-wider text-zinc-100">
                AUTONOMOUS QUANT STRATEGIST
              </h1>
              <span className="px-2 py-0.5 text-xs font-mono rounded bg-cyan-950 text-cyan-400 border border-cyan-800">
                OS v2.0-PROD
              </span>
            </div>
            <p className="text-xs text-zinc-400 font-mono">
              Constitutional Multi-Testing Defense • Causal Purged CPCV • DSR/WRC Reality Check • 3-Tier Frictions
            </p>
          </div>
        </div>

        {/* Global Telemetry & Daemon Toggle */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <div className="px-3 py-1.5 rounded-lg bg-zinc-800/80 border border-zinc-700/60 flex items-center space-x-2">
            <span className="text-zinc-400">Policy:</span>
            <span className="text-cyan-400 font-bold">{policy?.policy_version || 'STAT_POLICY_2026_V1'}</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-zinc-800/80 border border-zinc-700/60 flex items-center space-x-2">
            <span className="text-zinc-400">Cumulative Trials (N):</span>
            <span className="text-amber-400 font-bold">{cumulativeTrials}</span>
            <span className="text-zinc-500">/ 200 daily max</span>
          </div>
          <button
            onClick={handleToggleDaemon}
            disabled={isTogglingDaemon}
            className={`px-3 py-1.5 rounded-lg border font-semibold flex items-center space-x-2 transition-all ${
              isDaemonActive
                ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300 hover:bg-emerald-900/80'
                : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-750'
            }`}
          >
            <div
              className={`w-2 h-2 rounded-full ${
                isDaemonActive ? 'bg-emerald-400 animate-ping' : 'bg-zinc-500'
              }`}
            />
            <span>Autonomous Daemon: {isDaemonActive ? 'ON' : 'OFF'}</span>
          </button>
        </div>
      </div>

      {/* 2. Research Hypothesis & Synthesis Control Deck */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Input Parameters Form */}
        <div className="lg:col-span-3 p-4 rounded-xl bg-zinc-900/70 border border-zinc-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-sm font-semibold text-zinc-200">
              <Sliders className="w-4 h-4 text-cyan-400" />
              <span>Research Hypothesis & Parameter Specification</span>
            </div>
            <div className="flex items-center space-x-2">
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1 text-xs font-mono text-zinc-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="BTC/USDT">BTC/USDT</option>
                <option value="ETH/USDT">ETH/USDT</option>
                <option value="SOL/USDT">SOL/USDT</option>
              </select>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1 text-xs font-mono text-zinc-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="1h">1h</option>
                <option value="4h">4h</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono text-zinc-400 mb-1">
              HYPOTHESIS / MARKET PHENOMENON CONCEPT:
            </label>
            <textarea
              rows={2}
              value={concept}
              onChange={(e) => setConcept(e.target.value)}
              placeholder="Describe quantitative edge, microstructure imbalance, or SMC mechanism..."
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-xs text-zinc-200 font-mono focus:outline-none focus:border-cyan-500 resize-none"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex items-center space-x-4 text-xs font-mono">
              <div className="flex items-center space-x-2">
                <span className="text-zinc-400">EMA Fast:</span>
                <input
                  type="number"
                  value={paramEmaFast}
                  onChange={(e) => setParamEmaFast(Number(e.target.value))}
                  className="w-14 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-center text-zinc-200"
                />
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-zinc-400">EMA Slow:</span>
                <input
                  type="number"
                  value={paramEmaSlow}
                  onChange={(e) => setParamEmaSlow(Number(e.target.value))}
                  className="w-14 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-center text-zinc-200"
                />
              </div>
              <label className="flex items-center space-x-2 cursor-pointer text-zinc-300">
                <input
                  type="checkbox"
                  checked={isMutation}
                  onChange={(e) => setIsMutation(e.target.checked)}
                  className="rounded bg-zinc-800 border-zinc-700 text-cyan-600 focus:ring-0"
                />
                <span>Mutate Genome</span>
              </label>
              {isMutation && (
                <input
                  type="text"
                  placeholder="Parent Genome ID"
                  value={parentGenomeId}
                  onChange={(e) => setParentGenomeId(e.target.value)}
                  className="w-44 bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-zinc-200 text-xs"
                />
              )}
            </div>

            <button
              onClick={handleRunSynthesis}
              disabled={isSynthesizing}
              className={`px-5 py-2 rounded-lg font-bold text-xs tracking-wider flex items-center space-x-2 shadow-lg transition-all ${
                isSynthesizing
                  ? 'bg-zinc-800 text-zinc-500 border border-zinc-700 cursor-not-allowed'
                  : 'bg-cyan-600 hover:bg-cyan-500 text-white shadow-cyan-900/30'
              }`}
            >
              {isSynthesizing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>SYNTHESIZING & AUDITING...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  <span>EXECUTE RESEARCH CYCLE</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Experiment History Quick-Picker */}
        <div className="p-4 rounded-xl bg-zinc-900/70 border border-zinc-800 space-y-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-300 mb-2">
              <span className="flex items-center space-x-1.5">
                <Clock className="w-3.5 h-3.5 text-zinc-400" />
                <span>Recent Research Trials</span>
              </span>
              <span className="text-zinc-500 font-mono">{pastJobs.length} trials</span>
            </div>
            <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
              {pastJobs.map((j) => (
                <button
                  key={j.job_id}
                  onClick={() => handleSelectJob(j.job_id)}
                  className={`w-full text-left p-1.5 rounded text-xs font-mono flex items-center justify-between transition-colors ${
                    currentJob?.job_id === j.job_id
                      ? 'bg-cyan-950/80 border border-cyan-700 text-cyan-300'
                      : 'bg-zinc-800/40 hover:bg-zinc-800 text-zinc-400'
                  }`}
                >
                  <span className="truncate w-24 font-bold">{j.strategy_id}</span>
                  <span
                    className={`text-[10px] px-1 rounded ${
                      j.research_dossier.classification === 'ROBUST'
                        ? 'text-emerald-400 bg-emerald-950/60'
                        : j.research_dossier.classification === 'OVERFIT'
                        ? 'text-rose-400 bg-rose-950/60'
                        : 'text-amber-400 bg-amber-950/60'
                    }`}
                  >
                    {j.research_dossier.classification}
                  </span>
                </button>
              ))}
              {pastJobs.length === 0 && (
                <div className="text-xs text-zinc-500 italic py-2 text-center">No trials executed yet</div>
              )}
            </div>
          </div>
          <div className="text-[10px] text-zinc-500 font-mono border-t border-zinc-800/60 pt-2">
            M18 Execution Firewall: Active. Live routing prohibited.
          </div>
        </div>
      </div>

      {/* 3. Research Stepper & Verdict Display */}
      {currentJob && dossier && (
        <div className="space-y-3">
          {/* Scientific Verdict Banner */}
          <div
            className={`p-4 rounded-xl border flex flex-wrap items-center justify-between gap-4 backdrop-blur-sm ${classificationMeta.bg}`}
          >
            <div className="flex items-center space-x-3">
              {classificationMeta.icon}
              <div>
                <div className="flex items-center space-x-2">
                  <span className="text-sm font-bold tracking-wider">{classificationMeta.label}</span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-black/40 border border-white/10">
                    ID: {currentJob.strategy_id}
                  </span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-black/40 border border-white/10">
                    Trial #{currentJob.trial_number} (N={currentJob.cumulative_trials})
                  </span>
                </div>
                <div className="text-xs font-mono mt-1 opacity-90">
                  {dossier.quarantine_eligible
                    ? 'ADMITTED TO TIER 1 SMOKE QUARANTINE (Isolated Forward Paper Testing)'
                    : `REJECTED: ${dossier.rejection_reasons.join(' • ') || 'Did not meet institutional clearance criteria'}`}
                </div>
              </div>
            </div>

            {/* Epistemic Badges */}
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
              {dossier.epistemic_tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 rounded bg-black/40 border border-white/10 text-zinc-300 font-semibold"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>

          {/* Stepper Pipeline Indicators */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 text-xs font-mono">
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">1. COMPILATION</span>
              <span className="font-bold text-emerald-400 mt-1 flex items-center space-x-1">
                <CheckCircle className="w-3.5 h-3.5" />
                <span>GENOME READY</span>
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">2. CPCV PURGING</span>
              <span className="font-bold text-cyan-400 mt-1">
                {dossier.cpcv_result.num_paths} Paths • {dossier.cpcv_result.embargo_bars}b Embargo
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">3. 3-TIER FRICTION</span>
              <span className="font-bold text-zinc-300 mt-1">
                SR: {dossier.cpcv_result.friction_results['BASE']?.sharpe || 0} → {dossier.cpcv_result.friction_results['STRESS']?.sharpe || 0}
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">4. DSR DEFENSE</span>
              <span
                className={`font-bold mt-1 ${
                  dossier.dsr_report.is_tier1_eligible ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                DSR: {dossier.dsr_report.deflated_sharpe_ratio} (≥ 0.95)
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">5. WRC BOOTSTRAP</span>
              <span
                className={`font-bold mt-1 ${
                  dossier.wrc_report.is_significant_at_5pct ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                p-val: {dossier.wrc_report.p_value} (≤ 0.05)
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">6. PLATEAU TEST</span>
              <span
                className={`font-bold mt-1 ${
                  dossier.perturbation_report.is_plateau_robust ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                Plateau: {Math.round(dossier.perturbation_report.plateau_ratio * 100)}% (≥ 70%)
              </span>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 flex flex-col justify-between">
              <span className="text-zinc-500">7. QUARANTINE</span>
              <span
                className={`font-bold mt-1 ${
                  currentJob.tier1_quarantined ? 'text-emerald-400' : 'text-zinc-500'
                }`}
              >
                {currentJob.tier1_quarantined ? 'TIER 1 SMOKE' : 'REJECTED'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 4. Sub-Tab Navigation */}
      <div className="flex items-center space-x-2 border-b border-zinc-800 text-xs font-mono pb-2">
        <button
          onClick={() => setActiveTab('CPCV')}
          className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition-colors ${
            activeTab === 'CPCV'
              ? 'bg-zinc-800 text-cyan-400 border border-zinc-700'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>CPCV Fold Matrix & Frictions</span>
        </button>
        <button
          onClick={() => setActiveTab('STAT_DEFENSE')}
          className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition-colors ${
            activeTab === 'STAT_DEFENSE'
              ? 'bg-zinc-800 text-cyan-400 border border-zinc-700'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Statistical Defense (DSR & WRC)</span>
        </button>
        <button
          onClick={() => setActiveTab('PERTURBATION')}
          className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition-colors ${
            activeTab === 'PERTURBATION'
              ? 'bg-zinc-800 text-cyan-400 border border-zinc-700'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <BarChart2 className="w-3.5 h-3.5" />
          <span>Perturbation Plateau</span>
        </button>
        <button
          onClick={() => setActiveTab('REGIMES')}
          className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition-colors ${
            activeTab === 'REGIMES'
              ? 'bg-zinc-800 text-cyan-400 border border-zinc-700'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <TrendingUp className="w-3.5 h-3.5" />
          <span>Macro Regime Robustness</span>
        </button>
        <button
          onClick={() => setActiveTab('LINEAGE')}
          className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition-colors ${
            activeTab === 'LINEAGE'
              ? 'bg-zinc-800 text-cyan-400 border border-zinc-700'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <GitBranch className="w-3.5 h-3.5" />
          <span>Genome Lineage DAG ({lineageNodes.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('TEARSHEET')}
          className={`px-3 py-1.5 rounded-lg flex items-center space-x-1.5 transition-colors ${
            activeTab === 'TEARSHEET'
              ? 'bg-zinc-800 text-cyan-400 border border-zinc-700'
              : 'text-zinc-400 hover:text-zinc-200'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Tear Sheet & Telegram Bulletin</span>
        </button>
      </div>

      {/* 5. Sub-Tab Panes */}
      <div className="flex-1 min-h-[360px]">
        {/* Tab 1: CPCV & 3-Tier Frictions */}
        {activeTab === 'CPCV' && dossier && (
          <div className="space-y-4">
            {/* 3-Tier Friction Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
              {['BASE', 'CONSERVATIVE', 'STRESS'].map((tier) => {
                const metrics = dossier.cpcv_result.friction_results[tier];
                return (
                  <div
                    key={tier}
                    className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-2"
                  >
                    <div className="flex items-center justify-between text-zinc-300 font-bold">
                      <span>{tier} SCHEDULE</span>
                      <span className="text-cyan-400">{metrics?.total_friction_bps || 0} bps total</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-zinc-400 pt-1">
                      <div>
                        Sharpe:{' '}
                        <span className="text-zinc-200 font-bold">{metrics?.sharpe?.toFixed(2) || '0.00'}</span>
                      </div>
                      <div>
                        Win Rate:{' '}
                        <span className="text-zinc-200 font-bold">
                          {metrics?.win_rate_pct?.toFixed(1) || '0.0'}%
                        </span>
                      </div>
                      <div>
                        Max DD:{' '}
                        <span className="text-rose-400 font-bold">
                          {metrics?.max_drawdown_pct?.toFixed(1) || '0.0'}%
                        </span>
                      </div>
                      <div>
                        Net Return:{' '}
                        <span
                          className={`font-bold ${
                            (metrics?.net_return_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {metrics?.net_return_pct?.toFixed(1) || '0.0'}%
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Combinatorial Purged Folds Table */}
            <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-zinc-300 font-bold">
                  COMBINATORIAL PURGED CROSS-VALIDATION FOLD MATRIX (C({dossier.cpcv_result.n_partitions},{dossier.cpcv_result.k_test_groups}) = {dossier.cpcv_result.num_paths} Paths)
                </span>
                <span className="text-cyan-400">
                  Dynamic Embargo: h = {dossier.cpcv_result.embargo_bars} bars (derived from autocorrelation cutoff q)
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono text-zinc-300">
                  <thead>
                    <tr className="border-b border-zinc-800 text-zinc-500">
                      <th className="py-2">Fold ID</th>
                      <th className="py-2">Train Size</th>
                      <th className="py-2">Test Size</th>
                      <th className="py-2">Purged Bars</th>
                      <th className="py-2">Embargo Bars</th>
                      <th className="py-2">IS Sharpe</th>
                      <th className="py-2">OOS Sharpe</th>
                      <th className="py-2">OOS Win Rate</th>
                      <th className="py-2">OOS Trades</th>
                      <th className="py-2">Stability Ratio</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {dossier.cpcv_result.folds.map((f) => (
                      <tr key={f.fold_id} className="hover:bg-zinc-800/40">
                        <td className="py-2 font-bold text-zinc-400">Fold #{f.fold_id}</td>
                        <td className="py-2 text-zinc-400">{f.train_size}</td>
                        <td className="py-2 text-zinc-400">{f.test_size}</td>
                        <td className="py-2 text-amber-400">{f.purged_count}</td>
                        <td className="py-2 text-cyan-400">{f.embargo_count}</td>
                        <td className="py-2">{f.is_sharpe.toFixed(2)}</td>
                        <td
                          className={`py-2 font-bold ${
                            f.oos_sharpe >= 1.0 ? 'text-emerald-400' : 'text-zinc-300'
                          }`}
                        >
                          {f.oos_sharpe.toFixed(2)}
                        </td>
                        <td className="py-2">{(f.oos_win_rate * 100).toFixed(1)}%</td>
                        <td className="py-2 text-zinc-400">{f.oos_trade_count}</td>
                        <td className="py-2 text-zinc-400">{f.stability_ratio.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Statistical Defense (DSR & WRC) */}
        {activeTab === 'STAT_DEFENSE' && dossier && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Deflated Sharpe Ratio Card */}
            <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between text-zinc-200 font-bold border-b border-zinc-800 pb-2">
                <span className="flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-cyan-400" />
                  <span>DEFLATED SHARPE RATIO (DSR)</span>
                </span>
                <span
                  className={`px-2 py-0.5 rounded ${
                    dossier.dsr_report.is_tier1_eligible
                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                      : 'bg-rose-950 text-rose-400 border border-rose-800'
                  }`}
                >
                  {dossier.dsr_report.is_tier1_eligible ? 'PASS (≥ 0.95)' : 'FAIL (< 0.95)'}
                </span>
              </div>

              <div className="space-y-2 text-zinc-400">
                <div className="flex justify-between">
                  <span>Observed Annualized Sharpe:</span>
                  <span className="font-bold text-zinc-200">{dossier.dsr_report.observed_sharpe}</span>
                </div>
                <div className="flex justify-between">
                  <span>Expected Max Null Sharpe (E[max_N SR]):</span>
                  <span className="font-bold text-amber-400">{dossier.dsr_report.expected_max_null_sharpe}</span>
                </div>
                <div className="flex justify-between">
                  <span>Cumulative Trials Penalty (N):</span>
                  <span className="font-bold text-zinc-200">{dossier.dsr_report.cumulative_trials} trials</span>
                </div>
                <div className="flex justify-between">
                  <span>Mertens Skewness / Kurtosis:</span>
                  <span className="font-bold text-zinc-300">
                    {dossier.dsr_report.skewness} / {dossier.dsr_report.kurtosis}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Sharpe Standard Error (sigma_SR):</span>
                  <span className="font-bold text-zinc-300">{dossier.dsr_report.sr_standard_error}</span>
                </div>
                <div className="flex justify-between">
                  <span>Z-Score:</span>
                  <span className="font-bold text-cyan-400">{dossier.dsr_report.z_score}</span>
                </div>
                <div className="flex justify-between border-t border-zinc-800 pt-2 text-sm">
                  <span className="text-zinc-200 font-bold">Deflated Sharpe Ratio (DSR):</span>
                  <span
                    className={`font-bold ${
                      dossier.dsr_report.is_tier1_eligible ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {dossier.dsr_report.deflated_sharpe_ratio}
                  </span>
                </div>
              </div>
            </div>

            {/* White's Reality Check (WRC) Card */}
            <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between text-zinc-200 font-bold border-b border-zinc-800 pb-2">
                <span className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  <span>WHITE'S REALITY CHECK (WRC)</span>
                </span>
                <span
                  className={`px-2 py-0.5 rounded ${
                    dossier.wrc_report.is_significant_at_5pct
                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                      : 'bg-amber-950 text-amber-400 border border-amber-800'
                  }`}
                >
                  {dossier.wrc_report.is_significant_at_5pct ? 'PASS (p ≤ 0.05)' : 'BORDERLINE / FAIL'}
                </span>
              </div>

              <div className="space-y-2 text-zinc-400">
                <div className="flex justify-between">
                  <span>Bootstrap Replications (B):</span>
                  <span className="font-bold text-zinc-200">{dossier.wrc_report.bootstrap_replications}</span>
                </div>
                <div className="flex justify-between">
                  <span>Stationary Block Length (L):</span>
                  <span className="font-bold text-zinc-200">
                    {dossier.wrc_report.mean_block_length} bars (Politis-Romano)
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Observed Mean Return:</span>
                  <span className="font-bold text-zinc-200">{dossier.wrc_report.observed_mean_return}</span>
                </div>
                <div className="flex justify-between">
                  <span>Bootstrap Max Null Return:</span>
                  <span className="font-bold text-amber-400">{dossier.wrc_report.bootstrap_null_max}</span>
                </div>
                <div className="flex justify-between border-t border-zinc-800 pt-2 text-sm">
                  <span className="text-zinc-200 font-bold">WRC p-value:</span>
                  <span
                    className={`font-bold ${
                      dossier.wrc_report.is_significant_at_5pct ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {dossier.wrc_report.p_value}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Perturbation Plateau */}
        {activeTab === 'PERTURBATION' && dossier && (
          <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-4 font-mono text-xs">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-zinc-200 font-bold text-sm">
                  PARAMETER NEIGHBORHOOD PERTURBATION TEST (Plateau vs. Razor-Thin Needle Overfit)
                </span>
                <p className="text-zinc-400 text-xs mt-0.5">
                  Evaluates ±15% shifts around optimal parameters. True robust edges form broad plateaus.
                </p>
              </div>
              <div
                className={`px-3 py-1 rounded text-sm font-bold border ${
                  dossier.perturbation_report.is_plateau_robust
                    ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                    : 'bg-rose-950 text-rose-400 border-rose-800'
                }`}
              >
                Plateau Survival: {Math.round(dossier.perturbation_report.plateau_ratio * 100)}% (
                {dossier.perturbation_report.surviving_neighbors} / {dossier.perturbation_report.total_neighbors})
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {dossier.perturbation_report.grid_points.map((pt, idx) => (
                <div
                  key={idx}
                  className={`p-2.5 rounded-lg border ${
                    pt.is_surviving
                      ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                      : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
                  }`}
                >
                  <div className="flex items-center justify-between text-[11px] font-bold">
                    <span>Neighbor #{idx + 1}</span>
                    <span>{pt.is_surviving ? 'SURVIVED' : 'DROPPED'}</span>
                  </div>
                  <div className="text-sm font-bold mt-1">SR: {pt.perturbed_sharpe.toFixed(2)}</div>
                  <div className="text-[10px] text-zinc-400 mt-1 truncate">
                    {Object.entries(pt.parameter_deltas)
                      .map(([k, v]) => `${k}:${(v * 100).toFixed(0)}%`)
                      .join(' ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 4: Macro Regime Decomposition */}
        {activeTab === 'REGIMES' && dossier && (
          <div className="space-y-4 font-mono text-xs">
            <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-between">
              <div>
                <span className="text-zinc-200 font-bold text-sm">
                  MACRO REGIME ROBUSTNESS DECOMPOSITION (5 Distinct Market Environments)
                </span>
                <p className="text-zinc-400 text-xs mt-0.5">
                  Ensures strategy does not suffer catastrophic drawdowns during crisis or compression regimes.
                </p>
              </div>
              <div className="text-cyan-400 font-bold">
                Profitable Regimes: {dossier.regime_report.profitable_regimes_count} / 5
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              {Object.entries(dossier.regime_report.regimes).map(([rName, perf]) => (
                <div
                  key={rName}
                  className={`p-3.5 rounded-xl border space-y-2 ${
                    perf.is_catastrophic_loss
                      ? 'bg-rose-950/50 border-rose-700 text-rose-300'
                      : perf.sharpe > 0.5
                      ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                      : 'bg-zinc-900 border-zinc-800 text-zinc-300'
                  }`}
                >
                  <div className="font-bold text-[11px] truncate">{rName}</div>
                  <div className="text-zinc-400 text-[10px]">Sample: {perf.sample_bars_count} bars</div>
                  <div className="text-sm font-bold">Sharpe: {perf.sharpe.toFixed(2)}</div>
                  <div className="text-[11px]">Return: {perf.net_return_pct.toFixed(1)}%</div>
                  <div className="text-[11px] text-rose-400">Max DD: {perf.max_drawdown_pct.toFixed(1)}%</div>
                  {perf.is_catastrophic_loss && (
                    <div className="text-[10px] bg-rose-900/60 text-rose-200 px-1.5 py-0.5 rounded font-bold">
                      CATASTROPHIC RISK
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 5: Genome Lineage DAG */}
        {activeTab === 'LINEAGE' && (
          <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between text-zinc-300 font-bold">
              <span>STRATEGY GENOME EVOLUTIONARY LINEAGE GRAPH (SQLite experiment_store.db)</span>
              <span className="text-cyan-400">{lineageNodes.length} nodes tracked</span>
            </div>

            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-left text-zinc-300">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500">
                    <th className="py-2">Gen</th>
                    <th className="py-2">Strategy ID</th>
                    <th className="py-2">Parent ID</th>
                    <th className="py-2">Mutation</th>
                    <th className="py-2">Classification</th>
                    <th className="py-2">DSR</th>
                    <th className="py-2">OOS Sharpe</th>
                    <th className="py-2">Plateau</th>
                    <th className="py-2">Tier</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {lineageNodes.map((n) => (
                    <tr key={n.node_id} className="hover:bg-zinc-800/40">
                      <td className="py-2 text-zinc-500 font-bold">G{n.generation}</td>
                      <td className="py-2 font-bold text-cyan-400">{n.strategy_id}</td>
                      <td className="py-2 text-zinc-500">{n.parent_id || 'ORIGIN'}</td>
                      <td className="py-2 text-zinc-400">{n.mutation_type}</td>
                      <td className="py-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
                            n.research_classification === 'ROBUST'
                              ? 'text-emerald-400 bg-emerald-950/60'
                              : 'text-zinc-400 bg-zinc-800'
                          }`}
                        >
                          {n.research_classification}
                        </span>
                      </td>
                      <td className="py-2">{n.deflated_sharpe_ratio.toFixed(2)}</td>
                      <td className="py-2 font-bold">{n.oos_sharpe.toFixed(2)}</td>
                      <td className="py-2">{(n.plateau_survival_ratio * 100).toFixed(0)}%</td>
                      <td className="py-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            n.quarantine_tier === 1
                              ? 'bg-cyan-950 text-cyan-400 border border-cyan-800'
                              : 'bg-zinc-800 text-zinc-500'
                          }`}
                        >
                          {n.quarantine_tier === 1 ? 'TIER 1' : 'NONE'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {lineageNodes.length === 0 && (
                    <tr>
                      <td colSpan={9} className="text-center py-6 text-zinc-500 italic">
                        No lineage records registered yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 6: Tear Sheet & Telegram Preview */}
        {activeTab === 'TEARSHEET' && currentJob && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 font-mono text-xs">
            {/* Markdown Tear Sheet */}
            <div className="lg:col-span-2 p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <span className="text-zinc-200 font-bold flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-cyan-400" />
                  <span>INSTITUTIONAL TEAR SHEET (Markdown)</span>
                </span>
                <button
                  onClick={handleCopyTearSheet}
                  className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 flex items-center space-x-1.5 transition-colors"
                >
                  {copiedTearSheet ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <FileText className="w-3.5 h-3.5" />}
                  <span>{copiedTearSheet ? 'Copied' : 'Copy Tear Sheet'}</span>
                </button>
              </div>
              <pre className="p-3 bg-zinc-950 rounded-lg text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-96 text-[11px] leading-relaxed">
                {currentJob.tear_sheet_markdown}
              </pre>
            </div>

            {/* Telegram Live Desk Bulletin */}
            <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 space-y-3">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <span className="text-zinc-200 font-bold flex items-center space-x-2">
                  <Send className="w-4 h-4 text-cyan-400" />
                  <span>TELEGRAM BULLETIN (Informational Only)</span>
                </span>
              </div>
              <div className="p-3 bg-cyan-950/30 border border-cyan-900/60 rounded-lg text-cyan-200 whitespace-pre-wrap text-[11px] leading-relaxed">
                {currentJob.telegram_bulletin}
              </div>
              <div className="text-[10px] text-zinc-500 italic">
                Notice: Telegram broadcasts represent non-actionable research telemetry. All executions remain governed by Milestone 18 risk gates.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AutonomousStrategistDesk;
