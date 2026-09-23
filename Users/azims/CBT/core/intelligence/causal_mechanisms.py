"""
core/intelligence/causal_mechanisms.py
======================================
Causal Mechanism Registry & Preregistered Research Families for Milestone 28.

Enforces:
1. 5 Preregistered Research Families with bounded exploration budgets.
2. Formal economic transmission channels linking macro phenomena to microstructure receptors.
3. Explicit falsification parameters and default microstructure hurdle thresholds.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.intelligence.schema import IntelligenceDomain


class ResearchFamilyId(str, Enum):
    MACRO_LIQUIDITY_TRANSMISSION = "FAM_01_MACRO_LIQUIDITY"
    INFLATION_GROWTH_SURPRISE = "FAM_02_INFLATION_SURPRISE"
    REGULATORY_POLICY_SHOCK = "FAM_03_REGULATORY_SHOCK"
    ONCHAIN_STABLECOIN_DISLOCATION = "FAM_04_ONCHAIN_DISLOCATION"
    CROSS_ASSET_CONTAGION = "FAM_05_CROSS_ASSET_CONTAGION"


class CausalTransmissionType(str, Enum):
    LIQUIDITY_WITHDRAWAL = "LIQUIDITY_WITHDRAWAL"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    MOMENTUM_ACCELERATION = "MOMENTUM_ACCELERATION"
    MEAN_REVERSION_DISLOCATION = "MEAN_REVERSION_DISLOCATION"
    ABSORPTION_EXHAUSTION = "ABSORPTION_EXHAUSTION"


class MicrostructureReceptorType(str, Enum):
    CVD_ABSORPTION = "CVD_ABSORPTION"
    L2_ORDERBOOK_IMBALANCE = "L2_ORDERBOOK_IMBALANCE"
    SMC_ORDER_BLOCK = "SMC_ORDER_BLOCK"
    SMC_FVG = "SMC_FVG"
    SMC_LIQUIDITY_SWEEP = "SMC_LIQUIDITY_SWEEP"


class ResearchFamily(BaseModel):
    """Preregistered institutional research hypothesis family."""

    family_id: ResearchFamilyId
    name: str
    description: str
    applicable_domains: list[str]
    target_assets: list[str]
    timeframes: list[str]
    daily_trial_cap: int = 15
    base_required_sharpe: float = 1.50
    default_frictional_tier: str = "CONSERVATIVE"
    min_lookback_days: int = Field(90, description="Dynamic lookback duration in days")
    min_event_observations: int = Field(12, description="Minimum macro event instances")
    min_independent_episodes: int = Field(10, description="Minimum independent trade episodes")
    required_regimes: list[str] = Field(
        default_factory=lambda: ["HIGH_VOL", "LOW_VOL"],
        description="Regimes that must be covered across sample period",
    )
    event_clustering_window_seconds: float = Field(
        172800.0, description="Window to cluster co-occurring events (e.g. 48 hours)"
    )


class CausalMechanism(BaseModel):
    """Formal economic transmission mechanism connecting macro shock to orderbook footprint."""

    mechanism_id: str
    family_id: ResearchFamilyId
    name: str
    transmission_type: CausalTransmissionType
    primary_receptor: MicrostructureReceptorType
    secondary_receptor: MicrostructureReceptorType | None = None
    direction: str = Field("BULLISH", description="BULLISH, BEARISH, or VOLATILITY")
    economic_rationale: str
    lead_time_seconds_min: int = Field(
        60, description="Minimum delay after news before micro entry"
    )
    lead_time_seconds_max: int = Field(3600, description="Maximum valid response window")
    default_micro_conditions: dict[str, Any]
    default_falsification_criteria: dict[str, Any]


# ============================================================================
# Preregistered Research Families (Level 2 Governance)
# ============================================================================

RESEARCH_FAMILIES: dict[ResearchFamilyId, ResearchFamily] = {
    ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION: ResearchFamily(
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        name="Macro Central Bank & Global Liquidity Transmission",
        description="Interest rate cuts/hikes, balance sheet expansion, and sovereign bond yields propagating to spot/perp liquidity depth.",
        applicable_domains=[IntelligenceDomain.MACRO.value],
        target_assets=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        timeframes=["5m", "15m", "1h"],
        daily_trial_cap=15,
        base_required_sharpe=1.50,
        min_lookback_days=730,
        min_event_observations=16,
        min_independent_episodes=12,
        required_regimes=["TIGHTENING", "EASING", "HIGH_VOL", "LOW_VOL"],
        event_clustering_window_seconds=172800.0,
    ),
    ResearchFamilyId.INFLATION_GROWTH_SURPRISE: ResearchFamily(
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        name="Inflation & Economic Growth Surprise Transmission",
        description="CPI, PPI, and Non-Farm Payroll surprises driving aggressive market order sweeps and institutional absorption.",
        applicable_domains=[IntelligenceDomain.MACRO.value],
        target_assets=["BTC/USDT", "ETH/USDT"],
        timeframes=["1m", "5m", "15m"],
        daily_trial_cap=15,
        base_required_sharpe=1.60,
        min_lookback_days=365,
        min_event_observations=12,
        min_independent_episodes=10,
        required_regimes=["INFLATION_SURPRISE_UP", "INFLATION_SURPRISE_DOWN"],
        event_clustering_window_seconds=86400.0,
    ),
    ResearchFamilyId.REGULATORY_POLICY_SHOCK: ResearchFamily(
        family_id=ResearchFamilyId.REGULATORY_POLICY_SHOCK,
        name="Regulatory Enforcement & Policy Shift Shocks",
        description="SEC, CFTC, and legislative filings creating volatility expansion, orderbook skew, and liquidity pool sweeps.",
        applicable_domains=[IntelligenceDomain.CRYPTO.value, IntelligenceDomain.MACRO.value],
        target_assets=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        timeframes=["5m", "15m", "1h"],
        daily_trial_cap=10,
        base_required_sharpe=1.40,
        min_lookback_days=365,
        min_event_observations=10,
        min_independent_episodes=8,
        required_regimes=["HAWKISH_ENFORCEMENT", "DOVISH_CLARITY"],
        event_clustering_window_seconds=172800.0,
    ),
    ResearchFamilyId.ONCHAIN_STABLECOIN_DISLOCATION: ResearchFamily(
        family_id=ResearchFamilyId.ONCHAIN_STABLECOIN_DISLOCATION,
        name="On-Chain Stablecoin Dislocation & Reserve Flows",
        description="Large exchange stablecoin inflows, bridge evacuations, and de-pegging signals driving basis dislocation.",
        applicable_domains=[IntelligenceDomain.CRYPTO.value],
        target_assets=["BTC/USDT", "ETH/USDT"],
        timeframes=["1m", "5m", "15m"],
        daily_trial_cap=10,
        base_required_sharpe=1.50,
        min_lookback_days=180,
        min_event_observations=15,
        min_independent_episodes=12,
        required_regimes=["INFLOW_SURGE", "OUTFLOW_DRAIN"],
        event_clustering_window_seconds=43200.0,
    ),
    ResearchFamilyId.CROSS_ASSET_CONTAGION: ResearchFamily(
        family_id=ResearchFamilyId.CROSS_ASSET_CONTAGION,
        name="Cross-Asset Equities & Tech Beta Contagion",
        description="Nasdaq/S&P index momentum, semiconductor earnings, and VIX term structure shocks transmitting to high-beta crypto.",
        applicable_domains=[IntelligenceDomain.EQUITIES.value, IntelligenceDomain.MACRO.value],
        target_assets=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        timeframes=["5m", "15m"],
        daily_trial_cap=10,
        base_required_sharpe=1.50,
        min_lookback_days=180,
        min_event_observations=20,
        min_independent_episodes=15,
        required_regimes=["EQUITIES_RISK_ON", "EQUITIES_RISK_OFF"],
        event_clustering_window_seconds=86400.0,
    ),
}


# ============================================================================
# Preregistered Institutional Causal Mechanisms
# ============================================================================

CAUSAL_MECHANISMS: dict[str, CausalMechanism] = {
    # 1. Fed Dovish Pivot -> CVD Bullish Absorption
    "MEC_DOVISH_PIVOT_CVD_ABSORPTION": CausalMechanism(
        mechanism_id="MEC_DOVISH_PIVOT_CVD_ABSORPTION",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        name="Dovish Central Bank Pivot with Bullish CVD Absorption",
        transmission_type=CausalTransmissionType.ABSORPTION_EXHAUSTION,
        primary_receptor=MicrostructureReceptorType.CVD_ABSORPTION,
        secondary_receptor=MicrostructureReceptorType.L2_ORDERBOOK_IMBALANCE,
        direction="BULLISH",
        economic_rationale=(
            "Central bank dovish guidance reduces sovereign yield expectations. "
            "Retail panic sell orders are passively absorbed by institutional limit buy bids "
            "evident by rising CVD divergence and positive L2 bid depth."
        ),
        lead_time_seconds_min=30,
        lead_time_seconds_max=1800,
        default_micro_conditions={
            "cvd_absorption_type": "BULLISH_ABSORPTION",
            "cvd_absorption_score_min": 0.65,
            "obi_score_min": 0.20,
        },
        default_falsification_criteria={
            "max_adverse_excursion_r": 1.2,
            "cvd_flips_negative": True,
            "time_stop_minutes": 60,
        },
    ),
    # 2. Hawkish Surprise -> Bearish CVD Absorption / Liquidity Drain
    "MEC_HAWKISH_SURPRISE_CVD_DRAIN": CausalMechanism(
        mechanism_id="MEC_HAWKISH_SURPRISE_CVD_DRAIN",
        family_id=ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION,
        name="Hawkish Rate Surprise with Bearish CVD Distribution",
        transmission_type=CausalTransmissionType.LIQUIDITY_WITHDRAWAL,
        primary_receptor=MicrostructureReceptorType.CVD_ABSORPTION,
        secondary_receptor=MicrostructureReceptorType.L2_ORDERBOOK_IMBALANCE,
        direction="BEARISH",
        economic_rationale=(
            "Unexpected rate hike or hawkish forward guidance prompts institutional risk-off. "
            "Aggressive market buy orders are met with passive institutional sell walls, resulting in bearish absorption."
        ),
        lead_time_seconds_min=30,
        lead_time_seconds_max=1800,
        default_micro_conditions={
            "cvd_absorption_type": "BEARISH_ABSORPTION",
            "cvd_absorption_score_min": 0.65,
            "obi_score_max": -0.20,
        },
        default_falsification_criteria={
            "max_adverse_excursion_r": 1.2,
            "cvd_flips_positive": True,
            "time_stop_minutes": 60,
        },
    ),
    # 3. CPI Beat / Growth Surprise -> SMC Fair Value Gap Invalidation
    "MEC_CPI_SURPRISE_FVG_BREAK": CausalMechanism(
        mechanism_id="MEC_CPI_SURPRISE_FVG_BREAK",
        family_id=ResearchFamilyId.INFLATION_GROWTH_SURPRISE,
        name="Inflation Print Deviation with SMC FVG Creation",
        transmission_type=CausalTransmissionType.VOLATILITY_EXPANSION,
        primary_receptor=MicrostructureReceptorType.SMC_FVG,
        secondary_receptor=MicrostructureReceptorType.SMC_LIQUIDITY_SWEEP,
        direction="BEARISH",
        economic_rationale=(
            "Hot inflation print prompts sudden repricing of rate-cut probabilities, creating an impulse selloff "
            "that leaves a Bearish Fair Value Gap (FVG) on 5m/15m charts. Pullbacks into the gap offer favorable short entries."
        ),
        lead_time_seconds_min=60,
        lead_time_seconds_max=3600,
        default_micro_conditions={
            "smc_pattern_type": "BEARISH_FVG",
            "smc_strength_min": 0.70,
            "is_favorable": True,
        },
        default_falsification_criteria={
            "price_closes_above_fvg_top": True,
            "max_adverse_excursion_r": 1.5,
            "time_stop_minutes": 120,
        },
    ),
    # 4. Regulatory Enforcement -> Liquidity Pool Sweep & Mean Reversion
    "MEC_REGULATORY_SHOCK_SWEEP_REVERSION": CausalMechanism(
        mechanism_id="MEC_REGULATORY_SHOCK_SWEEP_REVERSION",
        family_id=ResearchFamilyId.REGULATORY_POLICY_SHOCK,
        name="Regulatory Enforcement Panic Sweep with Mean Reversion",
        transmission_type=CausalTransmissionType.MEAN_REVERSION_DISLOCATION,
        primary_receptor=MicrostructureReceptorType.SMC_LIQUIDITY_SWEEP,
        secondary_receptor=MicrostructureReceptorType.L2_ORDERBOOK_IMBALANCE,
        direction="BULLISH",
        economic_rationale=(
            "Headline regulatory enforcement creates a localized liquidation cascade that sweeps prior session lows. "
            "Once sell stop orders are liquidated, aggressive buyer exhaustion leads to sharp mean reversion."
        ),
        lead_time_seconds_min=120,
        lead_time_seconds_max=7200,
        default_micro_conditions={
            "smc_pattern_type": "BULLISH_SWEEP",
            "smc_strength_min": 0.75,
            "obi_score_min": 0.15,
        },
        default_falsification_criteria={
            "new_low_established_post_sweep": True,
            "max_adverse_excursion_r": 1.0,
            "time_stop_minutes": 90,
        },
    ),
    # 5. Tech AI Earnings Beat -> High-Beta Momentum Breakout
    "MEC_TECH_EARNINGS_CRYPTO_BETA": CausalMechanism(
        mechanism_id="MEC_TECH_EARNINGS_CRYPTO_BETA",
        family_id=ResearchFamilyId.CROSS_ASSET_CONTAGION,
        name="Mega-Cap Tech CapEx Surge with Crypto Beta Momentum",
        transmission_type=CausalTransmissionType.MOMENTUM_ACCELERATION,
        primary_receptor=MicrostructureReceptorType.SMC_ORDER_BLOCK,
        secondary_receptor=MicrostructureReceptorType.L2_ORDERBOOK_IMBALANCE,
        direction="BULLISH",
        economic_rationale=(
            "Tech AI giant reports blowout capex guidance, lifting global equity risk appetite. "
            "Crypto assets experience positive orderbook imbalance and form Bullish Order Blocks on 15m/1h timeframes."
        ),
        lead_time_seconds_min=300,
        lead_time_seconds_max=7200,
        default_micro_conditions={
            "smc_pattern_type": "BULLISH_OB",
            "smc_strength_min": 0.70,
            "obi_score_min": 0.25,
        },
        default_falsification_criteria={
            "order_block_mitigated_and_broken": True,
            "max_adverse_excursion_r": 1.3,
            "time_stop_minutes": 180,
        },
    ),
}


def lookup_mechanism(mechanism_id: str) -> CausalMechanism | None:
    """Returns the CausalMechanism if registered, None otherwise."""
    return CAUSAL_MECHANISMS.get(mechanism_id)


def lookup_family(family_id: str | ResearchFamilyId) -> ResearchFamily | None:
    """Returns the ResearchFamily if registered, None otherwise."""
    if isinstance(family_id, str):
        try:
            family_id = ResearchFamilyId(family_id)
        except ValueError:
            return None
    return RESEARCH_FAMILIES.get(family_id)


def match_candidate_mechanisms(
    domain: str,
    headline: str,
    entities: list[str] | None = None,
) -> list[CausalMechanism]:
    """
    Identifies plausible candidate causal mechanisms based on incoming event domain,
    headline content, and extracted entities.
    """
    candidates: list[CausalMechanism] = []
    text = (headline or "").lower()
    entities = [e.lower() for e in (entities or [])]
    entity_str = " ".join(entities)

    for mech in CAUSAL_MECHANISMS.values():
        family = RESEARCH_FAMILIES[mech.family_id]
        if domain not in family.applicable_domains:
            continue

        # Match domain-specific triggers
        if mech.family_id == ResearchFamilyId.MACRO_LIQUIDITY_TRANSMISSION:
            if any(
                k in text or k in entity_str
                for k in ["rate", "fed", "powell", "ecb", "liquidity", "yield", "dovish", "cut"]
            ):
                candidates.append(mech)
            elif any(k in text or k in entity_str for k in ["hike", "hawkish", "tightening"]):
                candidates.append(mech)
        elif mech.family_id == ResearchFamilyId.INFLATION_GROWTH_SURPRISE:
            if any(
                k in text or k in entity_str
                for k in ["cpi", "ppi", "inflation", "nfp", "payrolls", "gdp", "jobs"]
            ):
                candidates.append(mech)
        elif mech.family_id == ResearchFamilyId.REGULATORY_POLICY_SHOCK:
            if any(
                k in text or k in entity_str
                for k in [
                    "sec",
                    "cftc",
                    "lawsuit",
                    "regulation",
                    "enforcement",
                    "ban",
                    "etf",
                    "approval",
                ]
            ):
                candidates.append(mech)
        elif mech.family_id == ResearchFamilyId.CROSS_ASSET_CONTAGION:
            if any(
                k in text or k in entity_str
                for k in [
                    "earnings",
                    "nvidia",
                    "nasdaq",
                    "s&p",
                    "capex",
                    "tech",
                    "apple",
                    "microsoft",
                ]
            ):
                candidates.append(mech)
        elif mech.family_id == ResearchFamilyId.ONCHAIN_STABLECOIN_DISLOCATION:
            if any(
                k in text or k in entity_str
                for k in [
                    "usdt",
                    "usdc",
                    "tether",
                    "stablecoin",
                    "depeg",
                    "inflow",
                    "outflow",
                    "bridge",
                ]
            ):
                candidates.append(mech)

    return candidates
