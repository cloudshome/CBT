/**
 * Web Worker for Offloaded Technical Indicator Computation.
 * Computes multi-period EMAs, VWAP, Bollinger Bands, ATR, and RSI in the background
 * to maintain a rock-solid 60-120 FPS on the main UI thread.
 */

export interface WorkerCandle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorRequestMessage {
  id: string;
  candles: WorkerCandle[];
  indicators: {
    emaPeriods?: number[];
    rsiPeriod?: number;
    atrPeriod?: number;
    bollingerPeriod?: number;
    bollingerStdDev?: number;
    vwap?: boolean;
  };
}

export interface IndicatorPointResult {
  time: number;
  value: number;
}

export interface IndicatorResponseMessage {
  id: string;
  ema: Record<number, IndicatorPointResult[]>;
  rsi: IndicatorPointResult[];
  atr: IndicatorPointResult[];
  bollingerBands: {
    upper: IndicatorPointResult[];
    middle: IndicatorPointResult[];
    lower: IndicatorPointResult[];
  };
  vwap: {
    vwap: IndicatorPointResult[];
    upper1s: IndicatorPointResult[];
    lower1s: IndicatorPointResult[];
    upper2s: IndicatorPointResult[];
    lower2s: IndicatorPointResult[];
  };
}

/**
 * Calculates Exponential Moving Average.
 */
function computeEMA(candles: WorkerCandle[], period: number): IndicatorPointResult[] {
  if (candles.length < period) return [];

  const k = 2 / (period + 1);
  const results: IndicatorPointResult[] = [];

  // Initial SMA
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += candles[i].close;
  }
  let prevEMA = sum / period;
  results.push({ time: Math.floor(candles[period - 1].timestamp / 1000), value: Number(prevEMA.toFixed(4)) });

  for (let i = period; i < candles.length; i++) {
    const close = candles[i].close;
    const currentEMA = (close - prevEMA) * k + prevEMA;
    results.push({ time: Math.floor(candles[i].timestamp / 1000), value: Number(currentEMA.toFixed(4)) });
    prevEMA = currentEMA;
  }

  return results;
}

/**
 * Calculates Relative Strength Index (RSI).
 */
function computeRSI(candles: WorkerCandle[], period = 14): IndicatorPointResult[] {
  if (candles.length <= period) return [];

  const results: IndicatorPointResult[] = [];
  const gains: number[] = [];
  const losses: number[] = [];

  for (let i = 1; i < candles.length; i++) {
    const diff = candles[i].close - candles[i - 1].close;
    gains.push(diff > 0 ? diff : 0);
    losses.push(diff < 0 ? Math.abs(diff) : 0);
  }

  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

  let rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  let rsi = 100 - 100 / (1 + rs);
  results.push({ time: Math.floor(candles[period].timestamp / 1000), value: Number(rsi.toFixed(2)) });

  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    rsi = 100 - 100 / (1 + rs);
    results.push({ time: Math.floor(candles[i + 1].timestamp / 1000), value: Number(rsi.toFixed(2)) });
  }

  return results;
}

/**
 * Calculates Average True Range (ATR).
 */
function computeATR(candles: WorkerCandle[], period = 14): IndicatorPointResult[] {
  if (candles.length <= period) return [];

  const trs: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (i === 0) {
      trs.push(candles[i].high - candles[i].low);
    } else {
      const h_l = candles[i].high - candles[i].low;
      const h_pc = Math.abs(candles[i].high - candles[i - 1].close);
      const l_pc = Math.abs(candles[i].low - candles[i - 1].close);
      trs.push(Math.max(h_l, h_pc, l_pc));
    }
  }

  const results: IndicatorPointResult[] = [];
  let prevATR = trs.slice(0, period).reduce((a, b) => a + b, 0) / period;
  results.push({ time: Math.floor(candles[period - 1].timestamp / 1000), value: Number(prevATR.toFixed(4)) });

  for (let i = period; i < trs.length; i++) {
    const curATR = (prevATR * (period - 1) + trs[i]) / period;
    results.push({ time: Math.floor(candles[i].timestamp / 1000), value: Number(curATR.toFixed(4)) });
    prevATR = curATR;
  }

  return results;
}

/**
 * Calculates Bollinger Bands.
 */
function computeBollingerBands(
  candles: WorkerCandle[],
  period = 20,
  stdMultiplier = 2.0
): {
  upper: IndicatorPointResult[];
  middle: IndicatorPointResult[];
  lower: IndicatorPointResult[];
} {
  const upper: IndicatorPointResult[] = [];
  const middle: IndicatorPointResult[] = [];
  const lower: IndicatorPointResult[] = [];

  if (candles.length < period) return { upper, middle, lower };

  for (let i = period - 1; i < candles.length; i++) {
    const slice = candles.slice(i - period + 1, i + 1);
    const mean = slice.reduce((sum, c) => sum + c.close, 0) / period;
    const variance = slice.reduce((sum, c) => sum + Math.pow(c.close - mean, 2), 0) / period;
    const std = Math.sqrt(variance);
    const t = Math.floor(candles[i].timestamp / 1000);

    middle.push({ time: t, value: Number(mean.toFixed(4)) });
    upper.push({ time: t, value: Number((mean + stdMultiplier * std).toFixed(4)) });
    lower.push({ time: t, value: Number((mean - stdMultiplier * std).toFixed(4)) });
  }

  return { upper, middle, lower };
}

/**
 * Calculates Session VWAP and Standard Deviation Bands.
 */
function computeVWAPSeries(candles: WorkerCandle[]): {
  vwap: IndicatorPointResult[];
  upper1s: IndicatorPointResult[];
  lower1s: IndicatorPointResult[];
  upper2s: IndicatorPointResult[];
  lower2s: IndicatorPointResult[];
} {
  const vwapList: IndicatorPointResult[] = [];
  const upper1s: IndicatorPointResult[] = [];
  const lower1s: IndicatorPointResult[] = [];
  const upper2s: IndicatorPointResult[] = [];
  const lower2s: IndicatorPointResult[] = [];

  let cumVol = 0;
  let cumTPVol = 0;
  let cumTPSqVol = 0;

  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const tp = (c.high + c.low + c.close) / 3;
    const v = Math.max(c.volume || 1, 1e-6);

    cumVol += v;
    cumTPVol += tp * v;
    cumTPSqVol += tp * tp * v;

    const vwapVal = cumTPVol / cumVol;
    const variance = Math.max(0, (cumTPSqVol / cumVol) - (vwapVal * vwapVal));
    const std = Math.sqrt(variance);
    const t = Math.floor(c.timestamp / 1000);

    vwapList.push({ time: t, value: Number(vwapVal.toFixed(4)) });
    upper1s.push({ time: t, value: Number((vwapVal + std).toFixed(4)) });
    lower1s.push({ time: t, value: Number((vwapVal - std).toFixed(4)) });
    upper2s.push({ time: t, value: Number((vwapVal + 2 * std).toFixed(4)) });
    lower2s.push({ time: t, value: Number((vwapVal - 2 * std).toFixed(4)) });
  }

  return { vwap: vwapList, upper1s, lower1s, upper2s, lower2s };
}

// Web Worker message dispatcher
self.onmessage = (event: MessageEvent<IndicatorRequestMessage>) => {
  const { id, candles, indicators } = event.data;

  const emaMap: Record<number, IndicatorPointResult[]> = {};
  if (indicators.emaPeriods) {
    for (const period of indicators.emaPeriods) {
      emaMap[period] = computeEMA(candles, period);
    }
  }

  const rsi = computeRSI(candles, indicators.rsiPeriod || 14);
  const atr = computeATR(candles, indicators.atrPeriod || 14);
  const bollinger = computeBollingerBands(
    candles,
    indicators.bollingerPeriod || 20,
    indicators.bollingerStdDev || 2.0
  );
  const vwap = computeVWAPSeries(candles);

  const response: IndicatorResponseMessage = {
    id,
    ema: emaMap,
    rsi,
    atr,
    bollingerBands: bollinger,
    vwap,
  };

  self.postMessage(response);
};
