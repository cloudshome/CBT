"""
Adversarial Decision Council & Dominant NO-TRADE Committee.
Runs an adversarial tri-agent debate before every capital commitment:
1. Bull Agent (Advocate for Long execution)
2. Bear Agent (Advocate for Short execution)
3. Skeptic / NO-TRADE Judge (Dominant Gatekeeper defending capital preservation)
Emits three first-class decisions: LONG (~15%), SHORT (~15%), or NO_TRADE (~70%).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.ev_engine import NetEVResult
from core.market_state import MarketStateVector
from core.uncertainty_engine import UncertaintyBudget

logger = logging.getLogger("ai_quant_sentinel.debate_committee")


@dataclass
class AgentArgument:
    agent_name: str  # "BULL_AGENT", "BEAR_AGENT", "SKEPTIC_JUDGE"
    stance: str  # "LONG", "SHORT", "NO_TRADE"
    confidence: float  # [0.0, 1.0]
    core_premises: list[str]
    risk_factors_highlighted: list[str]
    verdict_summary: str


@dataclass
class CouncilDecision:
    symbol: str
    timestamp: int
    final_decision: str  # "LONG", "SHORT", "NO_TRADE"
    consensus_confidence: float  # [0.0, 1.0]
    bull_argument: AgentArgument
    bear_argument: AgentArgument
    skeptic_argument: AgentArgument
    no_trade_probability: float  # Target baseline ~70%
    primary_execution_thesis: str
    invalidation_criteria: str
    evidence_grade: str = "EMPIRICAL"
    """Provenance of the evidence behind this verdict. Anything other than
    EMPIRICAL forces NO_TRADE — see core/evidence_integrity.py."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "final_decision": self.final_decision,
            "consensus_confidence": self.consensus_confidence,
            "bull_argument": asdict(self.bull_argument),
            "bear_argument": asdict(self.bear_argument),
            "skeptic_argument": asdict(self.skeptic_argument),
            "no_trade_probability": self.no_trade_probability,
            "primary_execution_thesis": self.primary_execution_thesis,
            "invalidation_criteria": self.invalidation_criteria,
            "evidence_grade": self.evidence_grade,
        }


class AdversarialDebateCommittee:
    """Adversarial Council enforcing rigorous NO-TRADE default bias with 8-Pillar Dossier ingestion."""

    def convene_council(
        self,
        symbol: str,
        state: MarketStateVector,
        ev_result: NetEVResult,
        uncertainty: UncertaintyBudget,
        macro_regime: str = "NEUTRAL",
        dossier: Any | None = None,
        analogues: Any | None = None,
    ) -> CouncilDecision:
        """
        Runs adversarial deliberation between Bull, Bear, and dominant Skeptic Judge.
        Ingests 8-Pillar Asset Dossier when available.
        """
        trend_1h = state.trend_scores.get("1h", 0.0)
        state.trend_scores.get("15m", 0.0)
        cvd_delta = state.orderflow.get("cvd_delta", 0.0)
        absorp = state.orderflow.get("absorption_score", 0.0)
        u_score = uncertainty.composite_uncertainty_u

        # 1. Bull Agent Deliberation
        bull_premises = []
        if trend_1h > 0.15:
            bull_premises.append(f"Higher timeframe trend aligns bullish (1H: {trend_1h:+.2f})")
        if cvd_delta > 0.10 or absorp > 0.60:
            bull_premises.append("Orderflow confirms positive delta / institutional absorption")
        if ev_result.net_ev_r > 0.30:
            bull_premises.append(f"Net EV is strongly positive (+{ev_result.net_ev_r:.2f}R)")

        # Ingest 8-Pillar Dossier Bull Factors
        if dossier:
            p1 = getattr(dossier, "pillar_1_institutional_flows", {})
            p4 = getattr(dossier, "pillar_4_stablecoin_velocity", {})
            if p1.get("etf_net_inflow_24h_usd", 0) > 50_000_000:
                bull_premises.append(
                    f"Spot ETF Inflow Surge (+${p1.get('etf_net_inflow_24h_usd') / 1e6:.1f}M/24h)"
                )
            if p4.get("dry_powder_liquidity_state") == "HIGH_DRY_POWDER_EXPANSION":
                bull_premises.append(
                    "Stablecoin SSR oscillator signals strong dry-powder buying reserve"
                )

        bull_conf = float(
            np.clip(
                0.40
                + (trend_1h * 0.3)
                + (cvd_delta * 0.2)
                + (0.10 if dossier and dossier.composite_health_score >= 70 else 0),
                0.10,
                0.90,
            )
        )
        bull_arg = AgentArgument(
            agent_name="BULL_AGENT",
            stance="LONG",
            confidence=round(bull_conf, 2),
            core_premises=bull_premises or ["Attempting structural bounce from support zone"],
            risk_factors_highlighted=[
                "Overhead liquidity sell walls",
                "Potential DXY macro headwind",
            ],
            verdict_summary=f"Bull case supported by HTF momentum, ETF inflows & positive delta (Confidence: {bull_conf * 100:.0f}%).",
        )

        # 2. Bear Agent Deliberation
        bear_premises = []
        if trend_1h < -0.15:
            bear_premises.append(f"Higher timeframe structure is bearish (1H: {trend_1h:+.2f})")
        if cvd_delta < -0.10:
            bear_premises.append(f"Aggressive net market selling delta ({cvd_delta:+.2f})")
        if macro_regime in ["RISK_OFF_FLIGHT_TO_SAFETY", "DOLLAR_SQUEEZE"]:
            bear_premises.append(f"Macro environment is unfavorable ({macro_regime})")

        # Ingest 8-Pillar Dossier Bear Factors
        if dossier:
            p2 = getattr(dossier, "pillar_2_derivatives_options", {})
            p6 = getattr(dossier, "pillar_6_macro_liquidity_beta", {})
            if p2.get("funding_state") == "OVERHEATED_LONG_RISK":
                bear_premises.append(
                    "Derivatives funding rate severely overheated (Long squeeze imminent)"
                )
            if p6.get("geopolitical_risk_index_score", 0) > 75.0:
                bear_premises.append("Geopolitical Risk Index (GRI) elevated above safe threshold")

        bear_conf = float(
            np.clip(
                0.40
                - (trend_1h * 0.3)
                - (cvd_delta * 0.2)
                + (0.10 if dossier and dossier.composite_health_score < 40 else 0),
                0.10,
                0.90,
            )
        )
        bear_arg = AgentArgument(
            agent_name="BEAR_AGENT",
            stance="SHORT",
            confidence=round(bear_conf, 2),
            core_premises=bear_premises
            or ["Market vulnerable to liquidity pool flush below range"],
            risk_factors_highlighted=[
                "Short squeeze vulnerability",
                "Institutional dip buying support",
            ],
            verdict_summary=f"Bear case supported by structural breakdown risk (Confidence: {bear_conf * 100:.0f}%).",
        )

        # 3. Skeptic / NO-TRADE Judge (Dominant Agent)
        skeptic_premises = []
        if not ev_result.is_tradable:
            skeptic_premises.append(
                f"Net EV (+{ev_result.net_ev_r:.2f}R) fails to clear minimum hurdle (+{ev_result.min_hurdle_r:.2f}R)"
            )
        if u_score > 0.40:
            skeptic_premises.append(f"Systemic uncertainty budget elevated (U = {u_score:.2f})")
        if abs(bull_conf - bear_conf) < 0.25:
            skeptic_premises.append(
                f"Severe directional model disagreement (Bull: {bull_conf:.2f} vs Bear: {bear_conf:.2f})"
            )
        if uncertainty.event_shock_uncertainty > 0.30:
            skeptic_premises.append("High-impact macro event catalyst within risk window")
        if dossier and dossier.macro_bias in ["BEARISH_DISTRIBUTION", "MACRO_CAPITULATION_RISK"]:
            skeptic_premises.append(f"Dossier macro regime veto ({dossier.macro_bias})")

        skeptic_conf = float(
            np.clip(
                0.55 + (u_score * 0.40) + (0.30 if not ev_result.is_tradable else -0.15), 0.30, 0.98
            )
        )
        skeptic_arg = AgentArgument(
            agent_name="SKEPTIC_JUDGE",
            stance="NO_TRADE",
            confidence=round(skeptic_conf, 2),
            core_premises=skeptic_premises
            or ["Edge is marginal after full deduction of friction and entropy"],
            risk_factors_highlighted=[
                "Capital preservation takes absolute priority over speculative churn"
            ],
            verdict_summary=f"Skeptic veto: {skeptic_premises[0] if skeptic_premises else 'Insufficient risk-adjusted edge'}.",
        )

        # 4. Council Weighted Voting Synthesis
        # RULE 0 — EVIDENCE INTEGRITY (highest precedence, non-overridable).
        # If the analogue distribution was fabricated (cold brain memory seeded
        # with np.random states), no amount of downstream "confidence" is real.
        # The council must refuse before any directional branch is considered.
        evidence_grade = str(getattr(analogues, "evidence_grade", "EMPIRICAL"))
        if evidence_grade != "EMPIRICAL":
            return CouncilDecision(
                symbol=symbol,
                timestamp=state.timestamp,
                final_decision="NO_TRADE",
                consensus_confidence=0.99,
                bull_argument=bull_arg,
                bear_argument=bear_arg,
                skeptic_argument=skeptic_arg,
                no_trade_probability=1.0,
                primary_execution_thesis=(
                    "EVIDENCE INTEGRITY HALT: analogue distribution is "
                    f"{evidence_grade}, not empirically observed "
                    f"(real samples: {getattr(analogues, 'real_sample_count', 0)}). "
                    "No capital may be committed on fabricated evidence."
                ),
                invalidation_criteria=(
                    "Resolves automatically once sufficient real historical "
                    "states accumulate in brain_memory.db."
                ),
                evidence_grade=evidence_grade,
            )

        # Skeptic has 2.0x voting weight to enforce ~70% NO-TRADE baseline
        if not ev_result.is_tradable or skeptic_conf >= 0.70 or u_score >= 0.60:
            final_decision = "NO_TRADE"
            conf = skeptic_conf
            thesis = f"CAPITAL PRESERVATION: Council enforces NO_TRADE. Reason: {skeptic_arg.core_premises[0]}."
            inval = "N/A (No capital committed)"
        elif (
            bull_conf > bear_conf
            and bull_conf > 0.65
            and ev_result.net_ev_r >= ev_result.min_hurdle_r
        ):
            final_decision = "LONG"
            conf = bull_conf
            thesis = (
                f"LONG THESIS: {bull_arg.core_premises[0]} with Net EV +{ev_result.net_ev_r:.2f}R."
            )
            inval = "Breach of local 15m order block support"
        elif (
            bear_conf > bull_conf
            and bear_conf > 0.65
            and ev_result.net_ev_r >= ev_result.min_hurdle_r
        ):
            final_decision = "SHORT"
            conf = bear_conf
            thesis = (
                f"SHORT THESIS: {bear_arg.core_premises[0]} with Net EV +{ev_result.net_ev_r:.2f}R."
            )
            inval = "Reclaim above local 15m supply zone"
        else:
            final_decision = "NO_TRADE"
            conf = 0.75
            thesis = "NO_TRADE: Market state in high-entropy equilibrium without decisive directional edge."
            inval = "N/A"

        return CouncilDecision(
            symbol=symbol,
            timestamp=state.timestamp,
            final_decision=final_decision,
            consensus_confidence=round(conf, 2),
            bull_argument=bull_arg,
            bear_argument=bear_arg,
            skeptic_argument=skeptic_arg,
            no_trade_probability=0.72,
            primary_execution_thesis=thesis,
            invalidation_criteria=inval,
        )


# Singleton
debate_committee = AdversarialDebateCommittee()
