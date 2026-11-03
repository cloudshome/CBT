import request from 'supertest';
import { createApp } from '../src/server';

describe('CORS configuration (fail-closed in production)', () => {
  const originalEnv = process.env.NODE_ENV;
  const originalCors = process.env.CORS_ORIGIN;
  const originalApiKey = process.env.API_KEY;

  beforeEach(() => {
    process.env.API_KEY = 'test-long-valid-api-key-12345';
  });

  afterEach(() => {
    process.env.NODE_ENV = originalEnv;
    if (originalCors === undefined) {
      delete process.env.CORS_ORIGIN;
    } else {
      process.env.CORS_ORIGIN = originalCors;
    }
    if (originalApiKey === undefined) {
      delete process.env.API_KEY;
    } else {
      process.env.API_KEY = originalApiKey;
    }
  });

  it('throws in production when CORS_ORIGIN is unset', () => {
    process.env.NODE_ENV = 'production';
    delete process.env.CORS_ORIGIN;
    expect(() => createApp()).toThrow(/CORS_ORIGIN/);
  });

  it('throws in production when CORS_ORIGIN is a wildcard', () => {
    process.env.NODE_ENV = 'production';
    process.env.CORS_ORIGIN = '*';
    expect(() => createApp()).toThrow(/CORS_ORIGIN/);
  });

  it('accepts an explicit allowlist in production', async () => {
    process.env.NODE_ENV = 'production';
    process.env.CORS_ORIGIN = 'https://cbt.example.com';
    const app = createApp();
    const res = await request(app).get('/health').set('Origin', 'https://cbt.example.com');
    expect(res.status).toBe(200);
    expect(res.headers['access-control-allow-origin']).toBe('https://cbt.example.com');
  });

  it('allows all origins outside production when unset', async () => {
    process.env.NODE_ENV = 'test';
    delete process.env.CORS_ORIGIN;
    const app = createApp();
    const res = await request(app).get('/health').set('Origin', 'http://localhost:5173');
    expect(res.status).toBe(200);
    expect(res.headers['access-control-allow-origin']).toBe('*');
  });
});
