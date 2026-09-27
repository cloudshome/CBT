import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import {
  Layers,
  Activity,
  Zap,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  Eye,
  ShieldAlert,
} from 'lucide-react';

interface MicrostructureAnalyticsData {
  symbol: string;
  timestamp_ms: number;
  mid_price: number;
  spread_bps: number;
  depth_tiers: Record<string, number>;
  decay_weighted_imbalance: number;
  bid_slope_elasticity: number;
  ask_slope_elasticity: number;
  elasticity_asymmetry_ratio: number;
  icebergs_detected: Array<{
    side: string;
    price: number;
    executed_vol: number;
    apparent_depth: number;
    absorption_ratio: number;
  }>;
}

interface FlowToxicityData {
  symbol: string;
  timestamp_ms: number;
  vpin: number;
  vpin_regime: 'LOW_TOXICITY' | 'NORMAL' | 'ELEVATED' | 'HIGH_TOXICITY_ADVERSE_SELECTION';
  kyles_lambda: number;
  hasbrouck_lambda: number;
  toxicity_confidence: number;
}

interface MicrostructurePanelProps {
  symbol: string;
  currentPrice?: number;
}

export const MicrostructurePanel: React.FC<MicrostructurePanelProps> = ({
  symbol,
}) => {
  const [analytics, setAnalytics] = useState<MicrostructureAnalyticsData | null>(null);
  const [toxicity, setToxicity] = useState<FlowToxicityData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMicrostructure = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [analyticsRes, toxicityRes] = await Promise.all([
        api.getMicrostructureAnalytics(symbol),
        api.getMicrostructureToxicity(symbol),
      ]);
      setAnalytics(analyticsRes);
      setToxicity(toxicityRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch microstructure analytics');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchMicrostructure();
    const interval = setInterval(fetchMicrostructure, 15000);
    return () => clearInterval(interval);
  }, [fetchMicrostructure]);

  const getVpinColor = (vpin: number) => {
    if (vpin >= 0.7) return 'text-rose-400 bg-rose-500/10 border-rose-500/30';
    if (vpin >= 0.45) return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
    return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
  };

  const getVpinBarWidth = (vpin: number) => {
    return `${Math.min(100, Math.max(0, vpin * 100))}%`;
  };

  return (
    <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4 text-xs font-mono select-none">
      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-[#1e293b] pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-400">
            <Layers size={16} />
          </div>
          <div>
            <h3 className="font-bold text-slate-100 text-sm tracking-wide flex items-center gap-2">
              L2/L3 Microstructure & Flow Toxicity Alpha
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 font-semibold border border-sky-500/40">
                FRONTIER 1
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Depth slope elasticity (dQ/dP), VPIN toxicity & institutional iceberg absorption
            </p>
          </div>
        </div>

        <button
          onClick={fetchMicrostructure}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin text-sky-400' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {error ? (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 flex items-center gap-2">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Card 1: Multi-Tier Depth Imbalance Profile */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
              <span className="text-slate-300 font-bold flex items-center gap-1.5">
                <Activity size={13} className="text-sky-400" />
                Depth Imbalance Profile
              </span>
              <span className="text-[10px] text-slate-400">
                Decay Weighted: {analytics ? `${(analytics.decay_weighted_imbalance * 100).toFixed(1)}%` : '--'}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              {['L1', 'L5', 'L10', 'L20', 'L50'].map((tier) => {
                const imb = analytics?.depth_tiers?.[tier] ?? 0;
                const isBidDominant = imb >= 0;
                const percentBid = ((imb + 1) / 2) * 100;

                return (
                  <div key={tier} className="flex flex-col gap-0.5">
                    <div className="flex justify-between text-[10px] text-slate-400">
                      <span>Tier {tier}</span>
                      <span className={isBidDominant ? 'text-emerald-400' : 'text-rose-400'}>
                        {isBidDominant ? `+${(imb * 100).toFixed(1)}% Bid` : `${(imb * 100).toFixed(1)}% Ask`}
                      </span>
                    </div>
                    {/* Visual Bid/Ask Split Bar */}
                    <div className="h-1.5 w-full bg-rose-900/40 rounded overflow-hidden flex">
                      <div
                        className="h-full bg-emerald-500 transition-all duration-500"
                        style={{ width: `${percentBid}%` }}
                      />
                      <div
                        className="h-full bg-rose-500 transition-all duration-500"
                        style={{ width: `${100 - percentBid}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="pt-2 border-t border-slate-800/60 flex justify-between text-[11px]">
              <span className="text-slate-400">Spread:</span>
              <span className="text-slate-200 font-bold">{analytics?.spread_bps?.toFixed(2) ?? '--'} bps</span>
            </div>
          </div>

          {/* Card 2: Order Book Slope Elasticity & Stiffness */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-3 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-3">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <Zap size={13} className="text-amber-400" />
                  Slope Elasticity (dQ/dP)
                </span>
                <span className="text-[10px] text-slate-400">Stiffness Metric</span>
              </div>

              <div className="grid grid-cols-2 gap-2 mb-3">
                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-[10px] text-slate-400 flex items-center gap-1">
                    <TrendingUp size={11} className="text-emerald-400" />
                    Bid Slope
                  </span>
                  <span className="text-sm font-bold text-emerald-400">
                    {analytics?.bid_slope_elasticity?.toFixed(2) ?? '--'}
                  </span>
                  <span className="text-[9px] text-slate-500">Qty / \$1 Price</span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-[10px] text-slate-400 flex items-center gap-1">
                    <TrendingDown size={11} className="text-rose-400" />
                    Ask Slope
                  </span>
                  <span className="text-sm font-bold text-rose-400">
                    {analytics?.ask_slope_elasticity?.toFixed(2) ?? '--'}
                  </span>
                  <span className="text-[9px] text-slate-500">Qty / \$1 Price</span>
                </div>
              </div>

              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/80 flex flex-col gap-1 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-400">Asymmetry Ratio:</span>
                  <span className="text-slate-200 font-bold">
                    {analytics?.elasticity_asymmetry_ratio?.toFixed(3) ?? '--'}
                  </span>
                </div>
                <div className="text-[10px] text-slate-500">
                  {analytics && analytics.elasticity_asymmetry_ratio > 1.2
                    ? '🟢 Strong bid support cushion (Upward bias)'
                    : analytics && analytics.elasticity_asymmetry_ratio < 0.8
                    ? '🔴 Dense ask resistance ceiling (Downward bias)'
                    : '⚪ Balanced book liquidity elasticity'}
                </div>
              </div>
            </div>

            {/* Iceberg Footprints */}
            <div className="pt-2 border-t border-slate-800">
              <div className="text-[10px] text-slate-400 font-semibold mb-1 flex items-center gap-1">
                <Eye size={11} className="text-indigo-400" />
                Institutional Iceberg Footprints
              </div>
              {analytics?.icebergs_detected && analytics.icebergs_detected.length > 0 ? (
                <div className="flex flex-col gap-1">
                  {analytics.icebergs_detected.slice(0, 2).map((ice, i) => (
                    <div
                      key={i}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 flex justify-between"
                    >
                      <span>
                        {ice.side} @ \${ice.price.toFixed(2)}
                      </span>
                      <span className="font-bold">{ice.absorption_ratio.toFixed(1)}x depth absorption</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[10px] text-slate-500 italic">No iceberg absorption active</div>
              )}
            </div>
          </div>

          {/* Card 3: Continuous VPIN & Kyle's Lambda Toxicity */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-3 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-3">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <ShieldAlert size={13} className="text-rose-400" />
                  Flow Toxicity & Adverse Selection
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${
                    toxicity ? getVpinColor(toxicity.vpin) : 'text-slate-400 border-slate-700'
                  }`}
                >
                  {toxicity?.vpin_regime || 'CALCULATING'}
                </span>
              </div>

              {/* VPIN Gauge */}
              <div className="flex flex-col gap-1.5 mb-3">
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-400 text-[11px]">VPIN Index:</span>
                  <span className="text-base font-bold text-slate-100">
                    {toxicity?.vpin?.toFixed(3) ?? '--'}
                  </span>
                </div>
                <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      toxicity && toxicity.vpin >= 0.7
                        ? 'bg-rose-500'
                        : toxicity && toxicity.vpin >= 0.45
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{ width: toxicity ? getVpinBarWidth(toxicity.vpin) : '0%' }}
                  />
                </div>
                <div className="flex justify-between text-[9px] text-slate-500">
                  <span>0.0 (Passive Flow)</span>
                  <span>0.5</span>
                  <span>1.0 (Toxic Sweep)</span>
                </div>
              </div>

              {/* Kyle's Lambda Impact Metric */}
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400">Kyle's Lambda:</span>
                  <span className="text-slate-200 font-bold text-xs">
                    {toxicity?.kyles_lambda ? `${(toxicity.kyles_lambda * 1e4).toFixed(3)}` : '--'}
                  </span>
                  <span className="text-[9px] text-slate-500">bps per \$10k</span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400">Confidence:</span>
                  <span className="text-slate-200 font-bold text-xs">
                    {toxicity?.toxicity_confidence ? `${(toxicity.toxicity_confidence * 100).toFixed(0)}%` : '--'}
                  </span>
                  <span className="text-[9px] text-slate-500">Statistical Power</span>
                </div>
              </div>
            </div>

            <div className="text-[10px] text-slate-400 bg-slate-900/30 p-1.5 rounded border border-slate-800/40">
              💡 <span className="font-semibold text-slate-300">Desk Rule:</span> When VPIN &gt; 0.65, passive limit orders face severe adverse selection. SOR switches to IOC sweeps or Almgren-Chriss liquidation.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MicrostructurePanel;
