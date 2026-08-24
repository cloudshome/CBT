import request from 'supertest';
import { app } from '../src/server';

describe('Server Root & Readiness Endpoints', () => {
  describe('GET /', () => {
    it('should return 200 OK with server status info', async () => {
      const res = await request(app).get('/');
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('name', 'Crypto Brain Terminal (CTB) API');
      expect(res.body).toHaveProperty('status', 'online');
      expect(res.body).toHaveProperty('version', '0.1.0');
    });
  });

  describe('GET /health', () => {
    it('should return 200 OK with health status', async () => {
      const res = await request(app).get('/health');
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ status: 'ok', service: 'CTB-Backend' });
    });
  });

  describe('GET /api/readiness', () => {
    it('should return 200 OK with readiness status and ISO timestamp', async () => {
      const res = await request(app).get('/api/readiness');
      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('status', 'ok');
      expect(res.body).toHaveProperty('ready', true);
      expect(res.body).toHaveProperty('timestamp');
      expect(new Date(res.body.timestamp).toISOString()).toBe(res.body.timestamp);
    });
  });
});
