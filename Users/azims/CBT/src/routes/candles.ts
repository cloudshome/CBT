import { Router, Request, Response } from 'express';
import { validateCandlesQuery, ValidationError } from '../utils/validation';
import { fetchBinanceCandles } from '../services/binanceService';
import { fetchBybitCandles } from '../services/bybitService';
import { saveCandles, getCachedCandles } from '../services/candlesCacheService';
import { defaultRateLimiter } from '../middleware/rateLimit';
import { CandlesResponse, OHLCVCandle } from '../types/candles';

const router = Router();

// Apply rate limiting (60 req/min per IP)
router.use(defaultRateLimiter);

/**
 * GET /api/candles?symbol=BTCUSDT&timeframe=15m&limit=100
 *
 * Fallback Hierarchy:
 * 1. Binance Public REST API
 * 2. Bybit V5 Public REST API
 * 3. SQLite Cache (`candles_cache`)
 * 4. 502 Bad Gateway
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
  const errorLogs: string[] = [];

  // Tier 1: Try Binance REST
  try {
    const candles: OHLCVCandle[] = await fetchBinanceCandles(symbol, timeframe, limit);

    saveCandles(symbol, timeframe, candles).catch((cacheErr) => {
      console.error('Failed to write Binance candles to SQLite cache:', cacheErr);
    });

    res.setHeader('X-Data-Source', 'BINANCE');
    const response: CandlesResponse = {
      symbol,
      timeframe,
      candles,
    };
    res.json(response);
    return;
  } catch (binanceErr: unknown) {
    const msg = binanceErr instanceof Error ? binanceErr.message : String(binanceErr);
    errorLogs.push(`Binance: ${msg}`);
    console.warn(`Binance fetch failed for ${symbol} (${timeframe}): ${msg}. Falling back to Bybit...`);
  }

  // Tier 2: Try Bybit V5 REST
  try {
    const candles: OHLCVCandle[] = await fetchBybitCandles(symbol, timeframe, limit);

    saveCandles(symbol, timeframe, candles).catch((cacheErr) => {
      console.error('Failed to write Bybit candles to SQLite cache:', cacheErr);
    });

    res.setHeader('X-Data-Source', 'BYBIT');
    res.setHeader('X-Cache', 'BYBIT-FALLBACK');
    const response: CandlesResponse = {
      symbol,
      timeframe,
      candles,
    };
    res.json(response);
    return;
  } catch (bybitErr: unknown) {
    const msg = bybitErr instanceof Error ? bybitErr.message : String(bybitErr);
    errorLogs.push(`Bybit: ${msg}`);
    console.warn(`Bybit fetch failed for ${symbol} (${timeframe}): ${msg}. Falling back to SQLite cache...`);
  }

  // Tier 3: Try SQLite Cache
  try {
    const cachedCandles = await getCachedCandles(symbol, timeframe, limit);

    if (cachedCandles.length > 0) {
      res.setHeader('X-Data-Source', 'SQLITE_CACHE');
      res.setHeader('X-Cache', 'HIT-FALLBACK');
      const response: CandlesResponse = {
        symbol,
        timeframe,
        candles: cachedCandles,
      };
      res.json(response);
      return;
    }

    // Tier 4: All sources failed and no cache available
    res.status(502).json({
      error: 'Failed to fetch market data from all sources (Binance, Bybit) and no cached data available',
      details: errorLogs,
    });
  } catch (dbErr: unknown) {
    const msg = dbErr instanceof Error ? dbErr.message : String(dbErr);
    console.error('Database error during cache fallback:', dbErr);
    res.status(500).json({
      error: 'Internal server error while accessing cache',
      details: msg,
    });
  }
});

export default router;
