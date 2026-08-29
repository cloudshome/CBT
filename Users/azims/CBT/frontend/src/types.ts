export type OHLCVCandle = [
  number, // timestamp
  number, // open
  number, // high
  number, // low
  number, // close
  number  // volume
];

export type SupportedTimeframe = '5m' | '15m' | '1h' | '4h' | '1d';

export interface CandlesApiResponse {
  symbol: string;
  timeframe: SupportedTimeframe;
  limit: number;
  candles: OHLCVCandle[];
}

export interface IndicatorPoint {
  timestamp: number;
  value: number;
}

export interface MTFApiResponse {
  symbol: string;
  timeframe: SupportedTimeframe;
  indicators: {
    ema?: IndicatorPoint[];
    rsi?: IndicatorPoint[];
  };
}

export interface FVGItem {
  type: 'bullish' | 'bearish';
  price_zone: [number, number];
  mitigated: boolean;
  timestamp?: number;
}

export interface OrderBlockItem {
  type: 'bullish' | 'bearish';
  price_zone: [number, number];
  timestamp: number;
  mitigated?: boolean;
}

export interface SetupSuggestion {
  type: 'LONG' | 'SHORT';
  bias: string;
  trigger: string;
  entry: number;
  stopLoss: number;
  takeProfit: number;
  riskRewardRatio: number;
}

export interface ScanApiResponse {
  symbol: string;
  timeframe: SupportedTimeframe;
  fvg: FVGItem[];
  order_blocks: OrderBlockItem[];
  setup_suggestions: SetupSuggestion[];
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

export interface PaperTrade {
  id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  entryPrice: number;
  sl: number;
  tp: number;
  size: number;
  status: 'OPEN' | 'CLOSED' | 'CANCELLED';
  pnl?: number;
  exitPrice?: number;
  createdAt: string;
  closedAt?: string;
}

export interface PaperPositionsResponse {
  positions: PaperTrade[];
  count: number;
}

export interface RiskConfig {
  accountBalance: number;
  maxDrawdown: number;
  maxOpenTrades: number;
  dailyLossLimit: number;
  maxRiskPerTrade: number;
}

export interface DeskBriefResponse {
  symbol: string;
  timeframe: string;
  executiveSummary: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  keyLevels: {
    support: number[];
    resistance: number[];
    invalidation?: number;
  };
  riskAssessment: string;
  metrics: {
    lastPrice: number;
    ema?: number;
    rsi?: number;
    trend: string;
  };
  timestamp: number;
}

export interface DeskAskResponse {
  query: string;
  answer: string;
  timestamp: number;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
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

