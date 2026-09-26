"""
core/intelligence/synthetic_basis_engine.py
===========================================
Milestone 33: Multi-Venue Synthetic Cross-Arbitrage & Basis Dispersion Engine.

Architectural Mandates:
- Quantitative modeling of spot-perpetual basis and perpetual-perpetual spread.
- Real-time rolling funding carry yield dispersion estimation:
    Y_carry = FR * (24 / interval_hours) * 365
- Cointegration & Mean-Reversion Testing via Engle-Granger two-step OLS and
  Ornstein-Uhlenbeck (OU) half-life calibration:
    tau = ln(2) / kappa,  where kappa = -b / dt
- Multi-venue matrix support across Binance Spot, Binance Perp, Bybit Spot,
  Bybit Perp, and Hyperliquid L1.
- Strict Epistemic Taxonomy tagging: [FACT], [INFERENCE], [HYPOTHESIS].
- Permanent research & testnet isolation: zero live capital deployment.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from pydantic import BaseModel, Field
from scipy import stats

logger = logging.getLogger("ai_quant_sentinel.intelligence.synthetic_basis_engine")


class BasisRegime(str, Enum):
    """Regime classification for spot-perpetual basis."""
    CONTANGO = "CONTANGO"          # Perp > Spot (positive basis)
    BACKWARDATION = "BACKWARDATION"# Perp < Spot (negative basis)
    FLAT = "FLAT"                  # |Basis| < 1.0 bps


class EpistemicTag(str, Enum):
    """Epistemic taxonomy classification per QUANT_RESEARCH_PROTOCOL.md."""
    FACT = "[FACT]"              # Empirically measured observable data
    INFERENCE = "[INFERENCE]"    # Derived metrics, rolling statistics, carry yield
    HYPOTHESIS = "[HYPOTHESIS]"  # Statistical forecasting, cointegration, OU half-life


class BasisObservation(BaseModel):
    """Immutable market observation for a synthetic instrument pair."""
    symbol: str = Field(description="Canonical asset symbol (e.g. BTC, ETH, SOL)")
    spot_venue: str = Field(description="Venue for spot leg (e.g. BINANCE_SPOT, BYBIT_SPOT)")
    perp_venue: str = Field(description="Venue for perp leg (e.g. BINANCE_PERP, HYPERLIQUID_L1)")
    spot_bid: float = Field(gt=0.0, description="Best bid on spot venue")
    spot_ask: float = Field(gt=0.0, description="Best ask on spot venue")
    perp_bid: float = Field(gt=0.0, description="Best bid on perp venue")
    perp_ask: float = Field(gt=0.0, description="Best ask on perp venue")
    funding_rate: float = Field(default=0.0001, description="8h or 1h periodic funding rate (e.g. 0.0001 = 0.01%)")
    funding_interval_hours: float = Field(default=8.0, gt=0.0, description="Funding interval in hours (8.0 or 1.0)")
    borrow_rate_annual: float = Field(default=0.05, ge=0.0, description="Annualized borrow fee rate for shorting spot")
    timestamp_ns: int = Field(default_factory=time.monotonic_ns, description="Monotonic timestamp in nanoseconds")


class BasisMetrics(BaseModel):
    """Derived quantitative metrics for a single synthetic basis observation."""
    symbol: str
    spot_venue: str
    perp_venue: str
    spot_mid: float
    perp_mid: float
    raw_basis_bps: float
    executable_cash_carry_bps: float
    executable_reverse_carry_bps: float
    annualized_funding_yield: float
    net_cash_carry_apr: float
    net_reverse_carry_apr: float
    rolling_mean_basis_bps: float
    rolling_std_basis_bps: float
    z_score: float
    regime: BasisRegime
    epistemic_tag: EpistemicTag = EpistemicTag.INFERENCE
    timestamp_ns: int


class CointegrationResult(BaseModel):
    """Statistical outcome of Engle-Granger cointegration & OU half-life calibration."""
    symbol: str
    spot_venue: str
    perp_venue: str
    is_cointegrated: bool
    adf_t_stat: float
    critical_value_5pct: float = -2.86
    hedge_ratio_beta: float
    intercept_alpha: float
    ou_mean_reversion_speed_kappa: float
    ou_half_life_hours: float
    sample_size: int
    r_squared: float
    epistemic_tag: EpistemicTag = EpistemicTag.HYPOTHESIS
    timestamp_ns: int


@dataclass
class RollingBasisSeries:
    """Internal rolling memory buffer for statistical estimation."""
    max_window: int = 500
    timestamps: list[int] = field(default_factory=list)
    spot_mids: list[float] = field(default_factory=list)
    perp_mids: list[float] = field(default_factory=list)
    raw_basis_bps: list[float] = field(default_factory=list)

    def append(self, ts: int, s_mid: float, p_mid: float, b_bps: float) -> None:
        self.timestamps.append(ts)
        self.spot_mids.append(s_mid)
        self.perp_mids.append(p_mid)
        self.raw_basis_bps.append(b_bps)
        if len(self.timestamps) > self.max_window:
            self.timestamps.pop(0)
            self.spot_mids.pop(0)
            self.perp_mids.pop(0)
            self.raw_basis_bps.pop(0)


class SyntheticBasisEngine:
    """
    Generation 6 Multi-Venue Synthetic Cross-Arbitrage & Basis Dispersion Engine.

    Calculates basis, rolling statistical z-scores, annualized carry yields,
    cross-venue dispersion matrices, and calibrated Ornstein-Uhlenbeck mean-reversion dynamics.
    """

    def __init__(
        self,
        rolling_window_size: int = 120,
        z_candidate_threshold: float = 2.5,
        min_cointegration_samples: int = 30,
    ) -> None:
        self.rolling_window_size = rolling_window_size
        self.z_candidate_threshold = z_candidate_threshold
        self.min_cointegration_samples = min_cointegration_samples

        # Memory store: (symbol, spot_venue, perp_venue) -> RollingBasisSeries
        self._series: dict[tuple[str, str, str], RollingBasisSeries] = {}

    def ingest_observation(self, obs: BasisObservation) -> BasisMetrics:
        """
        Ingests a multi-venue market observation and computes full basis analytics.
        """
        if obs.spot_ask < obs.spot_bid:
            raise ValueError(f"Crossed spot orderbook on {obs.spot_venue}: bid={obs.spot_bid} > ask={obs.spot_ask}")
        if obs.perp_ask < obs.perp_bid:
            raise ValueError(f"Crossed perp orderbook on {obs.perp_venue}: bid={obs.perp_bid} > ask={obs.perp_ask}")

        spot_mid = (obs.spot_bid + obs.spot_ask) / 2.0
        perp_mid = (obs.perp_bid + obs.perp_ask) / 2.0

        # Raw basis in basis points: ((P_mid - S_mid) / S_mid) * 10,000
        raw_basis_bps = ((perp_mid - spot_mid) / spot_mid) * 10000.0

        # Executable basis accounting for full bid-ask spread
        # Cash & Carry: Buy Spot at Ask, Sell Perp at Bid
        executable_cash_carry_bps = ((obs.perp_bid - obs.spot_ask) / obs.spot_ask) * 10000.0
        # Reverse Cash & Carry: Short Spot at Bid, Buy Perp at Ask
        executable_reverse_carry_bps = ((obs.spot_bid - obs.perp_ask) / obs.perp_ask) * 10000.0

        # Annualized funding yield: FR * (24 / interval_hours) * 365
        annual_funding_multiplier = (24.0 / obs.funding_interval_hours) * 365.0
        annualized_funding_yield = obs.funding_rate * annual_funding_multiplier

        # Net Carry APR calculations:
        # Cash and Carry collects funding yield:
        net_cash_carry_apr = annualized_funding_yield + (raw_basis_bps / 10000.0)
        # Reverse Cash and Carry pays funding yield and pays spot borrow fee:
        net_reverse_carry_apr = -annualized_funding_yield - obs.borrow_rate_annual - (raw_basis_bps / 10000.0)

        # Update rolling series
        key = (obs.symbol, obs.spot_venue, obs.perp_venue)
        if key not in self._series:
            self._series[key] = RollingBasisSeries(max_window=self.rolling_window_size * 2)

        series = self._series[key]
        series.append(obs.timestamp_ns, spot_mid, perp_mid, raw_basis_bps)

        # Rolling statistics
        history = series.raw_basis_bps[-self.rolling_window_size :]
        rolling_mean = float(np.mean(history))
        rolling_std = float(np.std(history, ddof=1)) if len(history) > 1 else 0.0

        if rolling_std > 1e-6:
            z_score = (raw_basis_bps - rolling_mean) / rolling_std
        else:
            z_score = 0.0

        # Regime classification
        if raw_basis_bps > 1.0:
            regime = BasisRegime.CONTANGO
        elif raw_basis_bps < -1.0:
            regime = BasisRegime.BACKWARDATION
        else:
            regime = BasisRegime.FLAT

        return BasisMetrics(
            symbol=obs.symbol,
            spot_venue=obs.spot_venue,
            perp_venue=obs.perp_venue,
            spot_mid=spot_mid,
            perp_mid=perp_mid,
            raw_basis_bps=raw_basis_bps,
            executable_cash_carry_bps=executable_cash_carry_bps,
            executable_reverse_carry_bps=executable_reverse_carry_bps,
            annualized_funding_yield=annualized_funding_yield,
            net_cash_carry_apr=net_cash_carry_apr,
            net_reverse_carry_apr=net_reverse_carry_apr,
            rolling_mean_basis_bps=rolling_mean,
            rolling_std_basis_bps=rolling_std,
            z_score=z_score,
            regime=regime,
            epistemic_tag=EpistemicTag.INFERENCE,
            timestamp_ns=obs.timestamp_ns,
        )

    def compute_cointegration(
        self,
        symbol: str,
        spot_venue: str,
        perp_venue: str,
        dt_hours: float = 1.0,
    ) -> CointegrationResult:
        """
        Executes two-step Engle-Granger cointegration and Ornstein-Uhlenbeck
        mean-reversion half-life estimation.

        Step 1: OLS regression: Perp = alpha + beta * Spot + eps
        Step 2: Dickey-Fuller unit-root test on residuals eps_t:
                delta(eps_t) = gamma * eps_{t-1} + u_t
                t-stat = gamma / SE(gamma)
        Step 3: Ornstein-Uhlenbeck half-life estimation:
                tau = ln(2) / kappa, where kappa = -gamma / dt_hours
        """
        key = (symbol, spot_venue, perp_venue)
        if key not in self._series or len(self._series[key].spot_mids) < self.min_cointegration_samples:
            sample_size = len(self._series[key].spot_mids) if key in self._series else 0
            return CointegrationResult(
                symbol=symbol,
                spot_venue=spot_venue,
                perp_venue=perp_venue,
                is_cointegrated=False,
                adf_t_stat=0.0,
                critical_value_5pct=-2.86,
                hedge_ratio_beta=1.0,
                intercept_alpha=0.0,
                ou_mean_reversion_speed_kappa=0.0,
                ou_half_life_hours=float("inf"),
                sample_size=sample_size,
                r_squared=0.0,
                epistemic_tag=EpistemicTag.HYPOTHESIS,
                timestamp_ns=time.monotonic_ns(),
            )

        series = self._series[key]
        spot_arr = np.array(series.spot_mids)
        perp_arr = np.array(series.perp_mids)
        n = len(spot_arr)

        # Step 1: OLS regression
        ols_res = stats.linregress(spot_arr, perp_arr)
        beta = float(ols_res.slope)
        alpha = float(ols_res.intercept)
        r_squared = float(ols_res.rvalue ** 2)

        residuals = perp_arr - (alpha + beta * spot_arr)

        # Step 2: Unit Root Test on Residuals (ADF without constant since OLS residuals mean=0)
        dy = np.diff(residuals)
        y_lag = residuals[:-1]

        adf_reg = stats.linregress(y_lag, dy)
        gamma = float(adf_reg.slope)
        se_gamma = float(adf_reg.stderr) if adf_reg.stderr and adf_reg.stderr > 0 else 1e-9
        adf_t_stat = gamma / se_gamma

        # 5% critical value for cointegrating residuals is approximately -2.86 (MacKinnon)
        critical_val = -2.86
        is_cointegrated = bool(adf_t_stat < critical_val)

        # Step 3: Ornstein-Uhlenbeck Mean-Reversion Speed & Half-Life
        # Discrete AR(1): delta(y_t) = -kappa * dt * y_{t-1} => gamma = -kappa * dt
        # When gamma < 0, the process mean-reverts with speed kappa = -gamma / dt
        if gamma < 0.0 and se_gamma < 1.0:
            kappa = -gamma / dt_hours
            if kappa > 1e-6:
                half_life_hours = math.log(2.0) / kappa
            else:
                half_life_hours = float("inf")
        else:
            kappa = 0.0
            half_life_hours = float("inf")

        return CointegrationResult(
            symbol=symbol,
            spot_venue=spot_venue,
            perp_venue=perp_venue,
            is_cointegrated=is_cointegrated,
            adf_t_stat=adf_t_stat,
            critical_value_5pct=critical_val,
            hedge_ratio_beta=beta,
            intercept_alpha=alpha,
            ou_mean_reversion_speed_kappa=kappa,
            ou_half_life_hours=half_life_hours,
            sample_size=n,
            r_squared=r_squared,
            epistemic_tag=EpistemicTag.HYPOTHESIS,
            timestamp_ns=time.monotonic_ns(),
        )

    def get_cross_venue_dispersion_matrix(
        self,
        symbol: str,
        observations: list[BasisObservation],
    ) -> dict[str, BasisMetrics]:
        """
        Evaluates a collection of observations across multiple venue pairs
        and returns a dictionary of calculated basis metrics keyed by venue pair.
        """
        results: dict[str, BasisMetrics] = {}
        for obs in observations:
            if obs.symbol == symbol:
                pair_name = f"{obs.spot_venue}:{obs.perp_venue}"
                results[pair_name] = self.ingest_observation(obs)
        return results
