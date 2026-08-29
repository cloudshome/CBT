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

  /**
   * 8-Pillar Universal Asset Intelligence Dossier
   * GET /api/institutional/dossier
   */
  async getAssetDossier(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<import('../types').UniversalAssetDossier> {
    const res = await fetch(
      `${BASE_URL}/api/institutional/dossier?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`
    );
    return handleResponse<import('../types').UniversalAssetDossier>(res);
  },

  // ============================================================================
  // PYTHON FASTAPI — SKY INTELLIGENCE PIPELINE ENDPOINTS
  // Routed via Vite proxy → localhost:8000 (dev)
  //          via nginx  → python-backend:8000 (production)
  // ============================================================================

  /**
   * GET /api/sky/decision
   * Full 12-stage SKY Market Intelligence decision pipeline output.
   */
  async getSKYDecision(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<import('../types').SKYIntelligenceResponse> {
    const res = await fetch(
      `${BASE_URL}/api/sky/decision?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`
    );
    return handleResponse<import('../types').SKYIntelligenceResponse>(res);
  },

  /**
   * GET /api/sky/statistics
   * Empirical expectancy metrics from live sandbox_lab backtest.
   */
  async getSKYStatistics(
    concept = 'SETUP_A_SWEEP_MSS',
    regime = 'TRENDING_BULL',
    symbol = 'BTC/USDT',
    timeframe: SupportedTimeframe = '15m'
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/sky/statistics?concept=${encodeURIComponent(concept)}&regime=${encodeURIComponent(regime)}&symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/decision/council
   * Adversarial debate committee decision with EV and uncertainty budget.
   */
  async getDecisionCouncil(
    symbol: string
  ): Promise<import('../types').CouncilDecision> {
    const res = await fetch(
      `${BASE_URL}/api/decision/council?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<import('../types').CouncilDecision>(res);
  },

  /**
   * GET /api/decision/allocation
   * Conservative Kelly position sizing with uncertainty discounting.
   */
  async getAllocationSizing(
    symbol: string,
    equity = 100000
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/decision/allocation?symbol=${encodeURIComponent(symbol)}&equity=${equity}`
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/prediction/ladder
   * Multi-horizon probability ladder for price targets.
   */
  async getPredictionLadder(
    symbol: string
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/prediction/ladder?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/prediction/ledger
   * Verified prediction ledger with resolution history.
   */
  async getPredictionLedger(
    limit = 50
  ): Promise<{ count: number; records: unknown[] }> {
    const res = await fetch(
      `${BASE_URL}/api/prediction/ledger?limit=${limit}`
    );
    return handleResponse<{ count: number; records: unknown[] }>(res);
  },

  /**
   * GET /api/scenarios
   * Analogue-based multi-scenario distribution.
   */
  async getScenarios(
    symbol: string
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/scenarios?symbol=${encodeURIComponent(symbol)}`
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/path-simulation
   * Monte Carlo path cone (GBM) to TP/SL levels.
   */
  async getPathSimulation(
    symbol: string,
    tp?: number,
    sl?: number
  ): Promise<Record<string, unknown>> {
    let url = `${BASE_URL}/api/path-simulation?symbol=${encodeURIComponent(symbol)}`;
    if (tp !== undefined) url += `&tp=${tp}`;
    if (sl !== undefined) url += `&sl=${sl}`;
    const res = await fetch(url);
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/shadow/positions
   * Shadow paper positions with live P&L (Python portfolio_shadow).
   */
  async getShadowPositions(): Promise<{ open_positions: unknown[]; history: unknown[] }> {
    const res = await fetch(`${BASE_URL}/api/shadow/positions`);
    return handleResponse<{ open_positions: unknown[]; history: unknown[] }>(res);
  },

  /**
   * POST /api/shadow/trade
   * Open a shadow paper trade (Python portfolio_shadow).
   */
  async openShadowTrade(order: {
    symbol: string;
    direction: 'LONG' | 'SHORT';
    size: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
  }): Promise<{ status: string; position_id: string }> {
    const res = await fetch(`${BASE_URL}/api/shadow/trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(order),
    });
    return handleResponse<{ status: string; position_id: string }>(res);
  },

  /**
   * POST /api/lab/backtest
   * In-sample backtest via sandbox_lab.
   */
  async runBacktest(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/lab/backtest?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
      { method: 'POST' }
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * POST /api/lab/walk-forward
   * Purged walk-forward validation.
   */
  async runWalkForward(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/lab/walk-forward?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
      { method: 'POST' }
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * POST /api/lab/stress-test
   * Monte Carlo 10k path stress test on backtest return series.
   */
  async runStressTest(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<Record<string, unknown>> {
    const res = await fetch(
      `${BASE_URL}/api/lab/stress-test?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
      { method: 'POST' }
    );
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/league/leaderboard
   * Strategy league rankings.
   */
  async getStrategyLeaderboard(): Promise<{ leaderboard: unknown[] }> {
    const res = await fetch(`${BASE_URL}/api/league/leaderboard`);
    return handleResponse<{ leaderboard: unknown[] }>(res);
  },

  /**
   * GET /api/governance/proposals
   * Pending parameter governance proposals.
   */
  async getGovernanceProposals(): Promise<{ proposals: unknown[] }> {
    const res = await fetch(`${BASE_URL}/api/governance/proposals`);
    return handleResponse<{ proposals: unknown[] }>(res);
  },
};


