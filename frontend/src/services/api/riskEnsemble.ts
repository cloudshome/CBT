/**
 * frontend/src/services/api/riskEnsemble.ts
 * =========================================
 * Generation 7 Multi-Strategy Ensemble & Institutional Stress Testing Client API.
 */

import { authFetch, BASE_URL } from './client';

export interface EnsembleWeightsResponse {
  regime: string;
  weights: Record<string, number>;
  sum_weights: number;
  real_capital_enabled: boolean;
  watermark: string;
}

export interface ScenarioResult {
  scenario_id: string;
  price_shock_pct: number;
  volatility_multiplier: number;
  spread_widening_factor: number;
  post_stress_equity_usd: number;
  post_stress_margin_buffer_pct: number;
  is_liquidated: boolean;
  survives_stress_gate: boolean;
  narrative: string;
}

export interface StressSimulateResponse {
  total_equity_usd: number;
  total_portfolio_equity_usd?: number;
  total_notional_usd: number;
  maintenance_margin_usd: number;
  effective_leverage: number;
  current_margin_buffer_pct: number;
  var_99_1d_usd: number;
  cvar_99_1d_usd: number;
  is_within_heat_ceiling: boolean;
  all_stress_scenarios_passed: boolean;
  scenario_results: ScenarioResult[];
  real_capital_enabled: boolean;
  watermark: string;
}

export interface HRPAllocation {
  symbol: string;
  weight: number;
  target_risk_usd: number;
  target_notional_usd: number;
  risk_percentage: number;
  marginal_risk_contribution: number;
  percentage_risk_contribution: number;
  cap_breached: boolean;
  real_capital_enabled: boolean;
}

export interface HRPOptimizeResponse {
  account_equity_usd: number;
  symbols: string[];
  weights: Record<string, number>;
  market_regime: string;
  portfolio_volatility_annualized: number;
  portfolio_cvar_95_pct: number;
  diversification_ratio: number;
  total_portfolio_heat_pct: number;
  is_within_risk_caps: boolean;
  shrinkage_report: {
    sample_condition_number: number;
    shrunk_condition_number: number;
    optimal_shrinkage_delta: number;
    average_correlation: number;
    is_positive_definite: boolean;
  };
  allocations: HRPAllocation[];
  real_capital_enabled: boolean;
  watermark: string;
}

export async function fetchEnsembleWeights(regime: string = 'TRENDING_HIGH_VOL'): Promise<EnsembleWeightsResponse> {
  const url = `${BASE_URL}/api/v1/risk/ensemble/weights?regime=${encodeURIComponent(regime)}`;
  const resp = await authFetch(url);
  if (!resp.ok) {
    throw new Error(`Failed to fetch ensemble weights: ${resp.statusText}`);
  }
  return resp.json();
}

export async function simulateExtremeStress(
  collateralCashUsd: number = 25000,
  positions: Array<{
    symbol: string;
    quantity: number;
    entry_price: number;
    current_mark_price: number;
    initial_margin_rate?: number;
    maintenance_margin_rate?: number;
    asset_volatility?: number;
  }> = []
): Promise<StressSimulateResponse> {
  const defaultPositions = positions.length > 0 ? positions : [
    {
      symbol: 'BTC/USDT',
      quantity: 0.05,
      entry_price: 60000,
      current_mark_price: 60000,
      initial_margin_rate: 0.05,
      maintenance_margin_rate: 0.025,
      asset_volatility: 0.025,
    },
    {
      symbol: 'ETH/USDT',
      quantity: 0.5,
      entry_price: 3000,
      current_mark_price: 3000,
      initial_margin_rate: 0.05,
      maintenance_margin_rate: 0.025,
      asset_volatility: 0.035,
    },
  ];

  const url = `${BASE_URL}/api/v1/risk/stress-engine/simulate`;
  const resp = await authFetch(url, {
    method: 'POST',
    body: JSON.stringify({
      collateral_cash_usd: collateralCashUsd,
      positions: defaultPositions,
      estimated_portfolio_volatility: 0.02,
    }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to simulate extreme stress: ${resp.statusText}`);
  }
  return resp.json();
}

export async function optimizeHierarchicalRiskParity(
  accountEquityUsd: number = 50000,
  marketRegime: string = 'TRENDING_BULL'
): Promise<HRPOptimizeResponse> {
  const url = `${BASE_URL}/api/v1/risk/hrp/optimize`;
  const resp = await authFetch(url, {
    method: 'POST',
    body: JSON.stringify({
      account_equity_usd: accountEquityUsd,
      symbols: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PAXG/USDT'],
      market_regime: marketRegime,
      invalidation_distances: {
        'BTC/USDT': 0.04,
        'ETH/USDT': 0.05,
        'SOL/USDT': 0.08,
        'PAXG/USDT': 0.02,
      },
    }),
  });
  if (!resp.ok) {
    throw new Error(`Failed to optimize HRP: ${resp.statusText}`);
  }
  return resp.json();
}
