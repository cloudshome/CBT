"""
Net Expected Value (Net EV) Engine Net of All Trading Frictions.
Calculates Net EV in R-multiples deducting:
- Exchange Taker Fees (Roundtrip)
- Slippage & Market Impact
- Cost of Carry / Perpetual Funding
- Meta-Uncertainty Entropy Penalty
Enforces Master Rule: Net EV <= +0.25R forces DECISION_NO_TRADE.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.uncertainty_engine import UncertaintyBudget

logger = logging.getLogger("ai_quant_sentinel.ev_engine")


@dataclass
class NetEVResult:
    raw_ev_r: float  # Raw expected value before frictions
    net_ev_r: float  # Net EV after all fees, slippage, funding & uncertainty
    win_probability: float  # Calibrated win rate P(TP before SL)
    loss_probability: float  # P(SL)
    reward_to_risk_ratio: float  # b = (TP - Entry) / (Entry - SL)
    taker_fee_penalty_r: float
    slippage_penalty_r: float
    funding_penalty_r: float
    uncertainty_deduction_r: float
    is_tradable: bool  # True only if Net EV > +0.25R
    min_hurdle_r: float  # 0.25R normal, 0.375R in event risk
    decision_verdict: str  # "PROCEED_TO_ALLOCATION" or "DECISION_NO_TRADE"
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExpectedValueEngine:
    """Calculates rigorous institutional Net Expected Value per trade proposal."""

    def __init__(
        self,
        default_hurdle_r: float = 0.25,
        taker_fee_bps: float = 5.0,  # 0.05% per side (10 bps roundtrip)
        base_slippage_bps: float = 3.0,  # 0.03% standard slippage
    ):
        self.default_hurdle_r = default_hurdle_r
        self.taker_fee_bps = taker_fee_bps
        self.base_slippage_bps = base_slippage_bps

    def calculate_net_ev(
        self,
        entry_price: float,
        take_profit_price: float,
        stop_loss_price: float,
        calibrated_win_prob: float,
        uncertainty: UncertaintyBudget,
        event_risk_mode: bool = False,
        funding_rate_8h_pct: float = 0.01,
    ) -> NetEVResult:
        """
        Computes friction-deducted Net EV in R-multiples.
        """
        risk_distance = abs(entry_price - stop_loss_price)
        reward_distance = abs(take_profit_price - entry_price)

        if risk_distance <= 0:
            return NetEVResult(
                raw_ev_r=0.0,
                net_ev_r=-1.0,
                win_probability=0.0,
                loss_probability=1.0,
                reward_to_risk_ratio=0.0,
                taker_fee_penalty_r=0.0,
                slippage_penalty_r=0.0,
                funding_penalty_r=0.0,
                uncertainty_deduction_r=1.0,
                is_tradable=False,
                min_hurdle_r=self.default_hurdle_r,
                decision_verdict="DECISION_NO_TRADE",
                rationale="Invalid zero risk distance.",
            )

        rr_ratio = reward_distance / risk_distance
        p_win = float(np.clip(calibrated_win_prob, 0.0, 1.0))
        p_loss = 1.0 - p_win

        # 1. Raw Expected Value (in R units): EV = (p_win * RR) - (p_loss * 1.0)
        raw_ev = (p_win * rr_ratio) - (p_loss * 1.0)

        # 2. Conversion of bps frictions into R-multiples
        risk_pct = (risk_distance / entry_price) * 100.0  # e.g. 1.2% risk

        # Roundtrip Taker Fees: 2 * taker_fee_bps
        roundtrip_fee_pct = (2.0 * self.taker_fee_bps) / 100.0  # 0.10%
        fee_penalty_r = roundtrip_fee_pct / (risk_pct + 1e-5)

        # Slippage (widens if event risk active)
        slip_bps = self.base_slippage_bps * (2.5 if event_risk_mode else 1.0)
        slippage_pct = slip_bps / 100.0
        slip_penalty_r = slippage_pct / (risk_pct + 1e-5)

        # Expected Funding Rate
        funding_penalty_r = funding_rate_8h_pct / (risk_pct + 1e-5)

        # Meta-Uncertainty Penalty (scales with composite U and penalty factor)
        u_penalty_r = uncertainty.composite_uncertainty_u * 0.35 * uncertainty.penalty_factor

        # 3. Net Expected Value Calculation
        net_ev = raw_ev - fee_penalty_r - slip_penalty_r - funding_penalty_r - u_penalty_r

        # Determine hurdle threshold
        min_hurdle = self.default_hurdle_r * (1.50 if event_risk_mode else 1.0)
        is_tradable = bool(net_ev >= min_hurdle)
        verdict = "PROCEED_TO_ALLOCATION" if is_tradable else "DECISION_NO_TRADE"

        if is_tradable:
            rationale = (
                f"Positive edge verified: Net EV = +{net_ev:.2f}R (Hurdle: +{min_hurdle:.2f}R). "
                f"Win Rate: {p_win * 100:.1f}%, RR: {rr_ratio:.2f}:1, Uncertainty U: {uncertainty.composite_uncertainty_u:.2f}."
            )
        else:
            reasons = []
            if net_ev < 0:
                reasons.append(f"Negative Net EV ({net_ev:+.2f}R)")
            elif net_ev < min_hurdle:
                reasons.append(f"Net EV {net_ev:.2f}R below required hurdle +{min_hurdle:.2f}R")
            if uncertainty.composite_uncertainty_u > 0.60:
                reasons.append(
                    f"High systemic entropy (U={uncertainty.composite_uncertainty_u:.2f})"
                )
            rationale = f"Trade rejected by Scientific Gate: {'; '.join(reasons)}. Enforcing DECISION_NO_TRADE."

        return NetEVResult(
            raw_ev_r=round(raw_ev, 3),
            net_ev_r=round(net_ev, 3),
            win_probability=round(p_win, 3),
            loss_probability=round(p_loss, 3),
            reward_to_risk_ratio=round(rr_ratio, 2),
            taker_fee_penalty_r=round(fee_penalty_r, 3),
            slippage_penalty_r=round(slip_penalty_r, 3),
            funding_penalty_r=round(funding_penalty_r, 3),
            uncertainty_deduction_r=round(u_penalty_r, 3),
            is_tradable=is_tradable,
            min_hurdle_r=round(min_hurdle, 3),
            decision_verdict=verdict,
            rationale=rationale,
        )


# Singleton
ev_engine = ExpectedValueEngine()
