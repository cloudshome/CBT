import React, { useState, useEffect, useCallback } from 'react';
import { api, BurnInStatus, HFTelemetryMetrics, IncidentEscalation } from '../services/api';
import {
  Shield,
  Activity,
  AlertOctagon,
  CheckCircle2,
  RefreshCw,
  AlertTriangle,
  Clock,
  Zap,
  Play,
  Pause,
  RotateCcw,
  Flame,
  Radio,
  Sliders,
} from 'lucide-react';

export const ShadowBurnInHUD: React.FC = () => {
  const [status, setStatus] = useState<BurnInStatus | null>(null);
  const [metrics, setMetrics] = useState<HFTelemetryMetrics | null>(null);
  const [incidents, setIncidents] = useState<IncidentEscalation[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [simTier, setSimTier] = useState<string>('WARNING');
  const [actionInProgress, setActionInProgress] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, metricsRes, incidentsRes] = await Promise.all([
        api.getBurnInStatus(),
        api.getHFTelemetryMetrics(),
        api.getIncidentEscalations(15),
      ]);
      setStatus(statusRes);
      setMetrics(metricsRes.metrics);
      setIncidents(incidentsRes.incidents);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch canary burn-in telemetry');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleToggle = async (action: string) => {
    try {
      setActionInProgress(true);
      await api.toggleBurnIn(action);
      await fetchData();
    } catch (err: any) {
      setError(err?.message || `Failed to execute ${action}`);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleSimulateChaos = async () => {
    try {
      setActionInProgress(true);
      await api.simulateIncidentTrigger({
        tier: simTier,
        description: `Simulated operator chaos event [${simTier}]`,
        trigger_value: 99.5,
        threshold_value: 50.0,
      });
      await fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to trigger chaos event');
    } finally {
      setActionInProgress(false);
    }
  };

  const handleResolve = async (incidentId: string) => {
    try {
      await api.resolveIncident(incidentId, 'ADMIN', 'Resolved from HUD');
      await fetchData();
    } catch (err: any) {
      setError(err?.message || 'Failed to resolve incident');
    }
  };

  const getStateColor = (state: string) => {
    switch (state) {
      case 'RUNNING':
        return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'DEGRADED':
        return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
      case 'PAUSED':
        return 'text-blue-400 bg-blue-500/10 border-blue-500/20';
      case 'HALTED':
      case 'READ_ONLY':
        return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
      default:
        return 'text-gray-400 bg-gray-500/10 border-gray-500/20';
    }
  };

  const getTierBadge = (tier: string) => {
    switch (tier) {
      case 'EMERGENCY':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40 animate-pulse';
      case 'CRITICAL':
        return 'bg-orange-500/20 text-orange-300 border-orange-500/40';
      case 'WARNING':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      default:
        return 'bg-blue-500/20 text-blue-300 border-blue-500/40';
    }
  };

  return (
    <div className="bg-[#0B0E14] border border-[#1F2430] rounded-lg p-5 font-mono text-xs text-[#E6EDF3] shadow-2xl space-y-6">
      {/* 1. Header & Execution Mode Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-4 border-b border-[#1F2430]">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Flame className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold tracking-wider text-white uppercase">
                Phase 16 — Live Canary / Shadow Burn-In
              </h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                SHADOW [ISOLATED]
              </span>
            </div>
            <p className="text-[11px] text-[#8B949E] mt-0.5">
              Continuous session-aware paper execution, 30s heartbeat watchdog & 3-factor slippage attribution
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 rounded-md text-xs font-bold border ${getStateColor(
              status?.state || 'STOPPED'
            )}`}
          >
            {status?.state || 'STOPPED'}
          </span>
          <button
            onClick={fetchData}
            disabled={loading}
            className="p-1.5 rounded bg-[#161B22] border border-[#30363D] hover:bg-[#21262D] text-[#8B949E] hover:text-white transition"
            title="Refresh Telemetry"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-400' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-rose-400 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 2. Market Session & Heartbeat KPI Ribbon */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[#12161F] border border-[#1F2430] rounded p-3">
          <div className="flex items-center justify-between text-[#8B949E] mb-1">
            <span>ACTIVE SESSION</span>
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="text-base font-bold text-white tracking-wide">
            {status?.current_session || 'ASIA'}
          </div>
          <div className="text-[10px] text-indigo-400 mt-1 flex items-center justify-between">
            <span>Next: {status?.next_session || 'LONDON'}</span>
            <span>{Math.floor((status?.next_session_countdown_sec || 0) / 3600)}h left</span>
          </div>
        </div>

        <div className="bg-[#12161F] border border-[#1F2430] rounded p-3">
          <div className="flex items-center justify-between text-[#8B949E] mb-1">
            <span>BURN-IN UPTIME</span>
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-base font-bold text-emerald-400">
            {status?.burn_in_hours || 0.0} <span className="text-xs font-normal text-[#8B949E]">hours</span>
          </div>
          <div className="text-[10px] text-[#8B949E] mt-1">
            Target: 72.0h Canary Acceptance
          </div>
        </div>

        <div className="bg-[#12161F] border border-[#1F2430] rounded p-3">
          <div className="flex items-center justify-between text-[#8B949E] mb-1">
            <span>HEARTBEAT WATCHDOG</span>
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-base font-bold text-cyan-400">
            {status?.heartbeat_health_pct || 100.0}%
          </div>
          <div className="text-[10px] text-[#8B949E] mt-1">
            Seq #{status?.heartbeat_sequence || 0} ({status?.heartbeats_received || 0} recv / {status?.heartbeats_missed || 0} missed)
          </div>
        </div>

        <div className="bg-[#12161F] border border-[#1F2430] rounded p-3">
          <div className="flex items-center justify-between text-[#8B949E] mb-1">
            <span>SHADOW EQUITY</span>
            <Shield className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-base font-bold text-white">
            ${(status?.virtual_equity || 100000).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className={`text-[10px] mt-1 font-semibold ${(status?.total_realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            Realized PnL: ${(status?.total_realized_pnl || 0) >= 0 ? '+' : ''}{(status?.total_realized_pnl || 0).toFixed(2)}
          </div>
        </div>
      </div>

      {/* 3. Telemetry & 3-Factor Slippage Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Latency Percentiles */}
        <div className="bg-[#12161F] border border-[#1F2430] rounded p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-[#1F2430] pb-2">
            <span className="font-bold text-white uppercase text-[11px] flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-400" /> Execution Latency Decomposition
            </span>
            <span className="text-[10px] text-[#8B949E]">
              Samples: {metrics?.sample_count || 0}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center pt-1">
            <div className="bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
              <div className="text-[10px] text-[#8B949E]">P50 LATENCY</div>
              <div className="text-sm font-bold text-emerald-400 mt-0.5">
                {metrics?.latency_p50_ms !== null ? `${metrics?.latency_p50_ms} ms` : 'nominal'}
              </div>
            </div>
            <div className="bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
              <div className="text-[10px] text-[#8B949E]">P95 LATENCY</div>
              <div className="text-sm font-bold text-amber-400 mt-0.5">
                {metrics?.latency_p95_ms !== null ? `${metrics?.latency_p95_ms} ms` : 'nominal'}
              </div>
            </div>
            <div className="bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
              <div className="text-[10px] text-[#8B949E]">P99 LATENCY</div>
              <div className="text-sm font-bold text-rose-400 mt-0.5">
                {metrics?.latency_p99_ms !== null ? `${metrics?.latency_p99_ms} ms` : 'nominal'}
              </div>
            </div>
          </div>

          <div className="text-[10px] text-[#8B949E] bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
            <span className="text-indigo-400 font-semibold">Monotonic Pipeline:</span> t_recv → t_queue → t_decision → t_exec. Ring Buffer: {metrics?.ring_buffer_occupancy || 0} / {metrics?.ring_buffer_size || 1000} records.
          </div>
        </div>

        {/* 3-Factor Slippage Attribution */}
        <div className="bg-[#12161F] border border-[#1F2430] rounded p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-[#1F2430] pb-2">
            <span className="font-bold text-white uppercase text-[11px] flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-cyan-400" /> 3-Factor Slippage Attribution
            </span>
            <span className="text-[10px] text-cyan-400 font-bold">
              Total: {metrics?.avg_slippage_total_bps !== null ? `${metrics?.avg_slippage_total_bps} bps` : '0.0 bps'}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center pt-1">
            <div className="bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
              <div className="text-[10px] text-[#8B949E]">SPREAD COST</div>
              <div className="text-sm font-bold text-white mt-0.5">
                {metrics?.avg_slippage_spread_bps !== null ? `${metrics?.avg_slippage_spread_bps} bps` : '0.0 bps'}
              </div>
            </div>
            <div className="bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
              <div className="text-[10px] text-[#8B949E]">MARKET IMPACT</div>
              <div className="text-sm font-bold text-indigo-400 mt-0.5">
                {metrics?.avg_slippage_impact_bps !== null ? `${metrics?.avg_slippage_impact_bps} bps` : '0.0 bps'}
              </div>
            </div>
            <div className="bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
              <div className="text-[10px] text-[#8B949E]">LATENCY DRIFT</div>
              <div className="text-sm font-bold text-amber-400 mt-0.5">
                {metrics?.avg_slippage_latency_bps !== null ? `${metrics?.avg_slippage_latency_bps} bps` : '0.0 bps'}
              </div>
            </div>
          </div>

          <div className="text-[10px] text-[#8B949E] bg-[#0B0E14] p-2 rounded border border-[#1F2430]">
            <span className="text-cyan-400 font-semibold">Attribution Contract:</span> Spread = |Quote - Mid|. Impact = Y·σ·√(Order/ADV). Drift = |Exec - Quote|.
          </div>
        </div>
      </div>

      {/* 4. Incident Escalation Log */}
      <div className="bg-[#12161F] border border-[#1F2430] rounded p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-[#1F2430] pb-2">
          <span className="font-bold text-white uppercase text-[11px] flex items-center gap-1.5">
            <AlertOctagon className="w-3.5 h-3.5 text-rose-400" /> 4-Tier Incident Escalation Bus
          </span>
          <span className="text-[10px] text-[#8B949E]">
            Active / Historical Incidents ({incidents.length})
          </span>
        </div>

        {incidents.length === 0 ? (
          <div className="p-4 text-center text-[#8B949E] text-xs">
            <CheckCircle2 className="w-6 h-6 text-emerald-400 mx-auto mb-1 opacity-75" />
            Zero active incidents. All system health, latency, and CUSUM sentinels nominal.
          </div>
        ) : (
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {incidents.map((inc) => (
              <div
                key={inc.incident_id}
                className="bg-[#0B0E14] border border-[#1F2430] rounded p-2.5 flex items-center justify-between gap-3 text-[11px]"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${getTierBadge(inc.tier)}`}>
                    {inc.tier}
                  </span>
                  <div className="truncate">
                    <div className="text-white font-medium truncate">{inc.description}</div>
                    <div className="text-[9px] text-[#8B949E]">
                      {new Date(inc.timestamp).toLocaleTimeString()} • {inc.source_engine} • Action: {inc.automated_action}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {inc.resolved === 0 ? (
                    <button
                      onClick={() => handleResolve(inc.incident_id)}
                      className="px-2 py-1 rounded bg-[#161B22] border border-[#30363D] hover:bg-emerald-500/20 hover:text-emerald-300 text-[10px] text-[#8B949E] transition"
                    >
                      Acknowledge
                    </button>
                  ) : (
                    <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Resolved
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 5. Operator Control Panel */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-[#12161F] border border-[#1F2430] rounded">
        <div className="flex items-center gap-2">
          <span className="text-[#8B949E] text-[11px]">OPERATOR CONTROLS:</span>
          <button
            onClick={() => handleToggle('start')}
            disabled={actionInProgress || status?.state === 'RUNNING'}
            className="px-3 py-1 rounded bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-40"
          >
            <Play className="w-3 h-3" /> Start
          </button>
          <button
            onClick={() => handleToggle('pause')}
            disabled={actionInProgress || status?.state !== 'RUNNING'}
            className="px-3 py-1 rounded bg-amber-500/20 border border-amber-500/30 text-amber-300 hover:bg-amber-500/30 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-40"
          >
            <Pause className="w-3 h-3" /> Pause
          </button>
          <button
            onClick={() => handleToggle('recover')}
            disabled={actionInProgress || !['HALTED', 'READ_ONLY'].includes(status?.state || '')}
            className="px-3 py-1 rounded bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/30 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-40"
          >
            <RotateCcw className="w-3 h-3" /> Recover Halt
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[#8B949E] text-[11px]">CHAOS TEST:</span>
          <select
            value={simTier}
            onChange={(e) => setSimTier(e.target.value)}
            className="bg-[#0B0E14] border border-[#30363D] text-white rounded px-2 py-1 text-xs"
          >
            <option value="NOTICE">Tier 1: NOTICE</option>
            <option value="WARNING">Tier 2: WARNING</option>
            <option value="CRITICAL">Tier 3: CRITICAL</option>
            <option value="EMERGENCY">Tier 4: EMERGENCY</option>
          </select>
          <button
            onClick={handleSimulateChaos}
            disabled={actionInProgress}
            className="px-3 py-1 rounded bg-rose-500/20 border border-rose-500/30 text-rose-300 hover:bg-rose-500/30 text-xs font-semibold transition disabled:opacity-40"
          >
            Simulate
          </button>
        </div>
      </div>
    </div>
  );
};
