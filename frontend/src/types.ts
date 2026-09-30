export type OHLCVCandle = [
  number, // timestamp
  number, // open
  number, // high
  number, // low
  number, // close
  number  // volume
];

export type SupportedTimeframe = '1m' | '3m' | '5m' | '15m' | '1h' | '4h' | '1d';

export interface CandlesApiResponse {
  symbol: string;
  timeframe: SupportedTimeframe;
  limit: number;
  candles: OHLCVCandle[];
}

export interface IndicatorPoint {
  timestamp: number;
  value: number;
}

export interface MTFApiResponse {
  symbol: string;
  timeframe: SupportedTimeframe;
  indicators: {
    ema?: IndicatorPoint[];
    rsi?: IndicatorPoint[];
  };
}

export interface FVGItem {
  type: 'bullish' | 'bearish';
  price_zone: [number, number];
  mitigated: boolean;
  timestamp?: number;
}

export interface OrderBlockItem {
  type: 'bullish' | 'bearish';
  price_zone: [number, number];
  timestamp: number;
  mitigated?: boolean;
}

export interface SetupSuggestion {
  type: 'LONG' | 'SHORT';
  bias: string;
  trigger: string;
  entry: number;
  stopLoss: number;
  takeProfit: number;
  riskRewardRatio: number;
}

export interface ScanApiResponse {
  symbol: string;
  timeframe: SupportedTimeframe;
  fvg: FVGItem[];
  order_blocks: OrderBlockItem[];
  setup_suggestions: SetupSuggestion[];
  stats: {
    totalCandles: number;
    bullishFVGs: number;
    bearishFVGs: number;
    unmitigatedFVGs: number;
    mitigatedFVGs: number;
    bullishOBs: number;
    bearishOBs: number;
    lastPrice: number;
    highPrice: number;
    lowPrice: number;
    trend: string;
  };
}

export interface PaperTrade {
  id: number | string;
  symbol: string;
  side: 'BUY' | 'SELL';
  entryPrice: number;
  sl: number;
  tp: number;
  size: number;
  status: 'OPEN' | 'CLOSED' | 'CANCELLED';
  currentPrice?: number;
  pnl?: number;
  exitPrice?: number;
  breakevenTriggered?: boolean;
  createdAt: string;
  closedAt?: string;
}

export interface PaperPositionsResponse {
  positions: PaperTrade[];
  count: number;
}

export interface PaperDeskOverviewResponse {
  summary: {
    startingCapital?: number;
    settledCash?: number;
    virtualEquity?: number;
    accountBalance: number;
    totalRealizedPnl: number;
    totalUnrealizedPnl: number;
    winRatePct: number;
    profitFactor: number;
    openPositionsCount: number;
    closedPositionsCount: number;
    activeRiskPct?: number;
    maxRiskCapPct: number;
    circuitBreakerStatus: string;
    maxOpenPositions?: number;
    openSlotsRemaining?: number;
    gatingReason?: string;
  };
  current: Array<{
    id: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    size: number;
    entryPrice: number;
    currentPrice: number;
    sl: number;
    tp: number;
    pnlUsd: number;
    pnlPct: number;
    status: string;
    breakevenTriggered: boolean;
    trailingStop?: number | null;
    openedAt?: number | string;
    notionalUsd?: number;
    effectiveLeverage?: number;
    capitalAtRiskUsd?: number;
    riskOfAccountPct?: number;
    riskRewardRatio?: string;
    horizon?: 'SCALP' | 'DAY' | 'SWING';
    agentManager?: string;
    strategyName?: string;
    thesis?: string;
  }>;
  past: Array<{
    id: string;
    symbol: string;
    side: 'BUY' | 'SELL';
    size: number;
    entryPrice: number;
    exitPrice: number;
    sl: number;
    tp: number;
    realizedPnlUsd: number;
    realizedPnlPct: number;
    openedAt?: number | string;
    closedAt?: number | string;
    autopsyCategory: string;
    autopsyCause: string;
    autopsyRecommendation: string;
  }>;
  futureQueue: Array<{
    queueId: string;
    symbol: string;
    direction: 'LONG' | 'SHORT';
    setupName: string;
    archetype: string;
    triggerCondition: string;
    plannedEntry: number;
    stopLoss: number;
    tp1: number;
    tp2: number;
    tp3: number;
    riskReward: string;
    confluenceScore: number;
    kellyPct: number;
    queueStatus: string;
    statusNote: string;
  }>;
  tradingPlans: Array<{
    symbol: string;
    bias: string;
    pdh: number;
    pdl: number;
    fvgZone: string;
    orderBlock: string;
    bullPath: string;
    bearPath: string;
    note: string;
    macroAlignment?: 'CONFLUENT' | 'NEUTRAL' | 'CAUTION_DAMPENED';
    macroRegime?: string;
    macroDriver?: string;
    riskMultiplier?: number;
    currentPrice?: number;
    generatedAt?: number;
  }>;
}

export interface RiskConfig {
  accountBalance: number;
  maxDrawdown: number;
  maxOpenTrades: number;
  dailyLossLimit: number;
  maxRiskPerTrade: number;
}

export interface HalfKellySizingResponse {
  symbol: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  risk_reward_ratio: number;
  raw_kelly_fraction: number;
  half_kelly_fraction: number;
  bayesian_shrunk_fraction: number;
  recommended_risk_pct: number;
  position_size_usd: number;
  position_size_base: number;
  max_dollar_loss: number;
  invalidation_distance_pct: number;
  hurdle_passed: boolean;
  narrative: string;
}

export interface DeskBriefResponse {
  symbol: string;
  timeframe: string;
  executiveSummary: string;
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  keyLevels: {
    support: number[];
    resistance: number[];
    invalidation?: number;
  };
  riskAssessment: string;
  metrics: {
    lastPrice: number;
    ema?: number;
    rsi?: number;
    trend: string;
  };
  timestamp: number;
}

export interface DeskAskResponse {
  query: string;
  answer: string;
  timestamp: number;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
}

export interface VWAPData {
  timestamp: number;
  vwap: number;
  upper_band_1sigma: number;
  lower_band_1sigma: number;
  upper_band_2sigma: number;
  lower_band_2sigma: number;
  std_dev: number;
  deviation_sigmas: number;
  is_above_vwap: boolean;
  is_extended_overbought: boolean;
  is_extended_oversold: boolean;
  is_reclaiming: boolean;
  mean_reversion_prob: number;
  anchored_vwap?: number | null;
}

export interface SKYSetupData {
  setup_type: string;
  direction: 'LONG' | 'SHORT' | 'WATCH' | 'NO_TRADE';
  symbol: string;
  trigger_timeframe: string;
  timestamp: number;
  entry_price: number;
  invalidation_sl: number;
  target_tp: number;
  risk_reward_ratio: number;
  displacement_score: number;
  regime: string;
  historical_expectancy_r: number;
  historical_win_rate: number;
  historical_sample_size: number;
  confluence_score: number;
  is_qualified: boolean;
  rejection_reasons: string[];
  explanation_text: string;
}

export interface SKYIntelligenceResponse {
  decision: 'LONG' | 'SHORT' | 'WATCH' | 'NO_TRADE';
  symbol: string;
  timeframe: string;
  timestamp: number;
  setup_qualified?: SKYSetupData | null;
  net_ev_r: number;
  kelly_fraction: number;
  suggested_position_size_usd: number;
  risk_gate_passed: boolean;
  explanation_dossier: {
    regime: string;
    mtf_alignment?: string;
    volatility?: string;
    displacement_score?: number;
    active_pools?: number;
    active_fvgs?: number;
    candidate_obs?: number;
    vwap?: {
      vwap: number;
      deviation_sigmas: number;
      mean_reversion_prob: number;
    };
    explanation?: string;
    [key: string]: unknown;
  };
  no_trade_reason?: string | null;
  vwap: VWAPData;
  setups: SKYSetupData[];
}

export interface CVDSeriesData {
  symbol: string;
  timestamp: number;
  current_cvd: number;
  cvd_delta: number;
  absorption_detected: boolean;
  absorption_type: string;
  absorption_score: number;
  volume_ratio: number;
  divergence_score: number;
  narrative: string;
}

export interface OBIData {
  symbol: string;
  timestamp: number;
  obi_score: number;
  top_level_imbalance: number;
  depth_weighted_imbalance: number;
  flow_toxicity_vpin: number;
  bid_depth_total_usd: number;
  ask_depth_total_usd: number;
  micro_price_shift: number;
  regime: string;
  narrative: string;
}

export interface InstitutionalAlphaResponse {
  symbol: string;
  timeframe: string;
  timestamp: number;
  decision: 'LONG' | 'SHORT' | 'WATCH' | 'NO_TRADE';
  institutional_composite_score: number;
  lead_lag: {
    signals: Array<{
      driver_asset: string;
      target_asset: string;
      shock_zscore: number;
      direction: string;
      expected_lead_window_mins: string;
      confidence: number;
      timestamp: number;
      rationale: string;
    }>;
    dxy_price: number;
    us10y_yield: number;
    has_macro_shock: boolean;
  };
  cvd_absorption: CVDSeriesData;
  orderbook_imbalance: OBIData;
  oi_funding_squeeze: {
    open_interest_usd: number;
    oi_change_1h_pct: number;
    funding_rate_annualized_pct: number;
    funding_zscore: number;
    perpetual_basis_bps: number;
    squeeze_risk: string;
    squeeze_velocity_score: number;
    narrative: string;
  };
  judas_sweep: {
    symbol: string;
    session_name: string;
    timestamp: number;
    sweep_direction: string;
    asian_high: number;
    asian_low: number;
    swept_level: number;
    rejection_wick_pct: number;
    confidence: number;
    invalidation_level: number;
    target_level: number;
    narrative: string;
  };
  vwap_multisigma: {
    vwap: number;
    upper_1s: number;
    lower_1s: number;
    upper_2s: number;
    lower_2s: number;
    upper_3s: number;
    lower_3s: number;
    deviation_sigmas: number;
    mean_reversion_prob: number;
    is_reclaiming: boolean;
  };
  fractal_harmonics: {
    symbol: string;
    macro_tier: { timeframe: string; bias: string; structure_type: string; trend_strength: number };
    context_tier: { timeframe: string; bias: string; structure_type: string; trend_strength: number };
    micro_tier: { timeframe: string; bias: string; structure_type: string; trend_strength: number };
    harmonic_confluence_score: number;
    is_aligned: boolean;
    dominant_direction: string;
    narrative: string;
  };
  half_kelly_sizing: {
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    risk_reward_ratio: number;
    raw_kelly_fraction: number;
    half_kelly_fraction: number;
    bayesian_shrunk_fraction: number;
    recommended_risk_pct: number;
    position_size_usd: number;
    position_size_base: number;
    max_dollar_loss: number;
    invalidation_distance_pct: number;
    hurdle_passed: boolean;
    narrative: string;
  };
  execution_dossier: {
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    risk_reward_ratio: number;
    suggested_risk_usd: number;
    suggested_size_base: number;
  };
  hurdle_passed: boolean;
  narrative: string;
}

export interface AgentArgument {
  agent_name: string;
  stance: 'LONG' | 'SHORT' | 'NO_TRADE';
  confidence: number;
  core_premises: string[];
  risk_factors_highlighted: string[];
  verdict_summary: string;
}

export interface CouncilDecision {
  symbol: string;
  timestamp: number;
  final_decision: 'LONG' | 'SHORT' | 'NO_TRADE';
  consensus_confidence: number;
  bull_argument: AgentArgument;
  bear_argument: AgentArgument;
  skeptic_argument: AgentArgument;
  no_trade_probability: number;
  primary_execution_thesis: string;
  invalidation_criteria: string;
  net_ev_r?: number;
  uncertainty_score?: number;
}

export interface LiquidationCluster {
  price_level: number;
  estimated_volume_usd: number;
  cluster_type: 'LONG_LIQUIDATION' | 'SHORT_LIQUIDATION';
  cluster_label?: string;
  distance_pct: number;
  leverage_tier?: string;
  confidence_score?: number;
}

export interface WhaleRadarData {
  symbol: string;
  timestamp: number;
  reference_price?: number;
  model_source?: string;
  top_100_whale_flow_24h_usd: number;
  exchange_net_inflow_btc: number;
  exchange_flow_sentiment: 'HEAVY_ACCUMULATION' | 'MODERATE_INFLOW' | 'HEAVY_DISTRIBUTION' | 'NEUTRAL';
  cold_storage_outflows_usd: number;
  liquidation_clusters: LiquidationCluster[];
  cvd_delta: number;
  narrative: string;
}

export interface TiltStatus {
  is_shield_locked: boolean;
  consecutive_losses: number;
  lockout_remaining_minutes: number;
  tilt_triggers_detected: string[];
  allowed_to_execute: boolean;
  guidance_message: string;
  emotional_state_score: number; // 0 (calm) to 100 (extreme tilt)
}

export interface MonteCarloStressReport {
  num_simulations: number;
  probability_of_ruin: number;
  p50_max_drawdown_pct: number;
  p95_max_drawdown_pct: number;
  p99_max_drawdown_pct: number;
  is_safe: boolean;
  covid_shock_survival_score: number;
  ftx_shock_survival_score: number;
  summary: string;
}

export interface LeadSignal {
  driver_asset: string;
  target_asset: string;
  shock_zscore: number;
  direction: 'BULLISH_LEAD' | 'BEARISH_LEAD';
  expected_lead_window_mins: string;
  confidence: number;
  timestamp: number;
  rationale: string;
}

export interface HedgeRecommendation {
  hedge_required: boolean;
  target_symbol: string;
  hedge_direction: 'SHORT' | 'LONG' | 'NONE';
  hedge_size_units: number;
  hedge_notional_usd: number;
  trigger_shock: string;
  target_net_delta_pct: number;
  rationale: string;
  current_portfolio_delta_usd: number;
}

export interface UniversalAssetDossier {
  symbol: string;
  timestamp: number;
  current_price: number;
  composite_health_score: number;
  macro_bias: string;
  pillar_1_institutional_flows: {
    etf_net_inflow_24h_usd: number;
    etf_net_inflow_7d_usd: number;
    corporate_treasury_bias: string;
    sovereign_central_bank_net_tons_quarterly: number;
    sentiment_tier: string;
    flow_momentum_score: number;
    z_score: number;
  };
  pillar_2_derivatives_options: {
    funding_rate_annualized_pct: number;
    funding_state: string;
    open_interest_delta_24h_pct: number;
    options_max_pain_strike: number;
    net_dealer_gex: string;
    twenty_five_delta_skew_pct: number;
    primary_liquidation_pools: {
      long_liquidation_cluster: number;
      short_squeeze_target: number;
    };
    derivatives_bias: string;
    z_score: number;
  };
  pillar_3_valuation_cost_basis: {
    sth_realized_price: number;
    lth_realized_price: number;
    mvrv_z_score: number;
    production_cost_floor: number;
    cost_basis_health: string;
    valuation_regime: string;
    z_score: number;
  };
  pillar_4_stablecoin_velocity: {
    ssr_ratio: number;
    ssr_oscillator_bias: string;
    net_minting_velocity_24h_usd: number;
    usdt_market_cap_usd: number;
    usdc_market_cap_usd: number;
    dry_powder_liquidity_state: string;
    z_score: number;
  };
  pillar_5_seasonality_cyclical_dna: {
    day_of_week: string;
    month_name: string;
    historical_day_win_rate_pct: number;
    current_month_historical_return: string;
    halving_cycle_phase: string;
    days_post_halving: number;
    real_yield_pct: number;
    cyclical_bias: string;
    z_score: number;
  };
  pillar_6_macro_liquidity_beta: {
    dxy_correlation_30d: number;
    us10y_yield_pct: number;
    us10y_yield_delta_24h_bps: number;
    global_m2_status: string;
    global_m2_expansion_rate_pct: number;
    geopolitical_risk_index_score: number;
    macro_regime: string;
    z_score: number;
  };
  pillar_7_volatility_profile: {
    squeeze_state: string;
    squeeze_intensity_score: number;
    daily_vpoc: number;
    weekly_vpoc: number;
    value_area_high: number;
    value_area_low: number;
    volatility_regime: string;
    z_score: number;
  };
  pillar_8_physical_supply_shock: {
    exchange_reserve_delta_24h: string;
    exchange_net_flow_units: number;
    comex_registered_vault_delta_pct: number;
    shanghai_gold_exchange_premium_usd: number;
    supply_illiquidity_trend: string;
    supply_shock_state: string;
    z_score: number;
  };
  pillar_z_scores: number[];
  actionable_quant_verdict: string;
}

// ==============================================================================
// UNIVERSAL RESEARCH INGESTION & 4-VAULT TYPES
// ==============================================================================

export type ResearchSourceType = 'YOUTUBE' | 'GITHUB' | 'PDF' | 'REEL' | 'ARTICLE' | 'NOTES' | 'CODE' | 'DATASET' | 'TRADINGVIEW';
export type ResearchIngestMode = 'ANALYZE' | 'RESEARCH' | 'SAVE_KNOWLEDGE' | 'AUTO';

export interface ResearchProvenanceItem {
  knowledge_id: string;
  source_type: ResearchSourceType;
  source_uri: string;
  title: string;
  author_creator: string;
  ingested_at: number;
  raw_content_preview: string;
  confidence_score: number;
  status: 'PROCESSING' | 'ANALYZED' | 'CANDIDATE' | 'VALIDATED' | 'REJECTED';
  summary?: string;
  raw_excerpt?: string;
  facts_count?: number;
  hypotheses_count?: number;
  confidence?: number;
  chapter_breakdown?: string[];
  file_metadata?: {
    book_title?: string;
    author_creator?: string;
    isbn?: string;
    edition?: string;
    is_scanned?: boolean;
    ocr_provider?: string;
    total_pages?: number;
    pages_processed?: number;
  };
}

export interface KnowledgeItem {
  id: string;
  knowledge_id: string;
  category: string;
  concept_title: string;
  structured_explanation: string;
  tags: string[];
  created_at: number;
}

export interface StrategyCandidateItem {
  candidate_id: string;
  knowledge_id: string;
  strategy_name: string;
  hypothesis: string;
  entry_rules: Record<string, any>;
  exit_rules: Record<string, any>;
  parameter_bounds: Record<string, any>;
  timeframe: string;
  required_indicators: string[];
  validation_stage: 'UNTESTED' | 'BACKTESTING' | 'WALK_FORWARD' | 'PAPER_TEST' | 'DATA_INSUFFICIENT' | 'REJECTED' | 'PROMOTED';
  backtest_expectancy?: number;
  backtest_sharpe?: number;
  backtest_win_rate?: number;
  created_at: number;
}

export interface EvidenceItem {
  evidence_id: string;
  knowledge_id: string;
  claim_statement: string;
  verdict: 'SUPPORTED' | 'MIXED' | 'REJECTED';
  sample_size: number;
  statistical_p_value: number;
  evidence_details: Record<string, any>;
  created_at: number;
}

export interface RejectedClaimItem {
  rejected_id: string;
  knowledge_id: string;
  rejected_claim: string;
  failure_reason: string;
  historical_occurrences_tested: number;
  rejection_autopsy: string;
  created_at: number;
}

export interface ResearchVaultsResponse {
  counts: {
    knowledge_count: number;
    candidates_count: number;
    evidence_count: number;
    rejected_count: number;
    inbox_total: number;
  };
  knowledge: KnowledgeItem[];
  candidates: StrategyCandidateItem[];
  evidence: EvidenceItem[];
  rejected: RejectedClaimItem[];
}

export interface MacroCausalChain {
  cause: string;
  mechanism: string;
  market_impact: string;
  crypto_consequence: string;
  time_horizon: string;
}

export interface MacroAssetImpact {
  asset: string;
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'VOLATILE';
  sentiment_score: number;
  rationale: string;
  invalidation_level?: number | null;
}

export interface MacroEconomicCatalyst {
  event_name: string;
  expected_impact: string;
  urgency: 'HIGH' | 'MEDIUM' | 'LOW';
  invalidation_notes: string;
}

export interface MacroRegimeState {
  regime_name: string;
  monetary_stance: 'HAWKISH' | 'DOVISH' | 'NEUTRAL' | 'PIVOTING';
  inflation_trajectory: 'COOLING' | 'STICKY' | 'ACCELERATING';
  liquidity_cycle: 'EXPANDING' | 'CONTRACTING' | 'NEUTRAL';
  growth_outlook: 'EXPANSION' | 'SLOWDOWN' | 'STAGFLATION' | 'RECESSION_RISK';
  primary_driver: string;
}

export interface MacroComprehensionResult {
  source_title: string;
  speaker_author: string;
  source_worldview: string;
  executive_macro_thesis: string;
  macro_regime: MacroRegimeState;
  causal_chains: MacroCausalChain[];
  asset_matrix: Record<string, MacroAssetImpact>;
  catalysts: MacroEconomicCatalyst[];
  epistemic_facts: string[];
  hypotheses_claims: string[];
  hype_quarantined: string[];
  trade_planning_implications: {
    btc_bias: string;
    eth_bias: string;
    macro_risk_factor: string;
    kelly_multiplier: number;
    key_invalidation_trigger: string;
    planning_summary: string;
  };
  analyzed_at_ms?: number;
  engine_provider?: string;
}

export interface DynamicTradingPlan {
  symbol: string;
  bias: string;
  currentPrice: number;
  pdh: number;
  pdl: number;
  fvgZone: string;
  orderBlock: string;
  bullPath: string;
  bearPath: string;
  macroAlignment: 'CONFLUENT' | 'NEUTRAL' | 'CAUTION_DAMPENED';
  macroRegime: string;
  macroDriver: string;
  riskMultiplier: number;
  note: string;
  generatedAt: number;
}

export interface ResearchIngestResult {
  knowledge_id: string;
  source_id?: string;
  mode: ResearchIngestMode;
  provenance: ResearchProvenanceItem;
  executive_summary?: string;
  chapter_breakdown?: string[];
  file_metadata?: Record<string, any>;
  macro_analysis?: MacroComprehensionResult | null;
  dynamic_trading_plans?: DynamicTradingPlan[] | null;
  epistemic_counts?: {
    facts?: number;
    hypotheses?: number;
    rules?: number;
    contradictions?: number;
  };
  summary: {
    concepts_saved: number;
    candidates_queued: number;
    evidence_saved: number;
    rejected_archived: number;
    comprehension_score: number;
  };
  concepts: KnowledgeItem[];
  strategy_candidates: StrategyCandidateItem[];
  evidence: EvidenceItem[];
  rejected: RejectedClaimItem[];
  claims?: ClaimNodeItem[];
  verdict_message: string;
}

// ==============================================================================
// 6-NODE KNOWLEDGE GRAPH & HYPOTHESIS TYPES (10/10 ARCHITECTURE)
// ==============================================================================

export interface SourceNodeItem {
  source_id: string;
  source_type: string;
  source_uri: string;
  title: string;
  author_creator: string;
  original_worldview: string;
  ingested_at: number;
  raw_content_preview: string;
}

export interface ClaimNodeItem {
  claim_id: string;
  source_id: string;
  original_claim_verbatim: string;
  source_worldview: string;
  subject_concept: string;
  relationship_direction: string;
  object_domain: string;
  evidence_type: string;
  epistemic_status: 'UNVERIFIED' | 'HYPOTHESIZED' | 'EMPIRICALLY_TESTED' | 'REFUTED';
  confidence_score: number;
  timestamp_start?: string | null;
  timestamp_end?: string | null;
  timestamp_start_sec?: number | null;
  timestamp_end_sec?: number | null;
  video_url?: string | null;
  author_creator?: string | null;
  hype_detected?: boolean;
  hype_markers?: string[];
  book_title?: string | null;
  book_isbn?: string | null;
  book_edition?: string | null;
  chapter_title?: string | null;
  section_title?: string | null;
  page_number?: number | null;
  paragraph_index?: number | null;
  pdf_evidence_type?: string | null;
  applicability_domain?: string | null;
  created_at: number;
}

export interface ConceptNodeItem {
  concept_id: string;
  title: string;
  domain: string;
  normalized_description: string;
  tags: string[];
  created_at: number;
}

export interface VariableNodeItem {
  variable_id: string;
  name: string;
  category: string;
  observable_symbol: string;
  timeframe: string;
}

export interface ObservationNodeItem {
  observation_id: string;
  source_id: string;
  observation_text: string;
  period_context: string;
  observed_variables: string[];
  created_at: number;
}

export interface GraphEdgeItem {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relationship_type: string;
  edge_nature: 'SAME_DOMAIN' | 'CROSS_DOMAIN' | 'CONTRADICTION';
  strength_weight: number;
  empirical_status: 'UNTESTED' | 'TESTING' | 'SUPPORTED' | 'REFUTED';
  created_at: number;
}

export interface HypothesisNodeItem {
  hypothesis_id: string;
  claim_id?: string;
  title: string;
  null_hypothesis: string;
  alt_hypothesis: string;
  independent_variable: string;
  dependent_variable: string;
  target_symbol: string;
  test_method: string;
  control_variables: string[];
  validation_status: 'QUEUED' | 'TESTING' | 'SUPPORTED' | 'REJECTED' | 'INCONCLUSIVE';
  p_value?: number;
  effect_size?: number;
  test_result_summary?: string;
  created_at: number;
}

export interface CrossDomainDiscoveryItem {
  discovery_id: string;
  source_claim_id: string;
  source_worldview: string;
  premise: string;
  cross_domain_candidate: string;
  target_variable: string;
  target_symbol: string;
  status: 'UNTESTED' | 'HYPOTHESIS_FORMULATED';
  proposed_hypothesis: string;
}

export interface DiscoveryGraphResponse {
  nodes: {
    sources: SourceNodeItem[];
    claims: ClaimNodeItem[];
    concepts: ConceptNodeItem[];
    variables: VariableNodeItem[];
    observations: ObservationNodeItem[];
  };
  edges: GraphEdgeItem[];
  hypotheses: HypothesisNodeItem[];
  discoveries: CrossDomainDiscoveryItem[];
  counts: {
    sources_count: number;
    claims_count: number;
    concepts_count: number;
    variables_count: number;
    observations_count: number;
    edges_count: number;
    hypotheses_count: number;
  };
}

export interface ResearchTelegramShareRequest {
  knowledge_id: string;
  title: string;
  author_creator?: string;
  source_type?: string;
  executive_summary: string;
  chapter_breakdown?: string[];
  epistemic_counts?: {
    facts?: number;
    hypotheses?: number;
    rules?: number;
    contradictions?: number;
  };
  candidate_summary?: string;
  chat_id?: string;
}

export interface ResearchTelegramShareResponse {
  status: 'SENT' | 'QUEUED_LOCAL' | 'FAILED';
  configured: boolean;
  message: string;
  dispatched_text?: string;
}

// Phase 19: Cloud KMS / HSM Enclave & Execution Telemetry Types

export interface KMSEnclaveStatus {
  status: string;
  kms_enabled: boolean;
  provider: 'MOCK' | 'MOCK_HSM' | 'AWS_KMS' | 'GCP_KMS' | 'DISABLED';
  key_id: string;
  envelope_version: number;
  zeroization_guarantee: boolean;
  kill_switch_active: boolean;
  timestamp_ms: number;
}

export interface SORBenchmarkMetric {
  name: string;
  iterations: number;
  mean_us: number;
  median_us: number;
  p90_us: number;
  p95_us: number;
  p99_us: number;
  min_us: number;
  max_us: number;
  ops_per_sec: number;
  sla_target_us: number;
  sla_passed: boolean;
}

export interface SORBenchmarkSuite {
  timestamp_ms: number;
  iterations_per_test: number;
  overall_sla_passed: boolean;
  benchmarks: {
    depth_ladder_walk_20_levels?: SORBenchmarkMetric;
    almgren_chriss_slicer_20_intervals?: SORBenchmarkMetric;
    sor_multi_venue_optimal_route?: SORBenchmarkMetric;
    [key: string]: SORBenchmarkMetric | undefined;
  };
}

export interface WSReconciliationTelemetry {
  status: string;
  total_messages_received: number;
  total_fills_processed: number;
  total_fills_recorded: number;
  total_duplicates_filtered: number;
  buffered_events_count: number;
  max_buffer_size: number;
}

export interface WSNormalizedFill {
  exchange: string;
  client_order_id: string;
  exchange_order_id: string;
  execution_id: string;
  symbol: string;
  side: string;
  relationship_direction: string;
  object_domain: string;
  evidence_type: string;
  epistemic_status: 'UNVERIFIED' | 'HYPOTHESIZED' | 'EMPIRICALLY_TESTED' | 'REFUTED';
  confidence_score: number;
  timestamp_start?: string | null;
  timestamp_end?: string | null;
  timestamp_start_sec?: number | null;
  timestamp_end_sec?: number | null;
  video_url?: string | null;
  author_creator?: string | null;
  hype_detected?: boolean;
  hype_markers?: string[];
  book_title?: string | null;
  book_isbn?: string | null;
  book_edition?: string | null;
  chapter_title?: string | null;
  section_title?: string | null;
  page_number?: number | null;
  paragraph_index?: number | null;
  pdf_evidence_type?: string | null;
  applicability_domain?: string | null;
  created_at: number;
}

export interface ConceptNodeItem {
  concept_id: string;
  title: string;
  domain: string;
  normalized_description: string;
  tags: string[];
  created_at: number;
}

export interface VariableNodeItem {
  variable_id: string;
  name: string;
  category: string;
  observable_symbol: string;
  timeframe: string;
}

export interface ObservationNodeItem {
  observation_id: string;
  source_id: string;
  observation_text: string;
  period_context: string;
  observed_variables: string[];
  created_at: number;
}

export interface GraphEdgeItem {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relationship_type: string;
  edge_nature: 'SAME_DOMAIN' | 'CROSS_DOMAIN' | 'CONTRADICTION';
  strength_weight: number;
  empirical_status: 'UNTESTED' | 'TESTING' | 'SUPPORTED' | 'REFUTED';
  created_at: number;
}

export interface HypothesisNodeItem {
  hypothesis_id: string;
  claim_id?: string;
  title: string;
  null_hypothesis: string;
  alt_hypothesis: string;
  independent_variable: string;
  dependent_variable: string;
  target_symbol: string;
  test_method: string;
  control_variables: string[];
  validation_status: 'QUEUED' | 'TESTING' | 'SUPPORTED' | 'REJECTED' | 'INCONCLUSIVE';
  p_value?: number;
  effect_size?: number;
  test_result_summary?: string;
  created_at: number;
}

export interface CrossDomainDiscoveryItem {
  discovery_id: string;
  source_claim_id: string;
  source_worldview: string;
  premise: string;
  cross_domain_candidate: string;
  target_variable: string;
  target_symbol: string;
  status: 'UNTESTED' | 'HYPOTHESIS_FORMULATED';
  proposed_hypothesis: string;
}

export interface DiscoveryGraphResponse {
  nodes: {
    sources: SourceNodeItem[];
    claims: ClaimNodeItem[];
    concepts: ConceptNodeItem[];
    variables: VariableNodeItem[];
    observations: ObservationNodeItem[];
  };
  edges: GraphEdgeItem[];
  hypotheses: HypothesisNodeItem[];
  discoveries: CrossDomainDiscoveryItem[];
  counts: {
    sources_count: number;
    claims_count: number;
    concepts_count: number;
    variables_count: number;
    observations_count: number;
    edges_count: number;
    hypotheses_count: number;
  };
}

export interface ResearchTelegramShareRequest {
  knowledge_id: string;
  title: string;
  author_creator?: string;
  source_type?: string;
  executive_summary: string;
  chapter_breakdown?: string[];
  epistemic_counts?: {
    facts?: number;
    hypotheses?: number;
    rules?: number;
    contradictions?: number;
  };
  candidate_summary?: string;
  chat_id?: string;
}

export interface ResearchTelegramShareResponse {
  status: 'SENT' | 'QUEUED_LOCAL' | 'FAILED';
  configured: boolean;
  message: string;
  dispatched_text?: string;
}

// Phase 19: Cloud KMS / HSM Enclave & Execution Telemetry Types

export interface KMSEnclaveStatus {
  status: string;
  kms_enabled: boolean;
  provider: 'MOCK' | 'MOCK_HSM' | 'AWS_KMS' | 'GCP_KMS' | 'DISABLED';
  key_id: string;
  envelope_version: number;
  zeroization_guarantee: boolean;
  kill_switch_active: boolean;
  timestamp_ms: number;
}

export interface SORBenchmarkMetric {
  name: string;
  iterations: number;
  mean_us: number;
  median_us: number;
  p90_us: number;
  p95_us: number;
  p99_us: number;
  min_us: number;
  max_us: number;
  ops_per_sec: number;
  sla_target_us: number;
  sla_passed: boolean;
}

export interface SORBenchmarkSuite {
  timestamp_ms: number;
  iterations_per_test: number;
  overall_sla_passed: boolean;
  benchmarks: {
    depth_ladder_walk_20_levels?: SORBenchmarkMetric;
    almgren_chriss_slicer_20_intervals?: SORBenchmarkMetric;
    sor_multi_venue_optimal_route?: SORBenchmarkMetric;
    [key: string]: SORBenchmarkMetric | undefined;
  };
}

export interface WSReconciliationTelemetry {
  status: string;
  total_messages_received: number;
  total_fills_processed: number;
  total_fills_recorded: number;
  total_duplicates_filtered: number;
  buffered_events_count: number;
  max_buffer_size: number;
}

export interface WSNormalizedFill {
  exchange: string;
  client_order_id: string;
  exchange_order_id: string;
  execution_id: string;
  symbol: string;
  side: string;
  fill_price: number;
  fill_qty: number;
  fee_currency: string;
  fee_amount: number;
  is_maker: boolean;
  trade_time_ms: number;
  received_monotonic_ns: number;
}

// ==============================================================================
// SKY KNOWLEDGE OPERATING SYSTEM (PROJECT BRAIN + HUMAN BRAIN) TYPES
// ==============================================================================

export type KnowledgeAskMode = 'HUMAN' | 'PROJECT';
export type HumanQuestionMode =
  | 'EXPLAIN'
  | 'TEACH'
  | 'COMPARE'
  | 'CHALLENGE_ME'
  | 'QUIZ_ME'
  | 'PRACTICAL_EXERCISE'
  | 'RESEARCH_DEEP_DIVE'
  | 'WHAT_SHOULD_I_LEARN_NEXT';

export interface EpistemicCitation {
  source: string;
  author: string;
  location: string;
  status: string;
  quote?: string;
  node_id?: string;
  title?: string;
  citation?: string;
}

export interface EpistemicBreakdown {
  simple_explanation: string;
  source_knowledge: string[];
  cross_source_synthesis: string[];
  empirical_evidence: string[];
  sky_project_knowledge: string[];
  model_inference: string[];
  unknown_or_unestablished: string[];
}

export interface QuizItem {
  quiz_id: string;
  concept_id: string;
  question: string;
  options: string[];
  correct_option_index: number;
  explanation: string;
  misconception_trap: string;
}

export interface QuizSubmissionResult {
  quiz_id: string;
  is_correct: boolean;
  selected_option_index: number;
  correct_option_index: number;
  feedback: string;
  updated_mastery: number;
  next_review_days: number;
}

export interface HumanAnswerData {
  mode: string;
  primary_concept: string;
  missing_prerequisites: string[];
  answer_breakdown: EpistemicBreakdown;
  citations: EpistemicCitation[];
  quiz?: QuizItem;
  learn_next: Array<{ concept_id: string; title: string; domain: string }>;
  timestamp: number;
}

export interface ProjectKnowledgeContext {
  query: string;
  concepts: Array<Record<string, any>>;
  source_claims: Array<Record<string, any>>;
  competing_definitions: Array<Record<string, any>>;
  empirical_evidence: Array<Record<string, any>>;
  autopsy_failures: Array<Record<string, any>>;
  contradictions: Array<Record<string, any>>;
  current_sky_assumptions: string[];
  risk_boundary_warnings: string[];
  provenance_citations: EpistemicCitation[];
  recommendation: string;
  proposed_test_plan: string[];
  epistemic_summary: {
    total_relevant_claims: number;
    empirical_proofs_found: number;
    known_failures_autopsied: number;
    active_contradictions: number;
    highest_epistemic_tier: string;
    has_rejection_precedent: boolean;
  };
  safety_disclaimer: string;
  macro_intelligence?: MacroComprehensionResult | null;
  trade_plans?: DynamicTradingPlan[] | null;
  generated_at: number;
}

export interface KnowledgeAskResponse {
  mode: KnowledgeAskMode;
  question: string;
  answer_data?: HumanAnswerData;
  project_context?: ProjectKnowledgeContext;
  recommendation?: string;
  provenance_citations?: EpistemicCitation[];
  epistemic_summary?: Record<string, any>;
  safety_disclaimer: string;
}

export interface PersonalLearningGraphNode {
  concept_id: string;
  concept_title: string;
  domain: string;
  exposure_count: number;
  sources_read: number;
  explanations_seen: number;
  quiz_attempts: number;
  correct_answers: number;
  incorrect_answers: number;
  confidence: number;
  mastery_estimate: number;
  misconceptions: string[];
  prerequisite_concepts: string[];
  dependent_concepts: string[];
  last_reviewed?: number;
  next_review?: number;
  updated_at: number;
}

export interface PersonalLearningGraphResponse {
  concepts: PersonalLearningGraphNode[];
  summary: {
    total_concepts: number;
    mastered_count: number;
    in_progress_count: number;
    unstarted_count: number;
    overall_curriculum_progress_pct: number;
  };
}

export interface ResearchAdvisorResponse {
  recommended_concept_id: string;
  recommended_title: string;
  domain: string;
  current_mastery: number;
  rationale: string;
  suggested_actions: string[];
}

export interface BookIngestionJob {
  job_id: string;
  file_path: string;
  file_name: string;
  file_size_bytes: number;
  sha256_hash: string;
  total_pages: number;
  processed_pages: number;
  progress_pct: number;
  current_chapter: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'RESUMED';
  claims_count: number;
  concepts_count: number;
  error_log?: string;
  started_at: number;
  updated_at: number;
}

export interface LibraryStatsResponse {
  books_count: number;
  sources_count: number;
  pages_processed: number;
  claims_count: number;
  concepts_count: number;
  hypotheses_count: number;
  evidence_count: number;
  rejected_count: number;
  graph_edges_count: number;
  jobs_active: number;
  top_domains: Array<{ domain: string; count: number }>;
}

export interface ResearchGapItem {
  gap_id: string;
  concept_title: string;
  domain: string;
  claims_count: number;
  empirical_tests_count: number;
  gap_type: 'HIGH_TALK_ZERO_EVIDENCE' | 'CONFLICTING_DEFINITIONS' | 'UNTESTED_HYPOTHESIS' | 'KNOWLEDGE_BLIND_SPOT';
  priority_score: number;
  description: string;
  suggested_hypothesis: string;
  created_at: number;
}

export interface KnowledgeAuditCheck {
  check_name: string;
  status: 'PASS' | 'WARN' | 'FAIL';
  count: number;
  details: string;
  remediation: string;
}

export interface KnowledgeAuditReport {
  audit_id: string;
  overall_status: 'PASS' | 'WARN' | 'FAIL';
  summary: string;
  checks: KnowledgeAuditCheck[];
  total_sources: number;
  total_claims: number;
  total_evidence: number;
  total_autopsies: number;
  created_at: number;
}


// ============================================================================
// Institutional Master Command Cockpit (CTB Level 0 - Level 7)
// ============================================================================

export type TerminalDensityMode = 'COMMAND' | 'ANALYSIS' | 'REVIEW';

export interface MTFHeatmapRow {
  timeframe: string;
  label: string;
  isHTF: boolean;
  bias: string;
  structure: string;
  trend: string;
  rsi: number;
  vwapSigma: number;
  smcPattern: string;
  score: number;
  statusColor: 'emerald' | 'cyan' | 'amber' | 'rose';
}

export interface VolumeProfileBin {
  price: number;
  volume: number;
  percentage: number;
  isValueArea: boolean;
  isPOC: boolean;
}

export interface VolumeProfileData {
  vpoc: number;
  vah: number;
  val: number;
  hvnLevels: number[];
  lvnLevels: number[];
  bins: VolumeProfileBin[];
}

export interface LiquidationCluster {
  priceLevel: number;
  estimatedVolumeUsd: number;
  distancePct: number;
  leverageTier: string;
  clusterIntensity: number;
  label: string;
}

export interface LiquidationMapData {
  shortClusters: LiquidationCluster[];
  longClusters: LiquidationCluster[];
}

export interface MarketRegimeData {
  classification: 'TRENDING_EXPANSION' | 'COMPRESSION_COILING' | 'LIQUIDITY_HARVESTING' | 'DISTRIBUTION_PRESSURE' | 'MACRO_CHOP_UNCERTAIN';
  confidence: number;
  trendScore: number;
  volatilityScore: number;
  liquidityScore: number;
  momentumScore: number;
  correlationScore: number;
  preferredSetups: string[];
  avoidSetups: string[];
  summary: string;
}

export interface MarketDecisionData {
  primaryAction: 'LONG' | 'SHORT' | 'WAIT';
  edgeScore: number;
  alignmentScore: number;
  riskTier: string;
  stateLabel: string;
  narrative: string;
}

export interface ScorecardFactorWeight {
  name: string;
  weightPct: number;
  score: number;
  max: number;
  rationale: string;
}

export interface InstitutionalConfluenceData {
  qualityScore: number;
  qualityBadge: 'A+' | 'A' | 'B' | 'C';
  factorWeights: ScorecardFactorWeight[];
  confluenceRadar: {
    structure: number;
    trend: number;
    flow: number;
    macro: number;
    riskReward: number;
    derivatives: number;
  };
  qualityScoreHistory: number[];
}

export interface StyleSignalPlan {
  style: 'SCALP' | 'DAY' | 'SWING' | 'MOMENTUM' | 'POSITION';
  side: 'LONG' | 'SHORT';
  timeframe: string;
  entryZone: [number, number];
  invalidationPrice: number;
  stopLoss: number;
  tp1: number;
  tp2: number;
  tp3: number;
  riskRewardRatio: number;
  suggestedRiskPct: number;
  notionalUsd: number;
  halfKellyMultiplier: number;
  score: number;
  confidence: number;
  stableDurationSecs: number;
  reaffirmsCount: number;
  cooldownRemainingSecs: number;
  thesis: string;
}

export interface SignalBlotterRecord {
  id: string;
  symbol: string;
  style: 'SCALP' | 'DAY' | 'SWING' | 'MOMENTUM' | 'POSITION';
  side: 'LONG' | 'SHORT';
  score: number;
  qualityBadge: 'A+' | 'A' | 'B' | 'C';
  entryPrice: number;
  entryZone: [number, number];
  invalidationPrice: number;
  stopLoss: number;
  tpLadder: { tp1: number; tp2: number; tp3: number };
  riskRewardRatio: number;
  suggestedRiskPct: number;
  notionalUsd: number;
  halfKellyMultiplier: number;
  state: 'PENDING' | 'APPROVED' | 'EXECUTED' | 'CLOSED' | 'REJECTED';
  stableDurationSecs: number;
  reaffirmsCount: number;
  cooldownRemainingSecs: number;
  thesis: string;
  createdAt: number;
  approvedAt?: number;
  executedAt?: number;
  closedAt?: number;
  realizedPnlUsd?: number;
  realizedR?: number;
}

export interface PaperPortfolioCockpitData {
  equityUsd: number;
  todayPnlUsd: number;
  todayPnlPct: number;
  realizedPnlUsd: number;
  unrealizedPnlUsd: number;
  winRatePct: number;
  profitFactor: number;
  expectancyR: number;
  maxDrawdownPct: number;
  openPositionsCount: number;
  blotter: SignalBlotterRecord[];
  equityCurve: { time: string; equity: number }[];
  rDistribution: { rBucket: string; count: number }[];
  calibrationLab: {
    setupType: string;
    winRatePct: number;
    profitFactor: number;
    expectancyR: number;
    sizingMultiplier: number;
    status: string;
  }[];
}

export interface PolymarketIntelItem {
  question: string;
  previousProbPct: number;
  currentProbPct: number;
  deltaPct: number;
  bias: string;
}

export interface MacroCalendarEvent {
  event: string;
  impact: string;
  countdown: string;
  policyWarning: string;
}

export interface MacroCockpitRadarData {
  fearAndGreed: {
    score: number;
    classification: string;
    previousClose: number;
    historicalAvg7d: number;
  };
  marketDominance: {
    btcD: number;
    ethD: number;
    usdtD: number;
    othersD: number;
  };
  crossAssetCorrelation: {
    assets: string[];
    matrix: number[][];
  };
  polymarketIntelligence: PolymarketIntelItem[];
  macroCalendar: MacroCalendarEvent[];
  onChainVitals: {
    exchangeNetFlow24hUsd: number;
    exchangeFlowSentiment: string;
    whaleTransfers24hCount: number;
    whaleNetToExchangeCount: number;
    whaleNetToColdStorageCount: number;
    mempoolCongestionPct: number;
    medianGasSatVb: number;
  };
}

export interface PreTradeGateCheckItem {
  id: string;
  label: string;
  checked: boolean;
  required: boolean;
}

export interface AICoachCockpitData {
  currentThesis: string;
  supportingFactors: string[];
  threatFactors: string[];
  verdict: string;
  whyNotTradeEngine: {
    isTradingAllowed: boolean;
    primaryBlocker: string;
    activeBlockers: string[];
    capitalPreservationAdvice: string;
  };
  preTradeGateChecklist: PreTradeGateCheckItem[];
  behavioralTiltShield: {
    consecutiveLosses: number;
    recentTradeFrequencyPerHour: number;
    isTiltAlertActive: boolean;
    cooldownRemainingMinutes: number;
    advisoryMessage: string;
  };
}

export interface ProvenanceNodeItem {
  id: string;
  step?: string;
  source?: string;
  layer?: string;
  name?: string;
  algorithm?: string;
  idOrType?: string;
  classification?: string;
  check?: string;
  model?: string;
  latencyMs?: number;
  latency?: string;
  status: string;
  confidence: number;
  details?: string;
}

export interface ProvenanceGraphData {
  thesisId: string;
  timestamp: number;
  nodes: ProvenanceNodeItem[];
}

export interface MasterTerminalTelemetry {
  symbol: string;
  timeframe: string;
  currentPrice: number;
  priceChange24hPct: number;
  system: {
    service: string;
    version: string;
    timestamp: number;
    serverClockUtc: string;
    activeSession: string;
    marketDataLatencyMs: number;
    orderBookLatencyMs: number;
    derivativesLatencyMs: number;
    onChainLatencyMs: number;
    macroLatencyMs: number;
    aiLatencyMs: number;
    riskPerimeter: {
      status: 'ARMED';
      dailyLossPct: number;
      maxDailyLossPct: number;
      openRiskPct: number;
      maxOpenRiskPct: number;
      killSwitchReady: boolean;
    };
  };
  market: {
    mtfMatrix: MTFHeatmapRow[];
    regime: MarketRegimeData;
    marketDecision: MarketDecisionData;
    volumeProfile: VolumeProfileData;
    liquidationMap: LiquidationMapData;
    premiumDiscount: {
      currentZone: 'PREMIUM' | 'DISCOUNT';
      fib05Equilibrium: number;
      high50: number;
      low50: number;
    };
    smcStructures: {
      fvgList: FVGItem[];
      orderBlocks: OrderBlockItem[];
      bosList: unknown[];
      swings: unknown[];
    };
  };
  orderFlow: {
    currentCvd: number;
    cvdDeltaPct: number;
    divergenceAlert: {
      type: 'BULLISH_ABSORPTION' | 'BEARISH_EXHAUSTION';
      title: string;
      description: string;
      strengthScore: number;
      confidence: string;
    };
    derivativesVitals: {
      openInterestUsd: number;
      oiDelta1hPct: number;
      oiDelta24hPct: number;
      oiPriceTriadClassification: string;
      predictedFundingRate8hPct: number;
      fundingRateAnnualizedPct: number;
      longShortRatioTopTraders: number;
      longShortRatioGlobalAccounts: number;
      l2DepthImbalancePct: number;
      bidsPercentage: number;
      asksPercentage: number;
      liquidityWalls: {
        side: 'BID' | 'ASK';
        price: number;
        volumeUsd: number;
        distancePct: number;
      }[];
    };
  };
  confluence: InstitutionalConfluenceData;
  styleSignals: StyleSignalPlan[];
  executionAndRisk: PaperPortfolioCockpitData;
  macroAndContext: MacroCockpitRadarData;
  learningAndCoach: AICoachCockpitData;
  provenance: ProvenanceGraphData;
}

export interface SMCGlossaryItem {
  term: string;
  category: string;
  definition: string;
  rule: string;
  visualCue: string;
}

export interface ReplaySnapshotData {
  offset: string;
  timestamp: number;
  replayPrice: number;
  replayScore: number;
  replayAlignment: number;
  whatChanged: string;
}

// =============================================================================
// Milestone 22.3: Capital Escalation & Walk-Forward Risk Governance Types
// =============================================================================
export type CapitalTier =
  | 'TIER_0_PAPER'
  | 'TIER_1_CANARY_ELIGIBLE'
  | 'TIER_1_CANARY'
  | 'TIER_2_MICRO_ELIGIBLE'
  | 'TIER_2_MICRO_LIVE'
  | 'TIER_3_SCALED_ELIGIBLE'
  | 'TIER_3_SCALED_LIVE'
  | 'TIER_4_PRODUCTION_ELIGIBLE'
  | 'TIER_4_PRODUCTION';

export interface TierPolicyData {
  tier: CapitalTier;
  rank: number;
  name: string;
  max_notional_usd: number;
  max_risk_budget_usd: number;
  kelly_multiplier: number;
  max_concurrent_positions: number;
  is_live_capital: boolean;
  requires_operator_activation: boolean;
  description: string;
}

export interface DemotionStateData {
  is_demoted: boolean;
  current_tier: string;
  previous_tier: string;
  target_tier: string;
  triggering_metric: string;
  metric_value: number;
  threshold_value: number;
  demoted_at_ms: number;
  cooldown_until_ms: number;
  recovery_requirements: Record<string, any>;
  is_promotion_frozen: boolean;
  requires_human_reauth: boolean;
}

export interface CapitalEscalationDecisionData {
  decision_id: string;
  strategy_id: string;
  previous_tier: string;
  requested_tier: string;
  approved_tier: string;
  decision_type: string;
  reason_codes: string;
  metrics_snapshot: string;
  dsr: number;
  sharpe: number;
  trade_count: number;
  trials_count: number;
  walk_forward_score: number;
  max_drawdown: number;
  slippage_bps: number;
  regime: string;
  portfolio_heat: number;
  daily_drawdown: number;
  risk_multiplier: number;
  operator_authorization?: string | null;
  timestamp_ms: number;
  software_version: string;
  policy_version: string;
}

export interface CapitalEscalationReport {
  strategy_id: string;
  current_tier: CapitalTier;
  current_rank: number;
  tier_name: string;
  policy: TierPolicyData;
  is_live_capital: boolean;
  is_frozen: boolean;
  consecutive_clean_trades: number;
  total_live_trades: number;
  demotion_state: DemotionStateData;
  all_tiers: TierPolicyData[];
  recent_decisions: CapitalEscalationDecisionData[];
}

// =====================================================================
// Milestone K8: Kronos Probabilistic Foundation Forecasting Types
// =====================================================================

export interface KronosQuantileBands {
  p10: number[];
  p50: number[];
  p90: number[];
}

export interface KronosDecileBin {
  bin_index: number;
  range: [number, number];
  sample_count: number;
  mean_prediction: number;
  observed_frequency: number;
  absolute_error: number;
  status: 'SUFFICIENT_SAMPLE' | 'INSUFFICIENT_SAMPLE';
}

export interface KronosBrierReport {
  symbol: string;
  timeframe: string;
  sample_size: number;
  brier_score: number;
  murphy_decomposition: {
    reliability: number;
    resolution: number;
    uncertainty: number;
    within_bin_variance: number;
    reconstructed_bs: number;
  };
  reference_benchmark: {
    reference_name: string;
    base_rate: number;
    reference_brier: number;
    brier_skill_score: number;
  };
  calibration_quality: {
    expected_calibration_error: number;
    maximum_bin_error: number;
    epistemic_status: 'CALIBRATED' | 'WEAKLY_CALIBRATED' | 'INSUFFICIENT_DATA' | 'UNCALIBRATED' | 'DEGRADED' | 'SURROGATE';
  };
  confidence_intervals_95: {
    brier_score: [number, number];
    brier_skill_score: [number, number];
  };
  deciles: KronosDecileBin[];
  regime_breakdowns?: {
    volatility?: Record<string, { count: number; brier_score: number }>;
    sessions?: Record<string, { count: number; brier_score: number }>;
  };
}

export interface KronosDomainForecastData {
  forecast_id: string;
  request_id: string;
  symbol: string;
  timeframe: string;
  as_of_timestamp: number;
  horizon_bars: number;
  horizon_unit: string;
  horizon_ms: number;
  current_price: number;
  provider: {
    provider_type: 'LOCAL' | 'REMOTE' | 'SURROGATE';
    model_family: string;
    model_version: string;
    checkpoint_hash: string;
    latency_ms: number;
  };
  distribution: {
    expected_return_pct: number;
    median_return_pct: number;
    volatility_pct: number;
    path_dispersion_pct: number;
    directional_consensus: number;
    model_uncertainty: number;
    directional_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    quantile_bands: KronosQuantileBands;
  };
  probability: {
    raw_probability: number;
    raw_logit: number;
    calibrated_probability: number;
    calibration_id: string;
  };
  governance: {
    epistemic_status: string;
    brier_skill_score: number;
    is_tradeable: boolean;
    evidence_grade: string;
    created_at_ms: number;
  };
}

export interface KronosTournamentReport {
  symbol: string;
  timeframe: string;
  horizon_bars: number;
  sample_size: number;
  rankings: Array<{
    model_id: string;
    sample_size: number;
    brier_score: number;
    brier_skill_score: number;
    log_loss: number;
    roc_auc: number;
    expected_calibration_error: number;
    calibration_alpha: number;
    calibration_beta: number;
    beta_t_stat: number;
    reliability_curve?: Array<{
      bin_index: number;
      bin_min: number;
      bin_max: number;
      count: number;
      mean_predicted: number;
      observed_frequency: number;
      bin_error: number;
    }>;
  }>;
}

export interface KronosIncrementalReport {
  base_model_id: string;
  composite_model_id: string;
  sample_size: number;
  horizon_bars: number;
  base_brier_score: number;
  composite_brier_score: number;
  delta_brier: number;
  relative_brier_improvement_pct: number;
  base_log_loss: number;
  composite_log_loss: number;
  delta_log_loss: number;
  beta_base: number;
  beta_kronos: number;
  beta_kronos_se: number;
  beta_kronos_t_stat: number;
  beta_kronos_p_value: number;
  vuong_z_stat: number;
  vuong_p_value: number;
  test_verdict: string;
  residual_correlation: number;
}

export interface KronosRegimesReport {
  symbol: string;
  timeframe: string;
  sample_size: number;
  regime_slices: Array<{
    dimension: string;
    regime_name: string;
    sample_count: number;
    brier_score: number | null;
    brier_skill_score: number | null;
    log_loss: number | null;
    accuracy: number | null;
    status: string;
  }>;
}

export interface KronosAblationReport {
  symbol: string;
  timeframe: string;
  sample_size: number;
  ablation_variants: Array<{
    variant_id: string;
    name: string;
    sample_size: number;
    brier_score: number;
    brier_skill_score: number;
    log_loss: number;
    accuracy: number;
    incremental_bss_vs_raw: number;
    status: string;
  }>;
}

export interface KronosPromotionReport {
  governance_state: 'PROMOTE' | 'QUARANTINE' | 'REJECT' | 'INCONCLUSIVE';
  is_tradeable: boolean;
  sample_size: number;
  criteria_checklist: Record<string, boolean>;
  scorecard: Record<string, any>;
  summary_verdict: string;
  downstream_destination: string;
  governance_notes: string[];
}

// ----------------------------------------------------------------------------
// Milestone 20: Gate 5 Extended Testnet Reliability Qualification & Burn-In
// ----------------------------------------------------------------------------

export type TestnetBurnInState =
  | 'NOT_STARTED'
  | 'INITIALIZING'
  | 'WARMING_UP'
  | 'ACTIVE_REHEARSAL'
  | 'DEGRADED_OPERATION'
  | 'RECOVERY_RECONCILIATION'
  | 'ANOMALY_HALTED'
  | 'COMPLETED';

export interface TestnetSessionDurations {
  wallclock_elapsed_sec: number;
  healthy_duration_sec: number;
  invalidated_duration_sec: number;
  healthy_ratio_pct: number;
  target_duration_sec: number;
  target_progress_pct: number;
  wall_clock_seconds?: number;
  qualifying_active_seconds?: number;
  invalidated_quarantined_seconds?: number;
  qualifying_ratio_pct?: number;
}

export interface TestnetEpochSummary {
  epoch_id: string;
  epoch_index: number;
  started_at_utc: string;
  ended_at_utc: string | null;
  status: 'ACTIVE' | 'CLOSED_HEALTHY' | 'CLOSED_INVALIDATED';
  continuity_break_reason: string | null;
  healthy_duration_sec: number;
}

export interface TestnetLatencyStageSummary {
  stage_name: string;
  p50_us: number;
  p90_us: number;
  p99_us: number;
  p99_9_us: number;
  max_us: number;
  sample_count: number;
}

export interface TestnetInvariantStatus {
  name: string;
  description: string;
  status: 'PASS' | 'WARN' | 'FAIL';
  last_checked_utc: string;
  details: string;
}

export interface TestnetBurnInReport {
  session_id: string;
  state: TestnetBurnInState;
  durations: TestnetSessionDurations;
  active_epoch: TestnetEpochSummary | null;
  clock_offset_ms: number;
  clock_healthy: boolean;
  account_equity_usd: number;
  peak_equity_usd: number;
  drawdown_pct: number;
  rehearsal_drawdown_limit_pct: number;
  invariants: TestnetInvariantStatus[];
  clean_latency_summary: TestnetLatencyStageSummary[];
  fault_latency_summary: TestnetLatencyStageSummary[];
  fault_injection_stats: {
    injected_count: number;
    recovered_count: number;
    active_fault: string | null;
  };
  total_parent_orders: number;
  total_slices_dispatched: number;
  unresolved_quantity_abs: string;
  telemetry_seq?: number;
  fencing_token?: number;
  is_stale?: boolean;
  timestamp_utc?: string;
}

// ============================================================================
// Milestone 27: SKY Global Intelligence Fabric & Autonomous Web Scout Types
// ============================================================================

export type IntelligenceDomain = 'MACRO' | 'CRYPTO' | 'EQUITIES' | 'SOCIAL' | 'QUANT_RESEARCH';

export type EvidenceGrade =
  | 'VERIFIED_PRIMARY'
  | 'CORROBORATED_REPORT'
  | 'UNVERIFIED_CLAIM'
  | 'SPECULATION';

export type SourcePlatform =
  | 'WEB'
  | 'RSS'
  | 'YOUTUBE'
  | 'GITHUB'
  | 'TWITTER'
  | 'REDDIT'
  | 'XUEQIU';

export interface IntelligenceRecord {
  record_id: string;
  content_hash: string;
  source_platform: SourcePlatform | string;
  source_url: string;
  title: string;
  content_markdown: string;
  summary: string;
  domain: IntelligenceDomain | string;
  entities: string[];
  evidence_grade: EvidenceGrade | string;
  relevance_score: number;
  security_flags: string[];
  published_at_utc: number;
  collected_at_utc: number;
  metadata?: Record<string, any>;
}

export interface ScoutTelemetry {
  state: 'STOPPED' | 'RUNNING' | 'PAUSED';
  frontier_size: number;
  processed_count: number;
  relevant_count: number;
  error_count: number;
  last_active_time: number;
  poll_interval_range: [number, number];
  total_stored_records: number;
}

export interface ChannelCapabilityInfo {
  status: 'ONLINE' | 'DEGRADED' | 'UNAVAILABLE';
  description: string;
  requires_cookies: boolean;
  details: Record<string, any>;
}

export interface IntelligenceStatusResponse {
  status: string;
  timestamp_utc: number;
  scout: ScoutTelemetry;
  channels: Record<string, ChannelCapabilityInfo>;
  top_entities: Array<{ entity: string; count: number }>;
  total_records: number;
  non_executable_watermark: string;
}

export interface NarrativeCluster {
  theme: string;
  velocity_score: number;
  total_records: number;
  entities: string[];
  platforms: string[];
  evidence_breakdown: Record<string, number>;
  credibility_tag: 'INSTITUTIONAL_BACKED' | 'CORROBORATED' | 'HYPE_DRIVEN';
  latest_timestamp_utc: number;
  sample_headlines: string[];
}

export interface IntelligenceRecordsResponse {
  total: number;
  limit: number;
  offset: number;
  records: IntelligenceRecord[];
}

export interface NarrativesResponse {
  lookback_hours: number;
  count: number;
  narratives: NarrativeCluster[];
}

// ============================================================================
// Milestone 28: Cross-Domain Macro-Micro Causal Synthesis Interfaces
// ============================================================================

export interface PointInTimeEventContract {
  event_id: string;
  source_record_id: string;
  event_type: string;
  domain: string;
  headline: string;
  published_at_utc: number;
  collected_at_utc: number;
  effective_availability_utc: number;
  dissemination_buffer_seconds: number;
  initial_metric_value?: number | null;
  revised_metric_value?: number | null;
  revision_number: number;
  content_hash_sha256: string;
  epistemic_grade: string;
  epistemic_prior_weight: number;
  metadata?: Record<string, any>;
}

export interface ResearchFamily {
  family_id: string;
  name: string;
  description: string;
  applicable_domains: string[];
  target_assets: string[];
  timeframes: string[];
  daily_trial_cap: number;
  base_required_sharpe: number;
  default_frictional_tier: string;
}

export interface CausalMechanism {
  mechanism_id: string;
  family_id: string;
  name: string;
  transmission_type: string;
  primary_receptor: string;
  secondary_receptor?: string | null;
  direction: 'BULLISH' | 'BEARISH' | 'VOLATILITY';
  economic_rationale: string;
  lead_time_seconds_min: number;
  lead_time_seconds_max: number;
  default_micro_conditions: Record<string, any>;
  default_falsification_criteria: Record<string, any>;
}

export type CausalHypothesisStatus =
  | 'DRAFT'
  | 'FIREWALL_VALIDATED'
  | 'REJECTED'
  | 'QUEUED_FOR_LAB'
  | 'TESTING'
  | 'VALIDATED'
  | 'FALSIFIED'
  | 'QUARANTINED';

export interface CausalHypothesis {
  hypothesis_id: string;
  family_id: string;
  mechanism_id: string;
  macro_event_contract: PointInTimeEventContract;
  target_asset: string;
  timeframe: string;
  null_hypothesis: string;
  alternative_hypothesis: string;
  microstructure_conditions: Record<string, any>;
  falsification_criteria: Record<string, any>;
  epistemic_prior_weight: number;
  status: CausalHypothesisStatus;
  rejection_reason?: string | null;
  execution_authority: string;
  real_capital_enabled: boolean;
  created_at_utc: number;
  updated_at_utc: number;
}

export interface CausalFirewallDecision {
  passed: boolean;
  hypothesis_id: string;
  gate_results: Record<string, boolean>;
  violations: string[];
  audit_timestamp_utc: number;
}

export interface FamilyTrialBudget {
  name: string;
  daily_cap: number;
  trials_today: number;
  remaining: number;
}

export interface HypothesisStatsResponse {
  total_hypotheses_created: number;
  daily_family_trials: Record<string, FamilyTrialBudget>;
  daily_global_cap: number;
  real_capital_enabled: boolean;
  execution_authority: string;
}

export interface HypothesesListResponse {
  status: string;
  hypotheses: CausalHypothesis[];
  total: number;
  limit: number;
  offset: number;
  execution_isolation: string;
}

export interface SynthesizeResponse {
  status: string;
  count: number;
  hypotheses: CausalHypothesis[];
  execution_isolation: string;
}

export interface FamiliesResponse {
  families: ResearchFamily[];
  mechanisms: CausalMechanism[];
  governance_level: string;
}

// ============================================================================
// Milestone 29: Point-in-Time Replay, Validation & Falsification Interfaces
// ============================================================================

export type ResearchValidationStatus =
  | 'INCONCLUSIVE'
  | 'PRELIMINARY_SUPPORT'
  | 'FALSIFIED'
  | 'COST_INVALIDATED'
  | 'REGIME_DEPENDENT'
  | 'DATA_INVALID'
  | 'REPLICATION_PENDING'
  | 'OOS_VALIDATED'
  | 'INDEPENDENTLY_REPLICATED'
  | 'HUMAN_REVIEW_REQUIRED';

export interface PreregisteredResearchContract {
  contract_id: string;
  hypothesis_id: string;
  family_id: string;
  mechanism_id: string;
  target_symbol: string;
  timeframe: string;
  null_hypothesis: string;
  alternative_hypothesis: string;
  treatment_definition: Record<string, any>;
  comparator_definition: Record<string, any>;
  primary_endpoint: string;
  secondary_endpoints: string[];
  lookback_days: number;
  min_event_observations: number;
  min_independent_episodes: number;
  required_regimes: string[];
  holding_period_bars: number;
  frictional_tier: string;
  statistical_procedures: string[];
  falsification_criteria: Record<string, any>;
  trial_budget_allocated: number;
  contract_hash_sha256: string;
  is_immutable: boolean;
  execution_authority: string;
  real_capital_enabled: boolean;
  preregistered_at_utc: number;
}

export interface DurableExperimentPlan {
  plan_id: string;
  hypothesis_id: string;
  family_id: string;
  target_symbol: string;
  timeframe: string;
  backtest_range_start_utc: number;
  backtest_range_end_utc: number;
  lookback_days: number;
  frictional_tier: string;
  min_oos_trades: number;
  required_dsr: number;
  execution_authority: string;
  real_capital_enabled: boolean;
  plan_hash_sha256: string;
  state: 'QUEUED' | 'EXECUTING' | 'COMPLETED' | 'FALSIFIED' | 'CANCELLED';
  created_at_utc: number;
}

export interface ReplayEpisode {
  episode_id: string;
  event_id: string;
  event_effective_availability_utc: number;
  entry_bar_time_utc: number;
  entry_price: number;
  exit_bar_time_utc: number;
  exit_price: number;
  direction: string;
  holding_bars: number;
  gross_pnl_usd: number;
  gross_expectancy_r: number;
  net_pnl_usd: number;
  net_expectancy_r: number;
  stress_pnl_usd: number;
  frictions: Record<string, any>;
  exit_reason: string;
}

export interface ReplayExecutionReport {
  report_id: string;
  contract_id: string;
  manifest_id: string;
  config_hash_sha256: string;
  total_episodes: number;
  independent_episodes: number;
  gross_expectancy_r: number;
  net_expectancy_r: number;
  stress_expectancy_r: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown_pct: number;
  cost_erosion_pct: number;
  output_signature_sha256: string;
  episodes: ReplayEpisode[];
  created_at_utc: number;
}

export interface CausalValidationResult {
  result_id: string;
  contract_id: string;
  hypothesis_id: string;
  status: ResearchValidationStatus;
  primary_endpoint_value: number;
  benchmark_relative_alpha: number;
  effective_sample_size: number;
  deflated_sharpe_ratio: number;
  whites_reality_check_pvalue: number;
  regime_stability_ratio: number;
  parameter_perturbation_decay: number;
  cost_erosion_pct: number;
  verdict_rationale: string;
  scorecard_passes: Record<string, boolean>;
  execution_authority: string;
  real_capital_enabled: boolean;
  evaluated_at_utc: number;
}

export interface CausalFailureAutopsy {
  autopsy_id: string;
  hypothesis_id: string;
  contract_id: string;
  family_id: string;
  failure_category: string;
  gross_expectancy_r: number;
  net_expectancy_r: number;
  friction_sensitivity: Record<string, number>;
  regime_stability_ratio: number;
  parameter_perturbation_decay: number;
  sample_sufficiency_ratio: number;
  data_integrity_status: string;
  statistical_evidence: Record<string, any>;
  failure_mechanism: string;
  reusable_lesson: string;
  evidence_snapshot_hash: string;
  research_contract_hash: string;
  replay_configuration_hash: string;
  created_at_utc: number;
}

export interface ReplayResponse {
  status: string;
  validation_result: CausalValidationResult;
  replay_report: ReplayExecutionReport;
  manifest: Record<string, any>;
  autopsy?: CausalFailureAutopsy | null;
  execution_authority: string;
  real_capital_enabled: boolean;
}

export interface PlansListResponse {
  status: string;
  total: number;
  plans: DurableExperimentPlan[];
}

// ============================================================================
// Milestone 30-C: Evidence Qualification & Research Integration Interfaces
// ============================================================================

export type EvidenceKind =
  | 'raw_observation'
  | 'derived_fact'
  | 'temporal_association'
  | 'mechanistic_claim'
  | 'causal_hypothesis'
  | 'empirically_validated';

export type CausalQualificationStatus =
  | 'CANDIDATE_GENERATED'
  | 'EVIDENCE_ADMISSIBLE'
  | 'FIREWALL_EVALUATED'
  | 'QUALIFIED_FOR_RESEARCH'
  | 'PREREGISTERED_REPLAY_PENDING'
  | 'OUT_OF_SAMPLE_VALIDATION'
  | 'FALSIFIED'
  | 'RESEARCH_CONCLUSION_RECORDED';

export interface ConfidenceScores {
  source_reliability: number;
  fact_confidence: number;
  causal_prior_strength: number;
}

export interface EvidenceLineageNode {
  node_id: string;
  parent_ids: string[];
  evidence_kind: EvidenceKind;
  timestamp_utc: number;
  schema_version: string;
  content_hash_sha256: string;
  producer_actor: string;
  metadata: Record<string, any>;
}

export interface ResearchTemplate {
  template_id: string;
  causal_family: string;
  allowed_horizons: string[];
  outcome_definitions: string[];
  multiple_testing_policy: string;
  template_version: string;
  default_lookback_days: number;
  min_oos_trades: number;
  required_dsr: number;
  frictional_tier: string;
}

export interface EmpiricalFact {
  fact_id: string;
  evidence_kind: EvidenceKind;
  canonical_event_id: string;
  parent_evidence_id: string;
  parent_content_sha256: string;
  event_type: string;
  entity: string;
  metric_name: string;
  metric_value: number;
  unit: string;
  confidence_scores: ConfidenceScores;
  is_quarantined: boolean;
  quarantine_reason?: string | null;
  extracted_at_utc: number;
  metadata?: Record<string, any>;
}

export interface MultipleTestingBatch {
  batch_id: string;
  family_id: string;
  hypotheses_generated: number;
  hypotheses_tested: number;
  multiple_testing_policy: string;
  classification: string;
  created_at_utc: number;
  updated_at_utc: number;
}

export interface CrawlerTemplatesResponse {
  status: string;
  total: number;
  templates: ResearchTemplate[];
}

export interface CrawlerMultipleTestingResponse {
  status: string;
  total_batches: number;
  batches: MultipleTestingBatch[];
}

export interface EvidenceLineageResponse {
  status: string;
  root_node: EvidenceLineageNode;
  lineage_depth: number;
  trace: EvidenceLineageNode[];
}

export interface QualifyResponse {
  status: string;
  fact: EmpiricalFact;
  compilation: {
    success: boolean;
    hypothesis_id?: string;
    rejection_reason?: string | null;
    qualification_status: string;
  };
  firewall?: {
    admissible: boolean;
    qualification_status: string;
    causal_validity_established: boolean;
    replay_required: boolean;
    hypothesis_id: string;
    violations: string[];
    gate_results: Record<string, boolean>;
    lineage_node_id: string;
  } | null;
  plan?: {
    success: boolean;
    plan_id?: string | null;
    contract_id?: string | null;
    rejection_reason?: string | null;
    lineage_node_id?: string | null;
  } | null;
}

// ==============================================================================
// MILESTONE 30-D: REPLAY RUNNER & STATISTICAL AUDIT TYPES
// ==============================================================================

export interface ReplayJobItem {
  job_id: string;
  plan_id: string;
  hypothesis_id: string;
  research_contract_hash: string;
  dataset_manifest_hash: string;
  replay_engine_version: string;
  friction_model_version: string;
  statistical_protocol_version: string;
  frictional_tier: string;
  status: 'PENDING' | 'VALIDATING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  requested_at_utc: number;
  completed_at_utc?: number | null;
  idempotency_key: string;
  research_only: boolean;
  execution_authority: string;
  real_capital_enabled: boolean;
  output_signature_sha256?: string | null;
  error_message?: string | null;
  metadata?: Record<string, any>;
}

export interface ReplayJobsResponse {
  status: string;
  total_jobs: number;
  jobs: ReplayJobItem[];
}

export interface AuditReportData {
  audit_id: string;
  plan_id: string;
  hypothesis_id: string;
  family_id: string;
  status: string;
  primary_net_expectancy_r: number;
  gross_expectancy_r: number;
  stress_expectancy_r: number;
  cost_erosion_pct: number;
  dsr_result: {
    raw_sharpe: number;
    deflated_sharpe: number;
    sample_length: number;
    skewness: number;
    kurtosis: number;
    trial_count: number;
    expected_max_sharpe: number;
    z_stat: number;
    p_value: number;
    is_statistically_significant: boolean;
  };
  multiple_testing_policy: string;
  family_trial_count: number;
  holm_bonferroni_passed: boolean;
  stress_survival: boolean;
  scorecard_passes: Record<string, boolean>;
  verdict_rationale: string;
  human_review_required: boolean;
  execution_authority: string;
  real_capital_enabled: boolean;
  audit_hash_sha256: string;
  created_at_utc: number;
}

export interface DispatchReplayResponse {
  status: string;
  plan_id: string;
  job?: ReplayJobItem | null;
  frictional_reports?: Record<string, any>;
  audit?: AuditReportData | null;
  autopsy?: any | null;
  dossier_hash?: string | null;
}

export interface PlanAuditResponse {
  status: string;
  audit: AuditReportData;
}

export interface ResearchDossierResponse {
  status: string;
  plan_id: string;
  dossier_hash: string;
  content_markdown: string;
}

export interface QuarantineStatusResponse {
  status: string;
  quarantine: {
    mechanism_id: string;
    failure_count: number;
    level: string;
    last_failure_at_utc?: number | null;
    advisory_message: string;
  };
}

// =====================================================================
// Milestone 31: Continuous Forward Validation League & Markout Desk
// =====================================================================

export type ForwardAdmissionStatus =
  | 'ADMITTED'
  | 'ACTIVE'
  | 'QUARANTINED'
  | 'SUSPENDED'
  | 'GRADUATED'
  | 'EVALUATION_FAILED'
  | 'RETIRED';

export type DriftStatusType = 'NORMAL' | 'WATCH' | 'DEGRADED' | 'SEVERE' | 'INCONCLUSIVE';

export interface LeagueStrategyRecord {
  admission_id: string;
  strategy_genome_id: string;
  dossier_id: string;
  hypothesis_id: string;
  plan_id: string;
  parameter_hash: string;
  status: ForwardAdmissionStatus;
  evaluation_mode: string;
  market_universe: string[];
  timeframe: string;
  admission_timestamp_utc: number;
  evaluation_start_utc?: number | null;
  evaluation_end_utc?: number | null;
  total_observations: number;
  winning_observations: number;
  losing_observations: number;
  gross_pnl_bps: number;
  net_pnl_bps: number;
  max_drawdown_bps: number;
  high_water_mark_bps: number;
  avg_markout_5s_bps: number;
  last_observation_utc?: number | null;
  suspension_reason?: string | null;
}

export interface ForwardStrategiesResponse {
  status: string;
  strategies: LeagueStrategyRecord[];
  total: number;
  survivorship_bias_firewall: string;
}

export interface StrategyForwardScorecard {
  admission_id: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_pnl_bps: number;
  net_pnl_bps: number;
  mean_trade_net_bps: number;
  std_dev_bps: number;
  standard_error_bps: number;
  ci_95_lower_bps: number;
  ci_95_upper_bps: number;
  max_drawdown_bps: number;
  high_water_mark_bps: number;
  avg_slippage_bps: number;
  avg_fee_bps: number;
  markout_curve_bps: Record<string, number>;
  first_trade_utc?: number | null;
  last_trade_utc?: number | null;
  observation_age_days: number;
  is_statistically_significant_positive?: boolean;
}

export interface ForwardScorecardResponse {
  status: string;
  scorecard: StrategyForwardScorecard;
}

export interface AxisDriftResult {
  axis_name: string;
  status: DriftStatusType;
  statistic?: number | null;
  p_value?: number | null;
  details?: Record<string, any>;
  warning_message?: string | null;
}

export interface MultiDimensionalDriftReport {
  admission_id: string;
  sample_size_n: number;
  overall_status: DriftStatusType;
  axes: Record<string, AxisDriftResult>;
  drift_summary: string;
  timestamp_utc: number;
}

export interface ForwardDriftResponse {
  status: string;
  drift: MultiDimensionalDriftReport;
}

export interface SuspensionLogRecord {
  suspension_id: string;
  admission_id: string;
  trigger_name: string;
  threshold_val: number;
  observed_val: number;
  policy_version: string;
  details: string;
  timestamp_utc: number;
}

export interface ForwardSuspensionLogsResponse {
  status: string;
  admission_id: string;
  logs: SuspensionLogRecord[];
}

// =========================================================================
// SKY RESEARCH WIKIPEDIA & LIVING KNOWLEDGE JOURNAL
// =========================================================================

export type EpistemicStatus = 'FACT' | 'HYPOTHESIS' | 'NARRATIVE' | 'CONTRADICTION' | 'UNVERIFIED';

export interface WikiEpistemicClaim {
  claim_id: string;
  speaker_claim: string;
  epistemic_status: EpistemicStatus;
  cross_verification_evidence: string;
  confidence_score: number;
  empirical_dataset_reference: string;
}

export interface WikiArticleSummary {
  article_id: string;
  title: string;
  category: string;
  source_url: string;
  source_type: string;
  provenance_id: string;
  author_or_speaker: string;
  executive_summary: string;
  verification_score: number;
  claims_count: number;
  wikilinks: string[];
  tags: string[];
  created_at: number;
  updated_at: number;
}

export interface WikiArticleDetail extends WikiArticleSummary {
  key_claims: WikiEpistemicClaim[];
  contradictions_detected: string[];
  macro_regime_implications: string;
  full_markdown_content: string;
}

export interface WikiArticlesResponse {
  articles: WikiArticleSummary[];
  count: number;
}

export interface WikiArticleDetailResponse {
  article: WikiArticleDetail;
}

export interface WikiIngestRequestPayload {
  url_or_text: string;
  title?: string;
  category?: string;
  author?: string;
}








