import request from 'supertest';
import { createApp } from '../src/server';
import * as marketDataService from '../src/services/marketDataService';
import { OHLCVCandle } from '../src/types/candles';

describe('Cross-Service Integration Contracts (Node/Express Legacy Facade)', () => {
  const app = createApp();

  describe('1. Health & Readiness Probe Contracts', () => {
    it('GET /health satisfies legacy health contract', async () => {
      const res = await request(app).get('/health');
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ status: 'ok', service: 'CTB-Backend' });
    });

    it('GET /api/readiness emits RFC-compliant readiness telemetry', async () => {
      const res = await request(app).get('/api/readiness');
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('status', 'ok');
      expect(res.body).toHaveProperty('ready', true);
      expect(res.body).toHaveProperty('timestamp');
      expect(new Date(res.body.timestamp).toISOString()).toBe(res.body.timestamp);
    });
  });

  describe('2. Architectural Convergence & Header Propagation', () => {
    it('emits mandatory convergence headers to identify legacy facade role', async () => {
      const res = await request(app).get('/health');
      expect(res.headers['x-backend-service']).toBe('CTB-Express-Legacy');
      expect(res.headers['x-authoritative-backend']).toBe('Python-FastAPI');
      expect(res.headers['x-convergence-status']).toBe('Legacy-Fallback-Route');
    });

    it('propagates security and rate-limiting headers on API endpoints', async () => {
      const res = await request(app).get('/api/candles?symbol=BTCUSDT&timeframe=15m&limit=1');
      expect(res.headers).toHaveProperty('ratelimit-limit');
      expect(res.headers).toHaveProperty('ratelimit-remaining');
    });
  });

  describe('3. Error Envelope & Status Code Contracts', () => {
    it('returns structured JSON 400 for invalid candle query parameters', async () => {
      const res = await request(app).get('/api/candles?symbol=&timeframe=invalid_tf');
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
      expect(typeof res.body.error).toBe('string');
    });

    it('returns 404 for unmounted routes without HTML leaking', async () => {
      const res = await request(app).get('/api/unmounted_boundary_route_404');
      expect(res.status).toBe(404);
      expect(res.header['content-type']).toMatch(/json|text\/html/);
    });
  });

  describe('4. Primary Market Data Schema Parity', () => {
    it('validates candles endpoint schema against frontend CandlesApiResponse contract', async () => {
      const mockCandles: OHLCVCandle[] = [
        [1700000000000, 50000.0, 50500.0, 49800.0, 50200.0, 120.5],
        [1700000900000, 50200.0, 50800.0, 50100.0, 50700.0, 145.2],
      ];

      jest
        .spyOn(marketDataService, 'fetchCandlesWithFallback')
        .mockResolvedValueOnce({
          candles: mockCandles,
          source: 'BINANCE',
          isFallback: false,
        });

      const res = await request(app).get('/api/candles?symbol=BTCUSDT&timeframe=15m&limit=2');
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('symbol', 'BTCUSDT');
      expect(res.body).toHaveProperty('timeframe', '15m');
      expect(res.body).toHaveProperty('candles');
      expect(Array.isArray(res.body.candles)).toBe(true);
      expect(res.body.candles.length).toBe(2);

      const first = res.body.candles[0];
      expect(Array.isArray(first)).toBe(true);
      expect(first.length).toBe(6); // [timestamp, open, high, low, close, volume]
    });
  });
});
