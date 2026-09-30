import React, { useState, useEffect, memo } from 'react';
import {
  ShieldAlert,
  Activity,
  Layers,
  Coins,
  Calendar,
  Globe,
  BarChart3,
  Vault,
  ChevronRight,
  ChevronDown,
  Sparkles,
  RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';
import { UniversalAssetDossier } from '../types';

interface AssetDossierDockProps {
  currentSymbol: string;
  onSelectSymbol?: (symbol: string) => void;
}

const AssetDossierDockComponent: React.FC<AssetDossierDockProps> = ({
  currentSymbol,
  onSelectSymbol,
}) => {
  const [dossier, setDossier] = useState<UniversalAssetDossier | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedPillar, setExpandedPillar] = useState<number | null>(null);

  const fetchDossier = async (sym: string) => {
    try {
      setLoading(true);
      const data = await api.getAssetDossier(sym, '15m');
      setDossier(data);
    } catch (err) {
      console.warn('Failed to load asset dossier:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDossier(currentSymbol);
    const interval = setInterval(() => {
      fetchDossier(currentSymbol);
    }, 30000); // 30s background refresh
    return () => clearInterval(interval);
  }, [currentSymbol]);

  if (!dossier && loading) {
    return (
      <div className="bg-[#080b11] border border-[#1e293b] rounded-lg p-6 flex flex-col items-center justify-center min-h-[350px] font-mono text-slate-400">
        <RefreshCw className="w-8 h-8 animate-spin text-sky-400 mb-3" />
        <span className="text-sm font-semibold tracking-wider">COMPILING 8-PILLAR ASSET INTELLIGENCE DOSSIER...</span>
      </div>
    );
  }

  if (!dossier) return null;

  const score = Number(dossier?.composite_health_score) || 50;
  const scoreColor =
    score >= 80
      ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
      : score >= 60
      ? 'text-sky-400 border-sky-500/30 bg-sky-500/10'
      : score >= 40
      ? 'text-amber-400 border-amber-500/30 bg-amber-500/10'
      : 'text-rose-400 border-rose-500/30 bg-rose-500/10';

  const p1 = dossier?.pillar_1_institutional_flows || {} as any;
  const p2 = dossier?.pillar_2_derivatives_options || {} as any;
  const p3 = dossier?.pillar_3_valuation_cost_basis || {} as any;
  const p4 = dossier?.pillar_4_stablecoin_velocity || {} as any;
  const p5 = dossier?.pillar_5_seasonality_cyclical_dna || {} as any;
  const p6 = dossier?.pillar_6_macro_liquidity_beta || {} as any;
  const p7 = dossier?.pillar_7_volatility_profile || {} as any;
  const p8 = dossier?.pillar_8_physical_supply_shock || {} as any;

  const pillars = [
    {
      id: 1,
      name: 'Institutional Flows',
      icon: Layers,
      z: Number(p1.z_score) || 0,
      summary: `${p1.sentiment_tier || 'Equilibrium'} • 24h ETF: $${(
        (Number(p1.etf_net_inflow_24h_usd) || 0) / 1e6
      ).toFixed(1)}M`,
      details: [
        { label: '24h ETF Net Flow', val: `$${((Number(p1.etf_net_inflow_24h_usd) || 0) / 1e6).toFixed(1)}M` },
        { label: '7d ETF Net Flow', val: `$${((Number(p1.etf_net_inflow_7d_usd) || 0) / 1e6).toFixed(1)}M` },
        { label: 'Treasury Strategy', val: p1.corporate_treasury_bias || 'NEUTRAL' },
        { label: 'Central Bank Quarterly', val: `${Number(p1.sovereign_central_bank_net_tons_quarterly || 0)} tons` },
      ],
    },
    {
      id: 2,
      name: 'Derivatives & Options GEX',
      icon: Activity,
      z: Number(p2.z_score) || 0,
      summary: `Dealer GEX: ${p2.net_dealer_gex || 'BALANCED'} • Max Pain: $${Number(p2.options_max_pain_strike || 0).toLocaleString()}`,
      details: [
        { label: 'Funding Rate (Ann.)', val: `${(Number(p2.funding_rate_annualized_pct) || 0).toFixed(2)}%` },
        { label: '24h OI Delta', val: `${(Number(p2.open_interest_delta_24h_pct) || 0) > 0 ? '+' : ''}${Number(p2.open_interest_delta_24h_pct || 0)}%` },
        { label: '25-Delta Skew', val: `${Number(p2.twenty_five_delta_skew_pct || 0)}%` },
        { label: 'Short Squeeze Target', val: `$${Number(p2.primary_liquidation_pools?.short_squeeze_target || 0).toLocaleString()}` },
        { label: 'Long Risk Pool', val: `$${Number(p2.primary_liquidation_pools?.long_liquidation_cluster || 0).toLocaleString()}` },
      ],
    },
    {
      id: 3,
      name: 'On-Chain Valuation & Realized Cost',
      icon: Coins,
      z: Number(p3.z_score) || 0,
      summary: `STH Realized Price: $${Number(p3.sth_realized_price || 0).toLocaleString()} • MVRV Z: ${Number(p3.mvrv_z_score || 0)}`,
      details: [
        { label: 'STH Cost Basis', val: `$${Number(p3.sth_realized_price || 0).toLocaleString()}` },
        { label: 'LTH Cost Basis', val: `$${Number(p3.lth_realized_price || 0).toLocaleString()}` },
        { label: 'MVRV Z-Score', val: `${Number(p3.mvrv_z_score || 0)}` },
        { label: 'Production Cost Floor', val: `$${Number(p3.production_cost_floor || 0).toLocaleString()}` },
        { label: 'Cost Basis Health', val: p3.cost_basis_health || 'NORMAL' },
      ],
    },
    {
      id: 4,
      name: 'Stablecoin Dry-Powder Velocity',
      icon: Coins,
      z: Number(p4.z_score) || 0,
      summary: `SSR: ${p4.ssr_ratio ?? 0} • 24h Net Minting: +$${((Number(p4.net_minting_velocity_24h_usd) || 0) / 1e6).toFixed(0)}M`,
      details: [
        { label: 'SSR Ratio', val: `${p4.ssr_ratio ?? 0}` },
        { label: 'SSR Bias', val: p4.ssr_oscillator_bias || 'NEUTRAL' },
        { label: '24h Minting Delta', val: `+$${((Number(p4.net_minting_velocity_24h_usd) || 0) / 1e6).toFixed(0)}M` },
        { label: 'Dry Powder State', val: p4.dry_powder_liquidity_state || 'STABLE' },
      ],
    },
    {
      id: 5,
      name: 'Seasonality & Cyclical DNA',
      icon: Calendar,
      z: Number(p5.z_score) || 0,
      summary: `${p5.month_name || 'Monthly'} Historical: ${p5.current_month_historical_return || '+0.0%'} • Real Yield: ${Number(p5.real_yield_pct || 0)}%`,
      details: [
        { label: 'Day Win Rate', val: `${Number(p5.historical_day_win_rate_pct || 0)}% (${p5.day_of_week || 'Today'})` },
        { label: 'Cycle Phase', val: p5.halving_cycle_phase || 'EXPANSION' },
        { label: 'Days Post-Halving', val: `${p5.days_post_halving ?? 0} days` },
        { label: 'US Real Yield', val: `${Number(p5.real_yield_pct || 0)}%` },
      ],
    },
    {
      id: 6,
      name: 'Macro & Global M2 Liquidity Beta',
      icon: Globe,
      z: Number(p6.z_score) || 0,
      summary: `DXY Corr: ${p6.dxy_correlation_30d ?? 0} • M2 YoY: +${Number(p6.global_m2_expansion_rate_pct || 0)}%`,
      details: [
        { label: 'DXY 30d Correlation', val: `${p6.dxy_correlation_30d ?? 0}` },
        { label: 'US 10Y Yield', val: `${Number(p6.us10y_yield_pct || 0)}% (${Number(p6.us10y_yield_delta_24h_bps || 0)} bps)` },
        { label: 'Global M2 Status', val: p6.global_m2_status || 'NOMINAL' },
        { label: 'Geopolitical Risk (GRI)', val: `${Number(p6.geopolitical_risk_index_score || 0)}/100` },
      ],
    },
    {
      id: 7,
      name: 'Volatility Profile & VPOC Range',
      icon: BarChart3,
      z: Number(p7.z_score) || 0,
      summary: `Weekly VPOC: $${Number(p7.weekly_vpoc || 0).toLocaleString()} • VAH/VAL: $${Number(p7.value_area_high || 0).toLocaleString()} / $${Number(p7.value_area_low || 0).toLocaleString()}`,
      details: [
        { label: 'Squeeze State', val: p7.squeeze_state || 'NORMAL' },
        { label: 'Squeeze Intensity', val: `${Number(p7.squeeze_intensity_score || 0)}/10` },
        { label: 'Weekly VPOC', val: `$${Number(p7.weekly_vpoc || 0).toLocaleString()}` },
        { label: 'Value Area High (VAH)', val: `$${Number(p7.value_area_high || 0).toLocaleString()}` },
        { label: 'Value Area Low (VAL)', val: `$${Number(p7.value_area_low || 0).toLocaleString()}` },
      ],
    },
    {
      id: 8,
      name: 'Physical & Exchange Supply Shock',
      icon: Vault,
      z: Number(p8.z_score) || 0,
      summary: `24h Net Reserves: ${p8.exchange_reserve_delta_24h || '0'} • Trend: ${p8.supply_illiquidity_trend || 'STABLE'}`,
      details: [
        { label: 'Exchange Net Delta', val: p8.exchange_reserve_delta_24h || '0' },
        { label: 'COMEX Vault Drawdown', val: `${Number(p8.comex_registered_vault_delta_pct || 0)}%` },
        { label: 'Shanghai Gold Premium', val: `+$${Number(p8.shanghai_gold_exchange_premium_usd || 0)}/oz` },
        { label: 'Supply Shock State', val: p8.supply_shock_state || 'NOMINAL' },
      ],
    },
  ];

  return (
    <div className="bg-[#080b11] border border-[#1e293b] rounded-lg p-4 font-mono select-none flex flex-col gap-4">
      {/* Top Banner: Asset Selector, Health Score, Macro Bias */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1e293b] pb-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-amber-400 font-bold text-sm">
            <Sparkles className="w-4 h-4" />
            <span>8-PILLAR LIVE ASSET INTELLIGENCE DOSSIER</span>
          </div>

          {/* Asset Quick Switcher */}
          <div className="flex items-center gap-1 bg-[#0b101b] p-0.5 rounded border border-[#1e293b]">
            {['BTCUSDT', 'ETHUSDT', 'PAXGUSDT'].map((sym) => (
              <button
                key={sym}
                onClick={() => onSelectSymbol && onSelectSymbol(sym)}
                className={`px-2.5 py-1 text-xs rounded font-bold transition ${
                  currentSymbol === sym
                    ? 'bg-sky-500 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {sym.replace('USDT', '')}
              </button>
            ))}
          </div>
        </div>

        {/* Composite Score & Regime Pill */}
        <div className="flex items-center gap-2.5">
          <div className={`px-3 py-1 rounded-full border text-xs font-bold flex items-center gap-2 ${scoreColor}`}>
            <span className="text-base font-black">{score.toFixed(0)}/100</span>
            <span className="text-[10px] tracking-wider">{dossier.macro_bias}</span>
          </div>
          <button
            onClick={() => fetchDossier(currentSymbol)}
            className="p-1.5 rounded bg-[#0b101b] border border-[#1e293b] text-slate-400 hover:text-sky-400"
            title="Refresh Dossier"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Actionable Executive Quantitative Verdict */}
      <div className="bg-sky-500/10 border border-sky-400/30 rounded-lg p-3 text-xs flex items-start gap-2.5 text-sky-200 leading-relaxed shadow-sm">
        <ShieldAlert className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-sky-300 mr-1.5 uppercase tracking-wide">[Executive Alpha Verdict]:</span>
          <span>{dossier.actionable_quant_verdict}</span>
        </div>
      </div>

      {/* 8-Pillar Metric Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {pillars.map((p) => {
          const Icon = p.icon;
          const isExpanded = expandedPillar === p.id;
          const zColor =
            p.z >= 1.5
              ? 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30'
              : p.z >= 0
              ? 'text-sky-400 bg-sky-500/15 border-sky-500/30'
              : 'text-rose-400 bg-rose-500/15 border-rose-500/30';

          return (
            <div
              key={p.id}
              onClick={() => setExpandedPillar(isExpanded ? null : p.id)}
              className={`bg-[#0b101b] border rounded-lg p-3 cursor-pointer transition flex flex-col justify-between hover:border-slate-600 ${
                isExpanded ? 'border-sky-400 shadow-md shadow-sky-500/10' : 'border-[#1e293b]'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 text-slate-200 font-bold text-xs">
                  <Icon className="w-3.5 h-3.5 text-sky-400" />
                  <span>{`P${p.id}: ${p.name}`}</span>
                </div>
                <span className={`text-[10px] px-1.5 py-0.2 rounded border font-bold ${zColor}`}>
                  Z: {p.z > 0 ? '+' : ''}{p.z.toFixed(2)}
                </span>
              </div>

              <div className="text-[11px] text-slate-400 line-clamp-2 my-1 leading-snug">
                {p.summary}
              </div>

              {/* Expandable Breakdown Drawer */}
              {isExpanded && (
                <div className="mt-2 pt-2 border-t border-[#1e293b] flex flex-col gap-1 text-[10px]">
                  {p.details.map((d, i) => (
                    <div key={i} className="flex justify-between items-center text-slate-300">
                      <span className="text-slate-500">{d.label}:</span>
                      <span className="font-semibold text-slate-200">{d.val}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-end text-[9px] text-slate-500 mt-1">
                {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const AssetDossierDock = memo(AssetDossierDockComponent);
