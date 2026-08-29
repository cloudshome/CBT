export type CandleRaw = [number, number, number, number, number, number];

export interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  index: number;
}

export interface FVGItem {
  type: "bullish" | "bearish";
  price_zone: [number, number]; // [min, max]
  mitigated: boolean;
  candleIndex?: number;
  c1Index?: number;
  c2Index?: number;
  c3Index?: number;
  mitigationIndex?: number;
  mitigationTimestamp?: number;
  timestamp?: number;
  gapSize?: number;
  gapPercent?: number;
}

export interface OrderBlockItem {
  type: "bullish" | "bearish";
  price_zone: [number, number]; // [min, max]
  timestamp: number;
  candleIndex?: number;
  bosIndex?: number;
  bosPrice?: number;
  displacementCandles?: number[];
  mitigated?: boolean;
  mitigationIndex?: number;
  mitigationTimestamp?: number;
  volume?: number;
}

export interface SwingPoint {
  type: "high" | "low";
  price: number;
  candleIndex: number;
  timestamp: number;
}

export interface BreakOfStructure {
  type: "bullish" | "bearish";
  breakPrice: number;
  swingPrice: number;
  candleIndex: number;
  swingIndex: number;
  timestamp: number;
}

export interface StrictQuantOutput {
  fvg: Array<{
    type: "bullish" | "bearish";
    price_zone: [number, number];
    mitigated: boolean;
  }>;
  order_blocks: Array<{
    type: "bullish" | "bearish";
    price_zone: [number, number];
    timestamp: number;
  }>;
}

export interface DetectionResult {
  output: StrictQuantOutput;
  detailedFVGs: FVGItem[];
  detailedOrderBlocks: OrderBlockItem[];
  swings: SwingPoint[];
  bosList: BreakOfStructure[];
  candles: Candle[];
  stats: {
    totalCandles: number;
    bullishFVGs: number;
    bearishFVGs: number;
    unmitigatedFVGs: number;
    mitigatedFVGs: number;
    bullishOBs: number;
    bearishOBs: number;
    lastPrice: number;
    highPrice: number;
    lowPrice: number;
    trend: string;
  };
}

export interface SetupSuggestion {
  type: "LONG" | "SHORT";
  bias: string;
  trigger: string;
  entry: number;
  stopLoss: number;
  takeProfit: number;
  riskRewardRatio: number;
}

export interface ScanResponse {
  symbol: string;
  timeframe: string;
  fvg: Array<{
    type: "bullish" | "bearish";
    price_zone: [number, number];
    mitigated: boolean;
  }>;
  order_blocks: Array<{
    type: "bullish" | "bearish";
    price_zone: [number, number];
    timestamp: number;
  }>;
  detailedFVGs?: FVGItem[];
  detailedOrderBlocks?: OrderBlockItem[];
  setup_suggestions: SetupSuggestion[];
  stats: DetectionResult["stats"];
}

export interface PresetDataset {
  id: string;
  name: string;
  symbol: string;
  timeframe: string;
  description: string;
  candles: CandleRaw[];
}

export interface VWAPData {
  timestamp: number;
  vwap: number;
  upper_band_1sigma: number;
  lower_band_1sigma: number;
  upper_band_2sigma: number;
  lower_band_2sigma: number;
  std_dev: number;
  deviation_sigmas: number;
  is_above_vwap: boolean;
  is_extended_overbought: boolean;
  is_extended_oversold: boolean;
  is_reclaiming: boolean;
  mean_reversion_prob: number;
  anchored_vwap?: number | null;
}

export interface SKYSetupData {
  setup_type: string;
  direction: 'LONG' | 'SHORT' | 'WATCH' | 'NO_TRADE';
  symbol: string;
  trigger_timeframe: string;
  timestamp: number;
  entry_price: number;
  invalidation_sl: number;
  target_tp: number;
  risk_reward_ratio: number;
  displacement_score: number;
  regime: string;
  historical_expectancy_r: number;
  historical_win_rate: number;
  historical_sample_size: number;
  confluence_score: number;
  is_qualified: boolean;
  rejection_reasons: string[];
  explanation_text: string;
}

export interface SKYIntelligenceResponse {
  decision: 'LONG' | 'SHORT' | 'WATCH' | 'NO_TRADE';
  symbol: string;
  timeframe: string;
  timestamp: number;
  setup_qualified?: SKYSetupData | null;
  net_ev_r: number;
  kelly_fraction: number;
  suggested_position_size_usd: number;
  risk_gate_passed: boolean;
  explanation_dossier: {
    regime: string;
    mtf_alignment?: string;
    volatility?: string;
    displacement_score?: number;
    active_pools?: number;
    active_fvgs?: number;
    candidate_obs?: number;
    vwap?: {
      vwap: number;
      deviation_sigmas: number;
      mean_reversion_prob: number;
    };
    explanation?: string;
    [key: string]: unknown;
  };
  no_trade_reason?: string | null;
  vwap: VWAPData;
  setups: SKYSetupData[];
}

export interface CVDSeriesData {
  symbol: string;
  timestamp: number;
  current_cvd: number;
  cvd_delta: number;
  absorption_detected: boolean;
  absorption_type: string;
  absorption_score: number;
  volume_ratio: number;
  divergence_score: number;
  narrative: string;
}

export interface OBIData {
  symbol: string;
  timestamp: number;
  obi_score: number;
  top_level_imbalance: number;
  depth_weighted_imbalance: number;
  flow_toxicity_vpin: number;
  bid_depth_total_usd: number;
  ask_depth_total_usd: number;
  micro_price_shift: number;
  regime: string;
  narrative: string;
}

export interface InstitutionalAlphaResponse {
  symbol: string;
  timeframe: string;
  timestamp: number;
  decision: 'LONG' | 'SHORT' | 'WATCH' | 'NO_TRADE';
  institutional_composite_score: number;
  lead_lag: {
    signals: Array<{
      driver_asset: string;
      target_asset: string;
      shock_zscore: number;
      direction: string;
      expected_lead_window_mins: string;
      confidence: number;
      timestamp: number;
      rationale: string;
    }>;
    dxy_price: number;
    us10y_yield: number;
    has_macro_shock: boolean;
  };
  cvd_absorption: CVDSeriesData;
  orderbook_imbalance: OBIData;
  oi_funding_squeeze: {
    open_interest_usd: number;
    oi_change_1h_pct: number;
    funding_rate_annualized_pct: number;
    funding_zscore: number;
    perpetual_basis_bps: number;
    squeeze_risk: string;
    squeeze_velocity_score: number;
    narrative: string;
  };
  judas_sweep: {
    symbol: string;
    session_name: string;
    timestamp: number;
    sweep_direction: string;
    asian_high: number;
    asian_low: number;
    swept_level: number;
    rejection_wick_pct: number;
    confidence: number;
    invalidation_level: number;
    target_level: number;
    narrative: string;
  };
  vwap_multisigma: {
    vwap: number;
    upper_1s: number;
    lower_1s: number;
    upper_2s: number;
    lower_2s: number;
    upper_3s: number;
    lower_3s: number;
    deviation_sigmas: number;
    mean_reversion_prob: number;
    is_reclaiming: boolean;
  };
  fractal_harmonics: {
    symbol: string;
    macro_tier: { timeframe: string; bias: string; structure_type: string; trend_strength: number };
    context_tier: { timeframe: string; bias: string; structure_type: string; trend_strength: number };
    micro_tier: { timeframe: string; bias: string; structure_type: string; trend_strength: number };
    harmonic_confluence_score: number;
    is_aligned: boolean;
    dominant_direction: string;
    narrative: string;
  };
  half_kelly_sizing: {
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    risk_reward_ratio: number;
    raw_kelly_fraction: number;
    half_kelly_fraction: number;
    bayesian_shrunk_fraction: number;
    recommended_risk_pct: number;
    position_size_usd: number;
    position_size_base: number;
    max_dollar_loss: number;
    invalidation_distance_pct: number;
    hurdle_passed: boolean;
    narrative: string;
  };
  execution_dossier: {
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    risk_reward_ratio: number;
    suggested_risk_usd: number;
    suggested_size_base: number;
  };
  hurdle_passed: boolean;
  narrative: string;
}

