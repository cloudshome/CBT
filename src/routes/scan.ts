import { Router, Request, Response } from 'express';
import { validateCandlesQuery, ValidationError } from '../utils/validation';
import { fetchCandlesWithFallback, MarketDataFetchError } from '../services/marketDataService';
import { parseAndNormalizeCandles, runQuantDetection, generateSetups } from '../utils/quantEngine';
import { defaultRateLimiter } from '../middleware/rateLimit';
import { ScanResponse } from '../types';

const router = Router();

// Apply rate limiting (60 req/min per IP)
router.use(defaultRateLimiter);

/**
 * GET /api/scan?symbol=BTCUSDT&timeframe=15m&limit=100
 *
 * Runs candle data through the quantitative SMC engine to detect:
 * - Fair Value Gaps (FVG)
 * - Order Blocks (OB)
 * - Swings and Break of Structure (BOS)
 * - Actionable trade setup suggestions (entry, stop loss, take profit)
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
    // 1. Fetch candles via unified market data pipeline
    const marketData = await fetchCandlesWithFallback(symbol, timeframe, limit);

    res.setHeader('X-Data-Source', marketData.source);
    if (marketData.isFallback) {
      res.setHeader('X-Cache', marketData.source === 'BYBIT' ? 'BYBIT-FALLBACK' : 'HIT-FALLBACK');
    }

    // 2. Parse & normalize candles for quantEngine
    const normalizedCandles = parseAndNormalizeCandles(marketData.candles);

    // 3. Execute SMC detection algorithm
    const detectionResult = runQuantDetection(normalizedCandles);

    // 4. Generate trade setup suggestions
    const setups = generateSetups(detectionResult);

    const response: ScanResponse = {
      symbol,
      timeframe,
      fvg: detectionResult.output.fvg,
      order_blocks: detectionResult.output.order_blocks,
      detailedFVGs: detectionResult.detailedFVGs,
      detailedOrderBlocks: detectionResult.detailedOrderBlocks,
      setup_suggestions: setups,
      stats: detectionResult.stats,
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
      error: 'Internal server error executing SMC scan',
      details: msg,
    });
  }
});

export default router;
