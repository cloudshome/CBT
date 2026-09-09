import request from 'supertest';
import { app } from '../src/server';

describe('Express Server Hardening & Convergence (Option 2)', () => {
  it('should include architectural convergence headers on responses', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.headers['x-backend-service']).toBe('CTB-Express-Legacy');
    expect(res.headers['x-authoritative-backend']).toBe('Python-FastAPI');
    expect(res.headers['x-convergence-status']).toBe('Legacy-Fallback-Route');
  });

  it('should reject request bodies exceeding 100kb with HTTP 413', async () => {
    // Generate a payload slightly larger than 100kb (e.g. 105kb of repetitive data)
    const largeString = 'x'.repeat(105 * 1024);
    const res = await request(app)
      .post('/api/paper/trade')
      .send({
        symbol: 'BTCUSDT',
        side: 'BUY',
        entryPrice: 65000,
        sl: 64000,
        tp: 68000,
        extraData: largeString,
      });

    expect(res.status).toBe(413);
    expect(res.body.error).toContain('Payload too large');
  });

  it('should accept request bodies under 100kb limit', async () => {
    const res = await request(app)
      .post('/api/paper/trade')
      .send({
        symbol: 'BTCUSDT',
        side: 'BUY',
        entryPrice: 65000,
        sl: 64000,
        tp: 68000,
        evidenceGrade: 'EMPIRICAL',
      });

    expect(res.status).toBe(201);
    expect(res.body.trade).toHaveProperty('id');
  });
});
