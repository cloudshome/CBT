import express, { Express, Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import candlesRouter from './routes/candles';
import mtfRouter from './routes/mtf';

dotenv.config();

export function createApp(): Express {
  const app = express();

  app.use(cors());
  app.use(express.json());

  // Health check endpoint
  app.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', service: 'CTB-Backend' });
  });

  // API Endpoints
  app.use('/api/candles', candlesRouter);
  app.use('/api/mtf', mtfRouter);

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
