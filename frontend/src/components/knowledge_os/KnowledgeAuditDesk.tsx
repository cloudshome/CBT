import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  XCircle,
  CheckCircle2,
  RefreshCw,
  FileText,
  Activity,
  Layers,
  BookOpen,
  Cpu,
  Clock,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { api } from '../../services/api';
import {
  KnowledgeAuditReport,
  KnowledgeAuditCheck,
  LibraryStatsResponse,
  BookIngestionJob,
} from '../../types';

interface KnowledgeAuditDeskProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
}

export const KnowledgeAuditDesk: React.FC<KnowledgeAuditDeskProps> = ({ onNotify }) => {
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [auditReport, setAuditReport] = useState<KnowledgeAuditReport | null>(null);
  const [libraryStats, setLibraryStats] = useState<LibraryStatsResponse | null>(null);
  const [ingestionJobs, setIngestionJobs] = useState<BookIngestionJob[]>([]);
  const [expandedCheck, setExpandedCheck] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'AUDIT' | 'JOBS' | 'DOMAINS'>('AUDIT');

  const loadAllData = async () => {
    try {
      setRefreshing(true);
      const [report, stats, jobsData] = await Promise.all([
        api.runKnowledgeAudit(),
        api.getLibraryStats(),
        api.getLibraryJobs(),
      ]);
      setAuditReport(report);
      setLibraryStats(stats);
      setIngestionJobs(jobsData.jobs || []);
    } catch (err: any) {
      console.error('Failed to load knowledge audit data:', err);
      onNotify?.('error', 'Audit Failed', err.message || 'Unable to retrieve audit telemetry.');
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const handleRunAudit = async () => {
    setRefreshing(true);
    try {
      const report = await api.runKnowledgeAudit();
      setAuditReport(report);
      onNotify?.(
        report.overall_status === 'PASS' ? 'success' : report.overall_status === 'WARN' ? 'warning' : 'error',
        'Audit Completed',
        `Overall Status: ${report.overall_status}. ${report.summary}`
      );
    } catch (err: any) {
      onNotify?.('error', 'Audit Execution Error', err.message || 'Failed to execute audit checks.');
    } finally {
      setRefreshing(false);
    }
  };

  const getStatusBadge = (status: 'PASS' | 'WARN' | 'FAIL') => {
    switch (status) {
      case 'PASS':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
            <CheckCircle2 className="w-3.5 h-3.5" />
            PASS
          </span>
        );
      case 'WARN':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-800">
            <AlertTriangle className="w-3.5 h-3.5" />
            WARN
          </span>
        );
      case 'FAIL':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-800">
            <XCircle className="w-3.5 h-3.5" />
            FAIL
          </span>
        );
    }
  };

  const getJobStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="px-2 py-0.5 rounded text-xs font-mono bg-emerald-900/60 text-emerald-400 border border-emerald-800">
            COMPLETED
          </span>
        );
      case 'PROCESSING':
      case 'RESUMED':
        return (
          <span className="px-2 py-0.5 rounded text-xs font-mono bg-cyan-900/60 text-cyan-400 border border-cyan-800 animate-pulse">
            {status}
          </span>
        );
      case 'FAILED':
        return (
          <span className="px-2 py-0.5 rounded text-xs font-mono bg-rose-900/60 text-rose-400 border border-rose-800">
            FAILED
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-xs font-mono bg-slate-800 text-slate-400 border border-slate-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950/50 border border-slate-800 shadow-xl">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-indigo-900/40 rounded-xl border border-indigo-700/50 text-indigo-400 shadow-inner">
            <ShieldCheck className="w-7 h-7" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-white tracking-wide">
                Knowledge Quality & Integrity Auditor
              </h2>
              {auditReport && getStatusBadge(auditReport.overall_status)}
            </div>
            <p className="text-sm text-slate-400 mt-0.5">
              7-invariant mathematical verification: spatial provenance, isolation, non-destructive contradiction, and zero unverified alpha.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRunAudit}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg font-medium text-sm transition-all shadow-md active:scale-95"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Verifying Schema...' : 'Run Fresh Audit'}
          </button>
        </div>
      </div>

      {/* KPI Overview Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-xs font-mono uppercase">Sources</span>
            <FileText className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            {libraryStats?.sources_count ?? auditReport?.total_sources ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Ingested volumes</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-xs font-mono uppercase">Atomic Claims</span>
            <Layers className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            {libraryStats?.claims_count ?? auditReport?.total_claims ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Spatial assertions</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-xs font-mono uppercase">Empirical Vault</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">
            {libraryStats?.evidence_count ?? auditReport?.total_evidence ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Validated edge</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-xs font-mono uppercase">Autopsy Vault</span>
            <AlertTriangle className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold text-rose-400 font-mono">
            {libraryStats?.rejected_count ?? auditReport?.total_autopsies ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Disproven failures</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-xs font-mono uppercase">Books & Literature</span>
            <BookOpen className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400 font-mono">
            {libraryStats?.books_count ?? 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            {libraryStats?.pages_processed ?? 0} pages read
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-1">
            <span className="text-xs font-mono uppercase">Active Jobs</span>
            <Cpu className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-purple-400 font-mono">
            {libraryStats?.jobs_active ?? ingestionJobs.filter(j => j.status === 'PROCESSING').length}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">Background streaming</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
        <button
          onClick={() => setActiveTab('AUDIT')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'AUDIT'
              ? 'bg-indigo-900/50 text-indigo-300 border border-indigo-700/60'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          7-Invariant Integrity Checks ({auditReport?.checks?.length ?? 7})
        </button>
        <button
          onClick={() => setActiveTab('JOBS')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'JOBS'
              ? 'bg-indigo-900/50 text-indigo-300 border border-indigo-700/60'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          Streaming Book Ingestor Jobs ({ingestionJobs.length})
        </button>
        <button
          onClick={() => setActiveTab('DOMAINS')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'DOMAINS'
              ? 'bg-indigo-900/50 text-indigo-300 border border-indigo-700/60'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
          }`}
        >
          Domain Distribution ({libraryStats?.top_domains?.length ?? 0})
        </button>
      </div>

      {/* Tab 1: 7-Invariant Integrity Checks */}
      {activeTab === 'AUDIT' && (
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-sm text-slate-300">
            <span className="font-semibold text-white">Integrity Verdict: </span>
            {auditReport?.summary || 'Auditor ready. Running 7 systematic epistemic consistency checks across all stores.'}
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950/80 text-xs font-mono uppercase text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Invariant Check</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Anomalies Detected</th>
                  <th className="py-3 px-4">Details</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {auditReport?.checks && auditReport.checks.length > 0 ? (
                  auditReport.checks.map((chk: KnowledgeAuditCheck, idx: number) => {
                    const isExpanded = expandedCheck === chk.check_name;
                    return (
                      <React.Fragment key={idx}>
                        <tr className="hover:bg-slate-800/30 transition-colors">
                          <td className="py-3.5 px-4 font-mono font-medium text-slate-200">
                            {chk.check_name}
                          </td>
                          <td className="py-3.5 px-4">{getStatusBadge(chk.status)}</td>
                          <td className="py-3.5 px-4 font-mono text-slate-300">
                            <span
                              className={`px-2 py-0.5 rounded text-xs ${
                                chk.count > 0 ? 'bg-amber-950/70 text-amber-400 font-bold' : 'text-slate-400'
                              }`}
                            >
                              {chk.count}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-slate-400 text-xs max-w-md truncate">
                            {chk.details}
                          </td>
                          <td className="py-3.5 px-4 text-right">
                            <button
                              onClick={() => setExpandedCheck(isExpanded ? null : chk.check_name)}
                              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                            >
                              {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="bg-slate-950/60">
                            <td colSpan={5} className="p-4 border-t border-slate-800/50">
                              <div className="space-y-3">
                                <div>
                                  <div className="text-xs font-mono uppercase text-slate-400 mb-1">
                                    Full Finding:
                                  </div>
                                  <p className="text-sm text-slate-200 font-mono bg-slate-900/90 p-2.5 rounded border border-slate-800">
                                    {chk.details}
                                  </p>
                                </div>
                                <div>
                                  <div className="text-xs font-mono uppercase text-emerald-400 mb-1">
                                    Recommended Remediation:
                                  </div>
                                  <p className="text-sm text-slate-300 bg-emerald-950/30 p-2.5 rounded border border-emerald-800/50">
                                    {chk.remediation}
                                  </p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-slate-500 font-mono">
                      No audit checks returned. Click "Run Fresh Audit" to inspect the repository.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Streaming Book Ingestor Jobs */}
      {activeTab === 'JOBS' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-sm text-slate-400">
            <span>
              Resumable streaming checkpoints for large books (100MB to 2+ GB).
            </span>
            <span className="font-mono text-xs text-slate-500">
              Auto-persisted to <code className="text-indigo-400">book_ingestion_jobs</code>
            </span>
          </div>

          {ingestionJobs.length === 0 ? (
            <div className="p-8 text-center rounded-xl bg-slate-900/40 border border-slate-800 text-slate-500">
              <BookOpen className="w-8 h-8 mx-auto mb-2 text-slate-600" />
              <p>No multi-page book ingestion jobs registered yet.</p>
              <p className="text-xs text-slate-600 mt-1">
                Upload a book (PDF/EPUB) in the Research Dropzone to trigger the streaming parser.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {ingestionJobs.map((job) => (
                <div
                  key={job.job_id}
                  className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition-colors space-y-3"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-slate-800 rounded-lg text-slate-300">
                        <FileText className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-white">{job.file_name}</div>
                        <div className="text-xs font-mono text-slate-400 flex items-center gap-2 mt-0.5">
                          <span>SHA256: {job.sha256_hash.substring(0, 12)}...</span>
                          <span>•</span>
                          <span>{(job.file_size_bytes / (1024 * 1024)).toFixed(2)} MB</span>
                          {job.current_chapter && (
                            <>
                              <span>•</span>
                              <span className="text-indigo-300">Ch: {job.current_chapter}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      {getJobStatusBadge(job.status)}
                      <span className="text-xs font-mono text-slate-400">
                        {job.processed_pages} / {job.total_pages} pgs ({job.progress_pct.toFixed(0)}%)
                      </span>
                    </div>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-2 transition-all duration-300 ${
                        job.status === 'COMPLETED'
                          ? 'bg-emerald-500'
                          : job.status === 'FAILED'
                          ? 'bg-rose-500'
                          : 'bg-indigo-500'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
                    />
                  </div>

                  {/* Stats Row */}
                  <div className="flex items-center justify-between text-xs font-mono text-slate-400 pt-1 border-t border-slate-800/60">
                    <div className="flex items-center gap-4">
                      <span>Claims: <strong className="text-slate-200">{job.claims_count}</strong></span>
                      <span>Concepts: <strong className="text-slate-200">{job.concepts_count}</strong></span>
                    </div>
                    <div className="text-slate-500 flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {new Date(job.updated_at * 1000).toLocaleTimeString()}
                    </div>
                  </div>

                  {job.error_log && (
                    <div className="p-2.5 rounded bg-rose-950/40 border border-rose-800 text-xs font-mono text-rose-300">
                      Error: {job.error_log}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Domain Distribution */}
      {activeTab === 'DOMAINS' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-400">
            Categorized knowledge taxonomy distribution across normalized domains.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {libraryStats?.top_domains && libraryStats.top_domains.length > 0 ? (
              libraryStats.top_domains.map((dom, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl bg-slate-900/70 border border-slate-800 flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-900/40 border border-indigo-700/50 flex items-center justify-center text-xs font-mono text-indigo-400">
                      #{idx + 1}
                    </div>
                    <div className="text-sm font-semibold text-white">{dom.domain}</div>
                  </div>
                  <div className="text-right">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-xs font-mono text-slate-300">
                      {dom.count} items
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="col-span-full py-8 text-center text-slate-500 font-mono">
                No domain telemetry recorded yet.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
