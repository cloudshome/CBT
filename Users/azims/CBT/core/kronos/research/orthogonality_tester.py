"""
core/kronos/research/orthogonality_tester.py
===========================================
Milestone K9.6: Incremental Information & Orthogonality Testing Engine.
Evaluates whether Kronos provides statistically significant incremental predictive power
beyond existing SKY baselines (M0) using dependence-aware HAC Mincer-Zarnowitz regression,
out-of-sample score improvements, and overlap-adjusted likelihood ratio tests.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


@dataclass
class IncrementalInformationReport:
    base_model_id: str
    composite_model_id: str
    sample_size: int
    horizon_bars: int
    # Performance Deltas
    base_brier_score: float
    composite_brier_score: float
    delta_brier: float  # Positive = improvement (M1 has lower error than M0)
    relative_brier_improvement_pct: float
    base_log_loss: float
    composite_log_loss: float
    delta_log_loss: float  # Positive = improvement
    # Mincer-Zarnowitz Multi-Factor Regression: Y ~ alpha + beta_base * P_base + beta_kronos * P_kronos
    alpha: float
    beta_base: float
    beta_kronos: float
    beta_kronos_se: float
    beta_kronos_t_stat: float
    beta_kronos_p_value: float
    # Likelihood Ratio / Vuong-style Dependence-Adjusted Test
    mean_log_likelihood_diff: float
    hac_std_error_diff: float
    vuong_z_stat: float
    vuong_p_value: float
    test_verdict: str  # "SIGNIFICANT_INCREMENTAL_EDGE", "MARGINAL_IMPROVEMENT", "NO_INCREMENTAL_EDGE", "INCONCLUSIVE"
    # Residual Orthogonality
    residual_correlation: float  # Corr(Y - P_base, P_kronos)
    methodology_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrthogonalityTester:
    """
    Formally evaluates incremental predictive information and statistical orthogonality.
    """

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Standard normal cumulative distribution function."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def evaluate_incremental_information(
        self,
        base_probabilities: np.ndarray | list[float],
        kronos_probabilities: np.ndarray | list[float],
        labels: np.ndarray | list[int],
        composite_probabilities: np.ndarray | list[float] | None = None,
        base_model_id: str = "M_SKY_BASE",
        composite_model_id: str = "M_SKY_PLUS_KRONOS",
        horizon_bars: int = 12,
        eps: float = 1e-6,
    ) -> IncrementalInformationReport:
        """
        Executes formal out-of-sample incremental predictive test between M0 and M1.
        """
        p_base = np.asarray(base_probabilities, dtype=np.float64)
        p_kronos = np.asarray(kronos_probabilities, dtype=np.float64)
        y = np.asarray(labels, dtype=np.int64)
        n = len(y)

        if len(p_base) != n or len(p_kronos) != n:
            raise ValueError(
                f"Array length mismatch: base={len(p_base)}, kronos={len(p_kronos)}, y={n}"
            )
        if n < 15:
            raise ValueError(f"Insufficient samples for incremental information test: {n} < 15")

        # If composite not explicitly passed, construct log-odds equal blend
        if composite_probabilities is None:
            logit_b = np.log(
                np.clip(p_base, eps, 1.0 - eps) / (1.0 - np.clip(p_base, eps, 1.0 - eps))
            )
            logit_k = np.log(
                np.clip(p_kronos, eps, 1.0 - eps) / (1.0 - np.clip(p_kronos, eps, 1.0 - eps))
            )
            blended = (logit_b + logit_k) / 2.0
            p_comp = 1.0 / (1.0 + np.exp(-np.clip(blended, -15.0, 15.0)))
        else:
            p_comp = np.asarray(composite_probabilities, dtype=np.float64)

        # 1. Score Deltas
        bs_base = float(np.mean((p_base - y) ** 2))
        bs_comp = float(np.mean((p_comp - y) ** 2))
        delta_bs = bs_base - bs_comp  # Positive = improvement
        rel_bs_pct = (delta_bs / max(1e-8, bs_base)) * 100.0

        p_base_clip = np.clip(p_base, eps, 1.0 - eps)
        p_comp_clip = np.clip(p_comp, eps, 1.0 - eps)
        ll_base = float(-np.mean(y * np.log(p_base_clip) + (1.0 - y) * np.log(1.0 - p_base_clip)))
        ll_comp = float(-np.mean(y * np.log(p_comp_clip) + (1.0 - y) * np.log(1.0 - p_comp_clip)))
        delta_ll = ll_base - ll_comp

        # 2. Mincer-Zarnowitz Multi-Factor Regression with Newey-West HAC
        # Y ~ alpha + beta_base * P_base + beta_kronos * P_kronos
        nw_lag = max(1, 2 * horizon_bars)
        y_vec = y.astype(np.float64)

        try:
            base_has_variance = float(np.std(p_base)) > 1e-5
            if base_has_variance:
                x_mat = np.column_stack([np.ones(n), p_base, p_kronos])
                beta_vec, _, _, _ = np.linalg.lstsq(x_mat, y_vec, rcond=None)
                alpha_val = float(beta_vec[0])
                b_base = float(beta_vec[1])
                b_kronos = float(beta_vec[2])
                k_col = 2
            else:
                x_mat = np.column_stack([np.ones(n), p_kronos])
                beta_vec, _, _, _ = np.linalg.lstsq(x_mat, y_vec, rcond=None)
                alpha_val = float(beta_vec[0])
                b_base = 0.0
                b_kronos = float(beta_vec[1])
                k_col = 1

            resids = y_vec - (x_mat @ beta_vec)

            # Meat of HAC estimator
            z = x_mat * resids[:, np.newaxis]
            gamma_0 = (z.T @ z) / n
            s_mat = gamma_0.copy()
            for l_idx in range(1, nw_lag + 1):
                w_l = 1.0 - (l_idx / (nw_lag + 1.0))
                gamma_l = (z[l_idx:].T @ z[:-l_idx]) / n
                s_mat += w_l * (gamma_l + gamma_l.T)

            # Bread: Moore-Penrose pseudo-inverse for robust conditioning
            q_mat = (x_mat.T @ x_mat) / n
            q_inv = np.linalg.pinv(q_mat)
            v_mat = (q_inv @ s_mat @ q_inv) / n
            se_kronos = max(1e-6, math.sqrt(max(0.0, float(v_mat[k_col, k_col]))))
            t_kronos = b_kronos / se_kronos
            p_val_kronos = max(
                0.0, min(1.0, 1.0 - self._normal_cdf(t_kronos))
            )  # One-sided test H1: beta > 0
        except Exception:  # noqa: BLE001
            alpha_val, b_base, b_kronos = 0.0, 1.0, 0.0
            se_kronos, t_kronos, p_val_kronos = 0.1, 0.0, 0.50

        # 3. Dependence-Aware Overlap Likelihood Ratio Test
        # Pointwise log-likelihood diff: d_i = ln(p_comp(y_i)) - ln(p_base(y_i))
        log_lik_base = y * np.log(p_base_clip) + (1.0 - y) * np.log(1.0 - p_base_clip)
        log_lik_comp = y * np.log(p_comp_clip) + (1.0 - y) * np.log(1.0 - p_comp_clip)
        d_vec = log_lik_comp - log_lik_base
        d_mean = float(np.mean(d_vec))

        is_identical = bool(np.allclose(p_base, p_comp, atol=1e-5) or abs(d_mean) < 1e-9)
        if is_identical:
            s_d = 0.0
            se_d = 0.0
            z_vuong = 0.0
            p_vuong = 0.50
        else:
            # HAC standard error of difference d_vec
            d_centered = d_vec - d_mean
            gamma_d0 = float(np.mean(d_centered**2))
            s_d = gamma_d0
            max_lags = min(nw_lag, n - 2)
            for l_idx in range(1, max_lags + 1):
                w_l = 1.0 - (l_idx / (nw_lag + 1.0))
                cov_l = float(np.mean(d_centered[l_idx:] * d_centered[:-l_idx]))
                s_d += 2.0 * w_l * cov_l

            se_d = math.sqrt(max(1e-10, s_d / n))
            z_vuong = d_mean / se_d
            p_vuong = 1.0 - self._normal_cdf(z_vuong)

        # 4. Residual Orthogonality: Corr(e_base, P_kronos)
        e_base = y_vec - p_base
        cov_res = float(np.cov(e_base, p_kronos)[0, 1])
        std_e = float(np.std(e_base))
        std_k = float(np.std(p_kronos))
        corr_res = cov_res / (std_e * std_k) if std_e > 1e-6 and std_k > 1e-6 else 0.0

        # Verdict assignment
        notes: list[str] = [
            f"Evaluated on {n} aligned out-of-sample points with horizon H={horizon_bars}",
            f"Newey-West HAC Bartlett kernel with L={nw_lag} lags",
        ]

        if is_identical or math.isnan(z_vuong):
            verdict = "INCONCLUSIVE"
            notes.append(
                "Models are identical or likelihood variance near zero; statistically indistinguishable"
            )
        elif t_kronos >= 2.0 and delta_bs > 0 and p_vuong < 0.05:
            verdict = "SIGNIFICANT_INCREMENTAL_EDGE"
            notes.append(
                "Statistically significant incremental information confirmed (t >= 2.0, Delta BS > 0)"
            )
        elif t_kronos > 0 and delta_bs > 0:
            verdict = "MARGINAL_IMPROVEMENT"
            notes.append("Positive incremental improvement but t-stat below 2.0 critical threshold")
        else:
            verdict = "NO_INCREMENTAL_EDGE"
            notes.append(
                "Kronos does not improve over existing baseline (beta <= 0 or Delta BS <= 0)"
            )

        return IncrementalInformationReport(
            base_model_id=base_model_id,
            composite_model_id=composite_model_id,
            sample_size=n,
            horizon_bars=horizon_bars,
            base_brier_score=round(bs_base, 6),
            composite_brier_score=round(bs_comp, 6),
            delta_brier=round(delta_bs, 6),
            relative_brier_improvement_pct=round(rel_bs_pct, 4),
            base_log_loss=round(ll_base, 6),
            composite_log_loss=round(ll_comp, 6),
            delta_log_loss=round(delta_ll, 6),
            alpha=round(alpha_val, 4),
            beta_base=round(b_base, 4),
            beta_kronos=round(b_kronos, 4),
            beta_kronos_se=round(se_kronos, 4),
            beta_kronos_t_stat=round(t_kronos, 3),
            beta_kronos_p_value=round(p_val_kronos, 4),
            mean_log_likelihood_diff=round(d_mean, 6),
            hac_std_error_diff=round(se_d, 6),
            vuong_z_stat=round(z_vuong, 3),
            vuong_p_value=round(p_vuong, 4),
            test_verdict=verdict,
            residual_correlation=round(corr_res, 4),
            methodology_notes=notes,
        )


orthogonality_tester = OrthogonalityTester()
