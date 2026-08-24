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
