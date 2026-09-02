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
  id: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  entryPrice: number;
  sl: number;
  tp: number;
  size: number;
  status: 'OPEN' | 'CLOSED' | 'CANCELLED';
  pnl?: number;
  exitPrice?: number;
  createdAt: string;
  closedAt?: string;
}

export interface PaperPositionsResponse {
  positions: PaperTrade[];
  count: number;
}

export interface RiskConfig {
  accountBalance: number;
  maxDrawdown: number;
  maxOpenTrades: number;
  dailyLossLimit: number;
  maxRiskPerTrade: number;
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
export type ResearchIngestMode = 'ANALYZE' | 'RESEARCH' | 'SAVE_KNOWLEDGE';

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
  validation_stage: 'UNTESTED' | 'BACKTESTING' | 'WALK_FORWARD' | 'PAPER_TEST' | 'REJECTED' | 'PROMOTED';
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

export interface ResearchIngestResult {
  knowledge_id: string;
  mode: ResearchIngestMode;
  provenance: ResearchProvenanceItem;
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


