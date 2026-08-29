import request from 'supertest';
import { createApp } from '../src/server';
import { defaultRateLimiter } from '../src/middleware/rateLimit';

// Mock the market data service to return deterministic candles
jest.mock('../src/services/marketDataService', () => {
  const original = jest.requireActual('../src/services/marketDataService');
  return {
    ...original,
    fetchCandlesWithFallback: jest.fn(async () => {
      const now = Date.now();
      const candles = [];
      let p = 88000;
      for (let i = 0; i < 50; i++) {
        const o = p;
        const c = p + 25;
        candles.push([now - (50 - i) * 900000, o, o + 50, o - 30, c, 500]);
        p = c;
      }
      return { candles, source: 'binance' };
    }),
  };
});

describe('Institutional Alpha & Microstructure Routes (/api/institutional)', () => {
  const app = createApp();

  beforeEach(() => {
    defaultRateLimiter.reset();
  });

  it('GET /api/institutional/alpha returns 8-mechanic composite response', async () => {
    const res = await request(app).get('/api/institutional/alpha?symbol=BTCUSDT&timeframe=15m');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('symbol', 'BTCUSDT');
    expect(res.body).toHaveProperty('decision');
    expect(res.body).toHaveProperty('institutional_composite_score');
    expect(res.body).toHaveProperty('lead_lag');
    expect(res.body).toHaveProperty('cvd_absorption');
    expect(res.body).toHaveProperty('orderbook_imbalance');
    expect(res.body).toHaveProperty('oi_funding_squeeze');
    expect(res.body).toHaveProperty('judas_sweep');
    expect(res.body).toHaveProperty('vwap_multisigma');
    expect(res.body).toHaveProperty('fractal_harmonics');
    expect(res.body).toHaveProperty('half_kelly_sizing');
    expect(res.body).toHaveProperty('execution_dossier');
  });

  it('GET /api/institutional/cvd returns orderflow delta and absorption status', async () => {
    const res = await request(app).get('/api/institutional/cvd?symbol=BTCUSDT&timeframe=15m');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('current_cvd');
    expect(res.body).toHaveProperty('absorption_detected');
    expect(res.body).toHaveProperty('absorption_type');
  });

  it('GET /api/institutional/orderbook-imbalance returns OBI score and VPIN toxicity', async () => {
    const res = await request(app).get('/api/institutional/orderbook-imbalance?symbol=BTCUSDT');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('obi_score');
    expect(res.body).toHaveProperty('flow_toxicity_vpin');
    expect(res.body).toHaveProperty('regime');
  });
});
