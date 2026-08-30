import request from 'supertest';
import express, { Request, Response } from 'express';
import { createRateLimiter } from '../src/middleware/rateLimit';

describe('Enhanced Rate Limiting Middleware', () => {
  function createApp(limiter: ReturnType<typeof createRateLimiter>) {
    const app = express();
    app.use(express.json());
    app.get('/test', limiter, (_req: Request, res: Response) => {
      res.json({ success: true });
    });
    return app;
  }

  it('should enforce public IP rate limit after max requests', async () => {
    const limiter = createRateLimiter({
      windowMs: 10000,
      max: 3,
      authMax: 5,
    });
    const app = createApp(limiter);

    // 1st request
    const r1 = await request(app).get('/test');
    expect(r1.status).toBe(200);
    expect(r1.headers['ratelimit-limit']).toBe('3');
    expect(r1.headers['ratelimit-remaining']).toBe('2');

    // 2nd request
    const r2 = await request(app).get('/test');
    expect(r2.status).toBe(200);
    expect(r2.headers['ratelimit-remaining']).toBe('1');

    // 3rd request
    const r3 = await request(app).get('/test');
    expect(r3.status).toBe(200);
    expect(r3.headers['ratelimit-remaining']).toBe('0');

    // 4th request -> 429 Too Many Requests
    const r4 = await request(app).get('/test');
    expect(r4.status).toBe(429);
    expect(r4.body).toHaveProperty('error');
    expect(r4.headers).toHaveProperty('retry-after');

    limiter.cleanup();
  });

  it('should allow higher quota for authenticated requests with X-API-Key', async () => {
    const limiter = createRateLimiter({
      windowMs: 10000,
      max: 2,
      authMax: 4,
    });
    const app = createApp(limiter);

    // Send 4 requests with X-API-Key
    for (let i = 1; i <= 4; i++) {
      const res = await request(app)
        .get('/test')
        .set('X-API-Key', 'secret-agent-key');
      expect(res.status).toBe(200);
      expect(res.headers['ratelimit-limit']).toBe('4');
    }

    // 5th request breaches auth limit -> 429
    const r5 = await request(app)
      .get('/test')
      .set('X-API-Key', 'secret-agent-key');
    expect(r5.status).toBe(429);

    limiter.cleanup();
  });

  it('should isolate rate limits across different client IPs', async () => {
    const limiter = createRateLimiter({
      windowMs: 10000,
      max: 2,
    });
    const app = createApp(limiter);

    // IP 1: 2 requests
    await request(app).get('/test').set('X-Forwarded-For', '10.0.0.1');
    await request(app).get('/test').set('X-Forwarded-For', '10.0.0.1');
    const ip1Blocked = await request(app).get('/test').set('X-Forwarded-For', '10.0.0.1');
    expect(ip1Blocked.status).toBe(429);

    // IP 2: Should still have full quota
    const ip2Req = await request(app).get('/test').set('X-Forwarded-For', '10.0.0.2');
    expect(ip2Req.status).toBe(200);
    expect(ip2Req.headers['ratelimit-remaining']).toBe('1');

    limiter.cleanup();
  });

  it('should reset limits when reset() is invoked', async () => {
    const limiter = createRateLimiter({
      windowMs: 10000,
      max: 1,
    });
    const app = createApp(limiter);

    await request(app).get('/test');
    const blocked = await request(app).get('/test');
    expect(blocked.status).toBe(429);

    limiter.reset();

    const allowedAfterReset = await request(app).get('/test');
    expect(allowedAfterReset.status).toBe(200);

    limiter.cleanup();
  });
});
