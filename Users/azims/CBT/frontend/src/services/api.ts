import {
  OHLCVCandle,
  CandlesApiResponse,
  MTFApiResponse,
  ScanApiResponse,
  PaperPositionsResponse,
  PaperDeskOverviewResponse,
  PaperTrade,
  RiskConfig,
  DeskBriefResponse,
  DeskAskResponse,
  SupportedTimeframe,
  HalfKellySizingResponse,
  SKYIntelligenceResponse,
  VWAPData,
  ResearchIngestMode,
  ResearchIngestResult,
  ResearchVaultsResponse,
  ResearchProvenanceItem,
  DiscoveryGraphResponse,
  CrossDomainDiscoveryItem,
  HypothesisNodeItem,
  ResearchTelegramShareRequest,
  ResearchTelegramShareResponse,
} from '../types';

const BASE_URL = '';

let _apiKey: string =
  (typeof window !== 'undefined' ? localStorage.getItem('cbt_api_key') || '' : '') ||
  (((import.meta as unknown as { env?: Record<string, string> })?.env?.VITE_API_KEY) || '');

export function setApiKey(key: string): void {
  _apiKey = key;
  if (typeof window !== 'undefined') {
    if (key) {
      localStorage.setItem('cbt_api_key', key);
    } else {
      localStorage.removeItem('cbt_api_key');
    }
  }
}

export function getApiKey(): string {
  return _apiKey;
}

function authHeaders(extraHeaders?: HeadersInit): HeadersInit {
  const headers = new Headers(extraHeaders || {});
  if (_apiKey && !headers.has('X-API-Key') && !headers.has('Authorization')) {
    headers.set('X-API-Key', _apiKey);
  }
  return headers;
}

async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = authHeaders(init?.headers);
  return fetch(input, { ...init, headers });
}

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
    let errorMsg = res.statusText || 'API request failed';
    if (data) {
      if (typeof data.detail === 'string') {
        errorMsg = data.detail;
      } else if (Array.isArray(data.detail) && data.detail.length > 0) {
        errorMsg = data.detail
          .map((d: any) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d)))
          .join(', ');
      } else if (typeof data.error === 'string') {
        errorMsg = data.error;
      } else if (typeof data.message === 'string') {
        errorMsg = data.message;
      }
    }
    throw new ApiError(errorMsg, res.status, data);
  }

  return data as T;
}

export function normalizeCandle(c: unknown): OHLCVCandle {
  if (Array.isArray(c)) {
    return [
      Number(c[0]) || 0,
      Number(c[1]) || 0,
      Number(c[2]) || 0,
      Number(c[3]) || 0,
      Number(c[4]) || 0,
      Number(c[5]) || 0,
    ];
  }
  const obj = c as Record<string, unknown> | null | undefined;
  return [
    Number(obj?.timestamp ?? obj?.time ?? 0),
    Number(obj?.open ?? 0),
    Number(obj?.high ?? 0),
    Number(obj?.low ?? 0),
    Number(obj?.close ?? 0),
    Number(obj?.volume ?? 0),
  ];
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
   * GET /api/mtf
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
   * GET /api/scan
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
    const res = await authFetch(`${BASE_URL}/api/paper/trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trade),
    });
    return handleResponse<{ message: string; trade: PaperTrade }>(res);
  },

  /**
   * GET /api/paper/desk-overview
   * Complete institutional Paper Trading Desk Overview (Past, Current, Future Queue).
   */
  async getPaperDeskOverview(): Promise<PaperDeskOverviewResponse> {
    const res = await authFetch(`${BASE_URL}/api/paper/desk-overview`);
    return handleResponse<PaperDeskOverviewResponse>(res);
  },

  /**
   * GET /api/paper/positions
   */
  async getPositions(): Promise<PaperPositionsResponse> {
    const res = await authFetch(`${BASE_URL}/api/paper/positions`);
    return handleResponse<PaperPositionsResponse>(res);
  },

  /**
   * GET /api/paper/config
   */
  async getRiskConfig(): Promise<{ config: RiskConfig }> {
    const res = await authFetch(`${BASE_URL}/api/paper/config`);
    return handleResponse<{ config: RiskConfig }>(res);
  },

  /**
   * POST /api/paper/close
   */
  async closePaperPosition(positionId: string, exitPrice?: number): Promise<{ status: string; message: string }> {
    const res = await authFetch(`${BASE_URL}/api/paper/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positionId, exitPrice }),
    });
    return handleResponse<{ status: string; message: string }>(res);
  },

  /**
   * POST /api/risk/half-kelly-calc
   * Bayesian Half-Kelly capital sizing calculator with invalidation guard.
   */
  async calculateHalfKelly(params: {
    symbol: string;
    entryPrice: number;
    sl: number;
    tp: number;
    equity?: number;
    winProbability?: number;
  }): Promise<HalfKellySizingResponse> {
    const res = await authFetch(`${BASE_URL}/api/risk/half-kelly-calc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<HalfKellySizingResponse>(res);
  },

  /**
   * POST /api/desk/ai-brief
   */
  async getDeskBrief(symbol: string, timeframe: SupportedTimeframe = '15m'): Promise<DeskBriefResponse> {
    const res = await authFetch(`${BASE_URL}/api/desk/ai-brief`, {
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
    const res = await authFetch(`${BASE_URL}/api/desk/ask`, {
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
      `${BASE_URL}/api/institutional/debate?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`
    );
    return handleResponse<import('../types').CouncilDecision>(res);
  },

  /**
   * 2. GET /api/institutional/whale-radar
   */
  async getWhaleRadar(
    symbol: string,
    currentPrice?: number
  ): Promise<import('../types').WhaleRadarData> {
    const priceParam = currentPrice && currentPrice > 0 ? `&price=${encodeURIComponent(currentPrice)}` : '';
    const res = await authFetch(
      `${BASE_URL}/api/institutional/whale-radar?symbol=${encodeURIComponent(symbol)}${priceParam}`
    );
    return handleResponse<import('../types').WhaleRadarData>(res);
  },

  /**
   * 3. GET /api/institutional/psychology
   */
  async getPsychologyStatus(): Promise<import('../types').TiltStatus> {
    const res = await authFetch(`${BASE_URL}/api/institutional/psychology`);
    return handleResponse<import('../types').TiltStatus>(res);
  },

  /**
   * 4. POST /api/institutional/monte-carlo
   */
  async runMonteCarloStressTest(
    symbol: string,
    timeframe: SupportedTimeframe = '15m'
  ): Promise<import('../types').MonteCarloStressReport> {
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(`${BASE_URL}/api/tickers?symbols=${symbols.join(',')}`);
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(url);
    return handleResponse<Record<string, unknown>>(res);
  },

  /**
   * GET /api/shadow/positions
   * Shadow paper positions with live P&L (Python portfolio_shadow).
   */
  async getShadowPositions(): Promise<{ open_positions: unknown[]; history: unknown[] }> {
    const res = await authFetch(`${BASE_URL}/api/shadow/positions`);
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
    const res = await authFetch(`${BASE_URL}/api/shadow/trade`, {
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(
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
    const res = await authFetch(`${BASE_URL}/api/league/leaderboard`);
    return handleResponse<{ leaderboard: unknown[] }>(res);
  },

  /**
   * GET /api/governance/proposals
   * Pending parameter governance proposals.
   */
  async getGovernanceProposals(): Promise<{ proposals: unknown[] }> {
    const res = await authFetch(`${BASE_URL}/api/governance/proposals`);
    return handleResponse<{ proposals: unknown[] }>(res);
  },

  // ============================================================================
  // PHASE 16: VOICE & AUDIO TRANSLATION ENDPOINTS
  // ============================================================================

  /**
   * POST /api/voice/transcribe
   * Transcribes voice memo audio blob and automatically parses trade commands.
   */
  async transcribeVoiceAudio(
    audioBase64: string,
    filename = 'memo.webm'
  ): Promise<{
    transcript: string;
    is_trade_command: boolean;
    parsed_command: Record<string, unknown>;
  }> {
    const res = await authFetch(`${BASE_URL}/api/voice/transcribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio_base64: audioBase64, filename }),
    });
    return handleResponse(res);
  },

  /**
   * POST /api/voice/synthesize
   * Synthesizes text into spoken MP3 audio.
   */
  async synthesizeVoiceAudio(text: string, filename = 'desk_brief.mp3'): Promise<Blob> {
    const res = await authFetch(`${BASE_URL}/api/voice/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, filename }),
    });
    if (!res.ok) {
      throw new Error(`Voice synthesis failed: ${res.statusText}`);
    }
    return res.blob();
  },

  // ============================================================================
  // PHASE 17: TELEGRAM BOT INTEGRATION ENDPOINTS
  // ============================================================================

  /**
   * GET /api/telegram/status
   * Checks Telegram Bot configuration and active command handlers.
   */
  async getTelegramStatus(): Promise<{
    configured: boolean;
    bot_token_present: boolean;
    chat_id_present: boolean;
    registered_commands: string[];
  }> {
    const res = await authFetch(`${BASE_URL}/api/telegram/status`);
    return handleResponse(res);
  },

  /**
   * POST /api/telegram/broadcast
   * Dispatches custom telemetry alert to Telegram channel.
   */
  async broadcastTelegramAlert(
    text: string,
    parseMode: 'Markdown' | 'HTML' = 'Markdown'
  ): Promise<{ status: string; configured: boolean }> {
    const res = await authFetch(`${BASE_URL}/api/telegram/broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, parse_mode: parseMode }),
    });
    return handleResponse(res);
  },

  // ============================================================================
  // CONTINUOUS EMPIRICAL VALIDATION ACCUMULATOR
  // ============================================================================

  /**
   * GET /api/lab/empirical-status
   * Returns sample accumulation metrics across all market regimes.
   */
  async getEmpiricalValidationStatus(
    concept = 'SETUP_A_SWEEP_MSS'
  ): Promise<{
    total_samples_collected: number;
    validation_target_per_regime: number;
    regimes: Record<string, {
      regime: string;
      total_samples: number;
      target_samples: number;
      win_rate: number;
      expectancy_r: number;
      is_statistically_validated: boolean;
      status_label: string;
    }>;
    last_run_timestamp: number;
  }> {
    const res = await authFetch(
      `${BASE_URL}/api/lab/empirical-status?concept=${encodeURIComponent(concept)}`
    );
    return handleResponse(res);
  },

  /**
   * GET /api/memory/similarity
   * Returns top matching historical episodes, empirical win probability, and expected R:R.
   */
  async getMemorySimilarity(symbol: string, timeframe: SupportedTimeframe = '15m') {
    const res = await authFetch(
      `${BASE_URL}/api/memory/similarity?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`
    );
    return handleResponse<{
      symbol: string;
      timeframe: string;
      active_regime: string;
      k_samples_found: number;
      sample_adequacy_score: number;
      p_tp_hit: number;
      p_sl_hit: number;
      expected_r_multiple: number;
      median_mae_pct: number;
      median_mfe_pct: number;
      uncertainty_penalty: number;
      top_matches: Array<{
        state_id: string;
        timestamp: number;
        similarity_score: number;
        realized_return_1h: number;
        tp_hit: boolean;
        sl_hit: boolean;
        mae: number;
        mfe: number;
      }>;
    }>(res);
  },

  /**
   * GET /api/macro/gold
   */
  async getGoldMacroTelemetry(goldPrice?: number, paxgPrice?: number, dxy?: number, realYield?: number) {
    const params = new URLSearchParams();
    if (goldPrice !== undefined) params.append('gold_price', goldPrice.toString());
    if (paxgPrice !== undefined) params.append('paxg_price', paxgPrice.toString());
    if (dxy !== undefined) params.append('dxy', dxy.toString());
    if (realYield !== undefined) params.append('real_yield', realYield.toString());

    const qs = params.toString() ? `?${params.toString()}` : '';
    const res = await authFetch(`${BASE_URL}/api/macro/gold${qs}`);
    return handleResponse<{
      symbol: string;
      timestamp: number;
      current_gold_price: number;
      dxy_index: number;
      dxy_rolling_correlation_30d: number;
      us_10y_real_yield_pct: number;
      real_yield_beta: number;
      central_bank_net_flow_metric: number;
      active_fixing_session: string;
      is_in_prime_fixing_window: boolean;
      synthetic_paxg_basis_bps: number;
      macro_regime: string;
      macro_bias: string;
      macro_confidence: number;
      catalysts: string[];
    }>(res);
  },

  /**
   * GET /api/audit/events
   */
  async getAuditEvents(limit = 50, eventType?: string) {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (eventType) params.append('event_type', eventType);
    const res = await authFetch(`${BASE_URL}/api/audit/events?${params.toString()}`);
    return handleResponse<{
      events: Array<{
        event_id: string;
        timestamp: number;
        event_type: string;
        symbol: string;
        severity: string;
        reason: string;
        details: Record<string, any>;
        software_version: string;
      }>;
    }>(res);
  },

  /**
   * POST /api/ingest/source
   */
  async ingestSource(payload: {
    source_type: string;
    content: string;
    title?: string;
    source_url?: string;
    confidence?: number;
  }) {
    const res = await authFetch(`${BASE_URL}/api/ingest/source`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<{
      source_id: string;
      source_type: string;
      source_url?: string;
      retrieved_at: number;
      content_hash: string;
      title: string;
      confidence: number;
    }>(res);
  },

  /**
   * POST /api/strategy/compile
   */
  async compileStrategy(payload: {
    name: string;
    description: string;
    assets?: string[];
    timeframes?: Record<string, string>;
    entry_rules?: Array<Record<string, any>>;
    invalidation_rules?: Array<Record<string, any>>;
    exit_rules?: Array<Record<string, any>>;
  }) {
    const res = await authFetch(`${BASE_URL}/api/strategy/compile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<{
      strategy_id: string;
      name: string;
      status: string;
      confidence: number;
      missing_requirements: string[];
    }>(res);
  },

  /**
   * GET /api/kronos/forecast
   */
  async getKronosForecast(params?: {
    symbol?: string;
    timeframe?: string;
    lookback?: number;
    horizon?: number;
    samples?: number;
    freeze?: boolean;
  }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.samples) q.set('samples', params.samples.toString());
    if (params?.freeze !== undefined) q.set('freeze', params.freeze.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/forecast?${q.toString()}`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/kronos/health
   */
  async getKronosHealth() {
    const res = await authFetch(`${BASE_URL}/api/kronos/health`);
    return handleResponse<{
      status: string;
      total_inferences: number;
      failed_inferences: number;
      consecutive_errors: number;
      p50_latency_ms: number;
      p95_latency_ms: number;
      last_error?: string;
    }>(res);
  },

  /**
   * GET /api/kronos/history
   */
  async getKronosHistory(params?: { symbol?: string; timeframe?: string; limit?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.limit) q.set('limit', params.limit.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/history?${q.toString()}`);
    return handleResponse<{ records: any[]; count: number }>(res);
  },

  /**
   * POST /api/kronos/ablation
   */
  async runKronosAblation(params?: { symbol?: string; timeframe?: string; bars?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.bars) q.set('bars', params.bars.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/ablation?${q.toString()}`, {
      method: 'POST',
    });
    return handleResponse<any>(res);
  },

  /**
   * GET /api/kronos/calibration
   */
  async getKronosCalibration(params?: { symbol?: string; timeframe?: string }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    const res = await authFetch(`${BASE_URL}/api/kronos/calibration?${q.toString()}`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/kronos/advisory
   */
  async getKronosAdvisory(params?: { symbol?: string; timeframe?: string; sky_decision?: string }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.sky_decision) q.set('sky_decision', params.sky_decision);
    const res = await authFetch(`${BASE_URL}/api/kronos/advisory?${q.toString()}`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/microstructure/analytics
   */
  async getMicrostructureAnalytics(symbol = 'BTC/USDT') {
    const res = await authFetch(`${BASE_URL}/api/microstructure/analytics?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/microstructure/toxicity
   */
  async getMicrostructureToxicity(symbol = 'BTC/USDT') {
    const res = await authFetch(`${BASE_URL}/api/microstructure/toxicity?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/macro/network
   */
  async getMacroNetwork() {
    const res = await authFetch(`${BASE_URL}/api/macro/network`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/macro/spillover
   */
  async getMacroSpillover() {
    const res = await authFetch(`${BASE_URL}/api/macro/spillover`);
    return handleResponse<any>(res);
  },

  /**
   * POST /api/strategy/optimize/genetic
   */
  async runGeneticOptimization(params: {
    symbol?: string;
    timeframe?: string;
    bars?: number;
    generations?: number;
    population_size?: number;
  }) {
    const res = await authFetch(`${BASE_URL}/api/strategy/optimize/genetic`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: params.symbol || 'BTC/USDT',
        timeframe: params.timeframe || '15m',
        bars: params.bars || 120,
        generations: params.generations || 4,
        population_size: params.population_size || 15,
      }),
    });
    return handleResponse<any>(res);
  },

  /**
   * GET /api/strategy/optimize/results
   */
  async getGeneticOptimizationResults(symbol = 'BTC/USDT') {
    const res = await authFetch(`${BASE_URL}/api/strategy/optimize/results?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<any>(res);
  },

  /**
   * POST /api/execution/slice
   */
  async generateExecutionSlice(params: {
    qty: number;
    algo_type?: string;
    duration_sec?: number;
    num_slices?: number;
    mid_price?: number;
  }) {
    const res = await authFetch(`${BASE_URL}/api/execution/slice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        qty: params.qty,
        algo_type: params.algo_type || 'TWAP',
        duration_sec: params.duration_sec || 300,
        num_slices: params.num_slices || 5,
        mid_price: params.mid_price || 65000.0,
      }),
    });
    return handleResponse<any>(res);
  },

  /**
   * POST /api/execution/simulate_impact
   */
  async simulateMarketImpact(params: {
    order_size: number;
    order_side?: string;
    symbol?: string;
    mid_price?: number;
    urgency?: string;
  }) {
    const res = await authFetch(`${BASE_URL}/api/execution/simulate_impact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_size: params.order_size,
        order_side: params.order_side || 'BUY',
        symbol: params.symbol || 'BTC/USDT',
        mid_price: params.mid_price || 65000.0,
        urgency: params.urgency || 'MEDIUM',
      }),
    });
    return handleResponse<any>(res);
  },

  /**
   * GET /api/execution/routes
   */
  async getExecutionRoutes() {
    const res = await authFetch(`${BASE_URL}/api/execution/routes`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/auditor/telemetry
   */
  async getAuditorTelemetry() {
    const res = await authFetch(`${BASE_URL}/api/auditor/telemetry`);
    return handleResponse<any>(res);
  },

  /**
   * GET /api/auditor/drift
   */
  async getAuditorDrift() {
    const res = await authFetch(`${BASE_URL}/api/auditor/drift`);
    return handleResponse<any>(res);
  },

  /**
   * POST /api/auditor/record_trade
   */
  async recordAuditorTrade(params: {
    trade_id: string;
    symbol: string;
    side: string;
    entry_price: number;
    exit_price: number;
    qty: number;
    entry_time_ms: number;
    exit_time_ms: number;
    market_regime?: string;
    risk_per_trade_usd?: number;
  }) {
    const res = await authFetch(`${BASE_URL}/api/auditor/record_trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<any>(res);
  },

  // ============================================================================
  // UNIVERSAL RESEARCH & KNOWLEDGE LAB APIS
  // ============================================================================

  /**
   * POST /api/research/ingest (Raw text, YouTube/Reel URL, GitHub repo, PineScript)
   */
  async ingestResearchText(params: {
    content: string;
    mode: ResearchIngestMode;
    source_uri?: string;
    author_creator?: string;
    title?: string;
  }): Promise<ResearchIngestResult> {
    const res = await authFetch(`${BASE_URL}/api/research/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<ResearchIngestResult>(res);
  },

  /**
   * POST /api/research/ingest-file (Upload PDF, Code, Dataset, Notes)
   */
  async ingestResearchFile(params: {
    file: File;
    mode: ResearchIngestMode;
    author_creator?: string;
    title?: string;
  }): Promise<ResearchIngestResult> {
    const formData = new FormData();
    formData.append('file', params.file);
    formData.append('mode', params.mode);
    if (params.author_creator) formData.append('author_creator', params.author_creator);
    if (params.title) formData.append('title', params.title);

    const headers = authHeaders();
    // Do NOT set Content-Type header manually for FormData, let browser set boundary
    const res = await fetch(`${BASE_URL}/api/research/ingest-file`, {
      method: 'POST',
      headers,
      body: formData,
    });
    return handleResponse<ResearchIngestResult>(res);
  },

  /**
   * GET /api/research/inbox (Recent ingested items in provenance ledger)
   */
  async getResearchInbox(limit: number = 25): Promise<{ items: ResearchProvenanceItem[]; count: number }> {
    const res = await authFetch(`${BASE_URL}/api/research/inbox?limit=${limit}`);
    return handleResponse<{ items: ResearchProvenanceItem[]; count: number }>(res);
  },

  /**
   * GET /api/research/vaults (Overview and items across all 4 vaults)
   */
  async getResearchVaults(): Promise<ResearchVaultsResponse> {
    const res = await authFetch(`${BASE_URL}/api/research/vaults`);
    return handleResponse<ResearchVaultsResponse>(res);
  },

  /**
   * POST /api/research/candidates/:id/backtest (Run quantitative backtest verification)
   */
  async backtestResearchCandidate(candidateId: string, symbol: string = 'BTC/USDT', timeframe: string = '15m'): Promise<any> {
    const res = await authFetch(
      `${BASE_URL}/api/research/candidates/${encodeURIComponent(candidateId)}/backtest?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`,
      { method: 'POST' }
    );
    return handleResponse<any>(res);
  },

  /**
   * POST /api/research/share-telegram (Dispatch formatted literature / research summary to Telegram)
   */
  async sendSummaryToTelegram(payload: ResearchTelegramShareRequest): Promise<ResearchTelegramShareResponse> {
    const res = await authFetch(`${BASE_URL}/api/research/share-telegram`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    return handleResponse<ResearchTelegramShareResponse>(res);
  },

  // ============================================================================
  // SKY KNOWLEDGE & DISCOVERY GRAPH APIS (10/10 ARCHITECTURE)
  // ============================================================================

  /**
   * GET /api/research/graph (Full 6-node ontology + edge network)
   */
  async getDiscoveryGraph(): Promise<DiscoveryGraphResponse> {
    const res = await authFetch(`${BASE_URL}/api/research/graph`);
    return handleResponse<DiscoveryGraphResponse>(res);
  },

  /**
   * POST /api/research/discover (Scan cross-domain links)
   */
  async triggerCrossDomainDiscovery(): Promise<{ discoveries: CrossDomainDiscoveryItem[]; count: number }> {
    const res = await authFetch(`${BASE_URL}/api/research/discover`, { method: 'POST' });
    return handleResponse<{ discoveries: CrossDomainDiscoveryItem[]; count: number }>(res);
  },

  /**
   * POST /api/research/hypotheses/create
   */
  async createHypothesis(params: {
    title: string;
    null_hypothesis: string;
    alt_hypothesis: string;
    independent_variable: string;
    dependent_variable: string;
    claim_id?: string;
    target_symbol?: string;
    test_method?: string;
    control_variables?: string[];
  }): Promise<HypothesisNodeItem> {
    const res = await authFetch(`${BASE_URL}/api/research/hypotheses/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<HypothesisNodeItem>(res);
  },

  /**
   * POST /api/research/hypotheses/:id/run-test (Empirical statistical test)
   */
  async runHypothesisEmpiricalTest(hypothesisId: string): Promise<any> {
    const res = await authFetch(
      `${BASE_URL}/api/research/hypotheses/${encodeURIComponent(hypothesisId)}/run-test`,
      { method: 'POST' }
    );
    return handleResponse<any>(res);
  },

  /**
   * POST /api/research/youtube/explore (YouTube V5 Autonomous Channel & Playlist Explorer)
   */
  async exploreYouTube(params: {
    source_url_or_handle: string;
    limit?: number;
    sort_by?: string;
    force_refresh?: boolean;
    requested_by?: string;
  }): Promise<{ status: string; job_id: string; source: string; limit: number; message: string }> {
    const res = await authFetch(`${BASE_URL}/api/research/youtube/explore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; job_id: string; source: string; limit: number; message: string }>(res);
  },

  /**
   * GET /api/research/youtube/jobs/:job_id
   */
  async getYouTubeJob(jobId: string): Promise<any> {
    const res = await authFetch(`${BASE_URL}/api/research/youtube/jobs/${encodeURIComponent(jobId)}`);
    return handleResponse<any>(res);
  },

  // =========================================================================
  // Phase 16: Live Canary / Shadow Deployment & Telemetry Burn-In
  // =========================================================================

  /**
   * GET /api/burn-in/status
   */
  async getBurnInStatus(): Promise<BurnInStatus> {
    const res = await authFetch(`${BASE_URL}/api/burn-in/status`);
    return handleResponse<BurnInStatus>(res);
  },

  /**
   * POST /api/burn-in/toggle
   */
  async toggleBurnIn(action?: string, note?: string): Promise<{ status: string; orchestrator_state: string; burn_in_status: BurnInStatus }> {
    const res = await authFetch(`${BASE_URL}/api/burn-in/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action || 'toggle', note }),
    });
    return handleResponse<{ status: string; orchestrator_state: string; burn_in_status: BurnInStatus }>(res);
  },

  /**
   * GET /api/burn-in/sessions
   */
  async getBurnInSessions(limit: number = 20): Promise<{ status: string; sessions: BurnInSession[] }> {
    const res = await authFetch(`${BASE_URL}/api/burn-in/sessions?limit=${limit}`);
    return handleResponse<{ status: string; sessions: BurnInSession[] }>(res);
  },

  /**
   * GET /api/telemetry/hf/metrics
   */
  async getHFTelemetryMetrics(): Promise<{ status: string; metrics: HFTelemetryMetrics }> {
    const res = await authFetch(`${BASE_URL}/api/telemetry/hf/metrics`);
    return handleResponse<{ status: string; metrics: HFTelemetryMetrics }>(res);
  },

  /**
   * GET /api/telemetry/hf/recent
   */
  async getRecentHFTelemetry(limit: number = 50): Promise<{ status: string; records: HFTelemetryRecord[] }> {
    const res = await authFetch(`${BASE_URL}/api/telemetry/hf/recent?limit=${limit}`);
    return handleResponse<{ status: string; records: HFTelemetryRecord[] }>(res);
  },

  /**
   * GET /api/incident/escalations
   */
  async getIncidentEscalations(limit: number = 50, unresolvedOnly: boolean = false): Promise<{ status: string; incidents: IncidentEscalation[] }> {
    const res = await authFetch(`${BASE_URL}/api/incident/escalations?limit=${limit}&unresolved_only=${unresolvedOnly}`);
    return handleResponse<{ status: string; incidents: IncidentEscalation[] }>(res);
  },

  /**
   * POST /api/incident/simulate_trigger
   */
  async simulateIncidentTrigger(params: {
    tier: string;
    source_engine?: string;
    trigger_type?: string;
    trigger_value?: number;
    threshold_value?: number;
    description: string;
  }): Promise<{ status: string; incident: IncidentEscalation }> {
    const res = await authFetch(`${BASE_URL}/api/incident/simulate_trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; incident: IncidentEscalation }>(res);
  },

  /**
   * POST /api/incident/resolve/:incident_id
   */
  async resolveIncident(incidentId: string, operatorId: string = 'ADMIN', notes: string = 'Resolved'): Promise<{ status: string; incident_id: string; resolved: boolean }> {
    const res = await authFetch(`${BASE_URL}/api/incident/resolve/${encodeURIComponent(incidentId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operator_id: operatorId, notes }),
    });
    return handleResponse<{ status: string; incident_id: string; resolved: boolean }>(res);
  },

  // ============================================================================
  // MILESTONE 17: LIVE EXCHANGE EXECUTION & PRIVATE API CREDENTIAL VAULT (CLASS H)
  // ============================================================================

  /**
   * GET /api/vault/status
   */
  async getVaultStatus(): Promise<VaultStatus> {
    const res = await authFetch(`${BASE_URL}/api/vault/status`);
    return handleResponse<VaultStatus>(res);
  },

  /**
   * POST /api/vault/configure
   */
  async configureVaultCredential(params: {
    exchange: string;
    environment: string;
    api_key: string;
    api_secret: string;
    passphrase?: string;
    is_active?: boolean;
  }): Promise<{ status: string; message: string; credential: any }> {
    const res = await authFetch(`${BASE_URL}/api/vault/configure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; message: string; credential: any }>(res);
  },

  /**
   * POST /api/execution/live/order
   */
  async placeLiveOrder(req: LiveOrderRequest): Promise<{ status: string; receipt: LiveExecutionReceipt }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; receipt: LiveExecutionReceipt }>(res);
  },

  /**
   * POST /api/execution/live/cancel
   */
  async cancelLiveOrder(params: {
    exchange: string;
    environment: string;
    symbol: string;
    exchange_order_id?: string;
    client_order_id?: string;
    operator_id?: string;
  }): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  /**
   * GET /api/execution/live/balance
   */
  async getLiveBalances(exchange: string = 'BINANCE', environment: string = 'TESTNET'): Promise<LiveBalanceResponse> {
    const res = await authFetch(
      `${BASE_URL}/api/execution/live/balance?exchange=${encodeURIComponent(exchange)}&environment=${encodeURIComponent(environment)}`
    );
    return handleResponse<LiveBalanceResponse>(res);
  },

  /**
   * GET /api/execution/live/orders
   */
  async getLiveOrders(limit: number = 50): Promise<{ status: string; orders: any[] }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/orders?limit=${limit}`);
    return handleResponse<{ status: string; orders: any[] }>(res);
  },

  /**
   * POST /api/execution/live/kill-switch
   */
  async toggleLiveKillSwitch(action: 'engage' | 'disengage', reason: string, operator_id: string = 'ADMIN'): Promise<any> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/kill-switch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, reason, operator_id }),
    });
    return handleResponse<any>(res);
  },

  /**
   * POST /api/execution/live/reconcile
   */
  async reconcileLiveOrder(client_order_id: string): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/reconcile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_order_id }),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  /**
   * POST /api/execution/sor/route-quote
   */
  async getSORRouteQuote(req: {
    symbol: string;
    side: 'BUY' | 'SELL';
    total_qty: number;
    max_slippage_bps?: number;
  }): Promise<{ status: string; quote: SORRouteQuote }> {
    const res = await authFetch(`${BASE_URL}/api/execution/sor/route-quote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; quote: SORRouteQuote }>(res);
  },

  /**
   * POST /api/execution/slicer/almgren-chriss
   */
  async getAlmgrenChrissSchedule(req: {
    symbol: string;
    side: 'BUY' | 'SELL';
    total_qty: number;
    current_price: number;
    time_horizon_sec?: number;
    num_intervals?: number;
    annualized_volatility?: number;
    risk_aversion_lambda?: number;
  }): Promise<{ status: string; schedule: AlmgrenChrissSchedule }> {
    const res = await authFetch(`${BASE_URL}/api/execution/slicer/almgren-chriss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; schedule: AlmgrenChrissSchedule }>(res);
  },

  /**
   * GET /api/execution/reconciliation/report
   */
  async getReconciliationReport(
    symbol?: string,
    exchange?: string,
    window_hours: number = 24
  ): Promise<{ status: string; report: ReconciliationReport }> {
    const params = new URLSearchParams();
    if (symbol) params.append('symbol', symbol);
    if (exchange) params.append('exchange', exchange);
    params.append('window_hours', window_hours.toString());
    const res = await authFetch(`${BASE_URL}/api/execution/reconciliation/report?${params.toString()}`);
    return handleResponse<{ status: string; report: ReconciliationReport }>(res);
  },

  /**
   * GET /api/execution/reconciliation/records
   */
  async getReconciliationRecords(
    limit: number = 50,
    symbol?: string,
    exchange?: string,
    status?: string
  ): Promise<{ status: string; records: ReconciliationRecord[] }> {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    if (symbol) params.append('symbol', symbol);
    if (exchange) params.append('exchange', exchange);
    if (status) params.append('status', status);
    const res = await authFetch(`${BASE_URL}/api/execution/reconciliation/records?${params.toString()}`);
    return handleResponse<{ status: string; records: ReconciliationRecord[] }>(res);
  },
};

export interface BurnInStatus {
  status: string;
  state: string;
  execution_mode: 'SHADOW' | 'LIVE';
  current_session: string;
  active_sessions: string[];
  next_session: string;
  next_session_countdown_sec: number;
  burn_in_hours: number;
  burn_in_start_time_ms: number;
  heartbeat_interval_sec: number;
  heartbeat_sequence: number;
  heartbeats_received: number;
  heartbeats_missed: number;
  heartbeat_health_pct: number;
  last_heartbeat_timestamp_ms: number;
  trader_is_running: boolean;
  virtual_equity: number;
  total_realized_pnl: number;
  open_positions_count: number;
  closed_positions_count: number;
  win_rate_pct: number;
  profit_factor: number;
}

export interface BurnInSession {
  id: string;
  session_name: string;
  session_type: string;
  start_timestamp: number;
  end_timestamp?: number;
  opening_balance: number;
  closing_balance?: number;
  trade_count: number;
  winning_trades: number;
  losing_trades: number;
  session_pnl: number;
  session_return: number;
  max_drawdown: number;
  profit_factor?: number;
  win_rate?: number;
  heartbeat_expected: number;
  heartbeat_received: number;
  heartbeat_missed: number;
  status: string;
  execution_mode: string;
}

export interface HFTelemetryMetrics {
  sample_count: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  latency_p99_ms: number | null;
  avg_slippage_total_bps: number | null;
  avg_slippage_spread_bps: number | null;
  avg_slippage_impact_bps: number | null;
  avg_slippage_latency_bps: number | null;
  total_records_ingested: number;
  ring_buffer_size: number;
  ring_buffer_occupancy: number;
  flush_errors: number;
}

export interface HFTelemetryRecord {
  id: string;
  timestamp: number;
  symbol: string;
  exchange: string;
  execution_mode: string;
  timing: {
    t_recv_ns: number;
    t_queue_ns: number;
    t_decision_ns: number;
    t_exec_ns: number;
    recv_to_queue_ns: number;
    queue_to_decision_ns: number;
    decision_to_exec_ns: number;
    total_pipeline_latency_ns: number;
    total_pipeline_latency_ms: number;
  };
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  spread_bps: number;
  order_side: string;
  order_type: string;
  order_price: number;
  execution_price: number;
  order_size: number;
  queue_estimate: {
    visible_depth: number;
    estimated_volume_ahead: number;
    estimated_cancel_rate: number;
    estimated_fill_probability: number;
    confidence: number;
    model_type: string;
  };
  slippage: {
    slippage_total_bps: number;
    slippage_spread_bps: number;
    slippage_impact_bps: number;
    slippage_latency_bps: number;
    reference_mid: number;
    reference_quote: number;
    execution_price: number;
  };
  telemetry_sequence: number;
  integrity_valid: boolean;
}

export interface IncidentEscalation {
  id: string;
  incident_id: string;
  timestamp: number;
  tier: 'NOTICE' | 'WARNING' | 'CRITICAL' | 'EMERGENCY';
  severity: string;
  source_engine: string;
  trigger_type: string;
  trigger_value: number;
  threshold_value: number;
  description: string;
  automated_action: string;
  operator_action?: string;
  confirmation_required: number;
  confirmation_status: string;
  nonce?: string;
  token_hash?: string;
  issued_at?: number;
  expires_at?: number;
  resolved: number;
  resolved_at?: number;
  resolved_by?: string;
  execution_mode: string;
  metadata_json?: string;
}

export interface VaultStatus {
  status: string;
  live_execution_enabled: boolean;
  kill_switch: {
    is_active: boolean;
    reason: string;
    activated_by: string;
    activated_at: number;
    source: string;
  };
  configured_exchanges: Array<{
    exchange: string;
    environment: string;
    masked_api_key: string;
    is_active: boolean;
    has_secret: boolean;
    has_passphrase: boolean;
    updated_at: number;
    error?: string;
  }>;
  ambiguous_orders_count: number;
  timestamp_ms: number;
}

export interface LiveOrderRequest {
  exchange: string;
  environment: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: 'LIMIT' | 'MARKET';
  quantity: number;
  price?: number;
  stop_loss?: number;
  take_profit?: number;
  account_equity_usd?: number;
  daily_realized_pnl_usd?: number;
  daily_unrealized_pnl_usd?: number;
  current_open_positions_count?: number;
  max_open_positions_cap?: number;
  client_order_id?: string;
  correlation_id?: string;
}

export interface LiveExecutionReceipt {
  success: boolean;
  status: string;
  client_order_id: string;
  exchange_order_id: string;
  exchange: string;
  environment: string;
  symbol: string;
  side: string;
  order_type: string;
  requested_qty: number;
  executed_qty: number;
  executed_price: number;
  cumulative_quote_qty: number;
  latency_ms: number;
  audit_event_id: string;
  message: string;
  requires_reconciliation: boolean;
}

export interface LiveBalanceResponse {
  status: string;
  exchange: string;
  environment: string;
  balances: Array<{
    asset: string;
    free: number;
    locked: number;
    total: number;
  }>;
  timestamp_ms: number;
}

export interface VenueSplitQuote {
  exchange: string;
  allocated_qty: number;
  allocated_notional: number;
  expected_vwap: number;
  expected_fee_usd: number;
  expected_slippage_bps: number;
  percentage: number;
}

export interface SORRouteQuote {
  symbol: string;
  side: string;
  total_qty: number;
  reference_mid_price: number;
  weighted_vwap: number;
  total_fee_usd: number;
  total_effective_cost_usd: number;
  total_slippage_bps: number;
  splits: VenueSplitQuote[];
  routing_reason: string;
  timestamp_ms: number;
}

export interface AlmgrenChrissSlice {
  interval_index: number;
  scheduled_offset_sec: number;
  slice_qty: number;
  remaining_qty_after: number;
  fraction_of_total: number;
  instantaneous_impact_bps: number;
  expected_slice_price: number;
}

export interface AlmgrenChrissSchedule {
  symbol: string;
  side: string;
  total_qty: number;
  current_price: number;
  time_horizon_sec: number;
  num_intervals: number;
  interval_duration_sec: number;
  risk_aversion_lambda: number;
  volatility: number;
  expected_total_cost_usd: number;
  variance_cost_usd: number;
  expected_slippage_bps: number;
  is_linear_twap: boolean;
  slices: AlmgrenChrissSlice[];
  created_at_ms: number;
}

export interface ReconciliationReport {
  window_hours: number;
  total_reconciled_orders: number;
  fill_rate_pct: number;
  status_breakdown: Record<string, number>;
  average_slippage_bps: number;
  max_adverse_slippage_bps: number;
  total_fees_usd: number;
  average_roundtrip_latency_ms: number;
  venue_distribution: Record<string, number>;
}

export interface ReconciliationRecord {
  reconciliation_id: string;
  parent_order_id: string;
  client_order_id: string;
  exchange_order_id: string;
  exchange: string;
  symbol: string;
  side: string;
  requested_qty: number;
  executed_qty: number;
  expected_price: number;
  executed_price: number;
  slippage_bps: number;
  fee_paid_usd: number;
  fee_asset: string;
  route_venue: string;
  transit_latency_ms: number;
  exchange_ack_latency_ms: number;
  total_roundtrip_ms: number;
  reconciliation_status: string;
  created_at_ms: number;
  reconciled_at_ms: number;
}
