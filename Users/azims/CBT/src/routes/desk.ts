import { Router, Request, Response } from 'express';
import { validateCandlesQuery, ValidationError } from '../utils/validation';
import { fetchCandlesWithFallback, MarketDataFetchError } from '../services/marketDataService';
import { calculateEMA, calculateRSI } from '../utils/indicators';
import { parseAndNormalizeCandles, runQuantDetection, generateSetups } from '../utils/quantEngine';
import {
  generateMarketBrief,
  askDesk,
  GeminiServiceError,
} from '../services/geminiService';
import { defaultRateLimiter } from '../middleware/rateLimit';

const router = Router();

// Apply rate limiting
router.use(defaultRateLimiter);

/**
 * POST /api/desk/ai-brief
 *
 * Generates an executive AI intelligence brief by aggregating:
 * - Live market candles
 * - Multi-timeframe indicators (EMA, RSI)
 * - Smart Money Concepts (FVGs, Order Blocks, BOS, Setups)
 * - Gemini Desk analysis
 */
router.post('/ai-brief', async (req: Request, res: Response): Promise<void> => {
  const { symbol, timeframe = '15m' } = req.body || {};

  let validatedQuery;
  try {
    validatedQuery = validateCandlesQuery({ symbol, timeframe, limit: 100 });
  } catch (err: unknown) {
    if (err instanceof ValidationError) {
      res.status(err.statusCode).json({ error: err.message });
      return;
    }
    res.status(400).json({ error: 'Invalid request parameters' });
    return;
  }

  const { symbol: cleanSymbol, timeframe: cleanTimeframe, limit } = validatedQuery;

  try {
    // 1. Fetch candles via multi-source fallback
    const marketData = await fetchCandlesWithFallback(cleanSymbol, cleanTimeframe, limit);

    // 2. Compute technical indicators
    const ema = calculateEMA(marketData.candles, 14);
    const rsi = calculateRSI(marketData.candles, 14);

    // 3. Run SMC quantitative scan
    const normalizedCandles = parseAndNormalizeCandles(marketData.candles);
    const smc = runQuantDetection(normalizedCandles);
    const setups = generateSetups(smc);

    // 4. Generate Gemini intelligence brief
    const brief = await generateMarketBrief({
      symbol: cleanSymbol,
      timeframe: cleanTimeframe,
      lastPrice: smc.stats.lastPrice,
      highPrice: smc.stats.highPrice,
      lowPrice: smc.stats.lowPrice,
      trend: smc.stats.trend,
      ema,
      rsi,
      smc,
      setups,
    });

    res.json(brief);
  } catch (err: unknown) {
    if (err instanceof GeminiServiceError) {
      res.status(err.statusCode).json({
        error: err.message,
      });
      return;
    }

    if (err instanceof MarketDataFetchError) {
      res.status(err.statusCode).json({
        error: err.message,
        details: err.details,
      });
      return;
    }

    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({
      error: 'Failed to generate AI brief',
      details: msg,
    });
  }
});

/**
 * POST /api/desk/ask
 *
 * Grounded Q&A endpoint for quantitative desk queries.
 */
router.post('/ask', async (req: Request, res: Response): Promise<void> => {
  const { query, context } = req.body || {};

  if (!query || typeof query !== 'string' || query.trim() === '') {
    res.status(400).json({ error: 'Field "query" is required and must be a non-empty string.' });
    return;
  }

  try {
    const answer = await askDesk(query.trim(), context);
    res.json({
      query: query.trim(),
      answer,
      timestamp: Date.now(),
    });
  } catch (err: unknown) {
    if (err instanceof GeminiServiceError) {
      res.status(err.statusCode).json({
        error: err.message,
      });
      return;
    }

    const msg = err instanceof Error ? err.message : String(err);
    res.status(500).json({
      error: 'Failed to answer desk query',
      details: msg,
    });
  }
});

export default router;
