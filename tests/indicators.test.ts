import {
  calculateEMA,
  calculateEMAFromPrices,
  calculateRSI,
  calculateRSIFromPrices,
} from '../src/utils/indicators';
import { OHLCVCandle } from '../src/types/candles';

describe('Indicator Primitives (EMA & RSI)', () => {
  describe('Exponential Moving Average (EMA)', () => {
    it('should compute exact EMA on a known dataset', () => {
      const prices = [
        22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29, 22.15,
      ];
      // Period 10:
      // Initial SMA (first 10) = 222.21 / 10 = 22.221
      // Next EMA = (22.15 - 22.221) * (2/11) + 22.221 = 22.2081
      const ema = calculateEMAFromPrices(prices, 10);
      expect(ema.length).toBe(2);
      expect(ema[0]).toBeCloseTo(22.221, 3);
      expect(ema[1]).toBeCloseTo(22.2081, 3);
    });

    it('should return empty array if price count is smaller than period', () => {
      const prices = [10, 20, 30];
      expect(calculateEMAFromPrices(prices, 5)).toEqual([]);
      expect(calculateEMAFromPrices([], 14)).toEqual([]);
    });

    it('should map EMA calculations correctly to candle timestamps', () => {
      const candles: OHLCVCandle[] = [
        [1000, 10, 12, 9, 10, 100],
        [2000, 10, 13, 10, 12, 100],
        [3000, 12, 15, 11, 14, 100],
        [4000, 14, 17, 13, 16, 100],
      ];

      const emaPoints = calculateEMA(candles, 3);
      // Period 3:
      // First point at index 2 (ts 3000): SMA(10, 12, 14) = 12.0000
      // Second point at index 3 (ts 4000): EMA = 16 * (2/4) + 12 * (2/4) = 14.0000
      expect(emaPoints).toHaveLength(2);
      expect(emaPoints[0]).toEqual({ ts: 3000, value: 12.0 });
      expect(emaPoints[1]).toEqual({ ts: 4000, value: 14.0 });
    });
  });

  describe('Relative Strength Index (RSI)', () => {
    it('should compute Wilder RSI accurately on standard test dataset', () => {
      const prices = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.1, 45.42, 45.84, 46.08, 45.89,
        46.03, 45.61, 46.28, 46.28, 46.0,
      ];
      // 16 prices -> 15 changes. Period = 14
      // First RSI point at index 14: ~70.46
      // Second RSI point at index 15: ~66.25
      const rsi = calculateRSIFromPrices(prices, 14);
      expect(rsi.length).toBe(2);
      expect(rsi[0]).toBeCloseTo(70.46, 1);
      expect(rsi[1]).toBeCloseTo(66.25, 1);
    });

    it('should handle extreme upward momentum (all gains -> RSI 100)', () => {
      const strictlyIncreasing = [10, 11, 12, 13, 14, 15];
      const rsi = calculateRSIFromPrices(strictlyIncreasing, 4);
      expect(rsi.length).toBe(2);
      expect(rsi[0]).toBe(100);
      expect(rsi[1]).toBe(100);
    });

    it('should handle extreme downward momentum (all losses -> RSI 0)', () => {
      const strictlyDecreasing = [20, 18, 16, 14, 12, 10];
      const rsi = calculateRSIFromPrices(strictlyDecreasing, 4);
      expect(rsi.length).toBe(2);
      expect(rsi[0]).toBe(0);
      expect(rsi[1]).toBe(0);
    });

    it('should return empty array if price count <= period', () => {
      expect(calculateRSIFromPrices([10, 20, 30], 5)).toEqual([]);
      expect(calculateRSIFromPrices([], 14)).toEqual([]);
    });

    it('should map RSI correctly to candle timestamps', () => {
      const candles: OHLCVCandle[] = [
        [1000, 10, 10, 10, 10, 1],
        [2000, 10, 12, 10, 12, 1],
        [3000, 12, 14, 11, 14, 1],
        [4000, 14, 16, 13, 16, 1],
        [5000, 16, 18, 15, 18, 1],
      ];

      const rsiPoints = calculateRSI(candles, 3);
      // Period 3 -> starts at candle index 3 (ts 4000)
      expect(rsiPoints.length).toBe(2);
      expect(rsiPoints[0].ts).toBe(4000);
      expect(rsiPoints[0].value).toBe(100);
      expect(rsiPoints[1].ts).toBe(5000);
      expect(rsiPoints[1].value).toBe(100);
    });
  });
});
