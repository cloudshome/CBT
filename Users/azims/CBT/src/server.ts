import express, { Express, Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import candlesRouter from './routes/candles';
import mtfRouter from './routes/mtf';
import scanRouter from './routes/scan';
import paperRouter from './routes/paper';
import deskRouter from './routes/desk';
import skyRouter from './routes/sky';
import { institutionalRouter } from './routes/institutional';

dotenv.config();

export function createApp(): Express {
  const app = express();

  app.use(cors());
  app.use(express.json());

  // Default root status endpoint
  app.get('/', (_req: Request, res: Response) => {
    res.json({
      name: 'Crypto Brain Terminal (CTB) API',
      status: 'online',
      version: '0.1.0',
    });
  });

  // Health check endpoint
  app.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', service: 'CTB-Backend' });
  });

  // Readiness check endpoint
  app.get('/api/readiness', (_req: Request, res: Response) => {
    res.json({
      status: 'ok',
      ready: true,
      timestamp: new Date().toISOString(),
    });
  });

  // API Endpoints
  app.use('/api/candles', candlesRouter);
  app.use('/api/mtf', mtfRouter);
  app.use('/api/scan', scanRouter);
  app.use('/api/paper', paperRouter);
  app.use('/api/desk', deskRouter);
  app.use('/api/sky', skyRouter);
  app.use('/api/institutional', institutionalRouter);

  // 404 handler
  app.use((_req: Request, res: Response) => {
    res.status(404).json({ error: 'Endpoint not found' });
  });

  return app;
}

export const app = createApp();

const PORT = process.env.PORT || 3000;

if (process.env.NODE_ENV !== 'test') {
  app.listen(PORT, () => {
    console.log(`Crypto Brain Terminal backend running on port ${PORT}`);
  });
}
