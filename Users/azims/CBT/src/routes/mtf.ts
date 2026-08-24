import { Router, Request, Response } from 'express';
import { validateCandlesQuery, ValidationError } from '../utils/validation';
import { fetchCandlesWithFallback, MarketDataFetchError } from '../services/marketDataService';
import { calculateEMA, calculateRSI, IndicatorPoint } from '../utils/indicators';
import { defaultRateLimiter } from '../middleware/rateLimit';

const router = Router();

// Apply rate limiting (60 req/min per IP)
router.use(defaultRateLimiter);

const ALLOWED_INDICATORS = ['ema', 'rsi'] as const;
type SupportedIndicator = (typeof ALLOWED_INDICATORS)[number];

export interface MTFResponse {
  symbol: string;
  timeframe: string;
  indicators: {
    ema?: IndicatorPoint[];
    rsi?: IndicatorPoint[];
  };
}

/**
 * GET /api/mtf?symbol=BTCUSDT&timeframe=15m&indicators=ema,rsi&limit=100
 */
router.get('/', async (req: Request, res: Response): Promise<void> => {
  // 1. Validate standard candles query parameters
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

  // 2. Validate indicators parameter
  const rawIndicators = req.query.indicators;
  if (!rawIndicators || typeof rawIndicators !== 'string' || rawIndicators.trim() === '') {
    res.status(400).json({
      error: 'Query parameter "indicators" is required (e.g. indicators=ema,rsi).',
    });
    return;
  }

  const requestedIndicators = rawIndicators
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  if (requestedIndicators.length === 0) {
    res.status(400).json({
      error: 'At least one indicator must be specified (e.g. indicators=ema,rsi).',
    });
    return;
  }

  for (const ind of requestedIndicators) {
    if (!ALLOWED_INDICATORS.includes(ind as SupportedIndicator)) {
      res.status(400).json({
        error: `Unsupported indicator "${ind}". Supported indicators: ${ALLOWED_INDICATORS.join(', ')}.`,
      });
      return;
    }
  }

  // Optional custom period parameters
  const emaPeriod = req.query.emaPeriod ? Number(req.query.emaPeriod) : 14;
  const rsiPeriod = req.query.rsiPeriod ? Number(req.query.rsiPeriod) : 14;

  if (isNaN(emaPeriod) || emaPeriod <= 0 || !Number.isInteger(emaPeriod)) {
    res.status(400).json({ error: 'Parameter "emaPeriod" must be a positive integer.' });
    return;
  }

  if (isNaN(rsiPeriod) || rsiPeriod <= 0 || !Number.isInteger(rsiPeriod)) {
    res.status(400).json({ error: 'Parameter "rsiPeriod" must be a positive integer.' });
    return;
  }

  const { symbol, timeframe, limit } = validatedQuery;

  try {
    // 3. Fetch candles via unified market data pipeline
    const result = await fetchCandlesWithFallback(symbol, timeframe, limit);

    res.setHeader('X-Data-Source', result.source);
    if (result.isFallback) {
      res.setHeader('X-Cache', result.source === 'BYBIT' ? 'BYBIT-FALLBACK' : 'HIT-FALLBACK');
    }

    // 4. Compute requested indicators
    const indicatorsData: MTFResponse['indicators'] = {};

    if (requestedIndicators.includes('ema')) {
      indicatorsData.ema = calculateEMA(result.candles, emaPeriod);
    }

    if (requestedIndicators.includes('rsi')) {
      indicatorsData.rsi = calculateRSI(result.candles, rsiPeriod);
    }

    const response: MTFResponse = {
      symbol,
      timeframe,
      indicators: indicatorsData,
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
      error: 'Internal server error computing technical indicators',
      details: msg,
    });
  }
});

export default router;
