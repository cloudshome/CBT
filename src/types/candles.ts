export type OHLCVCandle = [
  ts: number,
  open: number,
  high: number,
  low: number,
  close: number,
  volume: number
];

export const SUPPORTED_TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'] as const;
export type SupportedTimeframe = (typeof SUPPORTED_TIMEFRAMES)[number];

export interface CandlesResponse {
  symbol: string;
  timeframe: string;
  candles: OHLCVCandle[];
}

export interface ValidatedCandlesQuery {
  symbol: string;
  timeframe: SupportedTimeframe;
  limit: number;
}
