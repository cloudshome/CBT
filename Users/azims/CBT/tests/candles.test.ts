import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import * as binanceService from '../src/services/binanceService';
import * as bybitService from '../src/services/bybitService';
import * as marketDataService from '../src/services/marketDataService';
import * as candlesCacheService from '../src/services/candlesCacheService';
import { defaultRateLimiter, createRateLimiter } from '../src/middleware/rateLimit';
import { OHLCVCandle } from '../src/types/candles';
import express from 'express';

describe('GET /api/candles Endpoint', () => {
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

  describe('Input Validation', () => {
    it('should return 400 if symbol parameter is missing', async () => {
      const res = await request(app).get('/api/candles');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Query parameter "symbol" is required');
    });

    it('should return 400 if symbol has invalid format (lowercase)', async () => {
      const res = await request(app).get('/api/candles?symbol=btcusdt');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Symbol must be uppercase alphanumeric');
    });

    it('should return 400 if symbol has invalid characters', async () => {
      const res = await request(app).get('/api/candles?symbol=BTC-USDT');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Symbol must be uppercase alphanumeric');
    });

    it('should return 400 if timeframe is unsupported', async () => {
      const res = await request(app).get('/api/candles?symbol=BTCUSDT&timeframe=30m');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Invalid timeframe "30m"');
    });

    it('should return 400 if limit is not a positive integer', async () => {
      const res = await request(app).get('/api/candles?symbol=BTCUSDT&limit=0');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Limit must be an integer between 1 and 1000');
    });

    it('should return 400 if limit exceeds 1000', async () => {
      const res = await request(app).get('/api/candles?symbol=BTCUSDT&limit=1001');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Limit must be an integer between 1 and 1000');
    });

    it('should normalize symbol by appending USDT if omitted', async () => {
      const mockCandles: OHLCVCandle[] = [
        [1700000000000, 50000.0, 51000.0, 49500.0, 50500.0, 12.5],
      ];

      const fetchSpy = jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockResolvedValueOnce(mockCandles);

      const res = await request(app).get('/api/candles?symbol=BTC&timeframe=15m');
      expect(res.status).toBe(200);
      expect(fetchSpy).toHaveBeenCalledWith('BTCUSDT', '15m', 100);
      expect(res.body.symbol).toBe('BTCUSDT');
      expect(res.body.timeframe).toBe('15m');
      expect(res.body.candles).toEqual(mockCandles);
    });
  });

  describe('Fallback Chain: Binance -> Bybit -> SQLite Cache -> 502', () => {
    it('Tier 1: should return Binance data with X-Data-Source: BINANCE and cache to SQLite', async () => {
      const binanceCandles: OHLCVCandle[] = [
        [1700000000000, 60000.0, 60500.0, 59900.0, 60200.0, 100.0],
        [1700000900000, 60200.0, 60800.0, 60100.0, 60750.0, 150.0],
      ];

      const binanceSpy = jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockResolvedValueOnce(binanceCandles);
      const bybitSpy = jest.spyOn(bybitService, 'fetchBybitCandles');

      const res = await request(app).get('/api/candles?symbol=BTCUSDT&timeframe=15m&limit=2');

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('BINANCE');
      expect(res.body).toEqual({
        symbol: 'BTCUSDT',
        timeframe: '15m',
        candles: binanceCandles,
      });
      expect(binanceSpy).toHaveBeenCalledTimes(1);
      expect(bybitSpy).not.toHaveBeenCalled();

      // Verify cached to SQLite
      await new Promise((resolve) => setTimeout(resolve, 80));
      const cached = await candlesCacheService.getCachedCandles('BTCUSDT', '15m', 10);
      expect(cached).toEqual(binanceCandles);
    });

    it('Tier 2: should fallback to Bybit when Binance fails, return normalized data, and cache to SQLite', async () => {
      const bybitCandles: OHLCVCandle[] = [
        [1700000000000, 3000.0, 3050.0, 2980.0, 3020.0, 50.0],
        [1700000900000, 3020.0, 3080.0, 3010.0, 3060.0, 75.0],
      ];

      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance 503 Service Unavailable', 503));

      const bybitSpy = jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockResolvedValueOnce(bybitCandles);

      const res = await request(app).get('/api/candles?symbol=ETHUSDT&timeframe=15m&limit=2');

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('BYBIT');
      expect(res.headers['x-cache']).toBe('BYBIT-FALLBACK');
      expect(res.body).toEqual({
        symbol: 'ETHUSDT',
        timeframe: '15m',
        candles: bybitCandles,
      });
      expect(bybitSpy).toHaveBeenCalledWith('ETHUSDT', '15m', 2);

      // Verify cached to SQLite
      await new Promise((resolve) => setTimeout(resolve, 80));
      const cached = await candlesCacheService.getCachedCandles('ETHUSDT', '15m', 10);
      expect(cached).toEqual(bybitCandles);
    });

    it('Tier 3: should fallback to SQLite cache when both Binance and Bybit fail', async () => {
      const cachedCandles: OHLCVCandle[] = [
        [1700000000000, 150.0, 155.0, 148.0, 152.0, 300.0],
        [1700000900000, 152.0, 158.0, 151.0, 156.0, 450.0],
      ];

      // Seed SQLite cache
      await candlesCacheService.saveCandles('SOLUSDT', '1h', cachedCandles);

      // Both APIs fail
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance timeout'));
      jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockRejectedValueOnce(new bybitService.BybitApiError('Bybit timeout'));

      const res = await request(app).get('/api/candles?symbol=SOLUSDT&timeframe=1h&limit=2');

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('SQLITE_CACHE');
      expect(res.headers['x-cache']).toBe('HIT-FALLBACK');
      expect(res.body).toEqual({
        symbol: 'SOLUSDT',
        timeframe: '1h',
        candles: cachedCandles,
      });
    });

    it('Tier 4: should return 502 Bad Gateway when all sources fail and cache is empty', async () => {
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance 429 Rate limited', 429));
      jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockRejectedValueOnce(new bybitService.BybitApiError('Bybit 500 Internal Error', 500));

      const res = await request(app).get('/api/candles?symbol=AVAXUSDT&timeframe=4h');

      expect(res.status).toBe(502);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Failed to fetch market data from all sources');
      expect(res.body.details).toEqual([
        expect.stringContaining('Binance'),
        expect.stringContaining('Bybit'),
      ]);
    });
  });

  describe('Rate Limiting Middleware', () => {
    it('should include rate limiting headers on responses', async () => {
      jest
        .spyOn(marketDataService, 'fetchCandlesWithFallback')
        .mockResolvedValueOnce({
          candles: [[1700000000000, 100, 105, 95, 102, 10]],
          source: 'BINANCE',
          isFallback: false,
        });

      const res = await request(app).get('/api/candles?symbol=BTCUSDT');

      expect(res.status).toBe(200);
      expect(res.headers).toHaveProperty('ratelimit-limit');
      expect(res.headers).toHaveProperty('ratelimit-remaining');
      expect(res.headers).toHaveProperty('ratelimit-reset');
      expect(res.headers['ratelimit-limit']).toBe('60');
    });

    it('should block requests and return 429 Too Many Requests when rate limit exceeded', async () => {
      const customApp = express();
      const testLimiter = createRateLimiter({ windowMs: 10000, max: 2 });
      customApp.use(testLimiter);
      customApp.get('/test', (_req, res) => res.json({ ok: true }));

      // Request 1: OK
      const res1 = await request(customApp).get('/test');
      expect(res1.status).toBe(200);
      expect(res1.headers['ratelimit-remaining']).toBe('1');

      // Request 2: OK
      const res2 = await request(customApp).get('/test');
      expect(res2.status).toBe(200);
      expect(res2.headers['ratelimit-remaining']).toBe('0');

      // Request 3: Blocked (429)
      const res3 = await request(customApp).get('/test');
      expect(res3.status).toBe(429);
      expect(res3.headers).toHaveProperty('retry-after');
      expect(res3.body).toEqual({
        error: 'Too many requests, please try again later.',
      });
    });
  });

  describe('Bybit Service Unit Tests', () => {
    it('should correctly map timeframes to Bybit interval parameters', () => {
      expect(bybitService.mapTimeframeToBybitInterval('5m')).toBe('5');
      expect(bybitService.mapTimeframeToBybitInterval('15m')).toBe('15');
      expect(bybitService.mapTimeframeToBybitInterval('1h')).toBe('60');
      expect(bybitService.mapTimeframeToBybitInterval('4h')).toBe('240');
      expect(bybitService.mapTimeframeToBybitInterval('1d')).toBe('D');
    });
  });

  describe('Direct Caching Service Unit Tests', () => {
    it('should upsert candles without duplicating timestamps', async () => {
      const candle1: OHLCVCandle = [1700000000000, 100, 110, 95, 105, 10];
      const candle1Updated: OHLCVCandle = [1700000000000, 100, 115, 95, 108, 15];
      const candle2: OHLCVCandle = [1700000900000, 108, 120, 106, 118, 20];

      await candlesCacheService.saveCandles('BNBUSDT', '5m', [candle1]);
      let cached = await candlesCacheService.getCachedCandles('BNBUSDT', '5m', 10);
      expect(cached.length).toBe(1);
      expect(cached[0]).toEqual(candle1);

      await candlesCacheService.saveCandles('BNBUSDT', '5m', [candle1Updated, candle2]);
      cached = await candlesCacheService.getCachedCandles('BNBUSDT', '5m', 10);
      expect(cached.length).toBe(2);
      expect(cached[0]).toEqual(candle1Updated);
      expect(cached[1]).toEqual(candle2);
    });

    it('should respect limit parameter and order chronologically', async () => {
      const candles: OHLCVCandle[] = [
        [1000, 1, 2, 0.5, 1.5, 10],
        [2000, 1.5, 2.5, 1.0, 2.0, 15],
        [3000, 2.0, 3.0, 1.8, 2.8, 20],
      ];

      await candlesCacheService.saveCandles('ADAUSDT', '1d', candles);

      const cachedLimit2 = await candlesCacheService.getCachedCandles('ADAUSDT', '1d', 2);
      expect(cachedLimit2.length).toBe(2);
      expect(cachedLimit2[0][0]).toBe(2000);
      expect(cachedLimit2[1][0]).toBe(3000);
    });
  });
});
