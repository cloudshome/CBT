import React, { useState, useEffect, useCallback } from 'react';
import {
  Shield,
  Activity,
  AlertOctagon,
  CheckCircle2,
  RefreshCw,
  AlertTriangle,
  Clock,
  Zap,
  Sliders,
  X,
  Gauge,
  Layers,
  ArrowRight,
} from 'lucide-react';
import {
  TestnetBurnInReport,
  TestnetBurnInState,
  TestnetLatencyStageSummary,
} from '../types';
import { api } from '../services/api';

export interface TestnetBurnInHUDProps {
  onClose?: () => void;
  initialSessionId?: string;
}

const formatDuration = (seconds: number): string => {
  if (seconds < 0) seconds = 0;
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (d > 0) return `${d}d ${h}h ${m}m ${s}s`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
};

const formatLatency = (us: number): string => {
  if (us >= 1000) {
    return `${(us / 1000).toFixed(2)}ms`;
  }
  return `${Math.round(us)}\u03bcs`;
};

export const TestnetBurnInHUD: React.FC<TestnetBurnInHUDProps> = ({
  onClose,
  initialSessionId,
}) => {
  const [report, setReport] = useState<TestnetBurnInReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [latencyView, setLatencyView] = useState<'clean' | 'fault'>('clean');
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);

  const fetchReport = useCallback(async () => {
    try {
      const data = await api.getTestnetBurnInReport(initialSessionId);
      setReport(data);
    } catch (err) {
      console.error('Failed to load Testnet Burn-In report', err);
    } finally {
      setLoading(false);
    }
  }, [initialSessionId]);

  useEffect(() => {
    fetchReport();
    if (!autoRefresh) return;
    const timer = setInterval(fetchReport, 3000);
    return () => clearInterval(timer);
  }, [fetchReport, autoRefresh]);

  if (loading && !report) {
    return (
      <div className="p-4 rounded bg-slate-950 border border-slate-800 text-slate-400 font-mono text-xs flex items-center gap-2">
        <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
        <span>Loading Gate 5 Extended Testnet Burn-In telemetry...</span>
      </div>
    );
  }

  if (!report) return null;

  const getStateColor = (state: TestnetBurnInState) => {
    switch (state) {
      case 'ACTIVE_REHEARSAL':
        return 'border-emerald-500/80 bg-emerald-950/40 text-emerald-300';
      case 'WARMING_UP':
      case 'INITIALIZING':
        return 'border-cyan-500/80 bg-cyan-950/40 text-cyan-300';
      case 'DEGRADED_OPERATION':
        return 'border-amber-500/80 bg-amber-950/40 text-amber-300';
      case 'RECOVERY_RECONCILIATION':
        return 'border-purple-500/80 bg-purple-950/40 text-purple-300';
      case 'ANOMALY_HALTED':
        return 'border-rose-500/80 bg-rose-950/40 text-rose-300';
      case 'COMPLETED':
        return 'border-blue-500/80 bg-blue-950/40 text-blue-300';
      default:
        return 'border-slate-700 bg-slate-900 text-slate-400';
    }
  };

  const isStale =
    report.is_stale ||
    (report.timestamp_utc
      ? Math.abs(Date.now() - new Date(report.timestamp_utc).getTime()) > 3000
      : false);

  const latencyData: TestnetLatencyStageSummary[] =
    latencyView === 'clean' ? report.clean_latency_summary : report.fault_latency_summary;

  return (
    <div className="p-3.5 rounded-lg bg-slate-950/95 border border-cyan-800/60 shadow-2xl flex flex-col gap-3 font-mono text-[11px] text-slate-200 backdrop-blur-md">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-slate-100 tracking-wide">
            GATE 5 EXTENDED TESTNET BURN-IN HUD
          </span>
          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-900 border border-slate-700 text-slate-300">
            {report.session_id}
          </span>
          {report.telemetry_seq !== undefined && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-slate-900 border border-slate-700 text-cyan-400" title="Monotonic Telemetry Sequence">
              Seq #{report.telemetry_seq}
            </span>
          )}
          {report.fencing_token !== undefined && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-slate-900 border border-slate-700 text-amber-400" title="Monotonic Lease Fencing Token">
              Token #{report.fencing_token}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Stale Telemetry Badge */}
          {isStale && (
            <span className="px-2 py-0.5 rounded border border-rose-500/80 bg-rose-950/80 text-rose-300 text-[10px] font-bold flex items-center gap-1 animate-pulse">
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              STALE (&gt;3000ms)
            </span>
          )}

          {/* FSM State Badge */}
          <span
            className={`px-2 py-0.5 rounded border text-[10px] font-bold flex items-center gap-1.5 ${getStateColor(
              report.state
            )}`}
          >
            <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
            {report.state}
          </span>

          <button
            type="button"
            onClick={() => setAutoRefresh(!autoRefresh)}
            title={autoRefresh ? 'Auto-refresh active (3s)' : 'Auto-refresh paused'}
            className={`p-1 rounded border ${
              autoRefresh
                ? 'bg-cyan-950/50 border-cyan-700 text-cyan-300'
                : 'bg-slate-900 border-slate-800 text-slate-500 hover:text-slate-300'
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${autoRefresh ? 'animate-spin' : ''}`} style={{ animationDuration: '6s' }} />
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Stale Telemetry Warning Banner */}
      {isStale && (
        <div className="px-2.5 py-1.5 rounded bg-rose-950/60 border border-rose-600/70 text-[9px] text-rose-200 flex items-center justify-between animate-pulse">
          <span className="flex items-center gap-1.5">
            <AlertOctagon className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
            <span><strong>STALE FLIGHT TELEMETRY WATERMARK EXCEEDED:</strong> Heartbeat latency &gt;3,000ms. Fail-closed safety governor engaged.</span>
          </span>
          <span className="font-bold text-rose-300">FAIL-CLOSED</span>
        </div>
      )}

      {/* Non-Negotiable Operational Safety Disclaimer */}
      <div className="px-2 py-1.5 rounded bg-blue-950/30 border border-blue-800/40 text-[9px] text-blue-300 flex items-center justify-between">
        <span className="flex items-center gap-1">
          <Activity className="w-3 h-3 text-blue-400 flex-shrink-0" />
          <span>RESEARCH &amp; TESTNET REHEARSAL QUALIFICATION ONLY &mdash; REAL CAPITAL IMMUTABLY DISABLED</span>
        </span>
        <span className="font-bold text-blue-200">real_capital_enabled: False</span>
      </div>

      {/* 3-Tier Duration & Epoch Accounting Panel (H_elapsed = H_qualified + H_disqualified) */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] flex items-center gap-1">
            <Clock className="w-3 h-3 text-cyan-400" />
            <span>ELAPSED (H_elapsed)</span>
          </div>
          <div className="text-sm font-bold text-slate-100 mt-1">
            {formatDuration(report.durations.wallclock_elapsed_sec)}
          </div>
          <div className="text-[8px] text-slate-500">
            Target: {formatDuration(report.durations.target_duration_sec)} (336h Continuous)
          </div>
        </div>

        <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>QUALIFIED (H_qualified)</span>
          </div>
          <div className="text-sm font-bold text-emerald-300 mt-1">
            {formatDuration(report.durations.healthy_duration_sec)}
          </div>
          <div className="text-[8px] text-emerald-400/80 font-bold">
            {report.durations.healthy_ratio_pct.toFixed(2)}% Qualification Ratio
          </div>
        </div>

        <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-amber-400" />
            <span>DISQUALIFIED (H_disqualified)</span>
          </div>
          <div className="text-sm font-bold text-amber-300 mt-1">
            {formatDuration(report.durations.invalidated_duration_sec)}
          </div>
          <div className="text-[8px] text-slate-500">
            {report.active_epoch ? `Epoch: ${report.active_epoch.epoch_id}` : 'No Active Epoch'}
          </div>
        </div>

        <div className="p-2 rounded bg-slate-900/80 border border-slate-800/80 flex flex-col justify-between">
          <div className="text-slate-400 text-[9px] flex items-center gap-1">
            <Gauge className="w-3 h-3 text-purple-400" />
            <span>SIMULATED EQUITY &amp; DD</span>
          </div>
          <div className="text-sm font-bold text-purple-200 mt-1">
            ${report.account_equity_usd.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
          <div className="flex items-center justify-between text-[8px]">
            <span
              className={
                report.drawdown_pct >= report.rehearsal_drawdown_limit_pct
                  ? 'text-rose-400 font-bold'
                  : 'text-slate-400'
              }
            >
              DD: {report.drawdown_pct.toFixed(2)}%
            </span>
            <span className="text-slate-500">
              Max: {report.rehearsal_drawdown_limit_pct.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* Progress Bar towards 14-day qualification */}
      <div className="flex flex-col gap-1">
        <div className="flex justify-between text-[9px] text-slate-400">
          <span>14-Day Qualification Continuity Progress</span>
          <span className="font-bold text-cyan-300">
            {report.durations.target_progress_pct.toFixed(2)}% Completed
          </span>
        </div>
        <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden border border-slate-800">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, report.durations.target_progress_pct))}%` }}
          />
        </div>
      </div>

      {/* 7-Stage Decomposed Latency Matrix */}
      <div className="p-2.5 rounded bg-slate-900/60 border border-slate-800/80 flex flex-col gap-2">
        <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
          <div className="flex items-center gap-1.5">
            <Zap className="w-3 h-3 text-amber-400" />
            <span className="font-bold text-slate-200 text-[10px]">
              7-Stage Microsecond Decomposed Latency Pipeline
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Clock offset status */}
            <span
              className={`px-1.5 py-0.5 rounded text-[9px] border ${
                report.clock_healthy
                  ? 'border-emerald-700/60 bg-emerald-950/40 text-emerald-300'
                  : 'border-rose-700/60 bg-rose-950/40 text-rose-300'
              }`}
            >
              Clock Offset: &Delta;t {report.clock_offset_ms.toFixed(2)}ms (Limit: 50ms)
            </span>

            {/* Toggle Clean vs Fault Injected */}
            <div className="flex rounded border border-slate-800 overflow-hidden text-[9px]">
              <button
                type="button"
                onClick={() => setLatencyView('clean')}
                className={`px-2 py-0.5 font-bold transition ${
                  latencyView === 'clean'
                    ? 'bg-cyan-900/70 text-cyan-200'
                    : 'bg-slate-900 text-slate-400 hover:text-slate-200'
                }`}
              >
                Clean Baseline
              </button>
              <button
                type="button"
                onClick={() => setLatencyView('fault')}
                className={`px-2 py-0.5 font-bold transition ${
                  latencyView === 'fault'
                    ? 'bg-amber-900/70 text-amber-200'
                    : 'bg-slate-900 text-slate-400 hover:text-slate-200'
                }`}
              >
                Fault Injected
              </button>
            </div>
          </div>
        </div>

        {/* Latency Quantile Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[9px]">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800/60">
                <th className="py-1 pr-2">Stage Pipeline</th>
                <th className="py-1 px-1.5 text-right">P50</th>
                <th className="py-1 px-1.5 text-right">P90</th>
                <th className="py-1 px-1.5 text-right">P99</th>
                <th className="py-1 px-1.5 text-right">P99.9</th>
                <th className="py-1 px-1.5 text-right">Max</th>
                <th className="py-1 pl-1.5 text-right">Samples</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {latencyData.map((stage) => {
                const isTotal = stage.stage_name.toLowerCase().includes('total');
                return (
                  <tr
                    key={stage.stage_name}
                    className={`hover:bg-slate-800/30 ${
                      isTotal ? 'font-bold text-cyan-300 bg-slate-900/40' : 'text-slate-300'
                    }`}
                  >
                    <td className="py-1 pr-2 flex items-center gap-1">
                      {isTotal ? (
                        <ArrowRight className="w-2.5 h-2.5 text-cyan-400" />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                      )}
                      <span>{stage.stage_name}</span>
                    </td>
                    <td className="py-1 px-1.5 text-right font-mono">{formatLatency(stage.p50_us)}</td>
                    <td className="py-1 px-1.5 text-right font-mono">{formatLatency(stage.p90_us)}</td>
                    <td className="py-1 px-1.5 text-right font-mono">{formatLatency(stage.p99_us)}</td>
                    <td className="py-1 px-1.5 text-right font-mono">{formatLatency(stage.p99_9_us)}</td>
                    <td className="py-1 px-1.5 text-right font-mono">{formatLatency(stage.max_us)}</td>
                    <td className="py-1 pl-1.5 text-right font-mono text-slate-500">
                      {stage.sample_count}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Invariant Health Checklist & Fault Injection Matrix */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {/* Continuous Invariant Checklist */}
        <div className="p-2.5 rounded bg-slate-900/60 border border-slate-800/80 flex flex-col gap-1.5">
          <div className="text-[10px] font-bold text-slate-200 border-b border-slate-800 pb-1 flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Layers className="w-3 h-3 text-cyan-400" />
              <span>Continuous Rehearsal Invariants</span>
            </span>
            <span className="text-[9px] text-slate-500">Zero Lookahead & Risk Primacy</span>
          </div>

          <div className="flex flex-col gap-1 mt-1">
            {report.invariants.map((inv) => (
              <div
                key={inv.name}
                className="p-1 rounded bg-slate-950/60 border border-slate-800/60 flex items-center justify-between text-[9px]"
              >
                <div className="flex items-center gap-1.5">
                  {inv.status === 'PASS' ? (
                    <CheckCircle2 className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                  ) : inv.status === 'WARN' ? (
                    <AlertTriangle className="w-3 h-3 text-amber-400 flex-shrink-0" />
                  ) : (
                    <AlertOctagon className="w-3 h-3 text-rose-400 flex-shrink-0" />
                  )}
                  <div className="flex flex-col">
                    <span className="font-bold text-slate-200">{inv.name}</span>
                    <span className="text-[8px] text-slate-400">{inv.description}</span>
                  </div>
                </div>
                <span
                  className={`px-1.5 py-0.2 rounded font-bold text-[8px] ${
                    inv.status === 'PASS'
                      ? 'bg-emerald-950 text-emerald-300'
                      : inv.status === 'WARN'
                      ? 'bg-amber-950 text-amber-300'
                      : 'bg-rose-950 text-rose-300'
                  }`}
                >
                  {inv.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 13-Point Fault Injection Matrix & Statistics */}
        <div className="p-2.5 rounded bg-slate-900/60 border border-slate-800/80 flex flex-col gap-1.5 justify-between">
          <div>
            <div className="text-[10px] font-bold text-slate-200 border-b border-slate-800 pb-1 flex items-center justify-between">
              <span className="flex items-center gap-1">
                <Sliders className="w-3 h-3 text-amber-400" />
                <span>13-Point Fault Matrix & FSM Resilience</span>
              </span>
              <span className="text-[9px] text-slate-500">Autonomous Self-Recovery</span>
            </div>

            <div className="grid grid-cols-3 gap-1.5 my-2 text-center text-[9px]">
              <div className="p-1.5 rounded bg-slate-950/80 border border-slate-800">
                <div className="text-slate-500 text-[8px]">ACTIVE FAULT</div>
                <div className="font-bold text-amber-300 truncate">
                  {report.fault_injection_stats.active_fault || 'NONE (CLEAN)'}
                </div>
              </div>
              <div className="p-1.5 rounded bg-slate-950/80 border border-slate-800">
                <div className="text-slate-500 text-[8px]">INJECTED</div>
                <div className="font-bold text-slate-200">
                  {report.fault_injection_stats.injected_count}
                </div>
              </div>
              <div className="p-1.5 rounded bg-slate-950/80 border border-slate-800">
                <div className="text-slate-500 text-[8px]">RECOVERED</div>
                <div className="font-bold text-emerald-400">
                  {report.fault_injection_stats.recovered_count}
                </div>
              </div>
            </div>

            <div className="p-1.5 rounded bg-slate-950/60 border border-slate-800/60 flex flex-col gap-0.5 text-[8px] text-slate-400">
              <div className="flex justify-between">
                <span>Orders Supervised:</span>
                <strong className="text-slate-200">{report.total_parent_orders}</strong>
              </div>
              <div className="flex justify-between">
                <span>SOR Slices Dispatched:</span>
                <strong className="text-slate-200">{report.total_slices_dispatched}</strong>
              </div>
              <div className="flex justify-between">
                <span>Unresolved Quantity:</span>
                <strong className="text-emerald-400">{report.unresolved_quantity_abs} (Exact 0)</strong>
              </div>
            </div>
          </div>

          <div className="text-[8px] text-slate-500 text-right pt-1 border-t border-slate-800/60">
            FSM Recovery Journal: SQLite <code>testnet_fsm_journal</code> Verified Green
          </div>
        </div>
      </div>
    </div>
  );
};
