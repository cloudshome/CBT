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

  const dec = alphaData.decision || 'NO_TRADE';
  const isLong = dec === 'LONG';
  const isShort = dec === 'SHORT';

  const score = Number(alphaData.institutional_composite_score) || 0;
  const leadLag = alphaData.lead_lag || ({} as any);
  const cvd = alphaData.cvd_absorption || ({} as any);
  const obi = alphaData.orderbook_imbalance || ({} as any);
  const squeeze = alphaData.oi_funding_squeeze || ({} as any);
  const judas = alphaData.judas_sweep || ({} as any);
  const vwap = alphaData.vwap_multisigma || ({} as any);
  const harmonics = alphaData.fractal_harmonics || ({} as any);
  const kelly = alphaData.half_kelly_sizing || ({} as any);

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
                {dec}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">{alphaData.narrative || 'Institutional signal synthesis calibrated.'}</p>
          </div>
        </div>

        {/* Score & Kelly Badge */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[10px] text-slate-500 block">ALPHA SCORE</span>
            <span
              className={`text-base font-black ${
                score >= 70
                  ? 'text-[#00f0a8]'
                  : score >= 50
                  ? 'text-sky-400'
                  : 'text-slate-400'
              }`}
            >
              {score.toFixed(1)}/100
            </span>
          </div>

          <div className="text-right pl-3 border-l border-slate-800">
            <span className="text-[10px] text-slate-500 block">HALF-KELLY</span>
            <span className="text-sm font-bold text-purple-400">
              {((Number(kelly.recommended_risk_pct) || 0) * 100).toFixed(2)}% Risk
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
            <span className="text-slate-300 font-bold">DXY: {leadLag.dxy_price ?? '---'}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {leadLag.signals?.[0]?.direction || 'NEUTRAL'} ({leadLag.signals?.[0]?.expected_lead_window_mins || '3-5m'})
          </p>
        </div>

        {/* 2. CVD Absorption */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Activity size={11} className="text-emerald-400" /> Order Flow CVD</span>
            <span className={(Number(cvd.current_cvd) || 0) >= 0 ? 'text-[#00f0a8]' : 'text-[#ff3b69]'}>
              {(Number(cvd.current_cvd) || 0) > 0 ? '+' : ''}{Number(cvd.current_cvd || 0).toLocaleString()}
            </span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {String(cvd.absorption_type || 'ABSORPTION_EQUILIBRIUM').replace(/_/g, ' ')}
          </p>
        </div>

        {/* 3. L2 OBI & VPIN */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Zap size={11} className="text-amber-400" /> OBI & VPIN</span>
            <span className="text-slate-300 font-bold">
              {(Number(obi.obi_score) || 0) > 0 ? '+' : ''}{((Number(obi.obi_score) || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            VPIN: {((Number(obi.flow_toxicity_vpin) || 0) * 100).toFixed(0)}% ({String(obi.regime || 'NOMINAL').split('_')[0]})
          </p>
        </div>

        {/* 4. OI & Funding Squeeze */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Flame size={11} className="text-rose-400" /> OI Squeeze</span>
            <span className="text-slate-300 font-bold">{(Number(squeeze.funding_rate_annualized_pct) || 0).toFixed(1)}% APR</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {String(squeeze.squeeze_risk || 'LOW_SQUEEZE_RISK').replace(/_/g, ' ')}
          </p>
        </div>

        {/* 5. Judas Liquidity Sweep */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Target size={11} className="text-purple-400" /> Judas Trap</span>
            <span className="text-slate-300 font-bold">{String(judas.session_name || 'LONDON').replace(/_OPEN/g, '')}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            {String(judas.sweep_direction || 'NO_SWEEP').replace(/_SWEEP/g, '')}
          </p>
        </div>

        {/* 6. Multi-Sigma VWAP */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><TrendingUp size={11} className="text-sky-400" /> VWAP Bands</span>
            <span className="text-slate-300 font-bold">${(Number(vwap.vwap) || 0).toFixed(0)}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            Dev: {(Number(vwap.deviation_sigmas) || 0).toFixed(2)}σ (Rev {Math.round((Number(vwap.mean_reversion_prob) || 0) * 100)}%)
          </p>
        </div>

        {/* 7. Fractal Harmonics */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><Layers size={11} className="text-indigo-400" /> Harmonics</span>
            <span className="text-slate-300 font-bold">{harmonics.dominant_direction || 'EQUILIBRIUM'}</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            Confluence: {Math.round((Number(harmonics.harmonic_confluence_score) || 0) * 100)}% (1D+15m+1m)
          </p>
        </div>

        {/* 8. Bayesian Half-Kelly Sizer */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><DollarSign size={11} className="text-emerald-400" /> Kelly Size</span>
            <span className="text-[#00f0a8] font-bold">${(Number(kelly.max_dollar_loss) || 0).toFixed(0)} max loss</span>
          </div>
          <p className="text-[10px] text-slate-300 font-medium truncate">
            R:R {kelly.risk_reward_ratio ?? 2}R ({kelly.position_size_base ?? 0} units)
          </p>
        </div>
      </div>
    </div>
  );
};
