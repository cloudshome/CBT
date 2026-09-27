import request from 'supertest';
import express, { Request, Response } from 'express';
import { apiKeyAuth } from '../src/middleware/apiKeyAuth';

describe('API Key Authentication Middleware', () => {
  const originalApiKey = process.env.API_KEY;

  afterEach(() => {
    process.env.API_KEY = originalApiKey;
  });

  function createTestApp() {
    const app = express();
    app.use(express.json());

    // Public route
    app.get('/public', (_req: Request, res: Response) => {
      res.json({ access: 'public' });
    });

    // Protected route
    app.get('/protected', apiKeyAuth, (_req: Request, res: Response) => {
      res.json({ access: 'granted' });
    });

    app.post('/protected-write', apiKeyAuth, (req: Request, res: Response) => {
      res.json({ status: 'ok', data: req.body });
    });

    return app;
  }

  describe('When API_KEY is not configured (Dev / Default Mode)', () => {
    it('should allow access to protected routes without any key', async () => {
      delete process.env.API_KEY;
      const testApp = createTestApp();

      const res = await request(testApp).get('/protected');
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ access: 'granted' });
    });

    it('should allow write operations without any key', async () => {
      delete process.env.API_KEY;
      const testApp = createTestApp();

      const res = await request(testApp)
        .post('/protected-write')
        .send({ trade: 'BTC' });
      expect(res.status).toBe(200);
      expect(res.body.data).toEqual({ trade: 'BTC' });
    });
  });

  describe('When API_KEY is configured', () => {
    const SECRET = 'test-secret-key-12345';
    let testApp: express.Express;

    beforeEach(() => {
      process.env.API_KEY = SECRET;
      testApp = createTestApp();
    });

    it('should allow access to public routes without key', async () => {
      const res = await request(testApp).get('/public');
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ access: 'public' });
    });

    it('should reject request without any key with 401 Unauthorized', async () => {
      const res = await request(testApp).get('/protected');
      expect(res.status).toBe(401);
      expect(res.body).toHaveProperty('error', 'Authentication required');
    });

    it('should reject request with invalid key with 403 Forbidden', async () => {
      const res = await request(testApp)
        .get('/protected')
        .set('X-API-Key', 'wrong-key');
      expect(res.status).toBe(403);
      expect(res.body).toHaveProperty('error', 'Invalid API key');
    });

    it('should accept request with valid X-API-Key header', async () => {
      const res = await request(testApp)
        .get('/protected')
        .set('X-API-Key', SECRET);
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ access: 'granted' });
    });

    it('should accept request with valid Authorization: Bearer token', async () => {
      const res = await request(testApp)
        .get('/protected')
        .set('Authorization', `Bearer ${SECRET}`);
      expect(res.status).toBe(200);
      expect(res.body).toEqual({ access: 'granted' });
    });

    it('should accept write operations with valid key', async () => {
      const res = await request(testApp)
        .post('/protected-write')
        .set('X-API-Key', SECRET)
        .send({ trade: 'ETH' });
      expect(res.status).toBe(200);
      expect(res.body.data).toEqual({ trade: 'ETH' });
    });
  });
});
