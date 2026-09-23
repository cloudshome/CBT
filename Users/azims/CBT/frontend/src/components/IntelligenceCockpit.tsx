import React, { useState, useEffect, useCallback } from 'react';
import {
  IntelligenceStatusResponse,
  IntelligenceRecordsResponse,
  NarrativesResponse,
  CausalHypothesis,
  HypothesisStatsResponse,
  FamiliesResponse,
  CausalFirewallDecision,
  PreregisteredResearchContract,
  ReplayResponse,
  CausalFailureAutopsy,
  DurableExperimentPlan,
} from '../types';
import {
  getIntelligenceStatus,
  getIntelligenceRecords,
  getActiveNarratives,
  startScoutDaemon,
  stopScoutDaemon,
  pauseScoutDaemon,
  resumeScoutDaemon,
  triggerScoutStep,
  ingestIntelligenceUrl,
  getHypotheses,
  synthesizeHypotheses,
  getResearchFamilies,
  getHypothesisStats,
  validateHypothesis,
  dispatchHypothesis,
  createResearchContract,
  getExperimentPlans,
  runCausalReplay,
} from '../services/api';

export const IntelligenceCockpit: React.FC = () => {
  // Subview toggle: FEED vs HYPOTHESIS_LAB vs REPLAY_LAB
  const [activeTab, setActiveTab] = useState<'FEED' | 'HYPOTHESIS_LAB' | 'REPLAY_LAB'>('FEED');

  // Milestone 27 Feed State
  const [statusData, setStatusData] = useState<IntelligenceStatusResponse | null>(null);
  const [recordsData, setRecordsData] = useState<IntelligenceRecordsResponse | null>(null);
  const [narrativesData, setNarrativesData] = useState<NarrativesResponse | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<string>('ALL');
  const [selectedGrade, setSelectedGrade] = useState<string>('ALL');
  const [selectedEntity, setSelectedEntity] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [actionInProgress, setActionInProgress] = useState<boolean>(false);
  const [ingestUrl, setIngestUrl] = useState<string>('');
  const [ingestPlatform, setIngestPlatform] = useState<string>('WEB');
  const [ingestFeedback, setIngestFeedback] = useState<string | null>(null);

  // Milestone 28 Causal Hypothesis Lab State
  const [hypotheses, setHypotheses] = useState<CausalHypothesis[]>([]);
  const [hypoTotal, setHypoTotal] = useState<number>(0);
  const [statsData, setStatsData] = useState<HypothesisStatsResponse | null>(null);
  const [familiesData, setFamiliesData] = useState<FamiliesResponse | null>(null);
  const [selectedFamilyFilter, setSelectedFamilyFilter] = useState<string>('ALL');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>('ALL');
  const [synthesisAsset, setSynthesisAsset] = useState<string>('BTC/USDT');
  const [synthesisTimeframe, setSynthesisTimeframe] = useState<string>('5m');
  const [isSynthesizing, setIsSynthesizing] = useState<boolean>(false);
  const [labFeedback, setLabFeedback] = useState<string | null>(null);

  // Firewall Audit Modal State
  const [selectedAuditDecision, setSelectedAuditDecision] = useState<CausalFirewallDecision | null>(null);
  const [selectedHypothesisForAudit, setSelectedHypothesisForAudit] = useState<CausalHypothesis | null>(null);
  const [isValidating, setIsValidating] = useState<boolean>(false);

  // Milestone 29 Replay & Falsification State
  const [plans, setPlans] = useState<DurableExperimentPlan[]>([]);
  const [activeContracts, setActiveContracts] = useState<PreregisteredResearchContract[]>([]);
  const [selectedContract, setSelectedContract] = useState<PreregisteredResearchContract | null>(null);
  const [replayReport, setReplayReport] = useState<ReplayResponse | null>(null);
  const [isReplaying, setIsReplaying] = useState<boolean>(false);
  const [selectedAutopsy, setSelectedAutopsy] = useState<CausalFailureAutopsy | null>(null);
  const [replayFeedback, setReplayFeedback] = useState<string | null>(null);
  const [selectedFrictionTier, setSelectedFrictionTier] = useState<string>('CONSERVATIVE');

  // =========================================================================
  // Telemetry Fetchers
  // =========================================================================

  const fetchFeedTelemetry = useCallback(async () => {
    try {
      const [sRes, rRes, nRes] = await Promise.all([
        getIntelligenceStatus(),
        getIntelligenceRecords({
          domain: selectedDomain === 'ALL' ? undefined : selectedDomain,
          evidence_grade: selectedGrade === 'ALL' ? undefined : selectedGrade,
          entity: selectedEntity ? selectedEntity : undefined,
          limit: 40,
        }),
        getActiveNarratives({ lookback_hours: 48, limit: 10 }),
      ]);
      setStatusData(sRes);
      setRecordsData(rRes);
      setNarrativesData(nRes);
    } catch (err) {
      console.error('Failed to refresh intelligence telemetry:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedDomain, selectedGrade, selectedEntity]);

  const fetchLabData = useCallback(async () => {
    try {
      const [hRes, sRes, fRes, pRes] = await Promise.all([
        getHypotheses({
          family_id: selectedFamilyFilter === 'ALL' ? undefined : selectedFamilyFilter,
          status: selectedStatusFilter === 'ALL' ? undefined : selectedStatusFilter,
          limit: 50,
        }),
        getHypothesisStats(),
        getResearchFamilies(),
        getExperimentPlans({ limit: 50 }),
      ]);
      setHypotheses(hRes.hypotheses || []);
      setHypoTotal(hRes.total || 0);
      setStatsData(sRes);
      setFamiliesData(fRes);
      setPlans(pRes.plans || []);
    } catch (err) {
      console.error('Failed to refresh Causal Lab telemetry:', err);
    }
  }, [selectedFamilyFilter, selectedStatusFilter]);

  const handleCreateContract = async (hypoId: string) => {
    setActionInProgress(true);
    setLabFeedback('Preregistering immutable research contract...');
    try {
      const res = await createResearchContract(hypoId, 12, 1);
      setActiveContracts((prev) => [res.contract, ...prev.filter((c) => c.contract_id !== res.contract.contract_id)]);
      setSelectedContract(res.contract);
      setLabFeedback(`Contract ${res.contract.contract_id} preregistered with ${res.contract.lookback_days}d lookback.`);
      setActiveTab('REPLAY_LAB');
    } catch (err: any) {
      setLabFeedback(`Preregistration failed: ${err.message || err}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleRunReplay = async (contractId: string) => {
    setIsReplaying(true);
    setReplayFeedback('Executing deterministic historical replay across market candles...');
    try {
      const res = await runCausalReplay(contractId, 10000, 200, selectedFrictionTier);
      setReplayReport(res);
      if (res.autopsy) {
        setSelectedAutopsy(res.autopsy);
      }
      setReplayFeedback(`Replay complete. Result: ${res.validation_result.status} (Net E[R]: ${res.validation_result.primary_endpoint_value >= 0 ? '+' : ''}${res.validation_result.primary_endpoint_value.toFixed(2)}R)`);
      fetchLabData();
    } catch (err: any) {
      setReplayFeedback(`Replay failed: ${err.message || err}`);
    } finally {
      setIsReplaying(false);
    }
  };

  useEffect(() => {
    fetchFeedTelemetry();
    fetchLabData();
    const interval = setInterval(() => {
      if (activeTab === 'FEED') {
        fetchFeedTelemetry();
      } else {
        fetchLabData();
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [activeTab, fetchFeedTelemetry, fetchLabData]);

  // =========================================================================
  // Feed Actions
  // =========================================================================

  const handleStartScout = async () => {
    setActionInProgress(true);
    try {
      await startScoutDaemon();
      await fetchFeedTelemetry();
    } finally {
      setActionInProgress(false);
    }
  };

  const handleStopScout = async () => {
    setActionInProgress(true);
    try {
      await stopScoutDaemon();
      await fetchFeedTelemetry();
    } finally {
      setActionInProgress(false);
    }
  };

  const handlePauseResume = async () => {
    if (!statusData?.scout) return;
    setActionInProgress(true);
    try {
      if (statusData.scout.state === 'RUNNING') {
        await pauseScoutDaemon();
      } else {
        await resumeScoutDaemon();
      }
      await fetchFeedTelemetry();
    } finally {
      setActionInProgress(false);
    }
  };

  const handleTriggerStep = async () => {
    setActionInProgress(true);
    try {
      await triggerScoutStep();
      await fetchFeedTelemetry();
    } finally {
      setActionInProgress(false);
    }
  };

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ingestUrl.trim()) return;
    setActionInProgress(true);
    setIngestFeedback(null);
    try {
      const res = await ingestIntelligenceUrl(ingestUrl.trim(), ingestPlatform, true);
      setIngestFeedback(`Ingestion success: ${res.status || 'OK'}`);
      setIngestUrl('');
      await fetchFeedTelemetry();
    } catch (err: any) {
      setIngestFeedback(`Ingestion failed: ${err.message || 'Error'}`);
    } finally {
      setActionInProgress(false);
    }
  };

  // =========================================================================
  // Milestone 28 Causal Lab Actions
  // =========================================================================

  const handleTriggerSynthesis = async () => {
    setIsSynthesizing(true);
    setLabFeedback(null);
    try {
      const res = await synthesizeHypotheses({
        target_asset: synthesisAsset,
        timeframe: synthesisTimeframe,
        auto_validate: true,
      });
      setLabFeedback(`Successfully compiled ${res.count} testable causal hypotheses.`);
      await fetchLabData();
    } catch (err: any) {
      setLabFeedback(`Synthesis failed: ${err.message || 'Error'}`);
    } finally {
      setIsSynthesizing(false);
    }
  };

  const handleAuditHypothesis = async (hypo: CausalHypothesis) => {
    setSelectedHypothesisForAudit(hypo);
    setIsValidating(true);
    try {
      const res = await validateHypothesis(hypo.hypothesis_id);
      setSelectedAuditDecision(res.decision);
      await fetchLabData();
    } catch (err: any) {
      alert(`Firewall audit error: ${err.message || 'Error'}`);
    } finally {
      setIsValidating(false);
    }
  };

  const handleDispatchLab = async (hypoId: string) => {
    try {
      const res = await dispatchHypothesis(hypoId, 'CONSERVATIVE');
      alert(`Dispatched to Research Lab successfully! Plan ID: ${res.plan?.plan_id}`);
      await fetchLabData();
    } catch (err: any) {
      alert(`Dispatch error: ${err.message || 'Error'}`);
    }
  };

  const scoutState = statusData?.scout?.state || 'STOPPED';

  const gradeBadge = (grade: string) => {
    switch (grade) {
      case 'VERIFIED_PRIMARY':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-950 text-emerald-300 border border-emerald-700/60">
            [PRIMARY] Official
          </span>
        );
      case 'CORROBORATED_REPORT':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-blue-950 text-blue-300 border border-blue-700/60">
            [REPORT] Wire
          </span>
        );
      case 'UNVERIFIED_CLAIM':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-amber-950 text-amber-300 border border-amber-700/60">
            [CLAIM] Blog
          </span>
        );
      case 'SPECULATION':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-purple-950 text-purple-300 border border-purple-700/60">
            [SPECULATION] Social
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-800 text-slate-300">
            {grade}
          </span>
        );
    }
  };

  const hypothesisStatusBadge = (status: string) => {
    switch (status) {
      case 'FIREWALL_VALIDATED':
        return (
          <span className="px-2 py-0.5 text-xs font-bold font-mono rounded bg-emerald-950 text-emerald-300 border border-emerald-600/70">
            ✓ FIREWALL PASS
          </span>
        );
      case 'REJECTED':
        return (
          <span className="px-2 py-0.5 text-xs font-bold font-mono rounded bg-rose-950 text-rose-300 border border-rose-700/70">
            ✕ REJECTED
          </span>
        );
      case 'QUEUED_FOR_LAB':
        return (
          <span className="px-2 py-0.5 text-xs font-bold font-mono rounded bg-indigo-950 text-indigo-300 border border-indigo-600/70">
            ➔ QUEUED FOR LAB
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 text-xs font-bold font-mono rounded bg-slate-800 text-slate-300 border border-slate-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 bg-slate-950 min-h-screen text-slate-100 font-sans">
      {/* Top Cockpit Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-cyan-400">🌐</span> SKY Global Intelligence & Causal Research Lab
            </h1>
            <span className="px-2.5 py-0.5 text-[11px] font-mono font-semibold rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800/80">
              M27–M28 SYNTHESIS
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Autonomous multi-domain intelligence ingestion, thematic clustering, and point-in-time causal hypothesis compilation.
          </p>
        </div>

        {/* Subview Selector Tabs */}
        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('FEED')}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition ${
              activeTab === 'FEED'
                ? 'bg-cyan-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            📡 Global Live Feed & Scout
          </button>
          <button
            onClick={() => setActiveTab('HYPOTHESIS_LAB')}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ${
              activeTab === 'HYPOTHESIS_LAB'
                ? 'bg-purple-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span>🧪 Causal Hypothesis Lab</span>
            <span className="px-1.5 py-0.2 text-[10px] font-mono bg-purple-950 text-purple-300 rounded border border-purple-700/60">
              {hypoTotal}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('REPLAY_LAB')}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ${
              activeTab === 'REPLAY_LAB'
                ? 'bg-amber-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <span>🔬 Replay & Falsification</span>
            <span className="px-1.5 py-0.2 text-[10px] font-mono bg-amber-950 text-amber-300 rounded border border-amber-700/60">
              M29
            </span>
          </button>
        </div>
      </div>

      {/* =====================================================================
          VIEW 1: GLOBAL LIVE FEED & SCOUT (M27)
          ===================================================================== */}
      {activeTab === 'FEED' && (
        <>
          {/* Scout Controls & Telemetry */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-900/80 border border-slate-800 rounded-xl">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Autonomous Scout Daemon:
              </span>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    scoutState === 'RUNNING'
                      ? 'bg-emerald-400 animate-pulse'
                      : scoutState === 'PAUSED'
                      ? 'bg-amber-400'
                      : 'bg-rose-500'
                  }`}
                />
                <span className="text-xs font-mono font-bold text-slate-200">{scoutState}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {scoutState === 'RUNNING' ? (
                <>
                  <button
                    onClick={handlePauseResume}
                    disabled={actionInProgress}
                    className="px-3 py-1.5 text-xs font-medium bg-amber-600/30 hover:bg-amber-600/50 text-amber-200 border border-amber-500/60 rounded-lg transition"
                  >
                    Pause
                  </button>
                  <button
                    onClick={handleStopScout}
                    disabled={actionInProgress}
                    className="px-3 py-1.5 text-xs font-medium bg-rose-900/40 hover:bg-rose-900/60 text-rose-200 border border-rose-700/60 rounded-lg transition"
                  >
                    Stop Scout
                  </button>
                </>
              ) : scoutState === 'PAUSED' ? (
                <>
                  <button
                    onClick={handlePauseResume}
                    disabled={actionInProgress}
                    className="px-3 py-1.5 text-xs font-medium bg-emerald-600/30 hover:bg-emerald-600/50 text-emerald-200 border border-emerald-500/60 rounded-lg transition"
                  >
                    Resume
                  </button>
                  <button
                    onClick={handleStopScout}
                    disabled={actionInProgress}
                    className="px-3 py-1.5 text-xs font-medium bg-rose-900/40 hover:bg-rose-900/60 text-rose-200 border border-rose-700/60 rounded-lg transition"
                  >
                    Stop
                  </button>
                </>
              ) : (
                <button
                  onClick={handleStartScout}
                  disabled={actionInProgress}
                  className="px-3 py-1.5 text-xs font-medium bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-200 border border-cyan-500/60 rounded-lg transition"
                >
                  Start 24/7 Scout
                </button>
              )}

              <button
                onClick={handleTriggerStep}
                disabled={actionInProgress}
                className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition"
              >
                Step Once
              </button>
              <button
                onClick={fetchFeedTelemetry}
                disabled={loading}
                className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition"
              >
                Refresh
              </button>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="text-xs font-medium text-slate-400">Total Records Stored</div>
              <div className="text-2xl font-bold font-mono text-cyan-400 mt-1">
                {statusData?.total_records ?? 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">SQLite WAL table</div>
            </div>

            <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="text-xs font-medium text-slate-400">Frontier Size</div>
              <div className="text-2xl font-bold font-mono text-indigo-400 mt-1">
                {statusData?.scout?.frontier_size ?? 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Pending prioritized seeds</div>
            </div>

            <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="text-xs font-medium text-slate-400">Relevant Passed (≥0.70)</div>
              <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
                {statusData?.scout?.relevant_count ?? 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Noise filter pass rate</div>
            </div>

            <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="text-xs font-medium text-slate-400">Active Narratives</div>
              <div className="text-2xl font-bold font-mono text-purple-400 mt-1">
                {narrativesData?.count ?? 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Cross-platform clusters</div>
            </div>
          </div>

          {/* Main Feed Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Cols: Feed Records */}
            <div className="lg:col-span-2 flex flex-col gap-4">
              <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-900 border border-slate-800 rounded-xl">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400 font-semibold mr-1">Domain:</span>
                  {['ALL', 'MACRO', 'CRYPTO', 'EQUITIES', 'QUANT_RESEARCH'].map((dom) => (
                    <button
                      key={dom}
                      onClick={() => setSelectedDomain(dom)}
                      className={`px-3 py-1 text-xs rounded-lg font-medium transition ${
                        selectedDomain === dom
                          ? 'bg-cyan-600 text-white font-semibold'
                          : 'bg-slate-800/80 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                      }`}
                    >
                      {dom}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400 font-semibold mr-1">Evidence:</span>
                  {['ALL', 'VERIFIED_PRIMARY', 'CORROBORATED_REPORT', 'SPECULATION'].map((grd) => (
                    <button
                      key={grd}
                      onClick={() => setSelectedGrade(grd)}
                      className={`px-2.5 py-1 text-xs rounded-lg font-medium transition ${
                        selectedGrade === grd
                          ? 'bg-indigo-600 text-white font-semibold'
                          : 'bg-slate-800/80 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                      }`}
                    >
                      {grd.replace('_', ' ')}
                    </button>
                  ))}
                  {selectedEntity && (
                    <button
                      onClick={() => setSelectedEntity('')}
                      className="px-2 py-1 text-xs rounded-lg bg-rose-950 text-rose-300 border border-rose-800/80 ml-2"
                    >
                      Clear Entity ({selectedEntity}) ✕
                    </button>
                  )}
                </div>
              </div>

              {recordsData?.records.length === 0 ? (
                <div className="p-8 text-center text-slate-500 bg-slate-900 border border-slate-800 rounded-xl">
                  No records matching filters.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {recordsData?.records.map((rec) => (
                    <div
                      key={rec.record_id}
                      className="p-4 bg-slate-900 border border-slate-800/90 hover:border-slate-700 rounded-xl flex flex-col gap-2.5 transition"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {rec.domain}
                          </span>
                          {gradeBadge(String(rec.evidence_grade))}
                          <span className="text-[11px] font-mono text-slate-400">
                            Relevance: {(rec.relevance_score * 100).toFixed(0)}%
                          </span>
                        </div>
                        <span className="text-[11px] text-slate-500 font-mono">
                          {new Date(rec.published_at_utc * 1000).toLocaleTimeString()}
                        </span>
                      </div>

                      <h3 className="text-sm font-semibold text-slate-100 hover:text-cyan-400 transition">
                        <a href={rec.source_url} target="_blank" rel="noopener noreferrer">
                          {rec.title}
                        </a>
                      </h3>

                      <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                        {rec.summary || rec.content_markdown}
                      </p>

                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        {rec.entities.map((ent) => (
                          <button
                            key={ent}
                            onClick={() => setSelectedEntity(ent)}
                            className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-800 text-cyan-300 hover:bg-slate-700 transition"
                          >
                            ${ent}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right Column: Ingest & Narrative Radar */}
            <div className="flex flex-col gap-6">
              {/* Ingest Box */}
              <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-4 shadow-lg">
                <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">
                  Targeted Ingest Receptor
                </h3>
                <form onSubmit={handleIngest} className="flex flex-col gap-3">
                  <input
                    type="url"
                    placeholder="https://... (RSS, Blog, Document)"
                    value={ingestUrl}
                    onChange={(e) => setIngestUrl(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-200 focus:outline-none focus:border-cyan-500"
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={ingestPlatform}
                      onChange={(e) => setIngestPlatform(e.target.value)}
                      className="px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-300"
                    >
                      <option value="WEB">Web URL</option>
                      <option value="RSS">RSS Feed</option>
                      <option value="GITHUB">GitHub</option>
                    </select>
                    <button
                      type="submit"
                      disabled={actionInProgress || !ingestUrl.trim()}
                      className="flex-1 py-1.5 text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition"
                    >
                      Fetch & Classify
                    </button>
                  </div>
                  {ingestFeedback && (
                    <div className="p-2 text-xs font-mono rounded bg-slate-950 border border-slate-800 text-slate-300">
                      {ingestFeedback}
                    </div>
                  )}
                </form>
              </div>

              {/* Narrative Radar */}
              <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-4 shadow-lg">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
                    Thematic Narrative Radar
                  </h3>
                  <span className="text-[11px] text-slate-500">48h velocity</span>
                </div>

                {narrativesData?.narratives.length === 0 ? (
                  <div className="p-4 text-center text-xs text-slate-500">
                    No active narrative clusters detected yet.
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    {narrativesData?.narratives.map((nar) => (
                      <div
                        key={nar.theme}
                        className="p-3.5 bg-slate-950 border border-slate-800 rounded-lg flex flex-col gap-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-semibold font-mono px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800/80">
                            {nar.credibility_tag}
                          </span>
                          <span className="text-xs font-mono font-bold text-purple-300">
                            {nar.velocity_score} / hr
                          </span>
                        </div>
                        <h4 className="text-xs font-semibold text-slate-200">{nar.theme}</h4>
                        <div className="flex flex-wrap items-center gap-1">
                          {nar.entities.map((e) => (
                            <span key={e} className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-900 text-slate-400">
                              ${e}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* =====================================================================
          VIEW 2: CAUSAL HYPOTHESIS LAB (M28)
          ===================================================================== */}
      {activeTab === 'HYPOTHESIS_LAB' && (
        <div className="flex flex-col gap-6">
          {/* Constitutional Watermark Banner */}
          <div className="p-4 bg-purple-950/40 border border-purple-800/80 rounded-xl flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🔒</span>
              <div>
                <h3 className="text-sm font-bold text-purple-200">
                  CONSTITUTIONAL RESEARCH ISOLATION ACTIVE
                </h3>
                <p className="text-xs text-purple-300/80">
                  All hypotheses stamped <code className="bg-purple-900/60 px-1.5 py-0.5 rounded text-purple-100 font-mono">NON_EXECUTABLE_RESEARCH_HYPOTHESIS</code>. Real capital routing is strictly disabled.
                </p>
              </div>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded-full bg-purple-900/80 text-purple-200 border border-purple-700">
              LEVEL 2 RESEARCH PROTOCOL
            </span>
          </div>

          {/* Research Families Summary Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {familiesData?.families.map((fam) => {
              const trialInfo = statsData?.daily_family_trials?.[fam.family_id];
              return (
                <div
                  key={fam.family_id}
                  className="p-3.5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col justify-between gap-2 shadow"
                >
                  <div>
                    <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                      {fam.family_id.replace('FAM_', '')}
                    </div>
                    <div className="text-xs font-bold text-slate-200 mt-0.5 line-clamp-1">
                      {fam.name}
                    </div>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px] font-mono">
                    <span className="text-slate-400">Today:</span>
                    <span className="font-bold text-cyan-300">
                      {trialInfo?.trials_today ?? 0} / {fam.daily_trial_cap}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Synthesis Action & Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-semibold">Asset:</span>
                <select
                  value={synthesisAsset}
                  onChange={(e) => setSynthesisAsset(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                >
                  <option value="BTC/USDT">BTC/USDT</option>
                  <option value="ETH/USDT">ETH/USDT</option>
                  <option value="SOL/USDT">SOL/USDT</option>
                </select>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-semibold">Timeframe:</span>
                <select
                  value={synthesisTimeframe}
                  onChange={(e) => setSynthesisTimeframe(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                >
                  <option value="1m">1m</option>
                  <option value="5m">5m</option>
                  <option value="15m">15m</option>
                  <option value="1h">1h</option>
                </select>
              </div>

              <button
                onClick={handleTriggerSynthesis}
                disabled={isSynthesizing}
                className="px-4 py-1.5 text-xs font-bold bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition flex items-center gap-1.5"
              >
                <span>⚡ Synthesize from Latest Feed</span>
                {isSynthesizing && <span className="animate-spin">◌</span>}
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-semibold">Family:</span>
                <select
                  value={selectedFamilyFilter}
                  onChange={(e) => setSelectedFamilyFilter(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                >
                  <option value="ALL">All Families</option>
                  {familiesData?.families.map((fam) => (
                    <option key={fam.family_id} value={fam.family_id}>
                      {fam.family_id.replace('FAM_', '')}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-semibold">Status:</span>
                <select
                  value={selectedStatusFilter}
                  onChange={(e) => setSelectedStatusFilter(e.target.value)}
                  className="px-2.5 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-200"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="FIREWALL_VALIDATED">FIREWALL PASS</option>
                  <option value="REJECTED">REJECTED</option>
                  <option value="QUEUED_FOR_LAB">QUEUED FOR LAB</option>
                  <option value="DRAFT">DRAFT</option>
                </select>
              </div>

              <button
                onClick={fetchLabData}
                className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition"
              >
                Refresh Ledger
              </button>
            </div>
          </div>

          {labFeedback && (
            <div className="p-3 bg-purple-950/60 border border-purple-800 text-purple-200 text-xs rounded-xl font-mono">
              {labFeedback}
            </div>
          )}

          {/* Hypotheses List Workstation */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold tracking-wider text-slate-300 uppercase">
                Preregistered Causal Hypotheses ({hypotheses.length} of {hypoTotal})
              </h2>
              <span className="text-xs text-slate-500 font-mono">WAL: causal_hypotheses_ledger</span>
            </div>

            {hypotheses.length === 0 ? (
              <div className="p-12 text-center text-slate-500 bg-slate-900 border border-slate-800 rounded-xl">
                No causal hypotheses matching criteria. Click &quot;⚡ Synthesize from Latest Feed&quot; to compile hypotheses from live market events.
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {hypotheses.map((hypo) => (
                  <div
                    key={hypo.hypothesis_id}
                    className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-4 shadow-lg hover:border-slate-700 transition"
                  >
                    {/* Header bar */}
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                      <div className="flex items-center gap-2.5">
                        <span className="text-xs font-mono font-bold text-purple-400 bg-purple-950/80 px-2.5 py-1 rounded border border-purple-800/60">
                          {hypo.hypothesis_id}
                        </span>
                        <span className="text-xs font-mono text-slate-400">
                          {hypo.family_id}
                        </span>
                        {hypothesisStatusBadge(hypo.status)}
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          {hypo.target_asset} ({hypo.timeframe})
                        </span>
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-amber-300">
                          Prior W: {hypo.epistemic_prior_weight.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Causal Chain Visualization */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3.5 bg-slate-950/70 border border-slate-800/60 rounded-xl">
                      {/* Step 1: Macro Trigger */}
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] font-bold font-mono text-cyan-400 uppercase tracking-wider">
                          1. Macro Point-in-Time Event
                        </span>
                        <p className="text-xs font-medium text-slate-200 line-clamp-2">
                          {hypo.macro_event_contract.headline}
                        </p>
                        <span className="text-[10px] text-slate-500 font-mono mt-1">
                          Pub: {new Date(hypo.macro_event_contract.published_at_utc * 1000).toLocaleTimeString()} • Avail: +{hypo.macro_event_contract.dissemination_buffer_seconds}s
                        </span>
                      </div>

                      {/* Step 2: Microstructure Gate */}
                      <div className="flex flex-col gap-1 border-t md:border-t-0 md:border-l border-slate-800/80 md:pl-3 pt-2 md:pt-0">
                        <span className="text-[10px] font-bold font-mono text-indigo-400 uppercase tracking-wider">
                          2. Microstructure Receptor Gate
                        </span>
                        <div className="text-xs font-mono text-indigo-200 line-clamp-2">
                          {Object.entries(hypo.microstructure_conditions).map(([k, v]) => (
                            <span key={k} className="mr-2">
                              {k}: {String(v)}
                            </span>
                          ))}
                        </div>
                        <span className="text-[10px] text-slate-500 font-mono mt-1">
                          Mech: {hypo.mechanism_id}
                        </span>
                      </div>

                      {/* Step 3: Predicted Edge H1 */}
                      <div className="flex flex-col gap-1 border-t md:border-t-0 md:border-l border-slate-800/80 md:pl-3 pt-2 md:pt-0">
                        <span className="text-[10px] font-bold font-mono text-emerald-400 uppercase tracking-wider">
                          3. Predicted Expectancy (H1)
                        </span>
                        <p className="text-xs text-slate-300 line-clamp-2">
                          {hypo.alternative_hypothesis}
                        </p>
                        <span className="text-[10px] text-slate-500 font-mono mt-1">
                          Hurdle: SR ≥ 1.50 • 3-Tier Frictions
                        </span>
                      </div>
                    </div>

                    {/* Falsification & Null Hypothesis */}
                    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400">
                      <div className="flex-1">
                        <span className="font-semibold text-slate-300">Null Hypothesis (H0): </span>
                        <span>{hypo.null_hypothesis}</span>
                      </div>

                      {hypo.rejection_reason && (
                        <div className="text-rose-400 text-xs font-mono">
                          Rejection: {hypo.rejection_reason}
                        </div>
                      )}
                    </div>

                    {/* Actions bar */}
                    <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-slate-800/80">
                      <button
                        onClick={() => handleAuditHypothesis(hypo)}
                        disabled={isValidating}
                        className="px-3.5 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition"
                      >
                        🛡️ Audit 9-Gate Firewall
                      </button>

                      {hypo.status === 'FIREWALL_VALIDATED' && (
                        <>
                          <button
                            onClick={() => handleCreateContract(hypo.hypothesis_id)}
                            disabled={actionInProgress}
                            className="px-3.5 py-1.5 text-xs font-semibold bg-amber-950 hover:bg-amber-900 text-amber-200 border border-amber-700/60 rounded-lg transition"
                          >
                            📜 Preregister M29 Contract
                          </button>
                          <button
                            onClick={() => handleDispatchLab(hypo.hypothesis_id)}
                            className="px-3.5 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition shadow"
                          >
                            🚀 Dispatch to Research Lab
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 3: EMPIRICAL REPLAY & FALSIFICATION LAB (M29)
          ===================================================================== */}
      {activeTab === 'REPLAY_LAB' && (
        <div className="flex flex-col gap-6">
          {/* Institutional Epistemic Status Guide */}
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <span>⚖️</span> Institutional Epistemic Governance Taxonomy (Level 2 Protocol)
              </span>
              <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
                REAL_CAPITAL_ENABLED = FALSE
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 text-center">
              <div className="p-2 bg-emerald-950/40 border border-emerald-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-emerald-400 font-mono">[FACT]</span>
                <span className="text-[11px] text-slate-300 font-medium">Observed Fact</span>
                <span className="text-[9px] text-slate-400">Verified OHLCV</span>
              </div>
              <div className="p-2 bg-purple-950/40 border border-purple-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-purple-400 font-mono">[MECHANISM]</span>
                <span className="text-[11px] text-slate-300 font-medium">Mechanism</span>
                <span className="text-[9px] text-slate-400">CVD / OBI / SMC</span>
              </div>
              <div className="p-2 bg-amber-950/40 border border-amber-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-amber-400 font-mono">[HYPO]</span>
                <span className="text-[11px] text-slate-300 font-medium">Untested Hypo</span>
                <span className="text-[9px] text-slate-400">Preregistered</span>
              </div>
              <div className="p-2 bg-blue-950/40 border border-blue-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-blue-400 font-mono">[REPLAY]</span>
                <span className="text-[11px] text-slate-300 font-medium">Replay Result</span>
                <span className="text-[9px] text-slate-400">Zero-Lookahead</span>
              </div>
              <div className="p-2 bg-teal-950/40 border border-teal-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-teal-400 font-mono">[SUPPORT]</span>
                <span className="text-[11px] text-slate-300 font-medium">Prelim Support</span>
                <span className="text-[9px] text-slate-400">Net E[R] &gt; 0</span>
              </div>
              <div className="p-2 bg-rose-950/40 border border-rose-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-rose-400 font-mono">[FALSIFIED]</span>
                <span className="text-[11px] text-slate-300 font-medium">Falsified</span>
                <span className="text-[9px] text-slate-400">H0 Confirmed</span>
              </div>
              <div className="p-2 bg-orange-950/40 border border-orange-800/60 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-orange-400 font-mono">[REVIEW]</span>
                <span className="text-[11px] text-slate-300 font-medium">Human Review</span>
                <span className="text-[9px] text-slate-400">Anomaly Check</span>
              </div>
              <div className="p-2 bg-red-950/60 border border-red-800 rounded-lg flex flex-col gap-1">
                <span className="text-[10px] font-bold text-red-300 font-mono">[BLOCKED]</span>
                <span className="text-[11px] text-slate-200 font-medium">No Execution</span>
                <span className="text-[9px] text-slate-400">Zero Order Auth</span>
              </div>
            </div>
          </div>

          {/* Replay Controls & Contract Selector */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="flex flex-wrap items-center gap-4">
              <span className="text-xs font-bold text-slate-300">Friction Stress Model:</span>
              <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
                {(['BASE', 'CONSERVATIVE', 'STRESS'] as const).map((tier) => (
                  <button
                    key={tier}
                    onClick={() => setSelectedFrictionTier(tier)}
                    className={`px-3 py-1 text-xs font-mono font-semibold rounded ${
                      selectedFrictionTier === tier
                        ? 'bg-amber-600 text-white shadow'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tier}
                  </button>
                ))}
              </div>

              {selectedContract && (
                <div className="text-xs font-mono text-amber-300 bg-amber-950/40 border border-amber-800/60 px-3 py-1.5 rounded-lg">
                  Contract: {selectedContract.contract_id} ({selectedContract.lookback_days}d lookback)
                </div>
              )}
            </div>

            <div className="flex items-center gap-3">
              {selectedContract && (
                <button
                  onClick={() => handleRunReplay(selectedContract.contract_id)}
                  disabled={isReplaying}
                  className="px-4 py-2 text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition shadow-md shadow-amber-950/50 flex items-center gap-2 disabled:opacity-50"
                >
                  {isReplaying ? (
                    <>
                      <span className="inline-block animate-spin">⟳</span> Replaying Candles...
                    </>
                  ) : (
                    <>
                      <span>⚡</span> Execute Historical Replay & Falsification
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {replayFeedback && (
            <div className="p-3 bg-amber-950/50 border border-amber-800/80 rounded-xl text-xs font-mono text-amber-200">
              {replayFeedback}
            </div>
          )}

          {/* Replay Execution Report & 8-Attribute Scorecard */}
          {replayReport && (
            <div className="flex flex-col gap-5 p-6 bg-slate-900 border border-slate-800 rounded-xl">
              <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-4 gap-4">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span>📊</span> Empirical Validation Report: {replayReport.replay_report.report_id}
                  </h3>
                  <p className="text-xs text-slate-400 font-mono mt-1">
                    Output Signature: {replayReport.replay_report.output_signature_sha256.slice(0, 24)}... (Deterministic Bit-Level Pass)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-3 py-1 rounded-lg text-xs font-bold font-mono border ${
                    replayReport.validation_result.status === 'OOS_VALIDATED'
                      ? 'bg-emerald-950 border-emerald-600 text-emerald-300'
                      : replayReport.validation_result.status === 'PRELIMINARY_SUPPORT'
                      ? 'bg-teal-950 border-teal-600 text-teal-300'
                      : 'bg-rose-950 border-rose-700 text-rose-300'
                  }`}>
                    {replayReport.validation_result.status}
                  </span>
                </div>
              </div>

              {/* 8-Attribute Scorecard Grid */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                  8-Attribute Empirical Falsification Scorecard
                </h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(replayReport.validation_result.scorecard_passes).map(([gate, passed]) => (
                    <div
                      key={gate}
                      className={`p-3 rounded-xl border flex items-center justify-between ${
                        passed
                          ? 'bg-slate-950 border-slate-800 text-slate-200'
                          : 'bg-rose-950/40 border-rose-800/80 text-rose-300'
                      }`}
                    >
                      <span className="text-[11px] font-mono">{gate}</span>
                      <span className={`text-[10px] font-bold font-mono px-2 py-0.5 rounded ${
                        passed ? 'bg-emerald-950 text-emerald-300' : 'bg-rose-900 text-rose-200'
                      }`}>
                        {passed ? 'PASS' : 'FAIL'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 3-Tier Friction Markout Breakdown */}
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 flex flex-col gap-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  3-Tier Execution Friction Waterfall & Expectancy
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-center">
                  <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800">
                    <div className="text-[10px] text-slate-400">Gross E[R]</div>
                    <div className="text-sm font-bold font-mono text-cyan-300">
                      {(replayReport.replay_report.gross_expectancy_r >= 0 ? '+' : '') + replayReport.replay_report.gross_expectancy_r.toFixed(2)}R
                    </div>
                  </div>
                  <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800">
                    <div className="text-[10px] text-slate-400">Net E[R] (Conservative)</div>
                    <div className={`text-sm font-bold font-mono ${replayReport.replay_report.net_expectancy_r > 0 ? 'text-emerald-300' : 'text-rose-400'}`}>
                      {(replayReport.replay_report.net_expectancy_r >= 0 ? '+' : '') + replayReport.replay_report.net_expectancy_r.toFixed(2)}R
                    </div>
                  </div>
                  <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800">
                    <div className="text-[10px] text-slate-400">Stress E[R]</div>
                    <div className={`text-sm font-bold font-mono ${replayReport.replay_report.stress_expectancy_r > 0 ? 'text-emerald-300' : 'text-rose-400'}`}>
                      {(replayReport.replay_report.stress_expectancy_r >= 0 ? '+' : '') + replayReport.replay_report.stress_expectancy_r.toFixed(2)}R
                    </div>
                  </div>
                  <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800">
                    <div className="text-[10px] text-slate-400">Cost Erosion</div>
                    <div className="text-sm font-bold font-mono text-amber-300">
                      {replayReport.replay_report.cost_erosion_pct}%
                    </div>
                  </div>
                  <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800">
                    <div className="text-[10px] text-slate-400">DSR Hurdle</div>
                    <div className="text-sm font-bold font-mono text-purple-300">
                      {replayReport.validation_result.deflated_sharpe_ratio}
                    </div>
                  </div>
                  <div className="p-2.5 bg-slate-900 rounded-lg border border-slate-800">
                    <div className="text-[10px] text-slate-400">Win Rate / PF</div>
                    <div className="text-sm font-bold font-mono text-slate-200">
                      {(replayReport.replay_report.win_rate * 100).toFixed(0)}% / {replayReport.replay_report.profit_factor}
                    </div>
                  </div>
                </div>
              </div>

              {/* Autopsy Card if Falsified */}
              {selectedAutopsy && (
                <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl flex flex-col gap-3">
                  <div className="flex items-center justify-between border-b border-rose-800/60 pb-2">
                    <span className="text-xs font-bold font-mono text-rose-300 flex items-center gap-2">
                      <span>💀</span> Causal Failure Autopsy [{selectedAutopsy.failure_category}]
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      Autopsy ID: {selectedAutopsy.autopsy_id}
                    </span>
                  </div>
                  <div className="text-xs text-rose-200 font-mono">
                    <div className="font-bold mb-1">Failure Mechanism:</div>
                    <p className="text-slate-300">{selectedAutopsy.failure_mechanism}</p>
                  </div>
                  <div className="text-xs bg-slate-950 p-3 rounded-lg border border-rose-900 text-amber-200 font-mono">
                    <div className="font-bold text-amber-400 mb-1">Reusable Institutional Lesson:</div>
                    <p>{selectedAutopsy.reusable_lesson}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Preregistered Contracts & Replay Queue */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-4">
            <h3 className="text-sm font-bold text-white flex items-center justify-between">
              <span>Preregistered Research Contracts ({activeContracts.length}) & Plans ({plans.length})</span>
              <span className="text-xs text-slate-400 font-mono">Durable SQLite Ledger</span>
            </h3>

            {activeContracts.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500 font-mono border border-dashed border-slate-800 rounded-xl">
                No active contracts in current session. Select a validated hypothesis in "Causal Hypothesis Lab" and click "📜 Preregister M29 Contract".
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {activeContracts.map((ctr) => (
                  <div
                    key={ctr.contract_id}
                    onClick={() => setSelectedContract(ctr)}
                    className={`p-4 rounded-xl border cursor-pointer transition flex flex-col md:flex-row md:items-center justify-between gap-4 ${
                      selectedContract?.contract_id === ctr.contract_id
                        ? 'bg-slate-950 border-amber-600 shadow-md shadow-amber-950/40'
                        : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold font-mono text-amber-300">{ctr.contract_id}</span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                          {ctr.family_id}
                        </span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          {ctr.lookback_days}d Lookback
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1 line-clamp-1">{ctr.alternative_hypothesis}</p>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedContract(ctr);
                          handleRunReplay(ctr.contract_id);
                        }}
                        disabled={isReplaying}
                        className="px-3.5 py-1.5 text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition disabled:opacity-50"
                      >
                        ⚡ Run Replay
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =====================================================================
          9-GATE CAUSAL FIREWALL AUDIT MODAL
          ===================================================================== */}
      {selectedAuditDecision && selectedHypothesisForAudit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 flex flex-col gap-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <span>🛡️</span> Causal Firewall Audit Report
                </h3>
                <p className="text-xs font-mono text-purple-300 mt-0.5">
                  Hypothesis: {selectedHypothesisForAudit.hypothesis_id}
                </p>
              </div>
              <button
                onClick={() => {
                  setSelectedAuditDecision(null);
                  setSelectedHypothesisForAudit(null);
                }}
                className="text-slate-400 hover:text-white text-lg p-1"
              >
                ✕
              </button>
            </div>

            {/* Overall Verdict Banner */}
            <div
              className={`p-3.5 rounded-xl border flex items-center justify-between ${
                selectedAuditDecision.passed
                  ? 'bg-emerald-950/60 border-emerald-700 text-emerald-200'
                  : 'bg-rose-950/60 border-rose-700 text-rose-200'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span className="text-xl">
                  {selectedAuditDecision.passed ? '✓' : '✕'}
                </span>
                <span className="text-sm font-bold font-mono">
                  {selectedAuditDecision.passed
                    ? 'OVERALL DECISION: ALL 9 GATES PASSED'
                    : 'OVERALL DECISION: FIREWALL REJECTED'}
                </span>
              </div>
              <span className="text-xs font-mono">
                {new Date(selectedAuditDecision.audit_timestamp_utc * 1000).toLocaleTimeString()}
              </span>
            </div>

            {/* Gate by Gate Inspection Grid */}
            <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1">
              {Object.entries(selectedAuditDecision.gate_results).map(([gate, passed]) => (
                <div
                  key={gate}
                  className={`p-2.5 rounded-lg border text-xs font-mono flex items-center justify-between ${
                    passed
                      ? 'bg-slate-950/80 border-slate-800 text-slate-300'
                      : 'bg-rose-950/40 border-rose-800 text-rose-300 font-bold'
                  }`}
                >
                  <span>{gate}</span>
                  <span className={`px-2 py-0.5 rounded text-[11px] ${passed ? 'bg-emerald-950 text-emerald-300' : 'bg-rose-900 text-rose-200'}`}>
                    {passed ? 'PASS' : 'FAIL'}
                  </span>
                </div>
              ))}
            </div>

            {/* Violations List */}
            {selectedAuditDecision.violations.length > 0 && (
              <div className="p-3 bg-rose-950/60 border border-rose-800 rounded-xl text-xs text-rose-200 font-mono">
                <div className="font-bold mb-1">Detected Violations:</div>
                <ul className="list-disc pl-4 space-y-1">
                  {selectedAuditDecision.violations.map((v, i) => (
                    <li key={i}>{v}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => {
                  setSelectedAuditDecision(null);
                  setSelectedHypothesisForAudit(null);
                }}
                className="px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition"
              >
                Close Audit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default IntelligenceCockpit;
