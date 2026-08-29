import React from 'react';
import { InstitutionalAlphaResponse } from '../types';
import {
  ShieldCheck,
  TrendingUp,
  Activity,
  Layers,
  Zap,
  Target,
  Compass,
  DollarSign,
  Flame,
} from 'lucide-react';

interface InstitutionalAlphaHUDProps {
  alphaData?: InstitutionalAlphaResponse | null;
  loading?: boolean;
}

export const InstitutionalAlphaHUD: React.FC<InstitutionalAlphaHUDProps> = ({
  alphaData,
  loading = false,
}) => {
  if (loading || !alphaData) {
    return (
      <div className="bg-[#080b11] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-500 animate-pulse flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-sky-400 animate-spin" />
          <span>Synthesizing 8 Institutional Alpha & Microstructure Mechanics...</span>
        </div>
      </div>
    );
  }

  const {
    decision,
    institutional_composite_score,
    lead_lag,
    cvd_absorption,
    orderbook_imbalance,
    oi_funding_squeeze,
    judas_sweep,
    vwap_multisigma,
    fractal_harmonics,
    half_kelly_sizing,
    narrative,
  } = alphaData;

  const isLong = decision === 'LONG';
  const isShort = decision === 'SHORT';

  return (
    <div className="bg-[#080b11] border border-[#1e293b] rounded-lg p-3.5 space-y-3 font-mono text-xs select-none">
      {/* Top Banner: Composite Decision & Score */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-sky-500/10 border border-sky-500/20 text-sky-400">
            <ShieldCheck size={16} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-slate-200 text-sm">Institutional Alpha Engine</span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider ${
                  isLong
                    ? 'bg-[#00f0a8]/15 text-[#00f0a8] border border-[#00f0a8]/40'
                    : isShort
                    ? 'bg-[#ff3b69]/15 text-[#ff3b69] border border-[#ff3b69]/40'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
              >
                {decision}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">{narrative}</p>
          </div>
        </div>

        {/* Score & Kelly Badge */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[10px] text-slate-500 block">ALPHA SCORE</span>
            <span
              className={`text-base font-black ${
                institutional_composite_score >= 70
                  ? 'text-[#00f0a8]'
                  : institutional_composite_score >= 50
                  ? 'text-sky-400'
                  : 'text-slate-400'
              }`}
            >
              {institutional_composite_score.toFixed(1)}/100
            </span>
          </div>

          <div className="text-right pl-3 border-l border-slate-800">
            <span className="text-[10px] text-slate-500 block">HALF-KELLY</span>
            <span className="text-sm font-bold text-purple-400">
              {(half_kelly_sizing.recommended_risk_pct * 100).toFixed(2)}% Risk
            </span>
          </div>
        </div>
      </div>

      {/* 8 Quantitative Mechanics Radar Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {/* 1. Cross-Asset Lead-Lag */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Compass size={11} className="text-sky-400" /> Lead-Lag</span>
            <span className="text-slate-300 font-bold">DXY: {lead_lag.dxy_price}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {lead_lag.signals[0]?.direction || 'NEUTRAL'} ({lead_lag.signals[0]?.expected_lead_window_mins || '3-5m'})
          </p>
        </div>

        {/* 2. CVD Absorption */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Activity size={11} className="text-emerald-400" /> Order Flow CVD</span>
            <span className={cvd_absorption.current_cvd >= 0 ? 'text-[#00f0a8]' : 'text-[#ff3b69]'}>
              {cvd_absorption.current_cvd > 0 ? '+' : ''}{cvd_absorption.current_cvd}
            </span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {cvd_absorption.absorption_type.replace(/_/g, ' ')}
          </p>
        </div>

        {/* 3. L2 OBI & VPIN */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Zap size={11} className="text-amber-400" /> OBI & VPIN</span>
            <span className="text-slate-300 font-bold">
              {orderbook_imbalance.obi_score > 0 ? '+' : ''}{(orderbook_imbalance.obi_score * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            VPIN: {(orderbook_imbalance.flow_toxicity_vpin * 100).toFixed(0)}% ({orderbook_imbalance.regime.split('_')[0]})
          </p>
        </div>

        {/* 4. OI & Funding Squeeze */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Flame size={11} className="text-rose-400" /> OI Squeeze</span>
            <span className="text-slate-300 font-bold">{oi_funding_squeeze.funding_rate_annualized_pct.toFixed(1)}% APR</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {oi_funding_squeeze.squeeze_risk.replace(/_/g, ' ')}
          </p>
        </div>

        {/* 5. Judas Liquidity Sweep */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Target size={11} className="text-purple-400" /> Judas Trap</span>
            <span className="text-slate-300 font-bold">{judas_sweep.session_name.replace(/_OPEN/g, '')}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {judas_sweep.sweep_direction.replace(/_SWEEP/g, '')}
          </p>
        </div>

        {/* 6. Multi-Sigma VWAP */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><TrendingUp size={11} className="text-sky-400" /> VWAP Bands</span>
            <span className="text-slate-300 font-bold">${vwap_multisigma.vwap.toFixed(0)}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            Dev: {vwap_multisigma.deviation_sigmas.toFixed(2)}σ (Rev {Math.round(vwap_multisigma.mean_reversion_prob * 100)}%)
          </p>
        </div>

        {/* 7. Fractal Harmonics */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Layers size={11} className="text-indigo-400" /> Harmonics</span>
            <span className="text-slate-300 font-bold">{fractal_harmonics.dominant_direction}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            Confluence: {Math.round(fractal_harmonics.harmonic_confluence_score * 100)}% (1D+15m+1m)
          </p>
        </div>

        {/* 8. Bayesian Half-Kelly Sizer */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><DollarSign size={11} className="text-emerald-400" /> Kelly Size</span>
            <span className="text-[#00f0a8] font-bold">${half_kelly_sizing.max_dollar_loss.toFixed(0)} max loss</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            R:R {half_kelly_sizing.risk_reward_ratio}R ({half_kelly_sizing.position_size_base} units)
          </p>
        </div>
      </div>
    </div>
  );
};
