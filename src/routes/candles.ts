import { Router, Request, Response } from 'express';
import { validateCandlesQuery, ValidationError } from '../utils/validation';
import { fetchCandlesWithFallback, MarketDataFetchError } from '../services/marketDataService';
import { defaultRateLimiter } from '../middleware/rateLimit';
import { CandlesResponse } from '../types/candles';

const router = Router();

// Apply rate limiting (60 req/min per IP)
router.use(defaultRateLimiter);

/**
 * GET /api/candles?symbol=BTCUSDT&timeframe=15m&limit=100
 */
router.get('/', async (req: Request, res: Response): Promise<void> => {
  let validatedQuery;
  try {
    validatedQuery = validateCandlesQuery(req.query);
  } catch (err: unknown) {
    if (err instanceof ValidationError) {
      res.status(err.statusCode).json({ error: err.message });
      return;
    }
    res.status(400).json({ error: 'Invalid request parameters' });
    return;
  }

  const { symbol, timeframe, limit } = validatedQuery;

  try {
    const result = await fetchCandlesWithFallback(symbol, timeframe, limit);

    res.setHeader('X-Data-Source', result.source);
    if (result.isFallback) {
      res.setHeader('X-Cache', result.source === 'BYBIT' ? 'BYBIT-FALLBACK' : 'HIT-FALLBACK');
    }

    const response: CandlesResponse = {
      symbol,
      timeframe,
      candles: result.candles,
    };
    res.json(response);
  } catch (err: unknown) {
    if (err instanceof MarketDataFetchError) {
      res.status(err.statusCode).json({
        error: err.message,
        details: err.details,
      });
      return;
    }

    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({
      error: 'Internal server error processing market data',
      details: msg,
    });
  }
});

export default router;
