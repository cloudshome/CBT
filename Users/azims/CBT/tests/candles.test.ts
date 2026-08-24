import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import * as binanceService from '../src/services/binanceService';
import * as candlesCacheService from '../src/services/candlesCacheService';
import { OHLCVCandle } from '../src/types/candles';

describe('GET /api/candles Endpoint', () => {
  beforeAll(async () => {
    // Ensure DB is initialized
    await prisma.$connect();
  });

  beforeEach(async () => {
    // Clean up cache table before each test
    await prisma.candlesCache.deleteMany({});
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

  describe('Successful Fetch & Caching', () => {
    it('should fetch from Binance REST, return normalized OHLCV arrays, and save to SQLite cache', async () => {
      const mockCandles: OHLCVCandle[] = [
        [1700000000000, 60000.1, 60500.2, 59900.0, 60200.5, 100.25],
        [1700000900000, 60200.5, 60800.0, 60100.0, 60750.0, 150.75],
      ];

      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockResolvedValueOnce(mockCandles);

      const res = await request(app).get('/api/candles?symbol=BTCUSDT&timeframe=15m&limit=2');

      expect(res.status).toBe(200);
      expect(res.body).toEqual({
        symbol: 'BTCUSDT',
        timeframe: '15m',
        candles: mockCandles,
      });

      // Allow async cache write to complete
      await new Promise((resolve) => setTimeout(resolve, 100));

      // Verify records are persisted in SQLite DB
      const cached = await candlesCacheService.getCachedCandles('BTCUSDT', '15m', 10);
      expect(cached).toEqual(mockCandles);
    });
  });

  describe('Cache Fallback when Binance REST fails', () => {
    it('should serve cached data with X-Cache header when Binance API fails and cache exists', async () => {
      const cachedCandles: OHLCVCandle[] = [
        [1700000000000, 3000.0, 3100.0, 2950.0, 3050.0, 45.0],
        [1700000900000, 3050.0, 3120.0, 3040.0, 3090.0, 60.5],
      ];

      // Populate SQLite cache
      await candlesCacheService.saveCandles('ETHUSDT', '1h', cachedCandles);

      // Simulate Binance API failure
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance API is unreachable', 503));

      const res = await request(app).get('/api/candles?symbol=ETHUSDT&timeframe=1h&limit=2');

      expect(res.status).toBe(200);
      expect(res.headers['x-cache']).toBe('HIT-FALLBACK');
      expect(res.body).toEqual({
        symbol: 'ETHUSDT',
        timeframe: '1h',
        candles: cachedCandles,
      });
    });

    it('should return 502 Bad Gateway when Binance API fails and no cached data exists', async () => {
      // Simulate Binance API network failure
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Network connection timeout'));

      const res = await request(app).get('/api/candles?symbol=SOLUSDT&timeframe=4h');

      expect(res.status).toBe(502);
      expect(res.body).toHaveProperty('error');
      expect(res.body.error).toContain('Failed to fetch market data from Binance and no cached data available');
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

      // Upsert update to candle1 + insert candle2
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
      // The 2 most recent candles in ascending order
      expect(cachedLimit2[0][0]).toBe(2000);
      expect(cachedLimit2[1][0]).toBe(3000);
    });
  });
});
