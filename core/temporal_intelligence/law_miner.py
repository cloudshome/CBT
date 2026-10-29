"""
core/temporal_intelligence/law_miner.py
=======================================
Mathematical Law Discovery Engine for Temporal Price Action (Milestone 22).

Enforces:
- Chronological train/test split with purge/embargo buffer to eliminate label leakage.
- Effective sample size estimation accounting for autocorrelation (Neft).
- Multiple hypothesis testing correction using Benjamini-Hochberg FDR control.
- Out-of-sample Brier Skill Score (BSS) evaluation relative to base rate.
- 3-tier economic friction modeling (Base: 14 bps, Conservative: 24 bps, Stress: 40 bps).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from scipy import stats

from core.temporal_intelligence.features import ZeroLookaheadFeatureExtractor
from core.temporal_intelligence.models import (
    ForecastHorizon,
    PriceActionLaw,
    PriceActionLawStatus,
    TemporalFeatureVector,
)

logger = logging.getLogger("sky.temporal.law_miner")

# 3-Tier Round-Trip Friction (fee + slippage across entry and exit)
FRICTION_BASE_PCT = 0.14          # 14 bps
FRICTION_CONSERVATIVE_PCT = 0.24  # 24 bps
FRICTION_STRESS_PCT = 0.40        # 40 bps


class MathematicalLawMiner:
    """Discovers and scientifically validates conditional price-action laws from historical data."""

    def __init__(
        self,
        candles: list[dict[str, Any]],
        train_ratio: float = 0.70,
        embargo_bars: int = 8,
    ) -> None:
        self.candles = candles
        self.total_bars = len(candles)
        self.train_split_idx = int(self.total_bars * train_ratio)
        self.test_start_idx = self.train_split_idx + embargo_bars
        self._precompute_features()

    def _precompute_features(self) -> None:
        """Precomputes point-in-time features strictly using past bars."""
        self.features: list[TemporalFeatureVector | None] = [None] * self.total_bars
        for i in range(20, self.total_bars):
            self.features[i] = ZeroLookaheadFeatureExtractor.extract_features(self.candles, i)

    def evaluate_predeclared_laws(self) -> list[PriceActionLaw]:
        """
        Evaluates the 5 pre-declared price-action hypotheses against historical data.
        Applies Benjamini-Hochberg FDR adjustment across all 5 candidate tests.
        """
        hypotheses = [
            (
                "LAW_01_MOMENTUM_CONT",
                "Momentum Continuation After Volume Surge",
                "15m return >= +0.40% with RVOL >= 1.5x predicts next 15m continuation >= +0.30%",
                lambda f: f.return_1bar_pct >= 0.40 and f.relative_volume >= 1.5,
                ForecastHorizon.H_15M,
                1,  # 1 bar forward
                0.30,
            ),
            (
                "LAW_02_EXHAUSTION_REVERSAL",
                "Exhaustion Reversal After Upper Wick Rejection",
                "15m pump >= +0.60% with upper wick ratio >= 0.40 predicts next 15m reversal <= -0.30%",
                lambda f: f.return_1bar_pct >= 0.60 and f.upper_wick_ratio >= 0.40,
                ForecastHorizon.H_15M,
                1,
                -0.30,  # Negative threshold (dump)
            ),
            (
                "LAW_03_BREAKOUT_EXPANSION",
                "Breakout Expansion From 20-Bar High",
                "Within 0.05% of 20-bar high with RVOL >= 1.8x predicts next 30m continuation >= +0.50%",
                lambda f: f.distance_to_swing_high_pct <= 0.05 and f.relative_volume >= 1.8,
                ForecastHorizon.H_30M,
                2,  # 2 bars forward (30m)
                0.50,
            ),
            (
                "LAW_04_VOLATILITY_EXPANSION",
                "Volatility Compression Preceding Expansion",
                "Compressed candle (volatility ratio <= 0.60 and body <= 0.40) predicts 1h absolute move >= 0.70%",
                lambda f: f.volatility_ratio <= 0.60 and f.body_to_range_ratio <= 0.40,
                ForecastHorizon.H_1H,
                4,  # 4 bars forward (1h)
                0.70,
            ),
            (
                "LAW_05_SWEEP_REVERSAL",
                "Liquidity Sweep Reversal At Swing Low",
                "Lower wick ratio >= 0.50 near 20-bar low predicts next 15m bounce >= +0.30%",
                lambda f: f.lower_wick_ratio >= 0.50 and f.distance_to_swing_low_pct <= 0.10,
                ForecastHorizon.H_15M,
                1,
                0.30,
            ),
        ]

        evaluated_laws: list[dict[str, Any]] = []

        # 1. Mine and compute raw p-values for all candidate hypotheses
        for law_id, name, desc, cond_fn, horizon, horizon_bars, threshold in hypotheses:
            res = self._mine_single_hypothesis(
                law_id, name, desc, cond_fn, horizon, horizon_bars, threshold
            )
            evaluated_laws.append(res)

        # 2. Benjamini-Hochberg False Discovery Rate (FDR) Adjustment
        evaluated_laws.sort(key=lambda x: x["raw_p_value"])
        m = len(evaluated_laws)
        for i, item in enumerate(evaluated_laws):
            rank = i + 1
            adj_p = min(1.0, item["raw_p_value"] * (m / rank))
            item["adjusted_p_value"] = round(adj_p, 5)

        # 3. Build validated PriceActionLaw models
        final_laws: list[PriceActionLaw] = []
        for item in evaluated_laws:
            # Classification Gate:
            # Must satisfy: N_eff >= 30, adj_p < 0.05, BSS_test > 0, and Base Expectancy > 0.10R
            is_valid = (
                item["effective_sample_size_train"] >= 30.0
                and item["adjusted_p_value"] < 0.05
                and item["brier_skill_score_test"] > 0.0
                and item["net_expectancy_r_base"] >= 0.10
            )

            status = PriceActionLawStatus.VALIDATED if is_valid else (
                PriceActionLawStatus.INCONCLUSIVE if item["effective_sample_size_train"] < 30.0
                else PriceActionLawStatus.REJECTED
            )

            rejection_reason = None
            if not is_valid:
                reasons = []
                if item["effective_sample_size_train"] < 30.0:
                    reasons.append(f"Insufficient Neff ({item['effective_sample_size_train']:.1f} < 30)")
                if item["adjusted_p_value"] >= 0.05:
                    reasons.append(f"FDR adj p-value not significant ({item['adjusted_p_value']:.4f} >= 0.05)")
                if item["brier_skill_score_test"] <= 0.0:
                    reasons.append(f"Failed out-of-sample BSS ({item['brier_skill_score_test']:.3f} <= 0)")
                if item["net_expectancy_r_base"] < 0.10:
                    reasons.append(f"Net expectancy below 0.10R ({item['net_expectancy_r_base']:.2f}R)")
                rejection_reason = "; ".join(reasons)

            law = PriceActionLaw(
                law_id=item["law_id"],
                name=item["name"],
                description=item["description"],
                condition_expr=item["condition_expr"],
                target_horizon=item["target_horizon"],
                movement_threshold_pct=item["threshold"],
                sample_size_train=item["n_train"],
                effective_sample_size_train=item["effective_sample_size_train"],
                base_rate_pump_pct=item["base_rate_train"],
                conditional_pump_pct_train=item["cond_rate_train"],
                lift_train=item["lift_train"],
                p_value=item["raw_p_value"],
                adjusted_p_value_fdr=item["adjusted_p_value"],
                sample_size_test=item["n_test"],
                conditional_pump_pct_test=item["cond_rate_test"],
                lift_test=item["lift_test"],
                brier_score_test=item["brier_score_test"],
                brier_skill_score_test=item["brier_skill_score_test"],
                net_expectancy_r_base=item["net_expectancy_r_base"],
                net_expectancy_r_conservative=item["net_expectancy_r_conservative"],
                net_expectancy_r_stress=item["net_expectancy_r_stress"],
                status=status,
                rejection_reason=rejection_reason,
            )
            final_laws.append(law)

        return final_laws

    def _mine_single_hypothesis(
        self,
        law_id: str,
        name: str,
        desc: str,
        cond_fn: Callable[[TemporalFeatureVector], bool],
        horizon: ForecastHorizon,
        horizon_bars: int,
        threshold: float,
    ) -> dict[str, Any]:
        """Evaluates a single hypothesis across in-sample train and sealed out-of-sample test."""
        # 1. In-Sample Train Evaluation
        train_matches = []
        train_all_targets = []
        is_absolute_target = (law_id == "LAW_04_VOLATILITY_EXPANSION")
        is_dump_target = (threshold < 0)

        for i in range(20, self.train_split_idx - horizon_bars):
            feat = self.features[i]
            if not feat:
                continue

            # Forward outcome return:
            p_cur = float(self.candles[i]["close"])
            p_fwd = float(self.candles[i + horizon_bars]["close"])
            ret_fwd = ((p_fwd - p_cur) / p_cur) * 100.0

            if is_absolute_target:
                hit = 1 if abs(ret_fwd) >= threshold else 0
            elif is_dump_target:
                hit = 1 if ret_fwd <= threshold else 0
            else:
                hit = 1 if ret_fwd >= threshold else 0

            train_all_targets.append(hit)
            if cond_fn(feat):
                train_matches.append((hit, ret_fwd))

        n_train = len(train_matches)
        base_rate_train = (sum(train_all_targets) / len(train_all_targets) * 100.0) if train_all_targets else 50.0
        success_train = sum(m[0] for m in train_matches)
        cond_rate_train = (success_train / n_train * 100.0) if n_train > 0 else 0.0
        lift_train = round(cond_rate_train / base_rate_train, 2) if base_rate_train > 0 else 1.0

        # Effective Sample Size (Neft) with lag-1 autocorrelation
        rho1 = 0.0
        if n_train > 5:
            hits = [m[0] for m in train_matches]
            mean_h = sum(hits) / len(hits)
            var_h = sum((x - mean_h) ** 2 for x in hits)
            if var_h > 0:
                cov1 = sum((hits[j] - mean_h) * (hits[j - 1] - mean_h) for j in range(1, len(hits)))
                rho1 = max(-0.9, min(0.9, cov1 / var_h))

        raw_neff = n_train * max(0.1, (1.0 - rho1) / (1.0 + rho1)) if n_train > 0 else 0.0
        neff_train = round(min(float(n_train), raw_neff), 1)

        # Binomial test p-value against base rate
        p0 = base_rate_train / 100.0
        p_val = 1.0
        if n_train >= 5 and 0.0 < p0 < 1.0:
            res = stats.binomtest(k=success_train, n=n_train, p=p0, alternative="two-sided")
            p_val = float(res.pvalue)

        # 2. Sealed Out-of-Sample Test Evaluation
        test_matches = []
        test_all_targets = []
        for i in range(self.test_start_idx, self.total_bars - horizon_bars):
            feat = self.features[i]
            if not feat:
                continue

            p_cur = float(self.candles[i]["close"])
            p_fwd = float(self.candles[i + horizon_bars]["close"])
            ret_fwd = ((p_fwd - p_cur) / p_cur) * 100.0

            if is_absolute_target:
                hit = 1 if abs(ret_fwd) >= threshold else 0
            elif is_dump_target:
                hit = 1 if ret_fwd <= threshold else 0
            else:
                hit = 1 if ret_fwd >= threshold else 0

            test_all_targets.append(hit)
            if cond_fn(feat):
                test_matches.append((hit, ret_fwd))

        n_test = len(test_matches)
        base_rate_test = (sum(test_all_targets) / len(test_all_targets) * 100.0) if test_all_targets else 50.0
        success_test = sum(m[0] for m in test_matches)
        cond_rate_test = (success_test / n_test * 100.0) if n_test > 0 else 0.0
        lift_test = round(cond_rate_test / base_rate_test, 2) if base_rate_test > 0 else 1.0

        # Brier Score & Brier Skill Score on Test
        p_model = cond_rate_train / 100.0 if n_train > 0 else p0
        p_base = base_rate_test / 100.0

        bs_model = (
            sum((p_model - m[0]) ** 2 for m in test_matches) / n_test
            if n_test > 0
            else 0.25
        )
        bs_base = (
            sum((p_base - m[0]) ** 2 for m in test_matches) / n_test
            if n_test > 0
            else 0.25
        )
        bss_test = round(1.0 - (bs_model / bs_base), 3) if bs_base > 0 else 0.0

        # Economic Expectancy in R after 3-tier friction:
        # Risk unit R is defined as the movement threshold (e.g. 0.30% or 0.50%)
        risk_unit = abs(threshold)
        returns = [m[1] if not is_dump_target else -m[1] for m in test_matches]
        mean_ret = sum(returns) / len(returns) if returns else 0.0

        exp_base = round((mean_ret - FRICTION_BASE_PCT) / risk_unit, 2) if risk_unit > 0 else 0.0
        exp_cons = round((mean_ret - FRICTION_CONSERVATIVE_PCT) / risk_unit, 2) if risk_unit > 0 else 0.0
        exp_stress = round((mean_ret - FRICTION_STRESS_PCT) / risk_unit, 2) if risk_unit > 0 else 0.0

        return {
            "law_id": law_id,
            "name": name,
            "description": desc,
            "condition_expr": desc,
            "target_horizon": horizon,
            "threshold": threshold,
            "n_train": n_train,
            "effective_sample_size_train": neff_train,
            "base_rate_train": round(base_rate_train, 1),
            "cond_rate_train": round(cond_rate_train, 1),
            "lift_train": lift_train,
            "raw_p_value": round(p_val, 5),
            "n_test": n_test,
            "cond_rate_test": round(cond_rate_test, 1),
            "lift_test": lift_test,
            "brier_score_test": round(bs_model, 4),
            "brier_skill_score_test": bss_test,
            "net_expectancy_r_base": exp_base,
            "net_expectancy_r_conservative": exp_cons,
            "net_expectancy_r_stress": exp_stress,
        }
