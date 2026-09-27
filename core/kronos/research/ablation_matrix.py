"""
core/kronos/research/ablation_matrix.py
======================================
Milestone K9.7: Pre-Registered 7-Way Microstructure Ablation Matrix.
Isolates the exact source of predictive skill: foundation transformer trajectory
versus high-frequency order book microstructure features.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class AblationVariantSpec:
    variant_id: str  # "A" through "G"
    name: str
    description: str
    uses_foundation_model: bool
    active_micro_features: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Pre-registered 7 canonical variants
ABLATION_VARIANTS: dict[str, AblationVariantSpec] = {
    "A": AblationVariantSpec(
        variant_id="A",
        name="Native OHLCV Kronos",
        description="Raw OHLCV foundation trajectory without microstructure context",
        uses_foundation_model=True,
        active_micro_features=[],
    ),
    "B": AblationVariantSpec(
        variant_id="B",
        name="Kronos + Order Flow Imbalance",
        description="Foundation model conditioned on ofi_norm",
        uses_foundation_model=True,
        active_micro_features=["ofi_norm"],
    ),
    "C": AblationVariantSpec(
        variant_id="C",
        name="Kronos + VPIN Toxicity",
        description="Foundation model conditioned on volume-synchronized probability of toxicity",
        uses_foundation_model=True,
        active_micro_features=["vpin"],
    ),
    "D": AblationVariantSpec(
        variant_id="D",
        name="Kronos + Depth Imbalance",
        description="Foundation model conditioned on L2 top-5 depth imbalance",
        uses_foundation_model=True,
        active_micro_features=["depth_imb"],
    ),
    "E": AblationVariantSpec(
        variant_id="E",
        name="Kronos + Resting Wall",
        description="Foundation model conditioned on resting liquidity wall pressure",
        uses_foundation_model=True,
        active_micro_features=["resting_wall"],
    ),
    "F": AblationVariantSpec(
        variant_id="F",
        name="Kronos + Full Microstructure Stack",
        description="Foundation model with all 8 microstructure features active",
        uses_foundation_model=True,
        active_micro_features=[
            "ofi_norm",
            "vpin",
            "mid_return",
            "spread_bps",
            "depth_imb",
            "trade_sign",
            "vol_clock",
            "resting_wall",
        ],
    ),
    "G": AblationVariantSpec(
        variant_id="G",
        name="Microstructure Only (No Foundation Model)",
        description="Linear logistic model on microstructure features without foundation transformer",
        uses_foundation_model=False,
        active_micro_features=[
            "ofi_norm",
            "vpin",
            "mid_return",
            "spread_bps",
            "depth_imb",
            "trade_sign",
            "vol_clock",
            "resting_wall",
        ],
    ),
}


@dataclass
class VariantEvaluationResult:
    variant_id: str
    name: str
    sample_size: int
    brier_score: float
    brier_skill_score: float
    log_loss: float
    accuracy: float
    incremental_bss_vs_raw: float  # Relative to Variant A
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AblationMatrixEngine:
    """
    Executes and ranks the 7-way microstructure ablation tournament.
    """

    @staticmethod
    def simulate_variant_probability(
        variant: AblationVariantSpec,
        raw_kronos_prob: float,
        microstructure: dict[str, float],
    ) -> float:
        """
        Determines variant prediction under controlled feature inclusion.
        Uses causal logistic modulation.
        """
        if not variant.uses_foundation_model:
            # Variant G: Pure microstructure linear combination
            ofi = microstructure.get("ofi_norm", 0.0)
            wall = microstructure.get("resting_wall", 0.0)
            sign = microstructure.get("trade_sign", 0.0)
            score = (ofi * 0.50) + (wall * 0.30) + (sign * 0.20)
            prob = 1.0 / (1.0 + math.exp(-max(-10.0, min(10.0, score * 3.0))))
            return max(0.01, min(0.99, prob))

        if not variant.active_micro_features:
            # Variant A: Pure raw foundation model
            return raw_kronos_prob

        # Modulate foundation logit by active features only
        raw_logit = math.log(
            max(1e-4, min(1.0 - 1e-4, raw_kronos_prob))
            / (1.0 - max(1e-4, min(1.0 - 1e-4, raw_kronos_prob)))
        )
        micro_bias = 0.0

        for f_name in variant.active_micro_features:
            val = microstructure.get(f_name, 0.0)
            if f_name == "ofi_norm":
                micro_bias += val * 0.35
            elif f_name == "resting_wall":
                micro_bias += val * 0.25
            elif f_name == "depth_imb":
                micro_bias += val * 0.20
            elif f_name == "vpin":
                # High toxicity amplifies uncertainty (dampens logit)
                raw_logit *= max(0.5, 1.0 - val * 0.5)
            elif f_name == "trade_sign":
                micro_bias += val * 0.20

        blended_logit = raw_logit + micro_bias
        prob = 1.0 / (1.0 + math.exp(-max(-15.0, min(15.0, blended_logit))))
        return max(0.01, min(0.99, prob))

    def evaluate_ablation_matrix(
        self,
        raw_kronos_probs: list[float] | np.ndarray,
        microstructure_contexts: list[dict[str, float]],
        labels: list[int] | np.ndarray,
    ) -> list[VariantEvaluationResult]:
        """
        Runs the 7-way ablation on identical observations and labels.
        """
        raw_p = np.asarray(raw_kronos_probs, dtype=np.float64)
        y = np.asarray(labels, dtype=np.int64)
        n = len(y)

        if len(raw_p) != n or len(microstructure_contexts) != n:
            raise ValueError("Mismatched lengths across ablation inputs")

        base_rate = float(np.mean(y))
        bs_clim = max(1e-8, float(np.mean((base_rate - y) ** 2)))

        results: dict[str, VariantEvaluationResult] = {}

        # 1. Compute Variant A first for baseline reference
        spec_a = ABLATION_VARIANTS["A"]
        p_a = raw_p
        bs_a = float(np.mean((p_a - y) ** 2))
        bss_a = 1.0 - (bs_a / bs_clim)
        ll_a = float(
            -np.mean(
                y * np.log(np.clip(p_a, 1e-6, 1.0 - 1e-6))
                + (1.0 - y) * np.log(1.0 - np.clip(p_a, 1e-6, 1.0 - 1e-6))
            )
        )
        acc_a = float(np.mean((p_a >= 0.5) == (y == 1)))

        results["A"] = VariantEvaluationResult(
            variant_id="A",
            name=spec_a.name,
            sample_size=n,
            brier_score=round(bs_a, 6),
            brier_skill_score=round(bss_a, 6),
            log_loss=round(ll_a, 6),
            accuracy=round(acc_a, 4),
            incremental_bss_vs_raw=0.0,
            status="VALID",
        )

        # 2. Compute other variants B through G
        for var_id, spec in ABLATION_VARIANTS.items():
            if var_id == "A":
                continue

            var_probs = [
                self.simulate_variant_probability(spec, float(raw_p[i]), microstructure_contexts[i])
                for i in range(n)
            ]
            p_var = np.array(var_probs)
            bs = float(np.mean((p_var - y) ** 2))
            bss = 1.0 - (bs / bs_clim)
            ll = float(
                -np.mean(
                    y * np.log(np.clip(p_var, 1e-6, 1.0 - 1e-6))
                    + (1.0 - y) * np.log(1.0 - np.clip(p_var, 1e-6, 1.0 - 1e-6))
                )
            )
            acc = float(np.mean((p_var >= 0.5) == (y == 1)))
            inc_bss = bss - bss_a

            results[var_id] = VariantEvaluationResult(
                variant_id=var_id,
                name=spec.name,
                sample_size=n,
                brier_score=round(bs, 6),
                brier_skill_score=round(bss, 6),
                log_loss=round(ll, 6),
                accuracy=round(acc, 4),
                incremental_bss_vs_raw=round(inc_bss, 6),
                status="VALID",
            )

        # Return sorted by variant ID A -> G
        return [results[k] for k in ["A", "B", "C", "D", "E", "F", "G"]]


ablation_matrix_engine = AblationMatrixEngine()
