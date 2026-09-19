"""
core/kronos/research/friction_evaluator.py
=========================================
Milestone K9.8: 3-Tier Friction Stress Testing & Hypothetical Economic Utility Engine.
Applies Base, Conservative, and Stress friction hurdles to pre-registered,
frozen exposure mappings. Enforces strict separation from live execution.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.statistical_defense import ACTIVE_STATISTICAL_POLICY, DeflatedSharpeEngine


@dataclass(frozen=True)
class FrictionScenario:
    tier: str  # "BASE", "CONSERVATIVE", "STRESS"
    name: str
    maker_fee_bps: float
    taker_fee_bps: float
    half_spread_bps: float
    slippage_bps: float
    provenance: str
    is_empirical: bool
    maker_uncertainty_modeled: bool = True

    @property
    def roundtrip_taker_cost_bps(self) -> float:
        """2 * (taker_fee + half_spread + slippage)."""
        return 2.0 * (self.taker_fee_bps + self.half_spread_bps + self.slippage_bps)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["roundtrip_taker_cost_bps"] = self.roundtrip_taker_cost_bps
        return d


CANONICAL_FRICTION_SCENARIOS: dict[str, FrictionScenario] = {
    "BASE": FrictionScenario(
        tier="BASE",
        name="Tier 1 Institutional VIP",
        maker_fee_bps=2.0,
        taker_fee_bps=5.0,
        half_spread_bps=1.0,
        slippage_bps=0.5,
        provenance="Binance VIP 4 Spot schedule",
        is_empirical=True,
    ),
    "CONSERVATIVE": FrictionScenario(
        tier="CONSERVATIVE",
        name="Tier 2 Standard Retail",
        maker_fee_bps=2.0,
        taker_fee_bps=6.0,
        half_spread_bps=2.5,
        slippage_bps=2.0,
        provenance="Bybit VIP 0 Perpetual Futures",
        is_empirical=True,
    ),
    "STRESS": FrictionScenario(
        tier="STRESS",
        name="Tier 3 Crisis Liquidity Shock",
        maker_fee_bps=5.0,
        taker_fee_bps=10.0,
        half_spread_bps=5.0,
        slippage_bps=5.0,
        provenance="March 2020 / FTX Shock empirical stress envelope",
        is_empirical=False,
    ),
}


@dataclass
class FrictionTierResult:
    tier: str
    roundtrip_cost_bps: float
    gross_ev_bps: float
    net_ev_bps: float
    gross_sharpe: float
    net_sharpe: float
    deflated_sharpe_ratio: float
    trade_count: int
    win_rate: float
    max_drawdown_pct: float
    is_net_positive: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EconomicUtilityReport:
    model_id: str
    sample_size: int
    horizon_bars: int
    cumulative_trials: int
    tier_results: dict[str, FrictionTierResult]
    survival_verdict: str  # "PASS_ALL_TIERS", "PASS_CONSERVATIVE", "FAIL_FRICTION", "UNPROFITABLE"
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "sample_size": self.sample_size,
            "horizon_bars": self.horizon_bars,
            "cumulative_trials": self.cumulative_trials,
            "tier_results": {k: v.to_dict() for k, v in self.tier_results.items()},
            "survival_verdict": self.survival_verdict,
            "notes": self.notes,
        }


class FrictionEvaluator:
    """
    Evaluates hypothetical economic utility with pre-registered, un-optimized mappings.
    """

    def __init__(self):
        self.policy = ACTIVE_STATISTICAL_POLICY

    @staticmethod
    def map_probabilities_to_exposures(
        probabilities: np.ndarray,
        long_threshold: float = 0.55,
        short_threshold: float = 0.45,
    ) -> np.ndarray:
        """
        Pre-registered fixed rule mapping:
        p > 0.55 -> +1 (Long)
        p < 0.45 -> -1 (Short)
        else     ->  0 (Flat)
        """
        exposures = np.zeros(len(probabilities), dtype=np.float64)
        exposures[probabilities > long_threshold] = 1.0
        exposures[probabilities < short_threshold] = -1.0
        return exposures

    def evaluate_hypothetical_utility(
        self,
        probabilities: np.ndarray | list[float],
        realized_returns: np.ndarray | list[float],
        cumulative_trials: int = 1,
        model_id: str = "KRONOS_FORECAST",
        horizon_bars: int = 12,
    ) -> EconomicUtilityReport:
        """
        Simulates fixed-horizon hypothetical holding utility under Base, Conservative, and Stress frictions.
        """
        p_arr = np.asarray(probabilities, dtype=np.float64)
        r_arr = np.asarray(realized_returns, dtype=np.float64)
        n = len(p_arr)

        if n != len(r_arr):
            raise ValueError(f"Length mismatch: {n} probabilities vs {len(r_arr)} returns")

        # 1. Fixed pre-registered exposure mapping
        exposures = self.map_probabilities_to_exposures(p_arr)
        trade_mask = exposures != 0.0
        trade_count = int(np.sum(trade_mask))

        if trade_count < 10:
            return EconomicUtilityReport(
                model_id=model_id,
                sample_size=n,
                horizon_bars=horizon_bars,
                cumulative_trials=cumulative_trials,
                tier_results={},
                survival_verdict="UNPROFITABLE",
                notes=[
                    "Insufficient non-flat trading exposures (|p - 0.5| > 0.05) to evaluate utility"
                ],
            )

        # Gross return on active bars
        gross_returns = exposures * r_arr
        gross_active = gross_returns[trade_mask]
        gross_ev_bps = float(np.mean(gross_active)) * 10000.0

        # Annualization factor assuming 15m bars (35,040 bars/year)
        ann_factor = math.sqrt(35040 / max(1, horizon_bars))
        gross_std = float(np.std(gross_active)) if len(gross_active) > 1 else 0.01
        gross_sharpe = (float(np.mean(gross_active)) / max(1e-6, gross_std)) * ann_factor

        tier_results: dict[str, FrictionTierResult] = {}
        pass_count = 0

        for tier_key, scenario in CANONICAL_FRICTION_SCENARIOS.items():
            cost_decimal = scenario.roundtrip_taker_cost_bps / 10000.0
            net_returns = gross_active - cost_decimal
            net_ev_bps = float(np.mean(net_returns)) * 10000.0
            net_std = float(np.std(net_returns)) if len(net_returns) > 1 else 0.01
            net_sharpe = (float(np.mean(net_returns)) / max(1e-6, net_std)) * ann_factor

            # Max drawdown calculation
            cum_rets = np.cumsum(net_returns)
            peak = np.maximum.accumulate(cum_rets)
            dd = peak - cum_rets
            max_dd_pct = float(np.max(dd)) * 100.0 if len(dd) > 0 else 0.0

            win_rate = float(np.mean(net_returns > 0.0))
            is_pos = net_ev_bps > 0.0
            if is_pos:
                pass_count += 1

            # Deflated Sharpe Ratio calculation
            dsr_report = DeflatedSharpeEngine.calculate_dsr(
                strategy_id=f"{model_id}_{tier_key}",
                observed_returns=net_returns,
                annualized_sharpe=net_sharpe,
                cumulative_trials_N=cumulative_trials,
                policy=self.policy,
            )

            tier_results[tier_key] = FrictionTierResult(
                tier=tier_key,
                roundtrip_cost_bps=scenario.roundtrip_taker_cost_bps,
                gross_ev_bps=round(gross_ev_bps, 2),
                net_ev_bps=round(net_ev_bps, 2),
                gross_sharpe=round(gross_sharpe, 2),
                net_sharpe=round(net_sharpe, 2),
                deflated_sharpe_ratio=round(dsr_report.deflated_sharpe_ratio, 4),
                trade_count=trade_count,
                win_rate=round(win_rate, 4),
                max_drawdown_pct=round(max_dd_pct, 2),
                is_net_positive=is_pos,
                status="VALID",
            )

        if pass_count == 3:
            verdict = "PASS_ALL_TIERS"
        elif (
            tier_results.get("CONSERVATIVE", None) and tier_results["CONSERVATIVE"].is_net_positive
        ):
            verdict = "PASS_CONSERVATIVE"
        elif tier_results.get("BASE", None) and tier_results["BASE"].is_net_positive:
            verdict = "FAIL_FRICTION"  # Survives only Base, fails Conservative
        else:
            verdict = "UNPROFITABLE"

        notes = [
            f"Evaluated {trade_count} active signals over {n} observations with horizon H={horizon_bars}",
            f"Trial budget penalty applied across K={cumulative_trials} cumulative experiments",
            "CRITICAL: Results represent HYPOTHETICAL research utility only, not live execution performance",
        ]

        return EconomicUtilityReport(
            model_id=model_id,
            sample_size=n,
            horizon_bars=horizon_bars,
            cumulative_trials=cumulative_trials,
            tier_results=tier_results,
            survival_verdict=verdict,
            notes=notes,
        )


friction_evaluator = FrictionEvaluator()
