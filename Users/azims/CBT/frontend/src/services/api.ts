import {
  CandlesApiResponse,
  MTFApiResponse,
  ScanApiResponse,
  PaperPositionsResponse,
  PaperTrade,
  RiskConfig,
  DeskBriefResponse,
  DeskAskResponse,
  SupportedTimeframe,
  SKYIntelligenceResponse,
  VWAPData,
} from '../types';

const BASE_URL = '';

export class ApiError extends Error {
  public statusCode: number;
  public details?: unknown;

  constructor(message: string, statusCode: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.details = details;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  const isJson = res.headers.get('content-type')?.includes('application/json');
  const data = isJson ? await res.json() : null;

  if (!res.ok) {
    const errorMsg = data?.error || res.statusText || 'API request failed';
    throw new ApiError(errorMsg, res.status, data);
  }

  return data as T;
}

export const api = {
  /**
   * GET /api/candles
   */
  async getCandles(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<CandlesApiResponse> {
    const res = await fetch(
      `${BASE_URL}/api/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<CandlesApiResponse>(res);
  },

  /**
   * GET /api/mtf
   */
  async getMTF(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    indicators = 'ema,rsi'
  ): Promise<MTFApiResponse> {
    const res = await fetch(
      `${BASE_URL}/api/mtf?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&indicators=${indicators}`
    );
    return handleResponse<MTFApiResponse>(res);
  },

  /**
   * GET /api/scan
   */
  async getSMCScan(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<ScanApiResponse> {
    const res = await fetch(
      `${BASE_URL}/api/scan?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<ScanApiResponse>(res);
  },

  /**
   * POST /api/paper/trade
   */
  async placePaperTrade(trade: {
    symbol: string;
    side: 'BUY' | 'SELL';
    entryPrice: number;
    sl: number;
    tp: number;
    size?: number;
  }): Promise<{ message: string; trade: PaperTrade }> {
    const res = await fetch(`${BASE_URL}/api/paper/trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trade),
    });
    return handleResponse<{ message: string; trade: PaperTrade }>(res);
  },

  /**
   * GET /api/paper/positions
   */
  async getPositions(): Promise<PaperPositionsResponse> {
    const res = await fetch(`${BASE_URL}/api/paper/positions`);
    return handleResponse<PaperPositionsResponse>(res);
  },

  /**
   * GET /api/paper/config
   */
  async getRiskConfig(): Promise<{ config: RiskConfig }> {
    const res = await fetch(`${BASE_URL}/api/paper/config`);
    return handleResponse<{ config: RiskConfig }>(res);
  },

  /**
   * POST /api/desk/ai-brief
   */
  async getDeskBrief(symbol: string, timeframe: SupportedTimeframe = '15m'): Promise<DeskBriefResponse> {
    const res = await fetch(`${BASE_URL}/api/desk/ai-brief`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, timeframe }),
    });
    return handleResponse<DeskBriefResponse>(res);
  },

  /**
   * POST /api/desk/ask
   */
  async askDesk(query: string, context?: Record<string, unknown>): Promise<DeskAskResponse> {
    const res = await fetch(`${BASE_URL}/api/desk/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, context }),
    });
    return handleResponse<DeskAskResponse>(res);
  },

  /**
   * GET /api/sky/intelligence
   */
  async getSKYIntelligence(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<SKYIntelligenceResponse> {
    const res = await fetch(
      `${BASE_URL}/api/sky/intelligence?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<SKYIntelligenceResponse>(res);
  },

  /**
   * GET /api/sky/vwap
   */
  async getSKYVWAP(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<{ symbol: string; timeframe: string; vwap: VWAPData }> {
    const res = await fetch(
      `${BASE_URL}/api/sky/vwap?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`
    );
    return handleResponse<{ symbol: string; timeframe: string; vwap: VWAPData }>(res);
  },

  /**
   * GET /api/institutional/alpha
   */
  async getInstitutionalAlpha(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<import('../types').InstitutionalAlphaResponse> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/alpha?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<import('../types').InstitutionalAlphaResponse>(res);
  },

  /**
   * GET /api/institutional/cvd
   */
  async getInstitutionalCVD(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<import('../types').CVDSeriesData> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/cvd?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<import('../types').CVDSeriesData>(res);
  },

  /**
   * GET /api/institutional/orderbook-imbalance
   */
  async getOrderBookImbalance(
    symbol: string
  ): Promise<import('../types').OBIData> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/orderbook-imbalance?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<import('../types').OBIData>(res);
  },

  /**
   * 1. GET /api/institutional/debate
   */
  async getDebateCouncil(
    symbol: string,
    timeframe: SupportedTimeframe = '15m',
    limit = 100
  ): Promise<import('../types').CouncilDecision> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/debate?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<import('../types').CouncilDecision>(res);
  },

  /**
   * 2. GET /api/institutional/whale-radar
   */
  async getWhaleRadar(
    symbol: string
  ): Promise<import('../types').WhaleRadarData> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/whale-radar?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<import('../types').WhaleRadarData>(res);
  },

  /**
   * 3. GET /api/institutional/psychology
   */
  async getPsychologyStatus(): Promise<import('../types').TiltStatus> {
    const res = await fetch(`${BASE_URL}/api/institutional/psychology`);
    return handleResponse<import('../types').TiltStatus>(res);
  },

  /**
   * 4. POST /api/institutional/monte-carlo
   */
  async runMonteCarloStressTest(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<import('../types').MonteCarloStressReport> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/monte-carlo?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
      { method: 'POST' }
    );
    return handleResponse<import('../types').MonteCarloStressReport>(res);
  },

  /**
   * 5. GET /api/institutional/lead-lag
   */
  async getCrossAssetLeadLag(
    symbol: string
  ): Promise<{ signals: import('../types').LeadSignal[]; dxy_price: number; us10y_yield: number; has_macro_shock: boolean }> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/lead-lag?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<{ signals: import('../types').LeadSignal[]; dxy_price: number; us10y_yield: number; has_macro_shock: boolean }>(res);
  },

  /**
   * 6. GET /api/institutional/dynamic-hedge
   */
  async getDynamicHedge(
    symbol: string
  ): Promise<import('../types').HedgeRecommendation> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/dynamic-hedge?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<import('../types').HedgeRecommendation>(res);
  },

  /**
   * GET /api/tickers
   * Fetches live 24hr market ticker prices for BTC, ETH, and GOLD (PAXG / XAU)
   */
  async getLiveTickers(
    symbols: string[] = ['BTCUSDT', 'ETHUSDT', 'PAXGUSDT', 'XAUUSDT']
  ): Promise<{
    tickers: Array<{
      symbol: string;
      name: string;
      price: number;
      change24h: number;
      high24h: number;
      low24h: number;
      volume24h: string;
      quoteVolume: number;
      timestamp: number;
      isGold?: boolean;
    }>;
    source: string;
    timestamp: string;
  }> {
    const res = await fetch(`${BASE_URL}/api/tickers?symbols=${symbols.join(',')}`);
    return handleResponse(res);
  },
};


