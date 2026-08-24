import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import * as binanceService from '../src/services/binanceService';
import * as bybitService from '../src/services/bybitService';
import * as candlesCacheService from '../src/services/candlesCacheService';
import { defaultRateLimiter } from '../src/middleware/rateLimit';
import { OHLCVCandle } from '../src/types/candles';

describe('GET /api/mtf Endpoint', () => {
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

  const mockCandles: OHLCVCandle[] = [
    [1000, 10, 11, 9, 10, 100],
    [2000, 10, 13, 10, 12, 100],
    [3000, 12, 15, 11, 14, 100],
    [4000, 14, 17, 13, 16, 100],
    [5000, 16, 19, 15, 18, 100],
  ];

  describe('Input Validation', () => {
    it('should return 400 if symbol is missing', async () => {
      const res = await request(app).get('/api/mtf?indicators=ema');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Query parameter "symbol" is required');
    });

    it('should return 400 if indicators parameter is missing', async () => {
      const res = await request(app).get('/api/mtf?symbol=BTCUSDT');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Query parameter "indicators" is required');
    });

    it('should return 400 if an unsupported indicator is requested', async () => {
      const res = await request(app).get('/api/mtf?symbol=BTCUSDT&indicators=macd');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Unsupported indicator "macd"');
    });

    it('should return 400 if invalid custom period is passed', async () => {
      const res = await request(app).get('/api/mtf?symbol=BTCUSDT&indicators=ema&emaPeriod=-5');
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('must be a positive integer');
    });
  });

  describe('Indicator Computation on Market Data', () => {
    it('should compute EMA successfully for requested symbol and timeframe', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValueOnce(mockCandles);

      const res = await request(app).get(
        '/api/mtf?symbol=BTCUSDT&timeframe=15m&indicators=ema&emaPeriod=3'
      );

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('BINANCE');
      expect(res.body.symbol).toBe('BTCUSDT');
      expect(res.body.timeframe).toBe('15m');
      expect(res.body.indicators).toHaveProperty('ema');
      expect(res.body.indicators).not.toHaveProperty('rsi');
      expect(res.body.indicators.ema).toEqual([
        { ts: 3000, value: 12.0 },
        { ts: 4000, value: 14.0 },
        { ts: 5000, value: 16.0 },
      ]);
    });

    it('should compute RSI successfully for requested symbol and timeframe', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValueOnce(mockCandles);

      const res = await request(app).get(
        '/api/mtf?symbol=ETHUSDT&timeframe=1h&indicators=rsi&rsiPeriod=3'
      );

      expect(res.status).toBe(200);
      expect(res.body.symbol).toBe('ETHUSDT');
      expect(res.body.timeframe).toBe('1h');
      expect(res.body.indicators).toHaveProperty('rsi');
      expect(res.body.indicators).not.toHaveProperty('ema');
      expect(res.body.indicators.rsi).toHaveLength(2);
      expect(res.body.indicators.rsi[0]).toEqual({ ts: 4000, value: 100 });
    });

    it('should compute both EMA and RSI simultaneously when requested', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValueOnce(mockCandles);

      const res = await request(app).get(
        '/api/mtf?symbol=BTCUSDT&timeframe=15m&indicators=ema,rsi&emaPeriod=3&rsiPeriod=3'
      );

      expect(res.status).toBe(200);
      expect(res.body.indicators).toHaveProperty('ema');
      expect(res.body.indicators).toHaveProperty('rsi');
      expect(res.body.indicators.ema.length).toBeGreaterThan(0);
      expect(res.body.indicators.rsi.length).toBeGreaterThan(0);
    });
  });

  describe('Fallback Integration', () => {
    it('should compute indicators using Bybit fallback if Binance fails', async () => {
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance down'));
      jest.spyOn(bybitService, 'fetchBybitCandles').mockResolvedValueOnce(mockCandles);

      const res = await request(app).get(
        '/api/mtf?symbol=SOLUSDT&timeframe=4h&indicators=ema&emaPeriod=3'
      );

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('BYBIT');
      expect(res.headers['x-cache']).toBe('BYBIT-FALLBACK');
      expect(res.body.indicators.ema).toHaveLength(3);
    });

    it('should compute indicators using SQLite cache if Binance and Bybit fail', async () => {
      await candlesCacheService.saveCandles('SOLUSDT', '4h', mockCandles);

      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance down'));
      jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockRejectedValueOnce(new bybitService.BybitApiError('Bybit down'));

      const res = await request(app).get(
        '/api/mtf?symbol=SOLUSDT&timeframe=4h&indicators=ema&emaPeriod=3'
      );

      expect(res.status).toBe(200);
      expect(res.headers['x-data-source']).toBe('SQLITE_CACHE');
      expect(res.headers['x-cache']).toBe('HIT-FALLBACK');
      expect(res.body.indicators.ema).toHaveLength(3);
    });

    it('should return 502 Bad Gateway if all sources fail and cache is empty', async () => {
      jest
        .spyOn(binanceService, 'fetchBinanceCandles')
        .mockRejectedValueOnce(new binanceService.BinanceApiError('Binance timeout'));
      jest
        .spyOn(bybitService, 'fetchBybitCandles')
        .mockRejectedValueOnce(new bybitService.BybitApiError('Bybit timeout'));

      const res = await request(app).get('/api/mtf?symbol=ADAUSDT&timeframe=1d&indicators=ema');

      expect(res.status).toBe(502);
      expect(res.body.error).toContain('Failed to fetch market data from all sources');
    });
  });
});
