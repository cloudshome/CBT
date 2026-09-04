import {
  parseAndNormalizeCandles,
  runQuantDetection,
  generateSetups,
} from '../src/utils/quantEngine';
import { Candle } from '../src/types';

describe('QuantEngine Deep Unit Tests (P0 Branch & Edge Coverage)', () => {
  describe('parseAndNormalizeCandles', () => {
    it('should return empty array for null, undefined, or empty input', () => {
      expect(parseAndNormalizeCandles(null)).toEqual([]);
      expect(parseAndNormalizeCandles(undefined)).toEqual([]);
      expect(parseAndNormalizeCandles('')).toEqual([]);
      expect(parseAndNormalizeCandles([])).toEqual([]);
    });

    it('should parse valid array of arrays [ts, o, h, l, c, v]', () => {
      const raw = [
        [2000, '102', '106', '101', '105', '50'],
        [1000, '100', '104', '98', '102', '40'],
      ];
      const parsed = parseAndNormalizeCandles(raw);
      expect(parsed).toHaveLength(2);
      // Chronological sort
      expect(parsed[0].timestamp).toBe(1000);
      expect(parsed[0].index).toBe(0);
      expect(parsed[1].timestamp).toBe(2000);
      expect(parsed[1].index).toBe(1);
    });

    it('should parse JSON string with candles object structure', () => {
      const jsonStr = JSON.stringify({
        candles: [
          { timestamp: 1000, open: 100, high: 105, low: 95, close: 103, volume: 10 },
          { t: 2000, o: 103, h: 108, l: 102, c: 106, v: 12 },
        ],
      });
      const parsed = parseAndNormalizeCandles(jsonStr);
      expect(parsed).toHaveLength(2);
      expect(parsed[0].open).toBe(100);
      expect(parsed[1].timestamp).toBe(2000);
    });

    it('should return empty array on malformed JSON string', () => {
      const invalidJson = '{ malformed json string !! ';
      expect(parseAndNormalizeCandles(invalidJson)).toEqual([]);
    });

    it('should skip rows with NaN values', () => {
      const mixed = [
        [1000, '100', '105', '95', '102', '10'],
        ['invalid_ts', 'abc', 'def', 'ghi', 'jkl', 'mno'],
      ];
      const parsed = parseAndNormalizeCandles(mixed);
      expect(parsed).toHaveLength(1);
      expect(parsed[0].timestamp).toBe(1000);
    });
  });

  describe('runQuantDetection & generateSetups', () => {
    it('should handle empty or minimal candle arrays safely', () => {
      const emptyDetection = runQuantDetection([]);
      expect(emptyDetection).toBeDefined();
      expect(emptyDetection.detailedFVGs).toEqual([]);
      expect(emptyDetection.detailedOrderBlocks).toEqual([]);
      expect(generateSetups(emptyDetection)).toEqual([]);
    });

    it('should identify Bullish and Bearish Fair Value Gaps (FVG)', () => {
      const candles: Candle[] = [
        { index: 0, timestamp: 1000, open: 100, high: 102, low: 98, close: 101, volume: 10 }, // C1: High 102
        { index: 1, timestamp: 2000, open: 101, high: 115, low: 101, close: 114, volume: 50 }, // C2: Impulsive Up
        { index: 2, timestamp: 3000, open: 114, high: 118, low: 106, close: 116, volume: 20 }, // C3: Low 106 -> Gap [102, 106]
        { index: 3, timestamp: 4000, open: 116, high: 120, low: 115, close: 119, volume: 30 },
        { index: 4, timestamp: 5000, open: 119, high: 122, low: 117, close: 121, volume: 40 },
      ];

      const detection = runQuantDetection(candles);
      expect(detection.detailedFVGs.length).toBeGreaterThanOrEqual(1);
      const bullFvg = detection.detailedFVGs.find((f: { type: string }) => f.type === 'bullish');
      expect(bullFvg).toBeDefined();
      expect(bullFvg?.price_zone[0]).toBe(102);
      expect(bullFvg?.price_zone[1]).toBe(106);
    });

    it('should detect Order Blocks, Swings, and generate Setup Suggestions', () => {
      const candles: Candle[] = [];
      for (let i = 0; i < 30; i++) {
        const base = 100 + i * 2;
        candles.push({
          index: i,
          timestamp: 1000 + i * 60000,
          open: base,
          high: base + 4,
          low: base - 1,
          close: base + 3,
          volume: 50 + (i === 15 ? 300 : 10), // Breakout volume spike at i=15
        });
      }

      const detection = runQuantDetection(candles);
      expect(detection).toHaveProperty('swings');
      expect(detection).toHaveProperty('detailedOrderBlocks');
      expect(detection).toHaveProperty('bosList');

      const setups = generateSetups(detection);
      expect(Array.isArray(setups)).toBe(true);
    });
  });
});
