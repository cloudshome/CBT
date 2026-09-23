import React, { useState, useEffect, useCallback } from 'react';
import {
  IntelligenceStatusResponse,
  IntelligenceRecordsResponse,
  NarrativesResponse,
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
} from '../services/api';

export const IntelligenceCockpit: React.FC = () => {
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

  const fetchTelemetry = useCallback(async () => {
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

  useEffect(() => {
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 15000);
    return () => clearInterval(interval);
  }, [fetchTelemetry]);

  const handleStartScout = async () => {
    setActionInProgress(true);
    try {
      await startScoutDaemon();
      await fetchTelemetry();
    } finally {
      setActionInProgress(false);
    }
  };

  const handleStopScout = async () => {
    setActionInProgress(true);
    try {
      await stopScoutDaemon();
      await fetchTelemetry();
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
      await fetchTelemetry();
    } finally {
      setActionInProgress(false);
    }
  };

  const handleTriggerStep = async () => {
    setActionInProgress(true);
    try {
      await triggerScoutStep();
      await fetchTelemetry();
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
      await fetchTelemetry();
    } catch (err: any) {
      setIngestFeedback(`Ingestion failed: ${err.message || 'Error'}`);
    } finally {
      setActionInProgress(false);
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
          <span className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-800 text-slate-400">
            {grade}
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 bg-slate-950 text-slate-100 min-h-screen">
      {/* Top Banner / Constitutional Warning */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between p-4 bg-slate-900 border border-slate-800 rounded-xl gap-4 shadow-xl">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
              SKY Global Intelligence Fabric
            </h1>
            <span className="px-2.5 py-0.5 text-[11px] font-mono tracking-wider bg-cyan-950 text-cyan-300 border border-cyan-800/80 rounded-full">
              AGENT-REACH × CBT
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Autonomous multi-domain intelligence ingestor • Fed / SEC / Crypto / Equities • Zero execution authority
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-lg">
            <span className="text-xs text-slate-400">Scout State:</span>
            <span
              className={`text-xs font-bold font-mono px-2 py-0.5 rounded ${
                scoutState === 'RUNNING'
                  ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700'
                  : scoutState === 'PAUSED'
                  ? 'bg-amber-900/60 text-amber-300 border border-amber-700'
                  : 'bg-slate-800 text-slate-400 border border-slate-700'
              }`}
            >
              {scoutState}
            </span>
          </div>

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
            onClick={fetchTelemetry}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Scout Telemetry & Receptors Health Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        {statusData?.channels &&
          Object.entries(statusData.channels).map(([channel, info]) => {
            const isOnline = info.status === 'ONLINE';
            const isDegraded = info.status === 'DEGRADED';
            return (
              <div
                key={channel}
                className="bg-slate-900 border border-slate-800/80 p-3 rounded-lg flex flex-col justify-between"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold font-mono text-slate-200">{channel}</span>
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isOnline
                        ? 'bg-emerald-400'
                        : isDegraded
                        ? 'bg-amber-400'
                        : 'bg-rose-500'
                    }`}
                  />
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>{info.status}</span>
                  {info.requires_cookies && <span className="text-[10px] text-slate-500">🔒 Cookie</span>}
                </div>
              </div>
            );
          })}
      </div>

      {/* Metric Counters Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-xs font-medium text-slate-400">Total Ingested Records</div>
          <div className="text-2xl font-bold font-mono text-cyan-400 mt-1">
            {statusData?.total_records ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Deduplicated SQLite storage</div>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-xs font-medium text-slate-400">Frontier Target Queue</div>
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

      {/* Filter Tabs & Domain Selectors */}
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

      {/* Main 2-Column Institutional Workstation */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Intelligence Stream (2/3 width) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold tracking-wider text-slate-300 uppercase">
              Intelligence Records ({recordsData?.total ?? 0})
            </h2>
            <span className="text-xs text-slate-500">Auto-refresh 15s</span>
          </div>

          {loading && !recordsData ? (
            <div className="p-8 text-center text-slate-500 bg-slate-900 border border-slate-800 rounded-xl">
              Loading intelligence records...
            </div>
          ) : recordsData?.records.length === 0 ? (
            <div className="p-8 text-center text-slate-500 bg-slate-900 border border-slate-800 rounded-xl">
              No intelligence records matching filters. Click &quot;Step Once&quot; or Ingest a URL.
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
                        {rec.source_platform}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-400">
                        Relevance: <strong className="text-cyan-400">{(rec.relevance_score * 100).toFixed(0)}%</strong>
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {new Date(rec.collected_at_utc * 1000).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>

                  <h3 className="text-base font-semibold text-white leading-snug">
                    {rec.title}
                  </h3>

                  <p className="text-xs text-slate-300 line-clamp-3 leading-relaxed">
                    {rec.summary || rec.content_markdown?.slice(0, 300)}
                  </p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800/60 mt-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {rec.entities.map((ent) => (
                        <button
                          key={ent}
                          onClick={() => setSelectedEntity(ent)}
                          className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700/60"
                        >
                          ${ent}
                        </button>
                      ))}
                      {rec.security_flags?.map((flg) => (
                        <span
                          key={flg}
                          className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-rose-950 text-rose-300 border border-rose-800/60"
                        >
                          🛡️ {flg}
                        </span>
                      ))}
                    </div>

                    <a
                      href={rec.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-cyan-400 hover:text-cyan-300 underline font-mono flex items-center gap-1"
                    >
                      Source Citation ↗
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column: Narrative Radar & On-Demand Ingest (1/3 width) */}
        <div className="flex flex-col gap-6">
          {/* On-Demand Targeted Ingest Widget */}
          <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl flex flex-col gap-3 shadow-lg">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              On-Demand Target Ingestion
            </h3>
            <p className="text-xs text-slate-400">
              Pass any URL, RSS feed, or GitHub repository for immediate sanitization and relevance inspection.
            </p>

            <form onSubmit={handleIngest} className="flex flex-col gap-3 mt-1">
              <input
                type="text"
                placeholder="https://... or ethereum/EIPs"
                value={ingestUrl}
                onChange={(e) => setIngestUrl(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-cyan-500"
              />

              <div className="flex items-center gap-2">
                <select
                  value={ingestPlatform}
                  onChange={(e) => setIngestPlatform(e.target.value)}
                  className="px-3 py-2 text-xs bg-slate-950 border border-slate-700 rounded-lg text-slate-200 focus:outline-none"
                >
                  <option value="WEB">Web Page</option>
                  <option value="RSS">RSS / Atom Feed</option>
                  <option value="GITHUB">GitHub Repo</option>
                  <option value="YOUTUBE">YouTube Video</option>
                </select>

                <button
                  type="submit"
                  disabled={actionInProgress || !ingestUrl.trim()}
                  className="flex-1 py-2 text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white rounded-lg transition"
                >
                  Analyze & Ingest
                </button>
              </div>

              {ingestFeedback && (
                <div className="p-2 text-xs font-mono rounded bg-slate-950 border border-slate-800 text-slate-300">
                  {ingestFeedback}
                </div>
              )}
            </form>
          </div>

          {/* Active Narrative Radar Panel */}
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
                      <span
                        className={`text-[10px] font-semibold font-mono px-2 py-0.5 rounded ${
                          nar.credibility_tag === 'INSTITUTIONAL_BACKED'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/80'
                            : nar.credibility_tag === 'HYPE_DRIVEN'
                            ? 'bg-purple-950 text-purple-300 border border-purple-800/80'
                            : 'bg-blue-950 text-blue-300 border border-blue-800/80'
                        }`}
                      >
                        {nar.credibility_tag}
                      </span>
                      <span className="text-xs font-mono font-bold text-purple-300">
                        {nar.velocity_score} / hr
                      </span>
                    </div>

                    <h4 className="text-xs font-semibold text-slate-200 leading-snug">
                      {nar.theme}
                    </h4>

                    <div className="flex flex-wrap items-center gap-1">
                      {nar.entities.map((e) => (
                        <span
                          key={e}
                          className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-slate-900 text-slate-400"
                        >
                          ${e}
                        </span>
                      ))}
                      <span className="text-[10px] text-slate-500 ml-auto font-mono">
                        {nar.total_records} mentions
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
export default IntelligenceCockpit;
