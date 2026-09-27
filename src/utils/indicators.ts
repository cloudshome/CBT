import { OHLCVCandle } from '../types/candles';

export interface IndicatorPoint {
  ts: number;
  value: number;
}

/**
 * Calculates Exponential Moving Average (EMA) for a sequence of prices.
 *
 * @param prices Array of numeric close prices.
 * @param period Lookback window size (default: 14).
 * @returns Array of EMA numbers aligned to prices starting at index (period - 1).
 */
export function calculateEMAFromPrices(prices: number[], period = 14): number[] {
  if (period <= 0 || prices.length < period) {
    return [];
  }

  const multiplier = 2 / (period + 1);
  const emaValues: number[] = [];

  // 1. Initial SMA for the first `period` elements
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += prices[i];
  }
  let currentEMA = sum / period;
  emaValues.push(currentEMA);

  // 2. Compute subsequent EMA values
  for (let i = period; i < prices.length; i++) {
    currentEMA = (prices[i] - currentEMA) * multiplier + currentEMA;
    emaValues.push(currentEMA);
  }

  return emaValues;
}

/**
 * Calculates EMA from OHLCV candles, mapping results to their corresponding timestamps.
 */
export function calculateEMA(candles: OHLCVCandle[], period = 14): IndicatorPoint[] {
  if (period <= 0 || candles.length < period) {
    return [];
  }

  const closePrices = candles.map((c) => c[4]); // close is index 4
  const emaValues = calculateEMAFromPrices(closePrices, period);

  const result: IndicatorPoint[] = [];
  const startIndex = period - 1;

  for (let i = 0; i < emaValues.length; i++) {
    const candleIndex = startIndex + i;
    result.push({
      ts: candles[candleIndex][0],
      value: Number(emaValues[i].toFixed(4)),
    });
  }

  return result;
}

/**
 * Calculates Wilder's Relative Strength Index (RSI) for a sequence of prices.
 *
 * @param prices Array of numeric close prices.
 * @param period Lookback window size (default: 14).
 * @returns Array of RSI numbers (0 - 100) aligned to prices starting at index `period`.
 */
export function calculateRSIFromPrices(prices: number[], period = 14): number[] {
  if (period <= 0 || prices.length <= period) {
    return [];
  }

  const rsiValues: number[] = [];

  // Calculate initial average gain and loss over the first `period` changes
  let gainSum = 0;
  let lossSum = 0;

  for (let i = 1; i <= period; i++) {
    const change = prices[i] - prices[i - 1];
    if (change >= 0) {
      gainSum += change;
    } else {
      lossSum += Math.abs(change);
    }
  }

  let avgGain = gainSum / period;
  let avgLoss = lossSum / period;

  // First RSI value
  if (avgLoss === 0) {
    rsiValues.push(100);
  } else if (avgGain === 0) {
    rsiValues.push(0);
  } else {
    const rs = avgGain / avgLoss;
    rsiValues.push(100 - 100 / (1 + rs));
  }

  // Wilder's smoothing for subsequent periods
  for (let i = period + 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? Math.abs(change) : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;

    if (avgLoss === 0) {
      rsiValues.push(100);
    } else if (avgGain === 0) {
      rsiValues.push(0);
    } else {
      const rs = avgGain / avgLoss;
      rsiValues.push(100 - 100 / (1 + rs));
    }
  }

  return rsiValues;
}

/**
 * Calculates Wilder's RSI from OHLCV candles, mapping results to their corresponding timestamps.
 */
export function calculateRSI(candles: OHLCVCandle[], period = 14): IndicatorPoint[] {
  if (period <= 0 || candles.length <= period) {
    return [];
  }

  const closePrices = candles.map((c) => c[4]);
  const rsiValues = calculateRSIFromPrices(closePrices, period);

  const result: IndicatorPoint[] = [];
  const startIndex = period;

  for (let i = 0; i < rsiValues.length; i++) {
    const candleIndex = startIndex + i;
    result.push({
      ts: candles[candleIndex][0],
      value: Number(rsiValues[i].toFixed(2)),
    });
  }

  return result;
}
