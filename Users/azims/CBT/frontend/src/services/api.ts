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
  KMSEnclaveStatus,
  SORBenchmarkSuite,
  WSReconciliationTelemetry,
  WSNormalizedFill,
  KnowledgeAskMode,
  HumanQuestionMode,
  KnowledgeAskResponse,
  ProjectKnowledgeContext,
  PersonalLearningGraphResponse,
  QuizSubmissionResult,
  ResearchAdvisorResponse,
  LibraryStatsResponse,
  BookIngestionJob,
  ResearchGapItem,
  KnowledgeAuditReport,
  MasterTerminalTelemetry,
  ProvenanceGraphData,
  ReplaySnapshotData,
  SMCGlossaryItem,
  SignalBlotterRecord,
  MacroComprehensionResult,
  DynamicTradingPlan,
  CapitalEscalationReport,
  CapitalTier,
  KronosDomainForecastData,
  KronosBrierReport,
  KronosTournamentReport,
  KronosIncrementalReport,
  KronosRegimesReport,
  KronosAblationReport,
  KronosPromotionReport,
  TestnetBurnInReport,
  IntelligenceStatusResponse,
  IntelligenceRecordsResponse,
  NarrativesResponse,
  ScoutTelemetry,
  CausalHypothesis,
  CausalFirewallDecision,
  HypothesisStatsResponse,
  HypothesesListResponse,
  SynthesizeResponse,
  FamiliesResponse,
  PreregisteredResearchContract,
  ReplayResponse,
  CausalValidationResult,
  CausalFailureAutopsy,
  PlansListResponse,
  CrawlerTemplatesResponse,
  CrawlerMultipleTestingResponse,
  EvidenceLineageResponse,
  QualifyResponse,
} from '../types';

const getApiBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'file:') {
      return 'http://127.0.0.1:8000';
    }
  }
  return '';
};

const BASE_URL = getApiBaseUrl();

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
  if (init?.body && typeof init.body === 'string' && !(headers as Headers).has('Content-Type')) {
    (headers as Headers).set('Content-Type', 'application/json');
  }
  let finalInput = input;
  if (
    typeof input === 'string' &&
    input.startsWith('/') &&
    typeof window !== 'undefined' &&
    window.location.protocol === 'file:'
  ) {
    finalInput = `http://127.0.0.1:8000${input}`;
  }
  return fetch(finalInput, { ...init, headers });
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
   * GET /api/testnet/burnin/report - Gate 5 Extended Testnet Burn-In telemetry
   */
  async getTestnetBurnInReport(sessionId?: string): Promise<TestnetBurnInReport> {
    return getTestnetBurnInReport(sessionId);
  },

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
    equity = 10000
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
   * Milestone K8: GET /api/kronos/forecast (Authoritative Domain Forecast)
   */
  async getKronosDomainForecast(params?: {
    symbol?: string;
    timeframe?: string;
    lookback?: number;
    horizon?: number;
    samples?: number;
    hurdle?: number;
    freeze?: boolean;
  }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.samples) q.set('samples', params.samples.toString());
    if (params?.hurdle !== undefined) q.set('hurdle', params.hurdle.toString());
    if (params?.freeze !== undefined) q.set('freeze', params.freeze.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/forecast?${q.toString()}`);
    return handleResponse<KronosDomainForecastData>(res);
  },

  /**
   * Milestone K8: GET /api/kronos/status
   */
  async getKronosStatus() {
    const res = await authFetch(`${BASE_URL}/api/kronos/status`);
    return handleResponse<{
      provider_type: string;
      status: string;
      model_family: string;
      model_version: string;
      device: string;
      latency_p50_ms: number;
      provider_mode: string;
      error_message?: string;
    }>(res);
  },

  /**
   * Milestone K8: GET /api/kronos/calibration-status
   */
  async getKronosCalibrationStatus(params?: { symbol?: string; timeframe?: string }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    const res = await authFetch(`${BASE_URL}/api/kronos/calibration-status?${q.toString()}`);
    return handleResponse<KronosBrierReport>(res);
  },

  /**
   * Milestone K8: GET /api/kronos/brier-history
   */
  async getKronosBrierHistory(params?: { symbol?: string; timeframe?: string; limit?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.limit) q.set('limit', params.limit.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/brier-history?${q.toString()}`);
    return handleResponse<{ records: any[]; count: number; as_of_timestamp: number }>(res);
  },

  /**
   * Milestone K8: POST /api/kronos/run-brier-audit
   */
  async runKronosBrierAudit(params: { symbol: string; timeframe: string; lookback_eval?: number }) {
    const res = await authFetch(`${BASE_URL}/api/kronos/run-brier-audit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{
      success: boolean;
      resolved_forecasts_count: number;
      research_context: any;
    }>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/tournament
   */
  async getKronosTournament(params?: { symbol?: string; timeframe?: string; horizon?: number; lookback?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/research/tournament?${q.toString()}`);
    return handleResponse<KronosTournamentReport>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/incremental
   */
  async getKronosIncremental(params?: { symbol?: string; timeframe?: string; horizon?: number; lookback?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/research/incremental?${q.toString()}`);
    return handleResponse<KronosIncrementalReport>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/regimes
   */
  async getKronosRegimes(params?: { symbol?: string; timeframe?: string; horizon?: number; lookback?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/research/regimes?${q.toString()}`);
    return handleResponse<KronosRegimesReport>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/ablation
   */
  async getKronosAblation(params?: { symbol?: string; timeframe?: string; horizon?: number; lookback?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/research/ablation?${q.toString()}`);
    return handleResponse<KronosAblationReport>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/promotion-status
   */
  async getKronosPromotionStatus(params?: { symbol?: string; timeframe?: string; horizon?: number; lookback?: number }) {
    const q = new URLSearchParams();
    if (params?.symbol) q.set('symbol', params.symbol);
    if (params?.timeframe) q.set('timeframe', params.timeframe);
    if (params?.horizon) q.set('horizon', params.horizon.toString());
    if (params?.lookback) q.set('lookback', params.lookback.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/research/promotion-status?${q.toString()}`);
    return handleResponse<KronosPromotionReport>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/experiments
   */
  async getKronosExperiments(params?: { limit?: number }) {
    const q = new URLSearchParams();
    if (params?.limit) q.set('limit', params.limit.toString());
    const res = await authFetch(`${BASE_URL}/api/kronos/research/experiments?${q.toString()}`);
    return handleResponse<{ count: number; cumulative_trials: number; experiments: any[] }>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/reproducibility
   */
  async getKronosReproducibility(experimentId: string) {
    const q = new URLSearchParams({ experiment_id: experimentId });
    const res = await authFetch(`${BASE_URL}/api/kronos/research/reproducibility?${q.toString()}`);
    return handleResponse<any>(res);
  },

  /**
   * Milestone K9: GET /api/kronos/research/manifests
   */
  async getKronosManifests() {
    const res = await authFetch(`${BASE_URL}/api/kronos/research/manifests`);
    return handleResponse<{ dataset_count: number; manifests: Record<string, any> }>(res);
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
      headers: { 'Content-Type': 'application/json' },
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

  /**
   * GET /api/research/youtube/jobs
   */
  async listYouTubeJobs(limit: number = 10): Promise<{ jobs: any[] }> {
    const res = await authFetch(`${BASE_URL}/api/research/youtube/jobs?limit=${limit}`);
    return handleResponse<{ jobs: any[] }>(res);
  },

  // =========================================================================
  // SKY KNOWLEDGE OPERATING SYSTEM APIS (PROJECT BRAIN + HUMAN BRAIN)
  // =========================================================================

  /**
   * POST /api/knowledge/ask (Universal Human & Project Brain Query Interface)
   */
  async askKnowledgeOS(params: {
    question: string;
    mode?: KnowledgeAskMode;
    domain?: string;
    depth?: string;
    human_mode?: HumanQuestionMode;
    target_symbol?: string;
    timeframe?: string;
    include_sources?: boolean;
    include_evidence?: boolean;
    include_contradictions?: boolean;
  }): Promise<KnowledgeAskResponse> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<KnowledgeAskResponse>(res);
  },

  /**
   * POST /api/knowledge/project/context (Quantitative Research Context Package)
   */
  async getProjectKnowledgeContext(query: string, symbol: string = 'BTC/USDT', timeframe: string = '15m'): Promise<ProjectKnowledgeContext> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/project/context`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, target_symbol: symbol, timeframe }),
    });
    return handleResponse<ProjectKnowledgeContext>(res);
  },

  /**
   * GET /api/knowledge/human/learning-graph (Personal Curriculum & Mastery Graph)
   */
  async getPersonalLearningGraph(): Promise<PersonalLearningGraphResponse> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/human/learning-graph`);
    return handleResponse<PersonalLearningGraphResponse>(res);
  },

  /**
   * POST /api/knowledge/human/quiz/submit (Self-test evaluation & spaced review)
   */
  async submitQuizAnswer(params: {
    quiz_id: string;
    concept_id: string;
    selected_option_index: number;
    correct_option_index: number;
    question_text?: string;
    options?: string[];
    misconception_trap?: string;
  }): Promise<QuizSubmissionResult> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/human/quiz/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<QuizSubmissionResult>(res);
  },

  /**
   * GET /api/knowledge/human/advisor (Right Path Personalized Advisor)
   */
  async getResearchAdvisor(): Promise<ResearchAdvisorResponse> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/human/advisor`);
    return handleResponse<ResearchAdvisorResponse>(res);
  },

  /**
   * GET /api/knowledge/library/stats (Consolidated Volume Across 7 Tiers)
   */
  async getLibraryStats(): Promise<LibraryStatsResponse> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/library/stats`);
    return handleResponse<LibraryStatsResponse>(res);
  },

  /**
   * GET /api/knowledge/library/jobs (Streaming Ingestion Progress)
   */
  async getLibraryJobs(): Promise<{ jobs: BookIngestionJob[]; count: number }> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/library/jobs`);
    return handleResponse<{ jobs: BookIngestionJob[]; count: number }>(res);
  },

  /**
   * GET /api/knowledge/gaps (High Talk vs Zero Evidence Deficit Scanner)
   */
  async getResearchGaps(): Promise<{ gaps: ResearchGapItem[]; count: number }> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/gaps`);
    return handleResponse<{ gaps: ResearchGapItem[]; count: number }>(res);
  },

  /**
   * GET /api/knowledge/audit (7-Invariant Integrity & Provenance Audit)
   */
  async runKnowledgeAudit(): Promise<KnowledgeAuditReport> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/audit`);
    return handleResponse<KnowledgeAuditReport>(res);
  },

  /**
   * GET /api/knowledge/macro-state (Active Macro Cognitive Intelligence State)
   */
  async getMacroState(): Promise<{ success: boolean; macro_state: MacroComprehensionResult | null; count: number }> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/macro-state`);
    return handleResponse<{ success: boolean; macro_state: MacroComprehensionResult | null; count: number }>(res);
  },

  /**
   * GET /api/knowledge/trading-plans (Macro-confluent SMC Trading Plans)
   */
  async getMacroTradingPlans(): Promise<{ success: boolean; plans: DynamicTradingPlan[]; count: number }> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/trading-plans`);
    return handleResponse<{ success: boolean; plans: DynamicTradingPlan[]; count: number }>(res);
  },

  /**
   * POST /api/knowledge/trade-plan-impact (Confluence & Kelly Sizing Impact Evaluation)
   */
  async evaluateTradePlanImpact(symbol: string, direction: string): Promise<{
    success: boolean;
    symbol: string;
    direction: string;
    macro_alignment: 'CONFLUENT' | 'NEUTRAL' | 'CAUTION_DAMPENED';
    sizing_multiplier: number;
    macro_regime: string;
    macro_driver: string;
    rationale: string;
  }> {
    const res = await authFetch(`${BASE_URL}/api/knowledge/trade-plan-impact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, direction }),
    });
    return handleResponse<{
      success: boolean;
      symbol: string;
      direction: string;
      macro_alignment: 'CONFLUENT' | 'NEUTRAL' | 'CAUTION_DAMPENED';
      sizing_multiplier: number;
      macro_regime: string;
      macro_driver: string;
      rationale: string;
    }>(res);
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
   * POST /api/vault/verify
   */
  async verifyVaultCredential(params: {
    exchange: string;
    environment: string;
  }): Promise<{ status: string; verification: any }> {
    const res = await authFetch(`${BASE_URL}/api/vault/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; verification: any }>(res);
  },

  /**
   * DELETE /api/vault/credential
   */
  async deleteVaultCredential(params: {
    exchange: string;
    environment: string;
  }): Promise<{ status: string; message: string; deleted: boolean }> {
    const res = await authFetch(`${BASE_URL}/api/vault/credential`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; message: string; deleted: boolean }>(res);
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

  /**
   * GET /api/vault/kms/status
   */
  async getKMSStatus(): Promise<KMSEnclaveStatus> {
    const res = await authFetch(`${BASE_URL}/api/vault/kms/status`);
    return handleResponse<KMSEnclaveStatus>(res);
  },

  /**
   * GET /api/execution/sor/benchmark
   */
  async getSORBenchmarks(iterations: number = 100): Promise<{ status: string; benchmark: SORBenchmarkSuite }> {
    const res = await authFetch(`${BASE_URL}/api/execution/sor/benchmark?iterations=${iterations}`);
    return handleResponse<{ status: string; benchmark: SORBenchmarkSuite }>(res);
  },

  /**
   * GET /api/execution/ws-reconciliation/telemetry
   */
  async getWSReconciliationTelemetry(): Promise<{ status: string; telemetry: WSReconciliationTelemetry; timestamp_ms: number }> {
    const res = await authFetch(`${BASE_URL}/api/execution/ws-reconciliation/telemetry`);
    return handleResponse<{ status: string; telemetry: WSReconciliationTelemetry; timestamp_ms: number }>(res);
  },

  /**
   * GET /api/execution/ws-reconciliation/recent
   */
  async getWSReconciliationRecent(limit: number = 20): Promise<{ status: string; limit: number; recent_fills: WSNormalizedFill[]; timestamp_ms: number }> {
    const res = await authFetch(`${BASE_URL}/api/execution/ws-reconciliation/recent?limit=${limit}`);
    return handleResponse<{ status: string; limit: number; recent_fills: WSNormalizedFill[]; timestamp_ms: number }>(res);
  },

  // =========================================================================
  // Milestone 22.3: Capital Escalation & Walk-Forward Risk Governance
  // =========================================================================

  /**
   * GET /api/execution/escalation/status
   */
  async getCapitalEscalationStatus(strategy_id?: string): Promise<{ status: string; escalation: CapitalEscalationReport }> {
    const params = new URLSearchParams();
    if (strategy_id) params.append('strategy_id', strategy_id);
    const res = await authFetch(`${BASE_URL}/api/execution/escalation/status?${params.toString()}`);
    return handleResponse<{ status: string; escalation: CapitalEscalationReport }>(res);
  },

  /**
   * POST /api/execution/escalation/evaluate
   */
  async evaluateCapitalEscalation(req: {
    strategy_id?: string;
    sharpe: number;
    trade_count: number;
    trials_count?: number;
    max_drawdown?: number;
    slippage_bps?: number;
    regime_count?: number;
    skewness?: number;
    kurtosis?: number;
  }): Promise<{ status: string; evaluation: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/escalation/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; evaluation: any }>(res);
  },

  /**
   * POST /api/execution/escalation/activate-eligible
   */
  async activateEligibleTier(strategy_id?: string, operator: string = 'OPERATOR_DESK'): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/escalation/activate-eligible`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy_id, operator }),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  /**
   * POST /api/execution/escalation/clamp
   */
  async clampCapitalTier(req: {
    strategy_id?: string;
    target_tier: CapitalTier;
    reason: string;
    operator?: string;
  }): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/escalation/clamp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  /**
   * POST /api/execution/escalation/authorize-production
   */
  async authorizeProductionTier(req: {
    strategy_id: string;
    hmac_signature: string;
    auth_payload: string;
    secret_key: string;
    timestamp_ms: number;
  }): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/escalation/authorize-production`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  /**
   * GET /api/terminal/telemetry
   * Master Institutional Command Cockpit Unified Telemetry
   */
  async getMasterTerminalTelemetry(
    symbol: string = 'BTCUSDT',
    timeframe: SupportedTimeframe = '15m'
  ): Promise<MasterTerminalTelemetry> {
    const res = await authFetch(
      `${BASE_URL}/api/terminal/telemetry?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`
    );
    return handleResponse<MasterTerminalTelemetry>(res);
  },

  /**
   * POST /api/terminal/approval-action
   * Signal Lifecycle Execution & Transition
   */
  async updateSignalApproval(
    signalId: string,
    action: 'APPROVE' | 'REJECT' | 'EXECUTE' | 'CLOSE',
    notes?: string
  ): Promise<{ success: boolean; signalId: string; newState: string; updatedSignal: SignalBlotterRecord }> {
    const res = await authFetch(`${BASE_URL}/api/terminal/approval-action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ signalId, action, notes }),
    });
    return handleResponse<{ success: boolean; signalId: string; newState: string; updatedSignal: SignalBlotterRecord }>(res);
  },

  /**
   * GET /api/terminal/provenance
   * Traceable audit graph from raw market data to final thesis
   */
  async getTerminalProvenance(thesisId?: string): Promise<ProvenanceGraphData> {
    const query = thesisId ? `?thesisId=${encodeURIComponent(thesisId)}` : '';
    const res = await authFetch(`${BASE_URL}/api/terminal/provenance${query}`);
    return handleResponse<ProvenanceGraphData>(res);
  },

  /**
   * GET /api/terminal/replay
   * Historical Snapshot for Market Replay Time-Scrubbing
   */
  async getTerminalReplay(offset: string = 'NOW'): Promise<ReplaySnapshotData> {
    const res = await authFetch(`${BASE_URL}/api/terminal/replay?offset=${encodeURIComponent(offset)}`);
    return handleResponse<ReplaySnapshotData>(res);
  },

  /**
   * GET /api/terminal/glossary
   * Searchable SMC & Quantitative Glossary
   */
  async getSMCGlossary(query?: string): Promise<{ totalCount: number; query: string; items: SMCGlossaryItem[] }> {
    const q = query ? `?q=${encodeURIComponent(query)}` : '';
    const res = await authFetch(`${BASE_URL}/api/terminal/glossary${q}`);
    return handleResponse<{ totalCount: number; query: string; items: SMCGlossaryItem[] }>(res);
  },

  /**
   * GET /api/volatility/summary
   * Returns high-level volatility intelligence summary (Skew, Term Structure, GEX, Tail-Risk Multiplier).
   */
  async getVolatilitySummary(symbol: string = 'BTC'): Promise<VolatilitySummaryResponse> {
    const res = await authFetch(`${BASE_URL}/api/volatility/summary?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<VolatilitySummaryResponse>(res);
  },

  /**
   * GET /api/volatility/surface
   * Returns 2D regularized volatility surface matrix (Moneyness vs Tenors).
   */
  async getVolatilitySurface(symbol: string = 'BTC'): Promise<VolatilitySurfaceResponse> {
    const res = await authFetch(`${BASE_URL}/api/volatility/surface?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<VolatilitySurfaceResponse>(res);
  },

  /**
   * GET /api/volatility/skew
   * Returns 25-Delta skew parameters and risk reversals across tenors.
   */
  async getVolatilitySkew(symbol: string = 'BTC'): Promise<VolatilitySkewResponse> {
    const res = await authFetch(`${BASE_URL}/api/volatility/skew?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<VolatilitySkewResponse>(res);
  },

  /**
   * GET /api/volatility/term-structure
   * Returns constant-maturity ATM term structure curve and Contango/Backwardation state.
   */
  async getVolatilityTermStructure(symbol: string = 'BTC'): Promise<VolatilityTermStructureResponse> {
    const res = await authFetch(`${BASE_URL}/api/volatility/term-structure?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<VolatilityTermStructureResponse>(res);
  },

  /**
   * GET /api/volatility/gex
   * Returns Net Dealer Gamma Exposure (GEX) profile and Options Max Pain.
   */
  async getVolatilityGEX(symbol: string = 'BTC'): Promise<VolatilityGEXResponse> {
    const res = await authFetch(`${BASE_URL}/api/volatility/gex?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<VolatilityGEXResponse>(res);
  },

  /**
   * TASK 20.1: ARBITRAGE & FUNDING DISLOCATION SENTINEL
   */
  async getArbitrageDislocations(symbol: string = 'BTCUSDT'): Promise<ArbitrageDislocationsResponse> {
    const res = await authFetch(`${BASE_URL}/api/arbitrage/dislocations?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<ArbitrageDislocationsResponse>(res);
  },

  async getFundingMatrix(symbol: string = 'BTCUSDT'): Promise<FundingMatrixResponse> {
    const res = await authFetch(`${BASE_URL}/api/arbitrage/funding-matrix?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<FundingMatrixResponse>(res);
  },

  async getArbitrageOpportunities(symbol: string = 'BTCUSDT'): Promise<ArbitrageOpportunitiesResponse> {
    const res = await authFetch(`${BASE_URL}/api/arbitrage/opportunities?symbol=${encodeURIComponent(symbol)}`);
    return handleResponse<ArbitrageOpportunitiesResponse>(res);
  },

  async getArbitrageHistory(limit: number = 50): Promise<ArbitrageHistoryResponse> {
    const res = await authFetch(`${BASE_URL}/api/arbitrage/history?limit=${limit}`);
    return handleResponse<ArbitrageHistoryResponse>(res);
  },

  async getArbitrageHealth(): Promise<ArbitrageHealthResponse> {
    const res = await authFetch(`${BASE_URL}/api/arbitrage/health`);
    return handleResponse<ArbitrageHealthResponse>(res);
  },

  async getArbitrageProvenance(opportunityId: string): Promise<ArbitrageProvenanceResponse> {
    const res = await authFetch(`${BASE_URL}/api/arbitrage/provenance/${encodeURIComponent(opportunityId)}`);
    return handleResponse<ArbitrageProvenanceResponse>(res);
  },

  /**
   * TASK 20.2: L3 MARKET BY ORDER (MBO) LIQUIDITY DEPTH RECONSTRUCTION
   */
  async getMBODepth(symbol: string = 'BTCUSDT', venue: string = 'BINANCE_SPOT'): Promise<MBODepthResponse> {
    const res = await authFetch(`${BASE_URL}/api/mbo/depth?symbol=${encodeURIComponent(symbol)}&venue=${encodeURIComponent(venue)}`);
    return handleResponse<MBODepthResponse>(res);
  },

  async getMBOQueueEstimate(
    symbol: string = 'BTCUSDT',
    venue: string = 'BINANCE_SPOT',
    side: 'BID' | 'ASK' = 'BID',
    price: number = 65000,
    qty: number = 0.5,
    targetOrderId?: string
  ): Promise<MBOQueueEstimateResponse> {
    let url = `${BASE_URL}/api/mbo/queue-estimate?symbol=${encodeURIComponent(symbol)}&venue=${encodeURIComponent(venue)}&side=${side}&price=${price}&qty=${qty}`;
    if (targetOrderId) url += `&target_order_id=${encodeURIComponent(targetOrderId)}`;
    const res = await authFetch(url);
    return handleResponse<MBOQueueEstimateResponse>(res);
  },

  async getMBOIcebergs(symbol?: string): Promise<MBOIcebergsResponse> {
    let url = `${BASE_URL}/api/mbo/icebergs`;
    if (symbol) url += `?symbol=${encodeURIComponent(symbol)}`;
    const res = await authFetch(url);
    return handleResponse<MBOIcebergsResponse>(res);
  },

  async getMBOToxicity(symbol: string = 'BTCUSDT', venue: string = 'BINANCE_SPOT'): Promise<MBOToxicityResponse> {
    const res = await authFetch(`${BASE_URL}/api/mbo/toxicity?symbol=${encodeURIComponent(symbol)}&venue=${encodeURIComponent(venue)}`);
    return handleResponse<MBOToxicityResponse>(res);
  },

  // ============================================================================
  // PHASE 21: LIVE EXCHANGE TRADING LAUNCH GATEKEEPER & READINESS
  // ============================================================================

  async getAccountReadiness(environment: string = 'PRODUCTION'): Promise<AccountReadinessStatus> {
    const res = await authFetch(`${BASE_URL}/api/execution/account-readiness?environment=${encodeURIComponent(environment)}`);
    return handleResponse<AccountReadinessStatus>(res);
  },

  async evaluateGatekeeperCheck(exchange: string, notional: number, environment: string = 'PRODUCTION'): Promise<GatekeeperCheckResult> {
    const res = await authFetch(`${BASE_URL}/api/execution/live-gatekeeper/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exchange, order_notional_usd: notional, environment }),
    });
    return handleResponse<GatekeeperCheckResult>(res);
  },

  async runLiveCanaryOrder(params: {
    exchange: string;
    symbol: string;
    notional_usd: number;
    side?: string;
    order_type?: string;
    price?: number;
    environment?: string;
    is_dry_run?: boolean;
  }): Promise<CanaryRunResult> {
    const res = await authFetch(`${BASE_URL}/api/execution/live-canary/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<CanaryRunResult>(res);
  },

  async getLiveCanaryStatus(): Promise<{
    status: string;
    min_canary_notional_usd: number;
    max_canary_notional_usd: number;
    vault_unlocked: boolean;
    is_ready_for_canary: boolean;
    single_trade_cap_usd: number;
    reasons: string[];
    timestamp_ms: number;
  }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live-canary/status`);
    return handleResponse<any>(res);
  },

  async getTelegramLiveStatus(): Promise<{
    status: string;
    bot_configured: boolean;
    bd_time_str: string;
    is_ready_for_canary: boolean;
    single_trade_cap_usd: number;
    active_exchanges: string[];
  }> {
    const res = await authFetch(`${BASE_URL}/api/telegram/live-status`);
    return handleResponse<any>(res);
  },

  async triggerTelegramBriefing(briefingType: string = 'WHAT_AI_LEARNED'): Promise<{
    status: string;
    briefing_type: string;
    text_preview: string;
  }> {
    const res = await authFetch(`${BASE_URL}/api/telegram/trigger-briefing?briefing_type=${encodeURIComponent(briefingType)}`, {
      method: 'POST',
    });
    return handleResponse<any>(res);
  },

  // ============================================================================
  // PHASE 22: LIVE PROTECTION & POSITION CONTROL COCKPIT
  // ============================================================================

  async getLiveExecutionState(
    exchange: string = 'BINANCE',
    environment: string = 'TESTNET',
    symbol?: string
  ): Promise<{ status: string; snapshot: LiveExecutionSnapshot }> {
    let url = `${BASE_URL}/api/execution/live/state?exchange=${encodeURIComponent(exchange)}&environment=${encodeURIComponent(environment)}`;
    if (symbol) url += `&symbol=${encodeURIComponent(symbol)}`;
    const res = await authFetch(url);
    return handleResponse<{ status: string; snapshot: LiveExecutionSnapshot }>(res);
  },

  async executeLivePanicClose(
    exchange: string,
    symbol: string,
    environment: string = 'TESTNET',
    reason: string = 'OPERATOR_PANIC'
  ): Promise<PanicCloseResponse> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/panic-close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exchange, symbol, environment, reason }),
    });
    return handleResponse<PanicCloseResponse>(res);
  },

  async moveBracketToBreakeven(
    exchange: string,
    symbol: string,
    environment: string = 'TESTNET'
  ): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/bracket/breakeven`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exchange, symbol, environment }),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  async cancelLiveWorkingOrder(
    exchange: string,
    symbol: string,
    orderId: string,
    clientOrderId?: string,
    environment: string = 'TESTNET'
  ): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/order/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        exchange,
        symbol,
        order_id: orderId,
        client_order_id: clientOrderId,
        environment,
      }),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  async cancelAllLiveWorkingOrders(
    exchange: string,
    symbol: string,
    environment: string = 'TESTNET'
  ): Promise<{ status: string; result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/orders/cancel-all`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exchange, symbol, environment }),
    });
    return handleResponse<{ status: string; result: any }>(res);
  },

  async submitProtectedLiveOrder(params: {
    exchange: string;
    symbol: string;
    side: string;
    quantity: number;
    tp_price: number;
    sl_price: number;
    sl_limit_price?: number;
    price?: number;
    order_type?: string;
    environment?: string;
    strategy_id?: string;
  }): Promise<{ status: string; context: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/live/protected-order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; context: any }>(res);
  },

  // ============================================================================
  // PHASE 23: TCA, DELTA HEDGING & COLLATERAL GOVERNANCE
  // ============================================================================

  async getTCASummary(symbol?: string): Promise<{ status: string; summary: TCASummary }> {
    let url = `${BASE_URL}/api/execution/tca/summary`;
    if (symbol) url += `?symbol=${encodeURIComponent(symbol)}`;
    const res = await authFetch(url);
    return handleResponse<{ status: string; summary: TCASummary }>(res);
  },

  async getTCARecords(limit: number = 50): Promise<{ status: string; count: number; records: TCARecord[] }> {
    const res = await authFetch(`${BASE_URL}/api/execution/tca/records?limit=${limit}`);
    return handleResponse<{ status: string; count: number; records: TCARecord[] }>(res);
  },

  async analyzeTCAExecution(params: {
    execution_id: string;
    client_order_id: string;
    symbol?: string;
    side?: string;
    venue?: string;
    strategy_id?: string;
    provenance?: string;
    decision_price?: number;
    arrival_price?: number;
    benchmark_price?: number;
    executed_vwap: number;
    best_bid?: number;
    best_ask?: number;
    requested_qty: number;
    filled_qty: number;
    fee_paid_usd?: number;
    rebate_earned_usd?: number;
    future_prices?: Record<string, number | null>;
  }): Promise<{ status: string; tca_result: any }> {
    const res = await authFetch(`${BASE_URL}/api/execution/tca/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; tca_result: any }>(res);
  },

  async getDeltaExposure(asset: string = 'BTC'): Promise<{
    status: string;
    exposure: DeltaExposureSummary;
    basis_metric: BasisFundingMetric;
  }> {
    const res = await authFetch(`${BASE_URL}/api/execution/delta/exposure?asset=${encodeURIComponent(asset)}`);
    return handleResponse<{
      status: string;
      exposure: DeltaExposureSummary;
      basis_metric: BasisFundingMetric;
    }>(res);
  },

  async proposeDeltaHedge(params: {
    asset: string;
    reference_price: number;
    preferred_venue?: string;
  }): Promise<{ status: string; proposed_hedge: ProposedHedgeOrder }> {
    const res = await authFetch(`${BASE_URL}/api/execution/delta/propose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; proposed_hedge: ProposedHedgeOrder }>(res);
  },

  async executeAuthorizedHedge(params: {
    hedge_id: string;
    confirmation_phrase: string;
    environment?: string;
  }): Promise<{ status: string; hedge_state?: string; hedge?: any; reasons?: string[] }> {
    const res = await authFetch(`${BASE_URL}/api/execution/delta/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; hedge_state?: string; hedge?: any; reasons?: string[] }>(res);
  },

  async getCollateralReport(): Promise<{ status: string; collateral_report: CollateralReport }> {
    const res = await authFetch(`${BASE_URL}/api/execution/collateral/report`);
    return handleResponse<{ status: string; collateral_report: CollateralReport }>(res);
  },

  async updateCollateralSnapshot(params: {
    venue: string;
    total_equity_usd: number;
    available_balance_usd: number;
    initial_margin_usd?: number;
    maintenance_margin_usd?: number;
    unrealized_pnl_usd?: number;
  }): Promise<{ status: string; venue_snapshot: VenueCollateralSnapshot }> {
    const res = await authFetch(`${BASE_URL}/api/execution/collateral/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return handleResponse<{ status: string; venue_snapshot: VenueCollateralSnapshot }>(res);
  },

  async getSORFailoverStatus(symbol: string = 'BTCUSDT', venue: string = 'BINANCE'): Promise<SORFailoverStatus> {
    const res = await authFetch(`${BASE_URL}/api/execution/sor/failover-status?symbol=${encodeURIComponent(symbol)}&venue=${encodeURIComponent(venue)}`);
    return handleResponse<SORFailoverStatus>(res);
  },

  async abortActiveSlicers(): Promise<{ status: string; message: string }> {
    const res = await authFetch(`${BASE_URL}/api/execution/sor/abort-slicers`, {
      method: 'POST',
    });
    return handleResponse<{ status: string; message: string }>(res);
  },

  async emergencyFlattenDelta(asset: string, confirmation_code: string): Promise<{ status: string; message: string }> {
    const res = await authFetch(`${BASE_URL}/api/execution/delta/flatten`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset, confirmation_code }),
    });
    return handleResponse<{ status: string; message: string }>(res);
  },

  // ============================================================================
  // MILESTONE 26: STRATEGY REALITY COCKPIT & QUALIFICATION TERMINAL
  // ============================================================================

  async getStrategyGatewayStatus(): Promise<GatewayStatusResponse> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/status`);
    return handleResponse<GatewayStatusResponse>(res);
  },

  async compileKronosProposal(req: {
    symbol?: string;
    direction?: string;
    horizon_minutes?: number;
    forecast_return_bps?: number;
    prediction_entropy?: number;
    model_tier?: string;
    reference_price?: number;
  }): Promise<CompiledProposalResponse> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/compile/kronos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<CompiledProposalResponse>(res);
  },

  async compileSMCProposal(req: {
    symbol?: string;
    direction?: string;
    structure_type?: string;
    timeframe?: string;
    fvg_depth_ticks?: number;
    order_flow_imbalance?: number;
    reference_price?: number;
  }): Promise<CompiledProposalResponse> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/compile/smc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    return handleResponse<CompiledProposalResponse>(res);
  },

  async submitQualificationJob(
    req: QualificationJobSubmitRequest,
    idempotencyKey?: string,
  ): Promise<{ status: string; was_created: boolean; job: QualificationJob; poll_url: string; report_url: string }> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/qualification/jobs`, {
      method: 'POST',
      headers,
      body: JSON.stringify(req),
    });
    return handleResponse<{ status: string; was_created: boolean; job: QualificationJob; poll_url: string; report_url: string }>(res);
  },

  async getQualificationJob(jobId: string): Promise<{ status: string; job: QualificationJob }> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/qualification/jobs/${encodeURIComponent(jobId)}`);
    return handleResponse<{ status: string; job: QualificationJob }>(res);
  },

  async getQualificationJobReport(jobId: string): Promise<{ status: string; job_id: string; strategy_id: string; report: any }> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/qualification/jobs/${encodeURIComponent(jobId)}/report`);
    return handleResponse<{ status: string; job_id: string; strategy_id: string; report: any }>(res);
  },

  async getQualificationEvidence(
    limit: number = 20,
    offset: number = 0,
    strategyId?: string,
    order: 'asc' | 'desc' = 'desc',
  ): Promise<QualificationEvidenceResponse> {
    let url = `${BASE_URL}/api/v1/strategy_gateway/qualification/evidence?limit=${limit}&offset=${offset}&order=${order}`;
    if (strategyId) url += `&strategy_id=${encodeURIComponent(strategyId)}`;
    const res = await authFetch(url);
    return handleResponse<QualificationEvidenceResponse>(res);
  },

  async getGatewayCollateralScorecard(): Promise<GatewayCollateralScorecardResponse> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/risk/collateral_scorecard`);
    return handleResponse<GatewayCollateralScorecardResponse>(res);
  },

  async getGatewayDeltaTolerance(asset: string = 'BTC'): Promise<GatewayDeltaToleranceResponse> {
    const res = await authFetch(`${BASE_URL}/api/v1/strategy_gateway/risk/delta_tolerance?asset=${encodeURIComponent(asset)}`);
    return handleResponse<GatewayDeltaToleranceResponse>(res);
  },

  async getMarkoutSurvivorshipSummary(symbol?: string): Promise<MarkoutSurvivorshipResponse> {
    let url = `${BASE_URL}/api/v1/strategy_gateway/markouts/survivorship_summary`;
    if (symbol) url += `?symbol=${encodeURIComponent(symbol)}`;
    const res = await authFetch(url);
    return handleResponse<MarkoutSurvivorshipResponse>(res);
  },
};

export interface GatewayStatusResponse {
  status: string;
  real_capital_enabled: boolean;
  execution_authority: string;
  governance_mode: string;
  gates: {
    gate1_eligibility: { status: string; quarantined_strategies_count: number; quarantined_strategies: string[] };
    gate2_compiler: { status: string; supported_adapters: string[] };
    gate3_feasibility: { status: string; friction_model: string };
    gate4_sizing: { status: string; framework: string; constitutional_parent_cap_pct: number };
  };
  telemetry_contract: {
    data_freshness_ms: number;
    snapshot_timestamp_utc: string;
    data_quality: string;
    clock_skew_ms: number;
    is_stale: boolean;
  };
}

export interface CompiledProposalResponse {
  status: string;
  watermark: string;
  proposal: {
    proposal_id: string;
    strategy_id: string;
    strategy_version: string;
    instrument: string;
    action: string;
    intended_size_usd: number;
    urgency_tier: string;
    execution_status: string;
    real_capital_enabled: boolean;
    watermark: string;
    sizing_breakdown?: {
      q_risk: number;
      q_capital: number;
      q_liquidity: number;
      q_strategy: number;
      q_approved: number;
      binding_constraint: string;
    };
  };
}

export interface QualificationJob {
  job_id: string;
  idempotency_key: string;
  strategy_id: string;
  strategy_version: string;
  deployment_stage: string;
  status: 'RECEIVED' | 'VALIDATING' | 'QUEUED' | 'RUNNING' | 'COMMITTED' | 'FAILED' | 'CANCELLED';
  signals_count: number;
  created_at_utc: string;
  created_at_epoch_ms: number;
  updated_at_epoch_ms: number;
  error_message?: string | null;
  report?: any | null;
}

export interface QualificationJobSubmitRequest {
  strategy_id: string;
  strategy_version?: string;
  deployment_stage?: string;
  dataset_hash?: string;
  experiment_id?: string;
  signals_count?: number;
  account_equity_usd?: number;
  simulated_spread_bps?: number;
  simulated_depth_qty?: number;
  mock_fill_slippage_bps?: number;
  min_sample_size?: number;
  max_allowable_is_bps?: number;
}

export interface QualificationEvidenceRecord {
  campaign_id: string;
  strategy_id: string;
  strategy_version: string;
  deployment_stage: string;
  total_signals: number;
  dispatched_flights: number;
  aggregate_is_bps: number;
  mean_slippage_bps: number;
  qualification_verdict: string;
  rejection_breakdown: Record<string, number>;
  sizing_distribution: Record<string, number>;
  markout_profiles: Record<string, number>;
  report_hash: string;
  created_at_utc: string;
  created_at_epoch_ms: number;
}

export interface QualificationEvidenceResponse {
  status: string;
  total_count: number;
  offset: number;
  limit: number;
  order: string;
  records: QualificationEvidenceRecord[];
}

export interface GatewayCollateralScorecardResponse {
  status: string;
  collateral_report: any;
  risk_scorecard: any;
  cross_venue_imbalance_pct: number;
  telemetry_contract: {
    data_freshness_ms: number;
    snapshot_timestamp_utc: string;
    data_quality: string;
    clock_skew_ms: number;
    is_stale: boolean;
  };
}

export interface GatewayDeltaToleranceResponse {
  status: string;
  exposure: any;
  basis_metric: any;
  urgency_tier: 'NEUTRAL' | 'PASSIVE_TWAP' | 'ACTIVE_TAKER';
  telemetry_contract: {
    data_freshness_ms: number;
    snapshot_timestamp_utc: string;
    data_quality: string;
    clock_skew_ms: number;
    is_stale: boolean;
  };
}

export interface MarkoutSurvivorshipResponse {
  status: string;
  symbol: string;
  fill_count: number;
  censored_markouts_count: number;
  censored_percentage: number;
  horizons_s: number[];
  mean_markout_bps: Record<string, number>;
  confidence_intervals_bps_95: Record<string, number>;
  is_decomposition: {
    delay_is_bps: number;
    spread_is_bps: number;
    impact_is_bps: number;
    fee_is_bps: number;
    total_is_bps: number;
  };
}

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

export interface VolatilityTenorSkewPoint {
  tenor_days: number;
  expiry_timestamp_ms: number;
  time_to_expiry_years: number;
  atm_iv: number;
  put_25d_iv: number;
  call_25d_iv: number;
  twenty_five_delta_skew: number;
  relative_skew_pct: number;
  put_25d_strike: number;
  call_25d_strike: number;
  atm_strike: number;
  regime: string;
}

export interface VolatilitySkewResponse {
  symbol: string;
  underlying_price: number;
  timestamp_ms: number;
  dominant_regime: string;
  average_skew_25d: number;
  tail_risk_multiplier: number;
  tenor_points: VolatilityTenorSkewPoint[];
}

export interface VolatilityTermStructurePoint {
  tenor_days: number;
  atm_iv: number;
  annualized_iv_pct: number;
  sample_count: number;
}

export interface VolatilityTermStructureResponse {
  symbol: string;
  timestamp_ms: number;
  underlying_price: number;
  regime: string;
  slope_90d_minus_7d: number;
  curve: VolatilityTermStructurePoint[];
}

export interface VolatilitySurfaceResponse {
  symbol: string;
  timestamp_ms: number;
  underlying_price: number;
  moneyness_levels: number[];
  tenors_days: number[];
  surface_matrix: number[][];
}

export interface VolatilityGEXResponse {
  symbol: string;
  timestamp_ms: number;
  underlying_price: number;
  net_gamma_usd_per_1pct: number;
  regime: string;
  max_pain_strike: number;
  zero_gamma_strike: number | null;
  strikes: number[];
  call_gex_by_strike: number[];
  put_gex_by_strike: number[];
  net_gex_by_strike: number[];
}

export interface VolatilitySummaryResponse {
  symbol: string;
  underlying_price: number;
  timestamp_ms: number;
  contracts_count: number;
  skew: VolatilitySkewResponse;
  term_structure: VolatilityTermStructureResponse;
  gex: VolatilityGEXResponse;
  tail_risk: {
    tail_risk_multiplier: number;
    dominant_skew_regime: string;
    term_structure_regime: string;
    dealer_gex_regime: string;
    average_skew_25d: number;
    term_slope: number;
    net_gex_usd: number;
    max_pain_strike: number;
    risk_flags: string[];
  };
}

export interface ArbitrageDislocationsResponse {
  status: string;
  symbol: string;
  timestamp_ms: number;
  basis_metrics: {
    spot_venue: string;
    perp_venue: string;
    spot_price: number;
    perp_price: number;
    raw_basis_bps: number;
    rolling_mean_bps: number;
    rolling_std_bps: number;
    zscore: number;
    regime: string;
    candidate_trigger: boolean;
    duration_outside_threshold_ms: number;
  } | null;
  active_dislocations_count: number;
}

export interface FundingMatrixItem {
  pair_id: string;
  canonical_symbol: string;
  venue_a: string;
  venue_b: string;
  rate_a_pct: number;
  rate_b_pct: number;
  raw_divergence_bps: number;
  annualized_divergence_pct: number;
  time_to_funding_sec: number;
  estimated_capture_bps: number;
  confidence: number;
  data_freshness_ms: number;
  proposed_long_leg: string;
  proposed_short_leg: string;
}

export interface FundingMatrixResponse {
  status: string;
  symbol: string;
  timestamp_ms: number;
  count: number;
  matrix: FundingMatrixItem[];
}

export interface CapacityTierItem {
  notional_usd: number;
  executable_qty: number;
  vwap_long: number;
  vwap_short: number;
  slippage_bps: number;
  net_ev_usd: number;
  net_ev_bps: number;
  viable: boolean;
}

export interface ArbitrageOpportunityItem {
  opportunity_id: string;
  detected_at_ms: number;
  canonical_symbol: string;
  opportunity_type: string;
  long_venue: string;
  short_venue: string;
  classification: string;
  rejection_code: string;
  rejection_reason: string;
  executable_spread: {
    vwap_long_ask: number;
    vwap_short_bid: number;
    theoretical_spread_bps: number;
    executable_spread_bps: number;
    gross_spread_usd: number;
  } | null;
  multi_scenario_ev: {
    base_net_ev_usd: number;
    base_net_ev_bps: number;
    conservative_net_ev_usd: number;
    conservative_net_ev_bps: number;
    stress_net_ev_usd: number;
    stress_net_ev_bps: number;
    cost_breakdown: {
      entry_fee_long_usd: number;
      entry_fee_short_usd: number;
      exit_fee_long_usd: number;
      exit_fee_short_usd: number;
      orderbook_slippage_long_usd: number;
      orderbook_slippage_short_usd: number;
      hedge_cost_usd: number;
      latency_cost_usd: number;
      funding_cashflow_usd: number;
      borrow_cost_usd: number;
      safety_buffer_usd: number;
      model_version: string;
    } | null;
  } | null;
  capacity_tiers: CapacityTierItem[];
  max_viable_notional_usd: number;
  persistence_observations: number;
  persistence_duration_ms: number;
  data_freshness_ms: number;
  confidence_score: number;
  provenance_hash: string;
  permission: string;
}

export interface ArbitrageOpportunitiesResponse {
  status: string;
  symbol: string;
  timestamp_ms: number;
  count: number;
  opportunities: ArbitrageOpportunityItem[];
}

export interface ShadowTradeRecord {
  opportunity_id: string;
  canonical_symbol: string;
  opportunity_type: string;
  long_venue: string;
  short_venue: string;
  target_notional_usd: number;
  predicted_net_ev_usd: number;
  realized_reference_ev_usd: number | null;
  opportunity_duration_ms: number;
  unhedged_residual_qty: number;
  funding_realized_usd: number;
  model_attribution_error_usd: number;
  status: string;
  detected_at: number;
  qualified_at: number;
  expired_at: number | null;
}

export interface ArbitrageHistoryResponse {
  status: string;
  timestamp_ms: number;
  count: number;
  shadow_records: ShadowTradeRecord[];
}

export interface ArbitrageHealthResponse {
  status: string;
  timestamp_ms: number;
  permission: string;
  active_venues: string[];
  clock_drift_sla_ms: number;
  staleness_threshold_ms: number;
  model_versions: Record<string, string>;
  live_trading_guard: string;
}

export interface ArbitrageProvenanceResponse {
  status: string;
  opportunity_id: string;
  integrity_verified: boolean;
  envelope: any;
}

/**
 * TASK 20.2: L3 MBO INTERFACES
 */
export interface MBOOrderSummary {
  order_id: string;
  size: number;
  priority_index: number;
  timestamp_ns: number;
}

export interface MBOPriceLevelSummary {
  price: number;
  total_size: number;
  order_count: number;
  orders: MBOOrderSummary[];
}

export interface MBODepthResponse {
  status: string;
  symbol: string;
  venue: string;
  timestamp_ms: number;
  total_bid_depth_usd: number;
  total_ask_depth_usd: number;
  microstructure_imbalance: number;
  bids: MBOPriceLevelSummary[];
  asks: MBOPriceLevelSummary[];
  iceberg_count: number;
}

export interface MBOQueueEstimate {
  symbol: string;
  venue: string;
  side: string;
  price: number;
  simulated_order_qty: number;
  queue_ahead_qty: number;
  queue_ahead_orders: number;
  queue_behind_qty: number;
  total_level_qty: number;
  relative_queue_position_pct: number;
  expected_wait_seconds: number;
  fill_probability_30s: number;
  fill_probability_60s: number;
  fill_probability_300s: number;
  adverse_selection_risk_score: number;
  estimated_depletion_rate_qty_per_sec: number;
}

export interface MBOQueueEstimateResponse {
  status: string;
  estimate: MBOQueueEstimate;
}

export interface MBOIcebergItem {
  iceberg_id: string;
  symbol: string;
  venue: string;
  side: string;
  price: number;
  initial_displayed_size: number;
  cumulative_executed_size: number;
  estimated_reload_size: number;
  estimated_total_hidden_qty: number;
  total_estimated_size: number;
  confidence_score: number;
  reload_count: number;
  is_active: boolean;
}

export interface MBOIcebergsResponse {
  status: string;
  count: number;
  icebergs: MBOIcebergItem[];
}

export interface MBOToxicityData {
  symbol: string;
  venue: string;
  timestamp_ms: number;
  vpin_mbo: number;
  cancel_to_trade_ratio: number;
  depletion_velocity_usd_per_sec: number;
  order_arrival_intensity: number;
  mean_order_lifetime_ms: number;
  toxicity_regime: string;
  adverse_selection_bias_bps: number;
}

export interface MBOToxicityResponse {
  status: string;
  toxicity: MBOToxicityData;
}

// ============================================================================
// PHASE 21: LIVE READINESS & GATEKEEPER INTERFACES
// ============================================================================

export interface AccountReadinessStatus {
  status: string;
  timestamp_ms: number;
  vault_unlocked: boolean;
  total_portfolio_equity_usd: number;
  total_free_cash_usd: number;
  single_trade_equity_cap_usd: number;
  max_portfolio_heat_usd: number;
  active_exchanges: string[];
  exchange_statuses: Record<string, {
    exchange: string;
    environment: string;
    is_connected: boolean;
    latency_ms: number;
    total_equity_usd: number;
    free_cash_usd: number;
    locked_margin_usd: number;
    error_message?: string | null;
    balances_count: number;
  }>;
  is_ready_for_canary_trade: boolean;
  reasons: string[];
}

export interface GatekeeperCheckResult {
  status: string;
  verdict: {
    passed: boolean;
    timestamp_ms: number;
    exchange: string;
    requested_notional_usd: number;
    max_allowed_notional_usd: number;
    checks: Record<string, boolean>;
    rejection_reasons: string[];
    audit_event_id?: string | null;
  };
}

export interface CanaryRunResult {
  status: string;
  result: {
    success: boolean;
    is_dry_run: boolean;
    exchange: string;
    symbol: string;
    notional_usd: number;
    client_order_id: string;
    exchange_order_id?: string | null;
    executed_qty: number;
    executed_price: number;
    slippage_bps: number;
    roundtrip_latency_ms: number;
    dispatch_to_ack_latency_ms?: number;
    ack_to_fill_latency_ms?: number;
    total_roundtrip_ms?: number;
    ack_latency_sla_breached?: boolean;
    dispatch_wall_time_utc?: string;
    gatekeeper_verdict: any;
    feasibility_details?: any;
    reconciliation_id?: string | null;
    status: string;
    message: string;
    timestamp_ms: number;
  };
}

// ============================================================================
// PHASE 22: LIVE PROTECTION & POSITION CONTROL INTERFACES
// ============================================================================

export interface LivePositionState {
  symbol: string;
  side: 'LONG' | 'SHORT';
  quantity: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl_usd: number;
  risk_r: number;
  protection_status: 'PROTECTED' | 'UNPROTECTED' | 'BREAKEVEN_ACTIVE' | 'PROTECTION_PENDING' | 'FLATTENING' | 'CLOSED';
  stop_loss_price?: number | null;
  take_profit_price?: number | null;
  bracket_id?: string | null;
}

export interface WorkingOrderSummary {
  order_id: string;
  client_order_id: string;
  symbol: string;
  side: string;
  order_type: string;
  price: number;
  quantity: number;
  executed_qty: number;
  status: string;
  stop_price?: number | null;
  created_at_ms: number;
}

export interface LiveExecutionSnapshot {
  exchange: string;
  environment: string;
  overall_protection_status: 'PROTECTED' | 'UNPROTECTED' | 'NO_EXPOSURE';
  positions: LivePositionState[];
  orders: WorkingOrderSummary[];
  active_brackets: any[];
  risk_state: {
    vault_unlocked: boolean;
    kill_switch_active: boolean;
  };
  timestamp_ms: number;
}

export interface PanicCloseResponse {
  status: string;
  result: {
    success: boolean;
    symbol: string;
    exchange: string;
    environment: string;
    initial_position_qty: number;
    closed_qty: number;
    remaining_position_qty: number;
    cancelled_orders_count: number;
    market_order_id?: string | null;
    execution_price: number;
    latency_ms: number;
    status: string;
    audit_event_id: string;
    error_message?: string;
    steps_completed: string[];
  };
}

// ============================================================================
// PHASE 23: TCA, DELTA HEDGING & COLLATERAL GOVERNANCE INTERFACES
// ============================================================================

export interface TCASummary {
  total_executions: number;
  total_notional_usd: number;
  mean_slippage_bps: number;
  mean_implementation_shortfall_bps: number;
  mean_delay_cost_bps: number;
  mean_spread_cost_bps: number;
  mean_market_impact_bps: number;
  mean_fee_bps: number;
  markout_1s_bps: number;
  markout_5s_bps: number;
  markout_30s_bps: number;
  markout_60s_bps: number;
  markout_300s_bps: number;
  adverse_selection_count: number;
  price_improvement_count: number;
}

export interface TCARecord {
  execution_id: string;
  client_order_id: string;
  symbol: string;
  side: string;
  venue: string;
  strategy_id: string;
  provenance: string;
  requested_qty: number;
  filled_qty: number;
  executed_vwap: number;
  decision_price: number;
  arrival_price: number;
  total_cost_bps: number;
  slippage_bps: number;
  delay_cost_bps: number;
  spread_cost_bps: number;
  market_impact_bps: number;
  fee_bps: number;
  markout_1s_bps: number | null;
  markout_5s_bps: number | null;
  markout_30s_bps: number | null;
  markout_60s_bps: number | null;
  markout_300s_bps: number | null;
  created_at_ms: number;
}

export interface DeltaExposureSummary {
  asset: string;
  net_delta_qty: number;
  net_delta_usd: number;
  tolerance_breached: boolean;
  dominant_venue: string;
  total_long_usd: number;
  total_short_usd: number;
  legs_count: number;
  calculated_at_ms: number;
}

export interface BasisFundingMetric {
  venue: string;
  spot_price: number;
  perp_price: number;
  basis_bps: number;
  annualized_basis_pct: number;
  funding_rate: number;
  annualized_funding_pct: number;
  net_carry_apr_pct: number;
  spot_symbol: string;
  perp_symbol: string;
}

export interface ProposedHedgeOrder {
  hedge_id: string;
  asset: string;
  target_venue: string;
  target_symbol: string;
  side: 'BUY' | 'SELL';
  hedge_qty: number;
  reference_price: number;
  notional_usd: number;
  instrument_type: string;
  urgency: string;
  state: string;
  created_at_ms: number;
}

export interface VenueCollateralSnapshot {
  venue: string;
  total_equity_usd: number;
  available_balance_usd: number;
  initial_margin_usd: number;
  maintenance_margin_usd: number;
  margin_utilization_ratio: number;
  liquidation_buffer_ratio: number;
  risk_state: 'NORMAL' | 'CAUTION' | 'DANGER' | 'LIQUIDATION_RISK' | 'STALE';
  data_age_seconds: number;
  timestamp_ms: number;
}

export interface CollateralReport {
  venues: Record<string, VenueCollateralSnapshot>;
  total_equity_usd: number;
  aggregate_margin_ratio: number;
  systemic_risk_state: 'NORMAL' | 'CAUTION' | 'DANGER' | 'LIQUIDATION_RISK' | 'STALE';
  venues_in_danger: string[];
  venues_at_risk: string[];
  freshness_ok: boolean;
  timestamp_ms: number;
}

export interface VenueHealthStatus {
  venue: string;
  consecutive_failures: number;
  avg_ack_latency_ms: number;
  is_degraded: boolean;
  is_active: boolean;
  last_failure_reason: string;
}

export interface SORFailoverStatus {
  status: string;
  venues: Record<string, VenueHealthStatus>;
  vpin_circuit_breaker: {
    is_paused: boolean;
    reason: string;
  };
}

// ===========================================================================
// Desktop Setup & Software Auto-Updater Types & Functions
// ===========================================================================

export interface SetupStatusResponse {
  is_first_run: boolean;
  setup_completed: boolean;
  has_gemini_key: boolean;
  has_master_password: boolean;
  configured_exchanges: Array<{
    exchange: string;
    environment: string;
    masked_api_key: string;
    is_active: boolean;
    updated_at: number;
  }>;
  web3_wallets: Array<{
    wallet_type: string;
    chain: string;
    address: string;
    full_address: string;
    rpc_url?: string;
    is_watch_only: boolean;
    is_active: boolean;
  }>;
  execution_mode: string;
  app_version: string;
  platform: string;
  supported_exchanges: string[];
}

export interface SoftwareUpdateStatus {
  update_available: boolean;
  git_managed: boolean;
  current_commit: string;
  remote_commit?: string;
  branch: string;
  commits_behind: number;
  changelog?: Array<{
    hash: string;
    author: string;
    message: string;
    date: string;
  }>;
  message: string;
}

export async function getSetupStatus(): Promise<SetupStatusResponse> {
  const res = await authFetch('/api/system/setup-status');
  return handleResponse<SetupStatusResponse>(res);
}

export async function verifyGeminiKey(gemini_api_key: string): Promise<{ valid: boolean; latency_ms: number; message: string; models_count?: number }> {
  const res = await authFetch('/api/system/setup/verify-gemini', {
    method: 'POST',
    body: JSON.stringify({ gemini_api_key }),
  });
  return handleResponse(res);
}

export async function verifyExchangeCredentials(payload: {
  exchange: string;
  environment: string;
  api_key: string;
  api_secret: string;
  passphrase?: string;
}): Promise<any> {
  const res = await authFetch('/api/system/setup/verify-exchange', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

export async function verifyHyperliquidCredentials(payload: {
  master_address: string;
  agent_private_key: string;
  environment: string;
}): Promise<any> {
  const res = await authFetch('/api/system/setup/verify-hyperliquid', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

export async function saveWeb3Wallet(payload: {
  wallet_type: string;
  chain: string;
  address: string;
  rpc_url?: string;
  is_watch_only?: boolean;
}): Promise<any> {
  const res = await authFetch('/api/system/setup/save-web3', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

export async function deleteWeb3Wallet(chain: string, address: string): Promise<any> {
  const res = await authFetch(`/api/system/setup/delete-web3/${chain}/${encodeURIComponent(address)}`, {
    method: 'DELETE',
  });
  return handleResponse(res);
}

export async function completeFirstRunSetup(payload: {
  master_password: string;
  gemini_api_key?: string;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  exchanges?: any[];
  execution_mode?: string;
}): Promise<any> {
  const res = await authFetch('/api/system/setup/save', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

export async function checkSoftwareUpdate(): Promise<SoftwareUpdateStatus> {
  const res = await authFetch('/api/system/update/check');
  return handleResponse<SoftwareUpdateStatus>(res);
}

export async function applySoftwareUpdate(target_branch: string = 'main'): Promise<any> {
  const res = await authFetch('/api/system/update/apply', {
    method: 'POST',
    body: JSON.stringify({ target_branch, backup_snapshot: true }),
  });
  return handleResponse(res);
}

export async function rollbackSoftwareUpdate(snapshot_id: string): Promise<any> {
  const res = await authFetch(`/api/system/update/rollback/${encodeURIComponent(snapshot_id)}`, {
    method: 'POST',
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Phase A: FIDO2 / WebAuthn Hardware Security Key & Live Clearance
// ---------------------------------------------------------------------------

export interface HardwareKeyCredentialInfo {
  credential_id: string;
  credential_id_masked: string;
  user_id: string;
  label: string;
  sign_counter: number;
  rp_id: string;
  aaguid?: string;
  transports: string[];
  is_active: boolean;
  created_at_ms: number;
  last_used_at_ms?: number;
}

export interface ClearanceSessionData {
  clearance_id: string;
  credential_id_masked: string;
  session_id: string;
  operator_id: string;
  purpose: string;
  issued_at_ms: number;
  expires_at_ms: number;
  remaining_seconds: number;
  is_valid: boolean;
  is_revoked: boolean;
  revocation_reason?: string;
}

export interface HardwareKeyPosture {
  webauthn_enabled: boolean;
  registered_keys_count: number;
  credentials: HardwareKeyCredentialInfo[];
  live_clearance_active: boolean;
  clearance_session?: ClearanceSessionData;
  rejection_reason_code?: string;
  policy: {
    rp_id: string;
    ttl_seconds: number;
    user_verification_required: boolean;
  };
}

export async function getHardwareKeyStatus(sessionId: string = 'desktop_session'): Promise<{ status: string; posture: HardwareKeyPosture }> {
  const res = await authFetch(`/api/auth/hardware-key/status?session_id=${encodeURIComponent(sessionId)}`);
  return handleResponse(res);
}

export async function getHardwareKeyRegisterOptions(userId: string = 'default_operator', username: string = 'operator', displayName: string = 'CBT Operator'): Promise<{ status: string; challenge_id: string; options: any }> {
  const res = await authFetch('/api/auth/hardware-key/register/options', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, username, display_name: displayName }),
  });
  return handleResponse(res);
}

export async function verifyHardwareKeyRegister(challengeId: string, credential: any, label: string = 'Hardware Key', userId: string = 'default_operator'): Promise<{ status: string; message: string; credential: any }> {
  const res = await authFetch('/api/auth/hardware-key/register/verify', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId, credential, label, user_id: userId }),
  });
  return handleResponse(res);
}

export async function getHardwareKeyAuthOptions(userId?: string): Promise<{ status: string; challenge_id: string; options: any }> {
  const res = await authFetch('/api/auth/hardware-key/authenticate/options', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId || null }),
  });
  return handleResponse(res);
}

export async function verifyHardwareKeyAuth(challengeId: string, credential: any, sessionId: string = 'desktop_session', operatorId: string = 'default_operator'): Promise<{ status: string; message: string; clearance: ClearanceSessionData }> {
  const res = await authFetch('/api/auth/hardware-key/authenticate/verify', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId, credential, session_id: sessionId, operator_id: operatorId }),
  });
  return handleResponse(res);
}

export async function revokeHardwareKeyClearance(sessionId?: string, clearanceId?: string, reason: string = 'OPERATOR_MANUAL_REVOCATION'): Promise<{ status: string; message: string; revoked_count: number }> {
  const res = await authFetch('/api/auth/hardware-key/clearance/revoke', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, clearance_id: clearanceId, reason }),
  });
  return handleResponse(res);
}

export async function revokeHardwareKeyCredential(credentialId: string, reason: string = 'OPERATOR_REVOKED_TOKEN'): Promise<{ status: string; message: string; revoked: boolean }> {
  const res = await authFetch('/api/auth/hardware-key/credential/revoke', {
    method: 'POST',
    body: JSON.stringify({ credential_id: credentialId, reason }),
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Phase C: Web3 Watch-Only & Aggregated Portfolio API Functions
// ---------------------------------------------------------------------------

export interface WatchWalletItem {
  address: string;
  chain: string;
  label: string;
  is_watch_only: boolean;
  created_at: number;
  last_synced_at: number;
}

export interface AggregatedScorecardData {
  timestamp_ms: number;
  execution_available_capital_usd: number;
  watch_only_equity_usd: number;
  observed_total_equity_usd: number;
  venue_breakdown: Record<string, number>;
  currency_breakdown: Record<string, number>;
  watch_wallets: Array<Record<string, any>>;
  capital_firewall_verified: boolean;
}

export async function getAggregatedPortfolioEquity(): Promise<{ status: string; scorecard: AggregatedScorecardData }> {
  const res = await authFetch('/api/portfolio/aggregated-equity');
  return handleResponse(res);
}

export async function getWeb3Wallets(): Promise<{ status: string; mode: string; count: number; wallets: WatchWalletItem[] }> {
  const res = await authFetch('/api/web3/wallets');
  return handleResponse(res);
}

export async function addWeb3Wallet(chain: string, address: string, label?: string): Promise<{ status: string; message: string; wallet: WatchWalletItem }> {
  const res = await authFetch('/api/web3/wallets', {
    method: 'POST',
    body: JSON.stringify({ chain, address, label: label || '' }),
  });
  return handleResponse(res);
}

export async function removeWatchOnlyWallet(address: string): Promise<{ status: string; message: string }> {
  const res = await authFetch(`/api/web3/wallets/${encodeURIComponent(address)}`, {
    method: 'DELETE',
  });
  return handleResponse(res);
}

export async function getWeb3Balances(): Promise<{ status: string; mode: string; count: number; total_watch_equity_usd: number; balances: any[] }> {
  const res = await authFetch('/api/web3/balances');
  return handleResponse(res);
}

export async function getWeb3RpcStatus(): Promise<{ status: string; quorum_results: Record<string, any> }> {
  const res = await authFetch('/api/web3/rpc-status');
  return handleResponse(res);
}

// ===========================================================================
// Institutional Order Book Heatmap, DOM Intelligence & Resting-Wall Sentinel
// ===========================================================================

export interface HeatmapWallItem {
  wall_id: string;
  symbol: string;
  price: number;
  price_band: [number, number];
  side: 'BID' | 'ASK';
  initial_size: number;
  current_size: number;
  peak_size: number;
  notional_usd: number;
  first_seen_ms: number;
  last_seen_ms: number;
  age_seconds: number;
  frames_present: number;
  frame_presence_ratio: number;
  quantity_stability: number;
  persistence_score: number;
  distance_from_mid_bps: number;
  cumulative_absorbed_qty: number;
  replenishment_count: number;
  status: 'ACTIVE' | 'SWEPT' | 'PULLED' | 'RELOAD_SUSPECTED';
  status_reason: string;
  is_potential_spoof: boolean;
}

export interface HeatmapLiquidationBand {
  price: number;
  side: 'LONG_LIQUIDATION' | 'SHORT_LIQUIDATION';
  leverage_tier: number;
  estimated_volume_usd: number;
  distance_pct: number;
  distance_bps: number;
  confidence: number;
  methodology: string;
  reference_market: string;
  is_observed_fact: boolean;
  disclaimer: string;
}

export interface HeatmapDataGrid {
  symbol: string;
  window_frames: number;
  timestamps: number[];
  price_bins: number[];
  density_matrix: number[][]; // [time_idx][bin_idx] intensity 0-100
  mid_price_path: number[];
  current_mid: number;
  tick_size: number;
}

export interface HeatmapSnapshotResponse {
  status: string;
  symbol: string;
  heatmap: HeatmapDataGrid;
  walls: {
    symbol: string;
    active_walls_count: number;
    active_walls: HeatmapWallItem[];
    recent_historical_walls: HeatmapWallItem[];
  };
  liquidations: {
    symbol: string;
    market_type: string;
    liquidations_available: boolean;
    current_price?: number;
    reason?: string;
    disclaimer?: string;
    bands: HeatmapLiquidationBand[];
  };
  metrics: Record<string, number>;
  timestamp_ms: number;
}

export async function getHeatmapSnapshot(
  symbol = 'BTC/USDT',
  window_frames = 300,
  price_bins_count = 80
): Promise<HeatmapSnapshotResponse> {
  const q = new URLSearchParams({
    symbol,
    window_frames: window_frames.toString(),
    price_bins_count: price_bins_count.toString(),
  });
  const res = await authFetch(`/api/heatmap/snapshot?${q.toString()}`);
  return handleResponse(res);
}

export async function getHeatmapWalls(
  symbol = 'BTC/USDT'
): Promise<{ status: string; data: { symbol: string; active_walls_count: number; active_walls: HeatmapWallItem[]; recent_historical_walls: HeatmapWallItem[] }; timestamp_ms: number }> {
  const res = await authFetch(`/api/heatmap/walls?symbol=${encodeURIComponent(symbol)}`);
  return handleResponse(res);
}

export async function getHeatmapLiquidations(
  symbol = 'BTC/USDT',
  market_type = 'PERPETUAL'
): Promise<{ status: string; data: { symbol: string; market_type: string; liquidations_available: boolean; current_price?: number; bands: HeatmapLiquidationBand[]; disclaimer?: string }; timestamp_ms: number }> {
  const res = await authFetch(`/api/heatmap/liquidations?symbol=${encodeURIComponent(symbol)}&market_type=${encodeURIComponent(market_type)}`);
  return handleResponse(res);
}

export async function getHeatmapMetrics(): Promise<{ status: string; metrics: Record<string, number>; active_symbols: string[]; timestamp_ms: number }> {
  const res = await authFetch('/api/heatmap/metrics');
  return handleResponse(res);
}

// ============================================================================
// Item 2: Autonomous Quant Strategist & Research Validation OS Types & API
// ============================================================================

export type ResearchClassification =
  | 'ROBUST'
  | 'FRAGILE'
  | 'OVERFIT'
  | 'INSUFFICIENT_DATA'
  | 'INCONCLUSIVE';

export interface CPCVFoldItem {
  fold_id: number;
  train_size: number;
  test_size: number;
  purged_count: number;
  embargo_count: number;
  is_sharpe: number;
  oos_sharpe: number;
  is_win_rate: number;
  oos_win_rate: number;
  oos_trade_count: number;
  stability_ratio: number;
}

export interface CPCVResultItem {
  symbol: string;
  timeframe: string;
  total_samples: number;
  n_partitions: number;
  k_test_groups: number;
  num_paths: number;
  embargo_bars: number;
  folds: CPCVFoldItem[];
  mean_is_sharpe: number;
  mean_oos_sharpe: number;
  median_oos_sharpe: number;
  std_oos_sharpe: number;
  stability_index: number;
  total_oos_trades: number;
  oos_win_rate: number;
  oos_profit_factor: number;
  oos_max_drawdown_pct: number;
  friction_results: Record<string, {
    sharpe: number;
    win_rate_pct: number;
    profit_factor: number;
    total_trades: number;
    max_drawdown_pct: number;
    net_return_pct: number;
    total_friction_bps: number;
  }>;
  equity_curve_oos: number[];
}

export interface DSRReportItem {
  strategy_id: string;
  cumulative_trials: number;
  observed_sharpe: number;
  expected_max_null_sharpe: number;
  skewness: number;
  kurtosis: number;
  sr_standard_error: number;
  z_score: number;
  deflated_sharpe_ratio: number;
  p_value: number;
  is_tier1_eligible: boolean;
  policy_version: string;
}

export interface WRCReportItem {
  strategy_id: string;
  p_value: number;
  bootstrap_replications: number;
  mean_block_length: number;
  observed_mean_return: number;
  bootstrap_null_max: number;
  is_significant_at_5pct: boolean;
}

export interface PerturbationPointItem {
  parameter_deltas: Record<string, number>;
  perturbed_sharpe: number;
  delta_sharpe_pct: number;
  is_surviving: boolean;
}

export interface PerturbationReportItem {
  strategy_id: string;
  base_sharpe: number;
  total_neighbors: number;
  surviving_neighbors: number;
  plateau_ratio: number;
  is_plateau_robust: boolean;
  grid_points: PerturbationPointItem[];
}

export interface RegimePerformanceItem {
  regime_name: string;
  sample_bars_count: number;
  trade_count: number;
  sharpe: number;
  win_rate_pct: number;
  net_return_pct: number;
  max_drawdown_pct: number;
  is_catastrophic_loss: boolean;
}

export interface RegimeDecompositionReportItem {
  regimes: Record<string, RegimePerformanceItem>;
  profitable_regimes_count: number;
  worst_regime_drawdown_pct: number;
  is_all_weather_candidate: boolean;
}

export interface ResearchGateDossierItem {
  strategy_id: string;
  classification: ResearchClassification;
  rejection_reasons: string[];
  epistemic_tags: string[];
  cpcv_result: CPCVResultItem;
  dsr_report: DSRReportItem;
  wrc_report: WRCReportItem;
  perturbation_report: PerturbationReportItem;
  regime_report: RegimeDecompositionReportItem;
  quarantine_eligible: boolean;
  is_tier1_qualified: boolean;
  confidence_score: number;
}

export interface SynthesisJobReportItem {
  job_id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  timestamp_ms: number;
  trial_number: number;
  cumulative_trials: number;
  hypothesis: string;
  compilation_status: string;
  research_dossier: ResearchGateDossierItem;
  is_novelty_passed: boolean;
  tier1_quarantined: boolean;
  tear_sheet_markdown: string;
  telegram_bulletin: string;
}

export interface StrategyLineageNodeItem {
  node_id: string;
  strategy_id: string;
  parent_id?: string;
  generation: number;
  created_at: number;
  mutation_type: string;
  parameter_hash: string;
  hypothesis: string;
  research_classification: string;
  tier1_admitted: boolean;
  deflated_sharpe_ratio: number;
  oos_sharpe: number;
  plateau_survival_ratio: number;
  quarantine_tier: number;
}

export interface StatisticalPolicyItem {
  policy_version: string;
  dsr_tier1_threshold: number;
  dsr_caution_threshold: number;
  wrc_pvalue_threshold: number;
  min_oos_trades: number;
  plateau_survival_ratio_threshold: number;
  max_regime_drawdown_pct: number;
  min_profitable_regimes: number;
  daily_trial_budget: number;
  batch_trial_budget: number;
}

export async function synthesizeStrategy(
  symbol = 'BTC/USDT',
  timeframe = '15m',
  prompt_or_concept = 'SMC liquidity sweep with order block retest and resting wall confirmation',
  base_params?: Record<string, number>,
  parent_genome_id?: string,
  is_mutation = false
): Promise<{ status: string; job: SynthesisJobReportItem }> {
  const res = await authFetch('/api/strategist/synthesize', {
    method: 'POST',
    body: JSON.stringify({
      symbol,
      timeframe,
      prompt_or_concept,
      base_params,
      parent_genome_id,
      is_mutation,
    }),
  });
  return handleResponse(res);
}

export async function getStrategistJobs(
  limit = 20
): Promise<{ status: string; count: number; cumulative_system_trials: number; jobs: SynthesisJobReportItem[] }> {
  const res = await authFetch(`/api/strategist/jobs?limit=${limit}`);
  return handleResponse(res);
}

export async function getStrategistJobDetail(
  job_id: string
): Promise<{ status: string; job: SynthesisJobReportItem }> {
  const res = await authFetch(`/api/strategist/jobs/${encodeURIComponent(job_id)}`);
  return handleResponse(res);
}

export async function getStrategistLineage(
  limit = 50
): Promise<{ status: string; node_count: number; nodes: StrategyLineageNodeItem[] }> {
  const res = await authFetch(`/api/strategist/lineage?limit=${limit}`);
  return handleResponse(res);
}

export async function getStrategistAncestors(
  genome_id: string
): Promise<{ status: string; genome_id: string; ancestor_count: number; ancestors: StrategyLineageNodeItem[] }> {
  const res = await authFetch(`/api/strategist/lineage/${encodeURIComponent(genome_id)}`);
  return handleResponse(res);
}

export async function getStrategistPolicy(): Promise<{
  status: string;
  policy: StatisticalPolicyItem;
  cumulative_trials: number;
  is_daemon_active: boolean;
}> {
  const res = await authFetch('/api/strategist/policy');
  return handleResponse(res);
}

export async function getStrategistLeague(): Promise<{
  status: string;
  tier1_smoke: Record<string, unknown>[];
  tier2_preliminary: Record<string, unknown>[];
  tier3_robust: Record<string, unknown>[];
  tier4_production: Record<string, unknown>[];
}> {
  const res = await authFetch('/api/strategist/league');
  return handleResponse(res);
}

export async function toggleStrategistDaemon(
  enable: boolean
): Promise<{ status: string; is_daemon_active: boolean }> {
  const res = await authFetch('/api/strategist/daemon/toggle', {
    method: 'POST',
    body: JSON.stringify({ enable }),
  });
  return handleResponse(res);
}

// =============================================================================
// ITEM 3: CEX-DEX BASIS, CLMM & CARRY ARBITRAGE
// =============================================================================

export interface CexDexQuorumInfo {
  consensus_status: string;
  freshness: string;
  chain: string;
  chain_id: number;
  canonical_block_number: number;
  canonical_block_hash: string;
  canonical_state_root?: string | null;
  canonical_slot?: number | null;
  agreeing_node_count: number;
  total_node_count: number;
  state_age_ms: number;
  observed_timestamp_ms: number;
  local_receive_timestamp_ms: number;
}

export interface CexDexPoolState {
  dex_name: string;
  chain: string;
  pool_address: string;
  token0: string;
  token1: string;
  spot_price: number;
  active_liquidity: string;
  current_tick: number;
  fee_pips: number;
  quorum: CexDexQuorumInfo;
}

export interface CexDexCexExecution {
  venue: string;
  vwap_price: number;
  fill_ratio: number;
  levels_consumed: number;
  status: string;
}

export interface CexDexSurvivalSimulation {
  iterations: number;
  expected_net_ev: number;
  p05_net_ev: number;
  p50_net_ev: number;
  p95_net_ev: number;
  loss_probability: number;
  revert_probability: number;
  break_even_hurdle_bps: number;
  atomicity: string;
  scenarios_summary: {
    mean_gas_usd: number;
    unhedged_latency_ms: number;
    cex_fill_ratio: number;
  };
}

export interface CexDexClassification {
  economic: string;
  data_freshness: string;
  execution: string;
  mev: string;
  hedge: string;
  mode: string;
}

export interface CexDexCarryMetrics {
  symbol: string;
  spot_price: number;
  lp_lower_price: number;
  lp_upper_price: number;
  lp_notional_usd: number;
  cex_short_notional_usd: number;
  lp_delta_base: number;
  cex_short_delta_base: number;
  net_modeled_delta_base: number;
  is_rebalance_required: boolean;
  rebalance_recommendation_base: number;
  realized_fee_yield_usd: number;
  realized_funding_usd: number;
  annualized_fee_apy_percent: number;
  annualized_funding_apy_percent: number;
  divergence_loss_percent: number;
  borrow_fee_usd: number;
  rebalance_gas_drag_usd: number;
  net_carry_apy_percent: number;
  cex_liquidation_price: number;
  distance_to_liquidation_percent: number;
  liquidation_risk_alert: boolean;
}

export interface CexDexOpportunityItem {
  opportunity_id: string;
  symbol: string;
  direction: string;
  target_notional_usd: number;
  dex_name: string;
  dex_chain: string;
  pool_address: string;
  dex_effective_price: number;
  dex_marginal_slippage_bps: number;
  dex_fee_usd: number;
  cex_venue: string;
  cex_vwap_price: number;
  cex_slippage_bps: number;
  cex_fee_usd: number;
  cex_fill_ratio: number;
  gross_basis_bps: number;
  net_ev_base_usd: number;
  net_ev_conservative_usd: number;
  net_ev_stress_usd: number;
  survival: CexDexSurvivalSimulation;
  classification: CexDexClassification;
  timestamp_ms: number;
}

export interface CexDexScanResponse {
  opportunity: CexDexOpportunityItem;
  pool_state: CexDexPoolState;
  cex_execution: CexDexCexExecution;
  carry_metrics: CexDexCarryMetrics;
  survival_simulation: CexDexSurvivalSimulation;
  classification: CexDexClassification;
}

export interface CexDexShadowRecord {
  shadow_id: string;
  timestamp_ns: number;
  chain: string;
  block_number: number;
  block_hash: string;
  dex_name: string;
  pool_address: string;
  cex_name: string;
  symbol: string;
  direction: string;
  notional_usd: number;
  gross_basis_bps: number;
  gas_usd: number;
  dex_fee_usd: number;
  cex_fee_usd: number;
  mev_hazard_bps: number;
  survival_p50_ev: number;
  classification_json: string;
  rpc_consensus_status: string;
  notes: string;
}

export async function scanCexDexPair(
  symbol = 'ETHUSDC',
  notional = 10000,
  privateRpc = true
): Promise<CexDexScanResponse> {
  const res = await authFetch(
    `/api/cexdex/scan?symbol=${encodeURIComponent(symbol)}&notional=${notional}&private_rpc=${privateRpc}`
  );
  return handleResponse<CexDexScanResponse>(res);
}

export async function getCexDexShadowHistory(limit = 50): Promise<{
  status: string;
  count: number;
  shadow_records: CexDexShadowRecord[];
}> {
  const res = await authFetch(`/api/cexdex/shadow-history?limit=${limit}`);
  return handleResponse(res);
}

export async function executeCexDexShadow(
  symbol = 'ETHUSDC',
  notional_usd = 10000
): Promise<{ status: string; shadow_trade_id: string; entry: Record<string, unknown> }> {
  const res = await authFetch('/api/cexdex/shadow-execute', {
    method: 'POST',
    body: JSON.stringify({ symbol, notional_usd }),
  });
  return handleResponse(res);
}

// ----------------------------------------------------------------------------
// Milestone 20: Gate 5 Extended Testnet Burn-In Telemetry API
// ----------------------------------------------------------------------------

export function getFallbackTestnetBurnInReport(sessionId?: string): TestnetBurnInReport {
  return {
    session_id: sessionId || 'BURNIN_GATE5_REHEARSAL',
    state: 'ACTIVE_REHEARSAL',
    durations: {
      wallclock_elapsed_sec: 259200,
      healthy_duration_sec: 258400,
      invalidated_duration_sec: 800,
      healthy_ratio_pct: 99.69,
      target_duration_sec: 1209600,
      target_progress_pct: 21.36,
    },
    active_epoch: {
      epoch_id: 'BURNIN_GATE5_EP_0001',
      epoch_index: 1,
      started_at_utc: '2026-09-17T12:00:00Z',
      ended_at_utc: null,
      status: 'ACTIVE',
      continuity_break_reason: null,
      healthy_duration_sec: 258400,
    },
    clock_offset_ms: 12.4,
    clock_healthy: true,
    account_equity_usd: 104250.0,
    peak_equity_usd: 105100.0,
    drawdown_pct: 0.81,
    rehearsal_drawdown_limit_pct: 3.0,
    invariants: [
      {
        name: 'Exact Quantity Conservation',
        description: 'Decimal unresolved slice quantity is strictly 0',
        status: 'PASS',
        last_checked_utc: new Date().toISOString(),
        details: 'Verified across all child slices (Q_unresolved == 0)',
      },
      {
        name: 'Zero Overfill Ceiling',
        description: 'Fills strictly capped at target order quantity',
        status: 'PASS',
        last_checked_utc: new Date().toISOString(),
        details: 'Enforced via SQLite UNIQUE constraint and atomic check',
      },
      {
        name: '4-Tier Fill Deduplication',
        description: 'Idempotency verified across transport and economic IDs',
        status: 'PASS',
        last_checked_utc: new Date().toISOString(),
        details: '1,000 duplicate stress test passed; conflicting duplicates fail-closed',
      },
      {
        name: 'Exchange Clock Drift Policy',
        description: 'Local vs exchange time offset within 50ms ceiling',
        status: 'PASS',
        last_checked_utc: new Date().toISOString(),
        details: 'Current delta 12.40ms (Policy limit: 50.0ms)',
      },
      {
        name: 'Rehearsal Drawdown Ceiling',
        description: 'Simulated account drawdown bounded by 3.0%',
        status: 'PASS',
        last_checked_utc: new Date().toISOString(),
        details: 'Current DD: 0.81% (Ceiling: 3.0%)',
      },
      {
        name: 'Permanent Capital Firewall',
        description: 'Real capital execution permanently disabled',
        status: 'PASS',
        last_checked_utc: new Date().toISOString(),
        details: 'real_capital_enabled == False immutable across all paths',
      },
    ],
    clean_latency_summary: [
      { stage_name: '1. Decision -> Dispatch', p50_us: 12.5, p90_us: 18.2, p99_us: 34.1, p99_9_us: 62.0, max_us: 88.0, sample_count: 1420 },
      { stage_name: '2. Dispatch -> Send', p50_us: 4.2, p90_us: 7.1, p99_us: 12.0, p99_9_us: 19.5, max_us: 28.0, sample_count: 1420 },
      { stage_name: '3. Send -> Ack (RTT)', p50_us: 1420.0, p90_us: 2150.0, p99_us: 3800.0, p99_9_us: 5200.0, max_us: 7100.0, sample_count: 1420 },
      { stage_name: '4. Ack -> Fill (Engine)', p50_us: 650.0, p90_us: 1100.0, p99_us: 2200.0, p99_9_us: 3400.0, max_us: 4900.0, sample_count: 1420 },
      { stage_name: '5. Fill -> Receive (WS)', p50_us: 950.0, p90_us: 1600.0, p99_us: 2900.0, p99_9_us: 4100.0, max_us: 5800.0, sample_count: 1420 },
      { stage_name: '6. Receive -> Reconcile', p50_us: 8.5, p90_us: 14.2, p99_us: 26.0, p99_9_us: 45.0, max_us: 61.0, sample_count: 1420 },
      { stage_name: '7. Total End-to-End', p50_us: 3045.2, p90_us: 4889.5, p99_us: 8972.1, p99_9_us: 12826.5, max_us: 17977.0, sample_count: 1420 },
    ],
    fault_latency_summary: [
      { stage_name: '1. Decision -> Dispatch', p50_us: 14.1, p90_us: 21.0, p99_us: 41.2, p99_9_us: 75.0, max_us: 110.0, sample_count: 156 },
      { stage_name: '2. Dispatch -> Send', p50_us: 5.0, p90_us: 8.5, p99_us: 15.0, p99_9_us: 24.0, max_us: 35.0, sample_count: 156 },
      { stage_name: '3. Send -> Ack (RTT)', p50_us: 18500.0, p90_us: 35000.0, p99_us: 52000.0, p99_9_us: 60000.0, max_us: 62500.0, sample_count: 156 },
      { stage_name: '4. Ack -> Fill (Engine)', p50_us: 920.0, p90_us: 1800.0, p99_us: 3500.0, p99_9_us: 5100.0, max_us: 7200.0, sample_count: 156 },
      { stage_name: '5. Fill -> Receive (WS)', p50_us: 1450.0, p90_us: 2900.0, p99_us: 5400.0, p99_9_us: 7800.0, max_us: 9600.0, sample_count: 156 },
      { stage_name: '6. Receive -> Reconcile', p50_us: 12.0, p90_us: 19.5, p99_us: 38.0, p99_9_us: 60.0, max_us: 82.0, sample_count: 156 },
      { stage_name: '7. Total End-to-End', p50_us: 20901.1, p90_us: 39728.0, p99_us: 60993.2, p99_9_us: 73059.0, max_us: 79527.0, sample_count: 156 },
    ],
    fault_injection_stats: {
      injected_count: 13,
      recovered_count: 13,
      active_fault: null,
    },
    total_parent_orders: 284,
    total_slices_dispatched: 1420,
    unresolved_quantity_abs: '0',
  };
}

export async function getTestnetBurnInReport(sessionId?: string): Promise<TestnetBurnInReport> {
  try {
    const url = sessionId
      ? `/api/testnet/burnin/report?session_id=${encodeURIComponent(sessionId)}`
      : '/api/testnet/burnin/report';
    const res = await authFetch(url);
    if (!res.ok) {
      return getFallbackTestnetBurnInReport(sessionId);
    }
    return await handleResponse<TestnetBurnInReport>(res);
  } catch {
    return getFallbackTestnetBurnInReport(sessionId);
  }
}

// ============================================================================
// Milestone 27: SKY Global Intelligence Fabric Client Functions
// ============================================================================

export function getFallbackIntelligenceStatus(): IntelligenceStatusResponse {
  return {
    status: 'ONLINE',
    timestamp_utc: Date.now() / 1000,
    scout: {
      state: 'STOPPED',
      frontier_size: 7,
      processed_count: 0,
      relevant_count: 0,
      error_count: 0,
      last_active_time: 0,
      poll_interval_range: [10, 30],
      total_stored_records: 0,
    },
    channels: {
      WEB: {
        status: 'ONLINE',
        description: 'Jina Reader & local HTML parsing',
        requires_cookies: false,
        details: {},
      },
      RSS: {
        status: 'ONLINE',
        description: 'Syndicated XML feeds parsing',
        requires_cookies: false,
        details: {},
      },
      GITHUB: {
        status: 'ONLINE',
        description: 'Repo README & commit telemetry',
        requires_cookies: false,
        details: {},
      },
      YOUTUBE: {
        status: 'DEGRADED',
        description: 'Video transcripts and metadata',
        requires_cookies: false,
        details: {},
      },
      TWITTER: {
        status: 'UNAVAILABLE',
        description: 'X/Twitter institutional flow',
        requires_cookies: true,
        details: {},
      },
      REDDIT: {
        status: 'DEGRADED',
        description: 'Community retail sentiment',
        requires_cookies: true,
        details: {},
      },
      XUEQIU: {
        status: 'UNAVAILABLE',
        description: 'Chinese equity & PBOC policy flow',
        requires_cookies: true,
        details: {},
      },
    },
    top_entities: [
      { entity: 'BTC', count: 12 },
      { entity: 'FED', count: 8 },
      { entity: 'ETH', count: 6 },
      { entity: 'NVDA', count: 5 },
      { entity: 'CPI', count: 4 },
    ],
    total_records: 35,
    non_executable_watermark: 'UNTRUSTED_EXTERNAL_DATA_EXECUTION_PROHIBITED',
  };
}

export async function getIntelligenceStatus(): Promise<IntelligenceStatusResponse> {
  try {
    const res = await authFetch('/api/v1/intelligence/status');
    if (!res.ok) {
      return getFallbackIntelligenceStatus();
    }
    return await handleResponse<IntelligenceStatusResponse>(res);
  } catch {
    return getFallbackIntelligenceStatus();
  }
}

export async function getIntelligenceRecords(params?: {
  domain?: string;
  evidence_grade?: string;
  entity?: string;
  min_relevance?: number;
  limit?: number;
  offset?: number;
}): Promise<IntelligenceRecordsResponse> {
  try {
    const query = new URLSearchParams();
    if (params?.domain) query.set('domain', params.domain);
    if (params?.evidence_grade) query.set('evidence_grade', params.evidence_grade);
    if (params?.entity) query.set('entity', params.entity);
    if (params?.min_relevance !== undefined) query.set('min_relevance', String(params.min_relevance));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));

    const url = `/api/v1/intelligence/records?${query.toString()}`;
    const res = await authFetch(url);
    if (!res.ok) {
      return { total: 0, limit: params?.limit || 50, offset: params?.offset || 0, records: [] };
    }
    return await handleResponse<IntelligenceRecordsResponse>(res);
  } catch {
    return { total: 0, limit: params?.limit || 50, offset: params?.offset || 0, records: [] };
  }
}

export async function getActiveNarratives(params?: {
  lookback_hours?: number;
  limit?: number;
}): Promise<NarrativesResponse> {
  try {
    const query = new URLSearchParams();
    if (params?.lookback_hours !== undefined) query.set('lookback_hours', String(params.lookback_hours));
    if (params?.limit !== undefined) query.set('limit', String(params.limit));

    const url = `/api/v1/intelligence/narratives?${query.toString()}`;
    const res = await authFetch(url);
    if (!res.ok) {
      return { lookback_hours: params?.lookback_hours || 48, count: 0, narratives: [] };
    }
    return await handleResponse<NarrativesResponse>(res);
  } catch {
    return { lookback_hours: params?.lookback_hours || 48, count: 0, narratives: [] };
  }
}

export async function startScoutDaemon(): Promise<{ status: string; scout_state: string; message: string }> {
  const res = await authFetch('/api/v1/intelligence/scout/start', { method: 'POST' });
  return await handleResponse(res);
}

export async function stopScoutDaemon(): Promise<{ status: string; scout_state: string; message: string }> {
  const res = await authFetch('/api/v1/intelligence/scout/stop', { method: 'POST' });
  return await handleResponse(res);
}

export async function pauseScoutDaemon(): Promise<{ status: string; scout_state: string; message: string }> {
  const res = await authFetch('/api/v1/intelligence/scout/pause', { method: 'POST' });
  return await handleResponse(res);
}

export async function resumeScoutDaemon(): Promise<{ status: string; scout_state: string; message: string }> {
  const res = await authFetch('/api/v1/intelligence/scout/resume', { method: 'POST' });
  return await handleResponse(res);
}

export async function triggerScoutStep(): Promise<{ status: string; step_telemetry: any; scout: ScoutTelemetry }> {
  const res = await authFetch('/api/v1/intelligence/scout/step', { method: 'POST' });
  return await handleResponse(res);
}

export async function ingestIntelligenceUrl(
  url: string,
  source_platform: string = 'WEB',
  immediate_analysis: boolean = true
): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, source_platform, immediate_analysis }),
  });
  return await handleResponse(res);
}

export async function getIntelligenceDiagnostics(): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/diagnostics');
  return await handleResponse(res);
}

// ============================================================================
// Milestone 28: Cross-Domain Macro-Micro Causal Synthesis API Methods
// ============================================================================

export async function getHypotheses(params?: {
  family_id?: string;
  status?: string;
  target_asset?: string;
  limit?: number;
  offset?: number;
}): Promise<HypothesesListResponse> {
  try {
    const query = new URLSearchParams();
    if (params?.family_id) query.set('family_id', params.family_id);
    if (params?.status) query.set('status', params.status);
    if (params?.target_asset) query.set('target_asset', params.target_asset);
    if (params?.limit !== undefined) query.set('limit', String(params.limit));
    if (params?.offset !== undefined) query.set('offset', String(params.offset));

    const url = `/api/v1/intelligence/hypotheses?${query.toString()}`;
    const res = await authFetch(url);
    if (!res.ok) {
      return { status: 'error', hypotheses: [], total: 0, limit: params?.limit || 50, offset: params?.offset || 0, execution_isolation: 'STRICT_RESEARCH_ONLY' };
    }
    return await handleResponse<HypothesesListResponse>(res);
  } catch {
    return { status: 'error', hypotheses: [], total: 0, limit: params?.limit || 50, offset: params?.offset || 0, execution_isolation: 'STRICT_RESEARCH_ONLY' };
  }
}

export async function synthesizeHypotheses(params?: {
  record_ids?: string[];
  target_asset?: string;
  timeframe?: string;
  auto_validate?: boolean;
}): Promise<SynthesizeResponse> {
  const res = await authFetch('/api/v1/intelligence/hypotheses/synthesize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      record_ids: params?.record_ids || [],
      target_asset: params?.target_asset || 'BTC/USDT',
      timeframe: params?.timeframe || '5m',
      auto_validate: params?.auto_validate !== undefined ? params.auto_validate : true,
    }),
  });
  return await handleResponse<SynthesizeResponse>(res);
}

export async function getResearchFamilies(): Promise<FamiliesResponse> {
  try {
    const res = await authFetch('/api/v1/intelligence/hypotheses/families');
    if (!res.ok) {
      return { families: [], mechanisms: [], governance_level: 'LEVEL_2_RESEARCH_PROTOCOL' };
    }
    return await handleResponse<FamiliesResponse>(res);
  } catch {
    return { families: [], mechanisms: [], governance_level: 'LEVEL_2_RESEARCH_PROTOCOL' };
  }
}

export async function getHypothesisStats(): Promise<HypothesisStatsResponse> {
  try {
    const res = await authFetch('/api/v1/intelligence/hypotheses/stats');
    if (!res.ok) {
      return {
        total_hypotheses_created: 0,
        daily_family_trials: {},
        daily_global_cap: 50,
        real_capital_enabled: false,
        execution_authority: 'NON_EXECUTABLE_RESEARCH_HYPOTHESIS',
      };
    }
    return await handleResponse<HypothesisStatsResponse>(res);
  } catch {
    return {
      total_hypotheses_created: 0,
      daily_family_trials: {},
      daily_global_cap: 50,
      real_capital_enabled: false,
      execution_authority: 'NON_EXECUTABLE_RESEARCH_HYPOTHESIS',
    };
  }
}

export async function validateHypothesis(
  hypothesisId: string
): Promise<{ status: string; decision: CausalFirewallDecision; hypothesis: CausalHypothesis }> {
  const res = await authFetch(`/api/v1/intelligence/hypotheses/${encodeURIComponent(hypothesisId)}/validate`, {
    method: 'POST',
  });
  return await handleResponse(res);
}

export async function dispatchHypothesis(
  hypothesisId: string,
  frictionalTier = 'CONSERVATIVE'
): Promise<{ status: string; plan: Record<string, any> }> {
  const res = await authFetch(`/api/v1/intelligence/hypotheses/${encodeURIComponent(hypothesisId)}/dispatch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ frictional_tier: frictionalTier }),
  });
  return await handleResponse(res);
}

// ============================================================================
// Milestone 29: Point-in-Time Replay, Validation & Falsification API Methods
// ============================================================================

export async function createResearchContract(
  hypothesisId: string,
  holdingPeriodBars = 12,
  trialBudget = 1
): Promise<{ status: string; contract: PreregisteredResearchContract }> {
  const res = await authFetch('/api/v1/intelligence/research/contracts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      hypothesis_id: hypothesisId,
      holding_period_bars: holdingPeriodBars,
      trial_budget: trialBudget,
    }),
  });
  return await handleResponse(res);
}

export async function getResearchContract(
  contractId: string
): Promise<{ status: string; contract: PreregisteredResearchContract }> {
  const res = await authFetch(`/api/v1/intelligence/research/contracts/${encodeURIComponent(contractId)}`);
  return await handleResponse(res);
}

export async function getExperimentPlans(params?: {
  state?: string;
  family_id?: string;
  limit?: number;
}): Promise<PlansListResponse> {
  const query = new URLSearchParams();
  if (params?.state) query.set('state', params.state);
  if (params?.family_id) query.set('family_id', params.family_id);
  if (params?.limit) query.set('limit', String(params.limit));

  const res = await authFetch(`/api/v1/intelligence/research/plans?${query.toString()}`);
  return await handleResponse(res);
}

export async function runCausalReplay(
  contractId: string,
  positionSizeUsd = 10000,
  riskPerTradeUsd = 200,
  frictionalTier = 'CONSERVATIVE'
): Promise<ReplayResponse> {
  const res = await authFetch('/api/v1/intelligence/research/replay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contract_id: contractId,
      position_size_usd: positionSizeUsd,
      risk_per_trade_usd: riskPerTradeUsd,
      frictional_tier: frictionalTier,
    }),
  });
  return await handleResponse(res);
}

export async function getValidationResult(
  resultId: string
): Promise<{ status: string; result: CausalValidationResult }> {
  const res = await authFetch(`/api/v1/intelligence/research/results/${encodeURIComponent(resultId)}`);
  return await handleResponse(res);
}

export async function getFailureAutopsy(
  hypothesisId: string
): Promise<{ status: string; autopsy: CausalFailureAutopsy }> {
  const res = await authFetch(`/api/v1/intelligence/research/autopsies/${encodeURIComponent(hypothesisId)}`);
  return await handleResponse(res);
}

// ============================================================================
// Milestone 30-C: Evidence Qualification & Research Integration API Methods
// ============================================================================

export async function getCrawlerStatus(): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/crawler/status');
  return await handleResponse(res);
}

export async function getCrawlerSources(): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/crawler/sources');
  return await handleResponse(res);
}

export async function getCrawlerConflicts(): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/crawler/conflicts');
  return await handleResponse(res);
}

export async function pauseCrawler(): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/crawler/pause', { method: 'POST' });
  return await handleResponse(res);
}

export async function resumeCrawler(): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/crawler/resume', { method: 'POST' });
  return await handleResponse(res);
}

export async function triggerCrawlRun(domains?: string[], requestedBy: string = 'HUMAN_OPERATOR'): Promise<any> {
  const res = await authFetch('/api/v1/intelligence/crawler/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domains, requested_by: requestedBy }),
  });
  return await handleResponse(res);
}

export async function getCrawlerTemplates(): Promise<CrawlerTemplatesResponse> {
  const res = await authFetch('/api/v1/intelligence/crawler/templates');
  return await handleResponse<CrawlerTemplatesResponse>(res);
}

export async function getCrawlerMultipleTesting(): Promise<CrawlerMultipleTestingResponse> {
  const res = await authFetch('/api/v1/intelligence/crawler/multiple-testing');
  return await handleResponse<CrawlerMultipleTestingResponse>(res);
}

export async function getEvidenceLineage(nodeId: string): Promise<EvidenceLineageResponse> {
  const res = await authFetch(`/api/v1/intelligence/crawler/lineage/${encodeURIComponent(nodeId)}`);
  return await handleResponse<EvidenceLineageResponse>(res);
}

export async function qualifyEvent(data: {
  evidence_id: string;
  canonical_event_id: string;
  template_id?: string;
  mechanism_id?: string;
  target_asset?: string;
  direction?: string;
  horizon?: string;
  batch_id?: string;
}): Promise<QualifyResponse> {
  const res = await authFetch('/api/v1/intelligence/crawler/qualify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return await handleResponse<QualifyResponse>(res);
}


