import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import * as binanceService from '../src/services/binanceService';
import * as bybitService from '../src/services/bybitService';
import * as candlesCacheService from '../src/services/candlesCacheService';
import { defaultRateLimiter } from '../src/middleware/rateLimit';
import { OHLCVCandle } from '../src/types/candles';

describe('GET /api/scan Endpoint (SMC Scanner)', () => {
  beforeAll(async () => {
    await prisma.$connect();
  });

  beforeEach(async () => {
    await prisma.candlesCache.deleteMany({});
    defaultRateLimiter.reset();
    jest.restoreAllMocks();
  });

  afterAll(async () => {
    await prisma.candlesCache.deleteMany({});
    await prisma.$disconnect();
  });

  // 10-candle dataset designed with a clear Bullish FVG (Candles 1, 2, 3) and Break of Structure
  const mockCandles: OHLCVCandle[] = [
    [1000, 100.0, 105.0, 98.0, 102.0, 50.0],
    [2000, 102.0, 104.0, 101.0, 103.0, 45.0], // C1: High = 104.0
    [3000, 103.0, 120.0, 102.5, 118.0, 200.0], // C2: Impulsive Green Candle
    [4000, 118.0, 122.0, 108.0, 121.0, 120.0], // C3: Low = 108.0 -> Gap: [104.0, 108.0]
    [5000, 121.0, 125.0, 119.0, 124.0, 110.0],
    [6000, 124.0, 128.0, 122.0, 126.0, 130.0],
    [7000, 126.0, 130.0, 125.0, 129.0, 140.0],
    [8000, 129.0, 135.0, 128.0, 134.0, 180.0],
    [9000, 134.0, 138.0, 132.0, 136.0, 160.0],
    [10000, 136.0, 140.0, 135.0, 139.0, 190.0],
  ];

  describe('Input Validation', () => {
    it('should return 400 if symbol parameter is missing', async () => {
      const res = await request(app).get('/api/scan');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Query parameter "symbol" is required');
    });

    it('should return 400 if symbol format is invalid', async () => {
      const res = await request(app).get('/api/scan?symbol=btc_usdt');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Symbol must be uppercase alphanumeric');
    });

    it('should return 400 if timeframe is unsupported', async () => {
      const res = await request(app).get('/api/scan?symbol=BTCUSDT&timeframe=2h');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Invalid timeframe "2h"');
    });

    it('should return 400 if limit is invalid', async () => {
      const res = await request(app).get('/api/scan?symbol=BTCUSDT&limit=0');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Limit must be an integer between 1 and 1000');
    });
  });

  describe('SMC Detection & Structure Scan', () => {
    it('should return 200 with detected FVGs, Order Blocks, and setup suggestions', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValueOnce(mockCandles);

      const res = await request(app).get('/api/scan?symbol=BTCUSDT&timeframe=15m');

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('BINANCE');
      expect(res.body.symbol).toBe('BTCUSDT');
      expect(res.body.timeframe).toBe('15m');

      // Verify FVGs
      expect(res.body).toHaveProperty('fvg');
      expect(Array.isArray(res.body.fvg)).toBe(true);
      expect(res.body.fvg.length).toBeGreaterThan(0);
      const bullishFvg = res.body.fvg.find((f: { type: string }) => f.type === 'bullish');
      expect(bullishFvg).toBeDefined();
      expect(bullishFvg.price_zone).toEqual([104.0, 108.0]);

      // Verify Order Blocks
      expect(res.body).toHaveProperty('order_blocks');
      expect(Array.isArray(res.body.order_blocks)).toBe(true);

      // Verify Setup Suggestions
      expect(res.body).toHaveProperty('setup_suggestions');
      expect(Array.isArray(res.body.setup_suggestions)).toBe(true);
      expect(res.body.setup_suggestions.length).toBeGreaterThan(0);

      const setup = res.body.setup_suggestions[0];
      expect(setup).toHaveProperty('type');
      expect(['LONG', 'SHORT']).toContain(setup.type);
      expect(setup).toHaveProperty('entry');
      expect(setup).toHaveProperty('stopLoss');
      expect(setup).toHaveProperty('takeProfit');
      expect(setup).toHaveProperty('riskRewardRatio');
      expect(setup.riskRewardRatio).toBeGreaterThan(0);

      // Verify Stats
      expect(res.body).toHaveProperty('stats');
      expect(res.body.stats.totalCandles).toBe(10);
      expect(res.body.stats.lastPrice).toBe(139.0);
      expect(res.body.stats.bullishFVGs).toBeGreaterThan(0);
    });
  });

  describe('Fallback Chain Integration', () => {
    it('should fallback to Bybit and perform SMC scan when Binance fails', async () => {
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance 503'));
      jest.spyOn(bybitService, 'fetchBybitCandles').mockResolvedValueOnce(mockCandles);

      const res = await request(app).get('/api/scan?symbol=ETHUSDT&timeframe=15m');

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('BYBIT');
      expect(res.headers['x-cache']).toBe('BYBIT-FALLBACK');
      expect(res.body.fvg.length).toBeGreaterThan(0);
    });

    it('should fallback to SQLite cache and perform SMC scan when both APIs fail', async () => {
      await candlesCacheService.saveCandles('SOLUSDT', '1h', mockCandles);

      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance timeout'));
      jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockRejectedValueOnce(new bybitService.BybitApiError('Bybit timeout'));

      const res = await request(app).get('/api/scan?symbol=SOLUSDT&timeframe=1h');

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('SQLITE_CACHE');
      expect(res.headers['x-cache']).toBe('HIT-FALLBACK');
      expect(res.body.stats.totalCandles).toBe(10);
    });

    it('should return 502 Bad Gateway when all market data sources fail and cache is empty', async () => {
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance 429'));
      jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockRejectedValueOnce(new bybitService.BybitApiError('Bybit 500'));

      const res = await request(app).get('/api/scan?symbol=AVAXUSDT&timeframe=4h');

      expect(res.status).toBe(502);
      expect(res.body.error).toContain('Failed to fetch market data from all sources');
    });
  });
});
