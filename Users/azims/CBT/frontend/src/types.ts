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
