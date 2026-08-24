import { Router, Request, Response } from 'express';
import { validateCandlesQuery, ValidationError } from '../utils/validation';
import { fetchBinanceCandles } from '../services/binanceService';
import { saveCandles, getCachedCandles } from '../services/candlesCacheService';
import { CandlesResponse } from '../types/candles';

const router = Router();

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
    // 1. Attempt fresh fetch from Binance public REST API
    const candles = await fetchBinanceCandles(symbol, timeframe, limit);

    // 2. Asynchronously save / update SQLite cache
    saveCandles(symbol, timeframe, candles).catch((cacheErr) => {
      console.error('Failed to write candles to SQLite cache:', cacheErr);
    });

    const response: CandlesResponse = {
      symbol,
      timeframe,
      candles,
    };

    res.json(response);
  } catch (binanceErr: unknown) {
    const binanceErrMsg =
      binanceErr instanceof Error ? binanceErr.message : String(binanceErr);

    console.warn(
      `Binance REST fetch failed for ${symbol} (${timeframe}): ${binanceErrMsg}. Attempting cache fallback...`
    );

    try {
      // 3. Fallback to SQLite cached data
      const cachedCandles = await getCachedCandles(symbol, timeframe, limit);

      if (cachedCandles.length > 0) {
        res.setHeader('X-Cache', 'HIT-FALLBACK');
        const response: CandlesResponse = {
          symbol,
          timeframe,
          candles: cachedCandles,
        };
        res.json(response);
        return;
      }

      res.status(502).json({
        error: 'Failed to fetch market data from Binance and no cached data available',
        details: binanceErrMsg,
      });
    } catch (dbErr: unknown) {
      const dbErrMsg = dbErr instanceof Error ? dbErr.message : String(dbErr);
      console.error('Database error during cache fallback:', dbErr);
      res.status(500).json({
        error: 'Internal server error while accessing cache',
        details: dbErrMsg,
      });
    }
  }
});

export default router;
