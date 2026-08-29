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

  const score = dossier.composite_health_score;
  const scoreColor =
    score >= 80
      ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
      : score >= 60
      ? 'text-sky-400 border-sky-500/30 bg-sky-500/10'
      : score >= 40
      ? 'text-amber-400 border-amber-500/30 bg-amber-500/10'
      : 'text-rose-400 border-rose-500/30 bg-rose-500/10';

  const pillars = [
    {
      id: 1,
      name: 'Institutional Flows',
      icon: Layers,
      z: dossier.pillar_1_institutional_flows.z_score,
      summary: `${dossier.pillar_1_institutional_flows.sentiment_tier} • 24h ETF: $${(
        dossier.pillar_1_institutional_flows.etf_net_inflow_24h_usd / 1e6
      ).toFixed(1)}M`,
      details: [
        { label: '24h ETF Net Flow', val: `$${(dossier.pillar_1_institutional_flows.etf_net_inflow_24h_usd / 1e6).toFixed(1)}M` },
        { label: '7d ETF Net Flow', val: `$${(dossier.pillar_1_institutional_flows.etf_net_inflow_7d_usd / 1e6).toFixed(1)}M` },
        { label: 'Treasury Strategy', val: dossier.pillar_1_institutional_flows.corporate_treasury_bias },
        { label: 'Central Bank Quarterly', val: `${dossier.pillar_1_institutional_flows.sovereign_central_bank_net_tons_quarterly} tons` },
      ],
    },
    {
      id: 2,
      name: 'Derivatives & Options GEX',
      icon: Activity,
      z: dossier.pillar_2_derivatives_options.z_score,
      summary: `Dealer GEX: ${dossier.pillar_2_derivatives_options.net_dealer_gex} • Max Pain: $${dossier.pillar_2_derivatives_options.options_max_pain_strike.toLocaleString()}`,
      details: [
        { label: 'Funding Rate (Ann.)', val: `${dossier.pillar_2_derivatives_options.funding_rate_annualized_pct.toFixed(2)}%` },
        { label: '24h OI Delta', val: `${dossier.pillar_2_derivatives_options.open_interest_delta_24h_pct > 0 ? '+' : ''}${dossier.pillar_2_derivatives_options.open_interest_delta_24h_pct}%` },
        { label: '25-Delta Skew', val: `${dossier.pillar_2_derivatives_options.twenty_five_delta_skew_pct}%` },
        { label: 'Short Squeeze Target', val: `$${dossier.pillar_2_derivatives_options.primary_liquidation_pools.short_squeeze_target.toLocaleString()}` },
        { label: 'Long Risk Pool', val: `$${dossier.pillar_2_derivatives_options.primary_liquidation_pools.long_liquidation_cluster.toLocaleString()}` },
      ],
    },
    {
      id: 3,
      name: 'On-Chain Valuation & Realized Cost',
      icon: Coins,
      z: dossier.pillar_3_valuation_cost_basis.z_score,
      summary: `STH Realized Price: $${dossier.pillar_3_valuation_cost_basis.sth_realized_price.toLocaleString()} • MVRV Z: ${dossier.pillar_3_valuation_cost_basis.mvrv_z_score}`,
      details: [
        { label: 'STH Cost Basis', val: `$${dossier.pillar_3_valuation_cost_basis.sth_realized_price.toLocaleString()}` },
        { label: 'LTH Cost Basis', val: `$${dossier.pillar_3_valuation_cost_basis.lth_realized_price.toLocaleString()}` },
        { label: 'MVRV Z-Score', val: `${dossier.pillar_3_valuation_cost_basis.mvrv_z_score}` },
        { label: 'Production Cost Floor', val: `$${dossier.pillar_3_valuation_cost_basis.production_cost_floor.toLocaleString()}` },
        { label: 'Cost Basis Health', val: dossier.pillar_3_valuation_cost_basis.cost_basis_health },
      ],
    },
    {
      id: 4,
      name: 'Stablecoin Dry-Powder Velocity',
      icon: Coins,
      z: dossier.pillar_4_stablecoin_velocity.z_score,
      summary: `SSR: ${dossier.pillar_4_stablecoin_velocity.ssr_ratio} • 24h Net Minting: +$${(dossier.pillar_4_stablecoin_velocity.net_minting_velocity_24h_usd / 1e6).toFixed(0)}M`,
      details: [
        { label: 'SSR Ratio', val: `${dossier.pillar_4_stablecoin_velocity.ssr_ratio}` },
        { label: 'SSR Bias', val: dossier.pillar_4_stablecoin_velocity.ssr_oscillator_bias },
        { label: '24h Minting Delta', val: `+$${(dossier.pillar_4_stablecoin_velocity.net_minting_velocity_24h_usd / 1e6).toFixed(0)}M` },
        { label: 'Dry Powder State', val: dossier.pillar_4_stablecoin_velocity.dry_powder_liquidity_state },
      ],
    },
    {
      id: 5,
      name: 'Seasonality & Cyclical DNA',
      icon: Calendar,
      z: dossier.pillar_5_seasonality_cyclical_dna.z_score,
      summary: `${dossier.pillar_5_seasonality_cyclical_dna.month_name} Historical: ${dossier.pillar_5_seasonality_cyclical_dna.current_month_historical_return} • Real Yield: ${dossier.pillar_5_seasonality_cyclical_dna.real_yield_pct}%`,
      details: [
        { label: 'Day Win Rate', val: `${dossier.pillar_5_seasonality_cyclical_dna.historical_day_win_rate_pct}% (${dossier.pillar_5_seasonality_cyclical_dna.day_of_week})` },
        { label: 'Cycle Phase', val: dossier.pillar_5_seasonality_cyclical_dna.halving_cycle_phase },
        { label: 'Days Post-Halving', val: `${dossier.pillar_5_seasonality_cyclical_dna.days_post_halving} days` },
        { label: 'US Real Yield', val: `${dossier.pillar_5_seasonality_cyclical_dna.real_yield_pct}%` },
      ],
    },
    {
      id: 6,
      name: 'Macro & Global M2 Liquidity Beta',
      icon: Globe,
      z: dossier.pillar_6_macro_liquidity_beta.z_score,
      summary: `DXY Corr: ${dossier.pillar_6_macro_liquidity_beta.dxy_correlation_30d} • M2 YoY: +${dossier.pillar_6_macro_liquidity_beta.global_m2_expansion_rate_pct}%`,
      details: [
        { label: 'DXY 30d Correlation', val: `${dossier.pillar_6_macro_liquidity_beta.dxy_correlation_30d}` },
        { label: 'US 10Y Yield', val: `${dossier.pillar_6_macro_liquidity_beta.us10y_yield_pct}% (${dossier.pillar_6_macro_liquidity_beta.us10y_yield_delta_24h_bps} bps)` },
        { label: 'Global M2 Status', val: dossier.pillar_6_macro_liquidity_beta.global_m2_status },
        { label: 'Geopolitical Risk (GRI)', val: `${dossier.pillar_6_macro_liquidity_beta.geopolitical_risk_index_score}/100` },
      ],
    },
    {
      id: 7,
      name: 'Volatility Profile & VPOC Range',
      icon: BarChart3,
      z: dossier.pillar_7_volatility_profile.z_score,
      summary: `Weekly VPOC: $${dossier.pillar_7_volatility_profile.weekly_vpoc.toLocaleString()} • VAH/VAL: $${dossier.pillar_7_volatility_profile.value_area_high.toLocaleString()} / $${dossier.pillar_7_volatility_profile.value_area_low.toLocaleString()}`,
      details: [
        { label: 'Squeeze State', val: dossier.pillar_7_volatility_profile.squeeze_state },
        { label: 'Squeeze Intensity', val: `${dossier.pillar_7_volatility_profile.squeeze_intensity_score}/10` },
        { label: 'Weekly VPOC', val: `$${dossier.pillar_7_volatility_profile.weekly_vpoc.toLocaleString()}` },
        { label: 'Value Area High (VAH)', val: `$${dossier.pillar_7_volatility_profile.value_area_high.toLocaleString()}` },
        { label: 'Value Area Low (VAL)', val: `$${dossier.pillar_7_volatility_profile.value_area_low.toLocaleString()}` },
      ],
    },
    {
      id: 8,
      name: 'Physical & Exchange Supply Shock',
      icon: Vault,
      z: dossier.pillar_8_physical_supply_shock.z_score,
      summary: `24h Net Reserves: ${dossier.pillar_8_physical_supply_shock.exchange_reserve_delta_24h} • Trend: ${dossier.pillar_8_physical_supply_shock.supply_illiquidity_trend}`,
      details: [
        { label: 'Exchange Net Delta', val: dossier.pillar_8_physical_supply_shock.exchange_reserve_delta_24h },
        { label: 'COMEX Vault Drawdown', val: `${dossier.pillar_8_physical_supply_shock.comex_registered_vault_delta_pct}%` },
        { label: 'Shanghai Gold Premium', val: `+$${dossier.pillar_8_physical_supply_shock.shanghai_gold_exchange_premium_usd}/oz` },
        { label: 'Supply Shock State', val: dossier.pillar_8_physical_supply_shock.supply_shock_state },
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
