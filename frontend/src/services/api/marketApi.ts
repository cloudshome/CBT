/**
 * frontend/src/services/api/marketApi.ts
 * =====================================
 * Market Data & Technical Structure API Client:
 * Handles Candles, MTF indicators, SMC scans, and Tickers.
 */

import { authFetch, BASE_URL } from './client';
import { handleResponse, normalizeCandle } from './utils';
import {
  OHLCVCandle,
  CandlesApiResponse,
  MTFApiResponse,
  ScanApiResponse,
  SupportedTimeframe,
} from '../../types';

export const marketApi = {
  /**
   * GET /api/candles - Fetch OHLCV candles
   */
  async getCandles(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<CandlesApiResponse> {
    const res = await authFetch(
      `${BASE_URL}/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    const data = await handleResponse<Record<string, unknown>>(res);
    const rawCandles = Array.isArray(data?.candles) ? data.candles : [];
    const normalizedCandles: OHLCVCandle[] = rawCandles.map(normalizeCandle);
    return {
      symbol: (data?.symbol as string) || symbol,
      timeframe: (data?.timeframe as SupportedTimeframe) || timeframe,
      limit: (data?.limit as number) || limit,
      candles: normalizedCandles,
    };
  },

  /**
   * GET /api/mtf - Multi-Timeframe indicator confluence
   */
  async getMTF(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    indicators = 'ema,rsi'
  ): Promise<MTFApiResponse> {
    const res = await authFetch(
      `${BASE_URL}/api/mtf?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&indicators=${indicators}`
    );
    const data = await handleResponse<any>(res);
    return {
      symbol: data?.symbol || symbol,
      timeframe: (data?.timeframe || timeframe) as SupportedTimeframe,
      indicators: {
        ema: data?.indicators?.ema || (Array.isArray(data?.ema) ? data.ema : []),
        rsi: data?.indicators?.rsi || (Array.isArray(data?.rsi) ? data.rsi : []),
      },
    };
  },

  /**
   * GET /api/scan - Smart Money Concepts (FVG, Order Blocks) structure scan
   */
  async getSMCScan(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<ScanApiResponse> {
    const res = await authFetch(
      `${BASE_URL}/api/scan?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    const data = await handleResponse<any>(res);
    return {
      symbol: data?.symbol || symbol,
      timeframe: (data?.timeframe || timeframe) as SupportedTimeframe,
      fvg: data?.fvg || data?.fvgs || [],
      order_blocks: data?.order_blocks || data?.orderBlocks || [],
      setup_suggestions: data?.setup_suggestions || data?.setups || [],
      stats: data?.stats || {
        totalCandles: 100,
        bullishFVGs: 0,
        bearishFVGs: 0,
        unmitigatedFVGs: 0,
        mitigatedFVGs: 0,
        bullishOBs: 0,
        bearishOBs: 0,
        lastPrice: data?.lastPrice || 0,
        highPrice: data?.highPrice || 0,
        lowPrice: data?.lowPrice || 0,
        trend: data?.trend || 'CONSOLIDATION',
      },
    };
  },

  /**
   * GET /api/tickers - Active market tickers
   */
  async getTickers(): Promise<string[]> {
    const res = await authFetch(`${BASE_URL}/api/tickers`);
    const data = await handleResponse<{ tickers: string[] }>(res);
    return data?.tickers || [];
  },
};
