"""
SKY Multi-Asset Macro Cross-Correlation & Regime Network Engine.

Computes rolling cross-asset correlation & covariance matrices,
Principal Component Analysis (PCA) systemic absorption ratio,
directional Lead-Lag Granger Causality, and the Systemic Macro Fragility Index.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

logger = logging.getLogger("sky.macro_network")


@dataclass
class CrossAssetCorrelationMatrix:
    assets: list[str]
    correlation_matrix: list[list[float]]  # NxN matrix
    covariance_matrix: list[list[float]]  # NxN matrix
    average_correlation: float
    dispersion: float


@dataclass
class PCASystemicAbsorption:
    eigenvalues: list[float]
    explained_variance_ratios: list[float]
    absorption_ratio_top2: float  # Variance explained by top 2 components [0.0, 1.0]
    market_synchronization_regime: (
        str  # "DECOUPLED_IDIOSYNCRATIC", "MODERATE_CO-MOVEMENT", "HIGH_SYSTEMIC_SYNCHRONIZATION"
    )


@dataclass
class LeadLagCausalLink:
    leader: str
    follower: str
    optimal_lag_periods: int
    granger_f_stat: float
    p_value: float
    is_statistically_significant: bool
    information_flow_bps: float


@dataclass
class MacroNetworkAnalysis:
    timestamp_ms: int
    assets: list[str]
    correlation_network: CrossAssetCorrelationMatrix
    pca_absorption: PCASystemicAbsorption
    lead_lag_links: list[LeadLagCausalLink]
    systemic_fragility_index: float  # [0.0, 1.0]
    macro_transmission_regime: (
        str  # "RISK_ON_EXPANSION", "RISK_OFF_CONTAGION", "FLIGHT_TO_SAFETY", "NEUTRAL_BALANCED"
    )
    primary_driver_asset: str
    narrative: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MacroNetworkEngine:
    """
    Evaluates multi-asset macro cross-correlations, systemic absorption,
    and lead-lag information spillovers across Crypto and Macro assets.
    """

    def __init__(self, significance_alpha: float = 0.05, max_lag: int = 3):
        self.significance_alpha = significance_alpha
        self.max_lag = max_lag

    def analyze(
        self,
        asset_returns: dict[
            str, list[float]
        ],  # Asset symbol -> chronological returns series (same length)
        timestamp_ms: int | None = None,
    ) -> MacroNetworkAnalysis:
        """
        Conducts full multi-asset macro network and spillover analysis.
        """
        now = timestamp_ms or int(time.time() * 1000)

        # Ensure we have at least 2 assets with valid return arrays
        valid_assets = [k for k, v in asset_returns.items() if len(v) >= 10]
        if len(valid_assets) < 2:
            return self._empty_analysis(now)

        # Align series length
        min_len = min(len(asset_returns[k]) for k in valid_assets)
        aligned_data = np.array(
            [asset_returns[k][-min_len:] for k in valid_assets], dtype=np.float64
        )

        # 1. Correlation & Covariance Matrix
        corr_matrix, cov_matrix, avg_corr, dispersion = self._compute_matrix(aligned_data)
        network_result = CrossAssetCorrelationMatrix(
            assets=valid_assets,
            correlation_matrix=[[round(float(c), 4) for c in row] for row in corr_matrix],
            covariance_matrix=[[round(float(c), 6) for c in row] for row in cov_matrix],
            average_correlation=round(avg_corr, 4),
            dispersion=round(dispersion, 4),
        )

        # 2. PCA Eigenvalue Decomposition & Systemic Absorption Ratio
        pca_result = self._compute_pca_absorption(cov_matrix)

        # 3. Pairwise Lead-Lag Granger Causality
        lead_lag_links = self._compute_lead_lag(aligned_data, valid_assets)

        # 4. Systemic Macro Fragility Index & Regime Synthesis
        fragility, regime, driver, narrative = self._synthesize_macro_state(
            network_result, pca_result, lead_lag_links, valid_assets
        )

        return MacroNetworkAnalysis(
            timestamp_ms=now,
            assets=valid_assets,
            correlation_network=network_result,
            pca_absorption=pca_result,
            lead_lag_links=lead_lag_links,
            systemic_fragility_index=round(fragility, 3),
            macro_transmission_regime=regime,
            primary_driver_asset=driver,
            narrative=narrative,
        )

    def _compute_matrix(
        self,
        data: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
        cov = np.cov(data)
        std = np.std(data, axis=1, keepdims=True)
        std_outer = np.dot(std, std.T)
        # Avoid division by zero
        std_outer[std_outer == 0] = 1e-8
        corr = cov / std_outer
        np.clip(corr, -1.0, 1.0, out=corr)
        np.fill_diagonal(corr, 1.0)

        # Extract off-diagonal correlations
        n = corr.shape[0]
        off_diag = corr[~np.eye(n, dtype=bool)]
        avg_corr = float(np.mean(off_diag)) if len(off_diag) > 0 else 0.0
        dispersion = float(np.std(off_diag)) if len(off_diag) > 0 else 0.0

        return corr, cov, avg_corr, dispersion

    def _compute_pca_absorption(self, cov_matrix: np.ndarray) -> PCASystemicAbsorption:
        try:
            eigenvalues, _ = np.linalg.eigh(cov_matrix)
            eigenvalues = np.sort(eigenvalues)[::-1]  # Descending
            eigenvalues = np.maximum(eigenvalues, 0.0)  # Non-negative

            total_var = float(np.sum(eigenvalues))
            if total_var > 0:
                ratios = [float(e / total_var) for e in eigenvalues]
                k = min(2, len(ratios))
                absorption_top2 = float(sum(ratios[:k]))
            else:
                ratios = [1.0 / len(eigenvalues)] * len(eigenvalues)
                absorption_top2 = min(1.0, 2.0 / max(1, len(eigenvalues)))

            if absorption_top2 > 0.75:
                regime = "HIGH_SYSTEMIC_SYNCHRONIZATION"
            elif absorption_top2 > 0.50:
                regime = "MODERATE_CO-MOVEMENT"
            else:
                regime = "DECOUPLED_IDIOSYNCRATIC"

            return PCASystemicAbsorption(
                eigenvalues=[round(float(e), 6) for e in eigenvalues],
                explained_variance_ratios=[round(r, 4) for r in ratios],
                absorption_ratio_top2=round(absorption_top2, 4),
                market_synchronization_regime=regime,
            )
        except Exception as e:
            logger.warning("PCA absorption calculation error: %s", e)
            return PCASystemicAbsorption(
                eigenvalues=[1.0],
                explained_variance_ratios=[1.0],
                absorption_ratio_top2=1.0,
                market_synchronization_regime="MODERATE_CO-MOVEMENT",
            )

    def _compute_lead_lag(
        self,
        data: np.ndarray,
        assets: list[str],
    ) -> list[LeadLagCausalLink]:
        links: list[LeadLagCausalLink] = []
        n_assets = len(assets)

        for i in range(n_assets):
            for j in range(n_assets):
                if i == j:
                    continue

                leader = assets[i]
                follower = assets[j]
                x = data[i]  # Potential leader
                y = data[j]  # Follower

                # Simple linear VAR lag regression: y_t ~ y_{t-1} + x_{t-1}
                # Check for lag 1 to max_lag
                best_f = 0.0
                best_lag = 1
                best_p = 1.0

                for lag in range(1, self.max_lag + 1):
                    y_target = y[lag:]
                    y_lagged = y[:-lag]
                    x_lagged = x[:-lag]

                    if len(y_target) < 6:
                        continue

                    # Restricted model: y_t = a0 + a1 * y_{t-lag}
                    x_r = np.column_stack([np.ones(len(y_target)), y_lagged])
                    # Unrestricted model: y_t = a0 + a1 * y_{t-lag} + b1 * x_{t-lag}
                    x_ur = np.column_stack([np.ones(len(y_target)), y_lagged, x_lagged])

                    try:
                        beta_r, _res_r, _, _ = np.linalg.lstsq(x_r, y_target, rcond=None)
                        beta_ur, _res_ur, _, _ = np.linalg.lstsq(x_ur, y_target, rcond=None)

                        rss_r = float(np.sum((y_target - x_r @ beta_r) ** 2))
                        rss_ur = float(np.sum((y_target - x_ur @ beta_ur) ** 2))

                        n_obs = len(y_target)
                        p_ur = x_ur.shape[1]
                        p_r = x_r.shape[1]

                        if rss_ur > 1e-12 and (n_obs - p_ur) > 0:
                            f_stat = ((rss_r - rss_ur) / (p_ur - p_r)) / (rss_ur / (n_obs - p_ur))
                            f_stat = max(0.0, f_stat)
                            # Approximate p-value using Fisher-Snedecor tail approximation
                            p_val = math.exp(-0.5 * f_stat) if f_stat > 0 else 1.0

                            if f_stat > best_f:
                                best_f = f_stat
                                best_lag = lag
                                best_p = p_val
                    except Exception:
                        pass

                is_sig = best_p < self.significance_alpha or best_f > 3.84
                if is_sig or best_f > 1.5:
                    links.append(
                        LeadLagCausalLink(
                            leader=leader,
                            follower=follower,
                            optimal_lag_periods=best_lag,
                            granger_f_stat=round(best_f, 3),
                            p_value=round(best_p, 4),
                            is_statistically_significant=is_sig,
                            information_flow_bps=round(float(best_f * 5.2), 2),
                        )
                    )

        # Sort by F-stat descending
        links.sort(key=lambda link: link.granger_f_stat, reverse=True)
        return links

    def _synthesize_macro_state(
        self,
        network: CrossAssetCorrelationMatrix,
        pca: PCASystemicAbsorption,
        links: list[LeadLagCausalLink],
        assets: list[str],
    ) -> tuple[float, str, str, str]:
        # Fragility Index: weighted composite of absorption ratio, average correlation, and spillover density
        sig_links_ratio = sum(1 for link in links if link.is_statistically_significant) / max(
            1, len(assets) * (len(assets) - 1)
        )
        fragility = (
            0.5 * pca.absorption_ratio_top2
            + 0.3 * max(0.0, network.average_correlation)
            + 0.2 * sig_links_ratio
        )
        fragility = float(np.clip(fragility, 0.05, 0.95))

        # Find primary driver (most frequent significant leader)
        leader_counts: dict[str, float] = {}
        for link in links:
            if link.is_statistically_significant:
                leader_counts[link.leader] = (
                    leader_counts.get(link.leader, 0.0) + link.granger_f_stat
                )

        primary_driver = (
            max(leader_counts.items(), key=lambda x: x[1])[0]
            if leader_counts
            else (assets[0] if assets else "BTC/USDT")
        )

        # Macro regime determination
        has_gold = any("PAXG" in a or "XAU" in a or "GOLD" in a for a in assets)
        if fragility > 0.70:
            regime = "RISK_OFF_CONTAGION"
            narrative = f"Systemic fragility elevated ({fragility:.2f}). High cross-asset absorption ({pca.absorption_ratio_top2:.1%}) driven by {primary_driver} spillover."
        elif has_gold and primary_driver in ["PAXG/USDT", "XAU/USDT", "PAXG"]:
            regime = "FLIGHT_TO_SAFETY"
            narrative = f"Macro safe-haven rotation active. Gold ({primary_driver}) demonstrates leading causal transmission over digital assets."
        elif network.average_correlation > 0.40 and fragility < 0.50:
            regime = "RISK_ON_EXPANSION"
            narrative = f"Broad-based risk asset expansion. Cross-asset dispersion ({network.dispersion:.2f}) indicates healthy liquidity participation."
        else:
            regime = "NEUTRAL_BALANCED"
            narrative = f"Macro network is balanced with moderate co-movement ({pca.market_synchronization_regime})."

        return fragility, regime, primary_driver, narrative

    def _empty_analysis(self, timestamp_ms: int) -> MacroNetworkAnalysis:
        default_assets = ["BTC/USDT", "ETH/USDT"]
        empty_matrix = CrossAssetCorrelationMatrix(
            assets=default_assets,
            correlation_matrix=[[1.0, 0.5], [0.5, 1.0]],
            covariance_matrix=[[0.001, 0.0005], [0.0005, 0.001]],
            average_correlation=0.5,
            dispersion=0.0,
        )
        empty_pca = PCASystemicAbsorption(
            eigenvalues=[1.0, 0.5],
            explained_variance_ratios=[0.67, 0.33],
            absorption_ratio_top2=1.0,
            market_synchronization_regime="MODERATE_CO-MOVEMENT",
        )
        return MacroNetworkAnalysis(
            timestamp_ms=timestamp_ms,
            assets=default_assets,
            correlation_network=empty_matrix,
            pca_absorption=empty_pca,
            lead_lag_links=[],
            systemic_fragility_index=0.35,
            macro_transmission_regime="NEUTRAL_BALANCED",
            primary_driver_asset="BTC/USDT",
            narrative="Insufficient asset history for macro network analysis.",
        )


macro_network_engine = MacroNetworkEngine()
