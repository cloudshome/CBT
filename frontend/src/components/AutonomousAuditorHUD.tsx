import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import {
  Shield,
  Activity,
  AlertOctagon,
  CheckCircle2,
  RefreshCw,
  TrendingDown,
  AlertTriangle,
  Clock,
  Zap,
} from 'lucide-react';

interface SystemAuditHealthReport {
  timestamp_ms: number;
  total_trades_logged: number;
  active_burn_in_hours: number;
  cumulative_pnl_usd: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_execution_latency_ms: number;
  avg_slippage_bps: number;
  regime_drift_scores: Record<string, number>;
  quarantined_strategies: string[];
  governance_status: 'HEALTHY_OPTIMAL' | 'ELEVATED_DRIFT' | 'CRITICAL_QUARANTINE_TRIGGERED';
  recent_loss_autopsies: Array<{
    autopsy_id: string;
    trade_id: string;
    symbol: string;
    loss_usd: number;
    slippage_bps: number;
    loss_category: string;
    recommendation: string;
  }>;
  narrative: string;
}

interface AuditorDriftReport {
  timestamp_ms: number;
  status: string;
  quarantined_strategies: string[];
  regime_drift_scores: Record<string, number>;
}

export const AutonomousAuditorHUD: React.FC = () => {
  const [report, setReport] = useState<SystemAuditHealthReport | null>(null);
  const [drift, setDrift] = useState<AuditorDriftReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAuditorData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [telemetryRes, driftRes] = await Promise.all([
        api.getAuditorTelemetry(),
        api.getAuditorDrift(),
      ]);
      setReport(telemetryRes);
      setDrift(driftRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch auditor telemetry');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAuditorData();
    const interval = setInterval(fetchAuditorData, 20000);
    return () => clearInterval(interval);
  }, [fetchAuditorData]);

  const getGovernanceColor = (status?: string) => {
    if (status === 'CRITICAL_QUARANTINE_TRIGGERED') return 'text-rose-400 border-rose-500/40 bg-rose-500/10';
    if (status === 'ELEVATED_DRIFT') return 'text-amber-400 border-amber-500/40 bg-amber-500/10';
    return 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10';
  };

  return (
    <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4 text-xs font-mono select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#1e293b] pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
            <Shield size={16} />
          </div>
          <div>
            <h3 className="font-bold text-slate-100 text-sm tracking-wide flex items-center gap-2">
              24/7 Live Burn-In Telemetry & Autonomous Risk Auditor
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/40">
                FRONTIER 5
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Regime-conditional CUSUM expectancy drift, automatic loss autopsy dispatch & quarantine circuit
            </p>
          </div>
        </div>

        <button
          onClick={fetchAuditorData}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin text-emerald-400' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {error ? (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 flex items-center gap-2">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Column 1: Execution Telemetry Scorecard */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-3 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2.5">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <Activity size={13} className="text-emerald-400" />
                  Live Burn-In Telemetry
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${getGovernanceColor(
                    report?.governance_status
                  )}`}
                >
                  {report?.governance_status?.replace(/_/g, ' ') || 'HEALTHY'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px] mb-2">
                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400">Total Trades Logged:</span>
                  <span className="text-sm font-bold text-slate-200">
                    {report?.total_trades_logged ?? 0}
                  </span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400">Burn-In Active:</span>
                  <span className="text-sm font-bold text-slate-200">
                    {report?.active_burn_in_hours ? `${report.active_burn_in_hours.toFixed(1)} hrs` : '--'}
                  </span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400">Avg Fill Latency:</span>
                  <span className="text-sm font-bold text-slate-200">
                    {report?.avg_execution_latency_ms ? `${report.avg_execution_latency_ms.toFixed(1)} ms` : '--'}
                  </span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400">Realized Slippage:</span>
                  <span className="text-sm font-bold text-slate-200">
                    {report?.avg_slippage_bps ? `${report.avg_slippage_bps.toFixed(2)} bps` : '--'}
                  </span>
                </div>
              </div>

              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/80 flex justify-between items-center text-[11px]">
                <span className="text-slate-400">Cumulative Realized PnL:</span>
                <span
                  className={`font-bold ${
                    (report?.cumulative_pnl_usd ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  \${report?.cumulative_pnl_usd ? report.cumulative_pnl_usd.toFixed(2) : '0.00'}
                </span>
              </div>
            </div>

            <div className="text-[10px] text-slate-400 bg-slate-900/30 p-1.5 rounded border border-slate-800/40 flex items-center gap-1">
              <Clock size={11} className="text-slate-500" />
              <span>Continuous 24/7 background auditor actively logging shadow execution.</span>
            </div>
          </div>

          {/* Column 2: Regime-Conditional Expectancy Drift & Quarantine Circuit */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2.5 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <Zap size={13} className="text-emerald-400" />
                  CUSUM Expectancy Drift
                </span>
                <span className="text-[10px] text-slate-400">4 Regimes</span>
              </div>

              <div className="flex flex-col gap-1.5">
                {[
                  'TRENDING_BULL',
                  'TRENDING_BEAR',
                  'RANGING_COMPRESSION',
                  'HIGH_VOLATILITY_EXPANSION',
                ].map((regime) => {
                  const driftScore = report?.regime_drift_scores?.[regime] ?? 0;
                  const isHighDrift = driftScore > 2.5;

                  return (
                    <div
                      key={regime}
                      className={`p-1.5 rounded border text-[10px] flex items-center justify-between ${
                        isHighDrift
                          ? 'bg-rose-500/10 border-rose-500/40 text-rose-300'
                          : 'bg-slate-900/40 border-slate-800 text-slate-300'
                      }`}
                    >
                      <span className="font-semibold">{regime.replace(/_/g, ' ')}</span>
                      <div className="flex items-center gap-2">
                        <span>Drift: {driftScore.toFixed(2)}σ</span>
                        <span className="font-bold">
                          {isHighDrift ? '⚠️ QUARANTINE' : '✅ STABLE'}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quarantined Strategies Indicator */}
            <div className="pt-2 border-t border-slate-800">
              <div className="text-[10px] text-slate-400 font-semibold mb-1 flex items-center gap-1">
                <AlertOctagon size={11} className="text-rose-400" />
                Quarantined Strategies:
              </div>
              {drift?.quarantined_strategies && drift.quarantined_strategies.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {drift.quarantined_strategies.map((strat, i) => (
                    <span
                      key={i}
                      className="text-[9px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 font-bold"
                    >
                      {strat}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-emerald-400 font-semibold flex items-center gap-1">
                  <CheckCircle2 size={11} />
                  <span>Zero strategies quarantined. Expectancy healthy.</span>
                </div>
              )}
            </div>
          </div>

          {/* Column 3: Automated Real-time Forensic Loss Autopsies */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <TrendingDown size={13} className="text-rose-400" />
                  Forensic Loss Autopsies
                </span>
                <span className="text-[10px] text-slate-400">11 Categories</span>
              </div>

              <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-1">
                {report?.recent_loss_autopsies && report.recent_loss_autopsies.length > 0 ? (
                  report.recent_loss_autopsies.slice(0, 3).map((autopsy) => (
                    <div
                      key={autopsy.autopsy_id}
                      className="p-1.5 rounded bg-slate-900/60 border border-slate-800 text-[10px] flex flex-col gap-0.5"
                    >
                      <div className="flex justify-between font-bold">
                        <span className="text-slate-300">{autopsy.symbol}</span>
                        <span className="text-rose-400">-\${autopsy.loss_usd.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-[9px] text-slate-400">
                        <span className="text-amber-400 font-semibold">{autopsy.loss_category}</span>
                        <span>{autopsy.slippage_bps.toFixed(1)} bps slip</span>
                      </div>
                      <div className="text-[9px] text-slate-500 italic truncate">
                        {autopsy.recommendation}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-[10px] text-slate-500 italic p-3 text-center">
                    No forensic loss events recorded.
                  </div>
                )}
              </div>
            </div>

            <div className="text-[10px] text-slate-400 border-t border-slate-800 pt-2 flex items-center gap-1">
              <CheckCircle2 size={11} className="text-emerald-400" />
              <span>Event-driven loss autopsies automatically published to immutable AuditBus.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AutonomousAuditorHUD;
