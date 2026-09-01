import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import {
  Globe,
  TrendingUp,
  Activity,
  AlertTriangle,
  RefreshCw,
  Zap,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';

interface MacroNetworkData {
  timestamp_ms: number;
  assets: string[];
  correlation_matrix: Record<string, Record<string, number>>;
  pca_explained_variance_ratio: number[];
  systemic_absorption_ratio: number;
  systemic_fragility_index: number;
  fragility_regime: 'BENIGN' | 'MODERATE' | 'ELEVATED' | 'CRITICAL_FRAGILITY_RISK_OFF';
  granger_lead_lag: Array<{
    leader: string;
    follower: string;
    f_statistic: number;
    p_value: number;
    lag_bars: number;
    is_significant: boolean;
  }>;
}

interface MacroSpilloverData {
  timestamp_ms: number;
  fragility_index: number;
  fragility_regime: string;
  absorption_ratio: number;
  gold_btc_correlation: number;
  spillover_narrative: string;
}

export const MacroNetworkRadar: React.FC = () => {
  const [network, setNetwork] = useState<MacroNetworkData | null>(null);
  const [spillover, setSpillover] = useState<MacroSpilloverData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMacroData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [netRes, spilRes] = await Promise.all([
        api.getMacroNetwork(),
        api.getMacroSpillover(),
      ]);
      setNetwork(netRes);
      setSpillover(spilRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch macro network data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMacroData();
    const interval = setInterval(fetchMacroData, 30000);
    return () => clearInterval(interval);
  }, [fetchMacroData]);

  const getCorrelationColor = (val: number) => {
    if (val >= 0.7) return 'bg-emerald-500/30 text-emerald-300';
    if (val >= 0.3) return 'bg-emerald-500/10 text-emerald-400';
    if (val <= -0.5) return 'bg-rose-500/30 text-rose-300';
    if (val <= -0.2) return 'bg-rose-500/10 text-rose-400';
    return 'bg-slate-800/40 text-slate-300';
  };

  const getFragilityColor = (regime?: string) => {
    if (regime === 'CRITICAL_FRAGILITY_RISK_OFF') return 'text-rose-400 border-rose-500/40 bg-rose-500/10';
    if (regime === 'ELEVATED') return 'text-amber-400 border-amber-500/40 bg-amber-500/10';
    return 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10';
  };

  return (
    <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4 text-xs font-mono select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#1e293b] pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400">
            <Globe size={16} />
          </div>
          <div>
            <h3 className="font-bold text-slate-100 text-sm tracking-wide flex items-center gap-2">
              Multi-Asset Macro Cross-Correlation & Regime Network
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold border border-amber-500/40">
                FRONTIER 2
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Gold (PAXG), DXY, Yield spillover, PCA Systemic Absorption & Granger Lead-Lag causality
            </p>
          </div>
        </div>

        <button
          onClick={fetchMacroData}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin text-amber-400' : ''} />
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
          {/* Column 1: Correlation Matrix Heatmap */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2.5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
              <span className="text-slate-300 font-bold flex items-center gap-1.5">
                <Activity size={13} className="text-amber-400" />
                Cross-Asset Correlation Matrix
              </span>
              <span className="text-[10px] text-slate-400">Rolling Pearson</span>
            </div>

            {network?.assets && (
              <div className="overflow-x-auto">
                <table className="w-full text-center text-[10px] border-collapse">
                  <thead>
                    <tr>
                      <th className="p-1 text-slate-500 text-left font-normal">Asset</th>
                      {network.assets.map((a) => (
                        <th key={a} className="p-1 text-slate-400 font-semibold">
                          {a.replace('/USDT', '')}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {network.assets.map((rowAsset) => (
                      <tr key={rowAsset} className="border-t border-slate-800/40">
                        <td className="p-1 text-slate-400 text-left font-semibold">
                          {rowAsset.replace('/USDT', '')}
                        </td>
                        {network.assets.map((colAsset) => {
                          const val = network.correlation_matrix?.[rowAsset]?.[colAsset] ?? 1.0;
                          return (
                            <td key={colAsset} className="p-1">
                              <span
                                className={`inline-block w-9 py-0.5 rounded font-mono font-semibold ${getCorrelationColor(
                                  val
                                )}`}
                              >
                                {val.toFixed(2)}
                              </span>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="pt-2 border-t border-slate-800 flex justify-between text-[11px]">
              <span className="text-slate-400">Gold/BTC Correlation:</span>
              <span
                className={`font-bold ${
                  (spillover?.gold_btc_correlation ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {spillover?.gold_btc_correlation !== undefined
                  ? spillover.gold_btc_correlation.toFixed(3)
                  : '--'}
              </span>
            </div>
          </div>

          {/* Column 2: PCA Systemic Absorption & Fragility Index */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-3 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2.5">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <Zap size={13} className="text-amber-400" />
                  Systemic Macro Fragility
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${getFragilityColor(
                    network?.fragility_regime
                  )}`}
                >
                  {network?.fragility_regime?.replace(/_/g, ' ') || 'BENIGN'}
                </span>
              </div>

              {/* Fragility Index Meter */}
              <div className="flex flex-col gap-1 mb-3">
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-400 text-[11px]">Fragility Index:</span>
                  <span className="text-base font-bold text-slate-100">
                    {network ? `${(network.systemic_fragility_index * 100).toFixed(1)}%` : '--'}
                  </span>
                </div>
                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      network && network.systemic_fragility_index >= 0.7
                        ? 'bg-rose-500'
                        : network && network.systemic_fragility_index >= 0.4
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{
                      width: network
                        ? `${Math.min(100, Math.max(0, network.systemic_fragility_index * 100))}%`
                        : '0%',
                    }}
                  />
                </div>
              </div>

              {/* PCA Absorption Ratio */}
              <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col gap-1 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-400">PCA Absorption Ratio (PC1+PC2):</span>
                  <span className="text-slate-200 font-bold">
                    {network ? `${(network.systemic_absorption_ratio * 100).toFixed(1)}%` : '--'}
                  </span>
                </div>
                <div className="text-[10px] text-slate-500">
                  {network && network.systemic_absorption_ratio > 0.75
                    ? '⚠️ High systemic coupling: macro shocks dominate crypto idiosyncratic alpha.'
                    : '✅ Healthy market dispersion: crypto fundamentals decoupling.'}
                </div>
              </div>
            </div>

            <div className="p-2 bg-slate-900/30 rounded border border-slate-800/40 text-[10px] text-slate-400">
              {spillover?.spillover_narrative || 'Macro cross-asset correlation network stable.'}
            </div>
          </div>

          {/* Column 3: Directional Granger Lead-Lag Causality */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2.5 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <TrendingUp size={13} className="text-amber-400" />
                  Lead-Lag Granger Causality
                </span>
                <span className="text-[10px] text-slate-400">VAR F-Tests</span>
              </div>

              <div className="flex flex-col gap-1.5">
                {network?.granger_lead_lag && network.granger_lead_lag.length > 0 ? (
                  network.granger_lead_lag.slice(0, 4).map((rel, idx) => (
                    <div
                      key={idx}
                      className={`p-1.5 rounded border text-[10px] flex items-center justify-between ${
                        rel.is_significant
                          ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                          : 'bg-slate-900/40 border-slate-800 text-slate-400'
                      }`}
                    >
                      <div className="flex items-center gap-1 font-semibold">
                        <span>{rel.leader.replace('/USDT', '')}</span>
                        <ArrowRight size={11} className="text-slate-500" />
                        <span>{rel.follower.replace('/USDT', '')}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span>Lag: {rel.lag_bars}b</span>
                        <span className="font-bold">
                          {rel.is_significant ? 'p < 0.05 ★' : `p=${rel.p_value.toFixed(2)}`}
                        </span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-[10px] text-slate-500 italic p-2">
                    Calibrating VAR lead-lag regression vectors...
                  </div>
                )}
              </div>
            </div>

            <div className="text-[10px] text-slate-500 border-t border-slate-800 pt-2 flex items-center gap-1">
              <ShieldAlert size={11} className="text-amber-400" />
              <span>Directional causality signals inform dynamic hedge ratios.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MacroNetworkRadar;
