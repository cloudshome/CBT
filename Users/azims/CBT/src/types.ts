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

