import { SUPPORTED_TIMEFRAMES, SupportedTimeframe, ValidatedCandlesQuery } from '../types/candles';

export class ValidationError extends Error {
  public statusCode: number;

  constructor(message: string, statusCode = 400) {
    super(message);
    this.name = 'ValidationError';
    this.statusCode = statusCode;
  }
}

/**
 * Validates and normalizes candles query parameters
 */
export function validateCandlesQuery(query: {
  symbol?: unknown;
  timeframe?: unknown;
  limit?: unknown;
}): ValidatedCandlesQuery {
  const { symbol, timeframe, limit } = query;

  // 1. Symbol validation
  if (!symbol || typeof symbol !== 'string' || symbol.trim() === '') {
    throw new ValidationError('Query parameter "symbol" is required.');
  }

  const rawSymbol = symbol.trim();
  const symbolRegex = /^[A-Z0-9]+$/;

  if (!symbolRegex.test(rawSymbol)) {
    throw new ValidationError(
      'Invalid symbol format. Symbol must be uppercase alphanumeric (e.g. BTCUSDT, BTC).'
    );
  }

  // Normalize: if symbol doesn't end with USDT, append USDT
  const normalizedSymbol = rawSymbol.endsWith('USDT') ? rawSymbol : `${rawSymbol}USDT`;

  // 2. Timeframe validation
  const tf = (timeframe !== undefined ? String(timeframe).trim() : '15m') as SupportedTimeframe;
  if (!SUPPORTED_TIMEFRAMES.includes(tf)) {
    throw new ValidationError(
      `Invalid timeframe "${timeframe}". Supported timeframes: ${SUPPORTED_TIMEFRAMES.join(', ')}.`
    );
  }

  // 3. Limit validation
  let parsedLimit = 100;
  if (limit !== undefined && limit !== null && limit !== '') {
    const limitNum = Number(limit);
    if (!Number.isInteger(limitNum) || limitNum < 1 || limitNum > 1000) {
      throw new ValidationError(
        'Invalid limit. Limit must be an integer between 1 and 1000.'
      );
    }
    parsedLimit = limitNum;
  }

  return {
    symbol: normalizedSymbol,
    timeframe: tf,
    limit: parsedLimit,
  };
}
