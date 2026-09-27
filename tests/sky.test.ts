import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import * as binanceService from '../src/services/binanceService';
import { defaultRateLimiter } from '../src/middleware/rateLimit';
import { OHLCVCandle } from '../src/types/candles';

describe('SKY Professional Market Intelligence Endpoints', () => {
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
    [1000, 100.0, 105.0, 98.0, 102.0, 50.0],
    [2000, 102.0, 104.0, 101.0, 103.0, 45.0],
    [3000, 103.0, 120.0, 102.5, 118.0, 200.0],
    [4000, 118.0, 122.0, 108.0, 121.0, 120.0],
    [5000, 121.0, 125.0, 119.0, 124.0, 110.0],
    [6000, 124.0, 128.0, 122.0, 126.0, 130.0],
    [7000, 126.0, 130.0, 125.0, 129.0, 140.0],
    [8000, 129.0, 135.0, 128.0, 134.0, 180.0],
    [9000, 134.0, 138.0, 132.0, 136.0, 160.0],
    [10000, 136.0, 140.0, 135.0, 139.0, 190.0],
  ];

  describe('GET /api/sky/intelligence', () => {
    it('should return quantitative decision output with regime, vwap, and setups', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValue(mockCandles);

      const res = await request(app).get('/api/sky/intelligence?symbol=BTCUSDT&timeframe=15m');

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('decision');
      expect(res.body).toHaveProperty('symbol', 'BTCUSDT');
      expect(res.body).toHaveProperty('timeframe', '15m');
      expect(res.body).toHaveProperty('explanation_dossier');
      expect(res.body).toHaveProperty('vwap');
      expect(res.body.vwap).toHaveProperty('vwap');
      expect(res.body.vwap).toHaveProperty('deviation_sigmas');
      expect(res.body).toHaveProperty('setups');
      expect(Array.isArray(res.body.setups)).toBe(true);
    });

    it('should validate query parameters and return 400 for invalid symbol', async () => {
      const res = await request(app).get('/api/sky/intelligence?symbol=invalid_sym');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
    });
  });

  describe('GET /api/sky/vwap', () => {
    it('should compute and return session VWAP with sigma bands', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValue(mockCandles);

      const res = await request(app).get('/api/sky/vwap?symbol=BTCUSDT&timeframe=15m');

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('symbol', 'BTCUSDT');
      expect(res.body).toHaveProperty('vwap');
      expect(res.body.vwap.vwap).toBeGreaterThan(0);
      expect(res.body.vwap.upper_band_1sigma).toBeGreaterThanOrEqual(res.body.vwap.vwap);
      expect(res.body.vwap.lower_band_1sigma).toBeLessThanOrEqual(res.body.vwap.vwap);
      expect(typeof res.body.vwap.mean_reversion_prob).toBe('number');
    });
  });

  describe('GET /api/sky/setups', () => {
    it('should return detected candidate and qualified setups', async () => {
      jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValue(mockCandles);

      const res = await request(app).get('/api/sky/setups?symbol=BTCUSDT&timeframe=15m');

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('total_scanned');
      expect(res.body).toHaveProperty('qualified_count');
      expect(Array.isArray(res.body.setups)).toBe(true);
    });
  });
});
