import express, { Express, Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import candlesRouter from './routes/candles';
import mtfRouter from './routes/mtf';
import scanRouter from './routes/scan';
import paperRouter from './routes/paper';
import deskRouter from './routes/desk';
import skyRouter from './routes/sky';
import tickersRouter from './routes/tickers';
import { institutionalRouter } from './routes/institutional';
import { metricsRouter } from './routes/metrics';
import { apiKeyAuth } from './middleware/apiKeyAuth';

dotenv.config();

export function createApp(): Express {
  const app = express();

  // --- CORS Configuration (fail-closed in production) ---
  // Production MUST set CORS_ORIGIN to an explicit allowlist; a wildcard
  // fallback in production is a security misconfiguration, so we refuse to
  // start rather than silently allowing every origin.
  // In development/test (or when unset outside production) allow all origins.
  const corsOrigin = process.env.CORS_ORIGIN;
  const allowWildcard = corsOrigin === '*';
  if (process.env.NODE_ENV === 'production' && (!corsOrigin || allowWildcard)) {
    throw new Error(
      'Security misconfiguration: CORS_ORIGIN must be set to an explicit ' +
      'comma-separated origin allowlist (not "*") when NODE_ENV=production.'
    );
  }
  app.use(cors({
    origin: corsOrigin && !allowWildcard ? corsOrigin.split(',').map(o => o.trim()) : '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key'],
    credentials: !!corsOrigin && !allowWildcard,
  }));
  app.use(express.json());

  // Metrics endpoints (Prometheus /metrics and /api/metrics/json)
  app.use(metricsRouter);

  // Default root status endpoint (public)
  app.get('/', (_req: Request, res: Response) => {
    res.json({
      name: 'Crypto Brain Terminal (CTB) API',
      status: 'online',
      version: '3.0.0',
    });
  });

  // Health check endpoint (public)
  app.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', service: 'CTB-Backend' });
  });

  app.get('/api/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', service: 'CTB-Backend' });
  });

  // Readiness check endpoint (public)
  app.get('/api/readiness', (_req: Request, res: Response) => {
    res.json({
      status: 'ok',
      ready: true,
      timestamp: new Date().toISOString(),
    });
  });

  // NOTE: The React terminal is served by nginx, which routes the full
  // intelligence surface (/api/candles .. /api/auditor) to the FastAPI
  // Python backend. These Express routers are the LEGACY / direct-access
  // implementation (dev convenience + API compatibility) — FastAPI is the
  // authoritative implementation. Keep behavior in sync or migrate callers.
  // --- Public Read-Only Routes (no auth required) ---
  app.use('/api/candles', candlesRouter);
  app.use('/api/mtf', mtfRouter);
  app.use('/api/scan', scanRouter);
  app.use('/api/sky', skyRouter);
  app.use('/api/tickers', tickersRouter);

  // --- Sensitive Routes (auth required when API_KEY is set) ---
  app.use('/api/paper', apiKeyAuth, paperRouter);
  app.use('/api/desk', apiKeyAuth, deskRouter);
  app.use('/api/institutional', apiKeyAuth, institutionalRouter);

  // 404 handler
  app.use((_req: Request, res: Response) => {
    res.status(404).json({ error: 'Endpoint not found' });
  });

  return app;
}


export const app = createApp();

const PORT = process.env.NODE_PORT || 3000;

if (process.env.NODE_ENV !== 'test') {
  app.listen(PORT, () => {
    console.log(`Crypto Brain Terminal backend running on port ${PORT}`);
  });
}
