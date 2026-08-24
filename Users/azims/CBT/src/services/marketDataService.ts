import { fetchBinanceCandles } from './binanceService';
import { fetchBybitCandles } from './bybitService';
import { saveCandles, getCachedCandles } from './candlesCacheService';
import { OHLCVCandle, SupportedTimeframe } from '../types/candles';

export interface MarketDataResult {
  candles: OHLCVCandle[];
  source: 'BINANCE' | 'BYBIT' | 'SQLITE_CACHE';
  isFallback: boolean;
}

export class MarketDataFetchError extends Error {
  public details: string[];
  public statusCode: number;

  constructor(message: string, details: string[] = [], statusCode = 502) {
    super(message);
    this.name = 'MarketDataFetchError';
    this.details = details;
    this.statusCode = statusCode;
  }
}

/**
 * Fetches market candles using the unified fallback chain:
 * 1. Binance REST -> 2. Bybit REST -> 3. SQLite Cache
 */
export async function fetchCandlesWithFallback(
  symbol: string,
  timeframe: SupportedTimeframe,
  limit: number
): Promise<MarketDataResult> {
  const errorLogs: string[] = [];

  // Tier 1: Try Binance Public REST
  try {
    const candles = await fetchBinanceCandles(symbol, timeframe, limit);
    saveCandles(symbol, timeframe, candles).catch((err) => {
      console.error('Failed to cache Binance candles to SQLite:', err);
    });

    return {
      candles,
      source: 'BINANCE',
      isFallback: false,
    };
  } catch (binanceErr: unknown) {
    const msg = binanceErr instanceof Error ? binanceErr.message : String(binanceErr);
    errorLogs.push(`Binance: ${msg}`);
    console.warn(`Binance fetch failed for ${symbol} (${timeframe}): ${msg}. Falling back to Bybit...`);
  }

  // Tier 2: Try Bybit V5 Public REST
  try {
    const candles = await fetchBybitCandles(symbol, timeframe, limit);
    saveCandles(symbol, timeframe, candles).catch((err) => {
      console.error('Failed to cache Bybit candles to SQLite:', err);
    });

    return {
      candles,
      source: 'BYBIT',
      isFallback: true,
    };
  } catch (bybitErr: unknown) {
    const msg = bybitErr instanceof Error ? bybitErr.message : String(bybitErr);
    errorLogs.push(`Bybit: ${msg}`);
    console.warn(`Bybit fetch failed for ${symbol} (${timeframe}): ${msg}. Falling back to SQLite cache...`);
  }

  // Tier 3: Try Local SQLite Cache
  try {
    const cachedCandles = await getCachedCandles(symbol, timeframe, limit);
    if (cachedCandles.length > 0) {
      return {
        candles: cachedCandles,
        source: 'SQLITE_CACHE',
        isFallback: true,
      };
    }
  } catch (dbErr: unknown) {
    const msg = dbErr instanceof Error ? dbErr.message : String(dbErr);
    console.error('Database error reading cache fallback:', dbErr);
    errorLogs.push(`SQLite: ${msg}`);
  }

  // Tier 4: All sources failed
  throw new MarketDataFetchError(
    'Failed to fetch market data from all sources (Binance, Bybit) and no cached data available',
    errorLogs,
    502
  );
}
