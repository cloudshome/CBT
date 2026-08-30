import request from 'supertest';
import { app } from '../src/server';

describe('Prometheus Metrics & Observability Endpoints', () => {
  it('GET /metrics should return standard Prometheus plain text format', async () => {
    const res = await request(app).get('/metrics');
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toContain('text/plain');
    expect(res.text).toContain('ctb_node_uptime_seconds');
    expect(res.text).toContain('ctb_node_heap_used_bytes');
    expect(res.text).toContain('ctb_exchange_circuit_breaker_state');
  });

  it('GET /api/metrics/json should return JSON diagnostic summary', async () => {
    const res = await request(app).get('/api/metrics/json');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('uptime_seconds');
    expect(res.body).toHaveProperty('memory');
    expect(res.body).toHaveProperty('circuit_breakers');
    expect(res.body.circuit_breakers).toHaveProperty('binance');
    expect(res.body.circuit_breakers).toHaveProperty('bybit');
  });
});
