"""
core/risk_engine/basis_governor.py
==================================
Milestone 33: Multi-Venue Quantitative Basis Risk Governor.

Mandates:
- Non-negotiable constitutional capital isolation: real_capital_enabled = False.
- Strict 1.5% maximum single-trade portfolio equity loss ceiling.
- Basis Dislocation Breaker: Rejects trades when basis exceeds 300 bps shock threshold.
- Funding Inversion Alarm: Blocks carry entry when funding rate is severely inverted.
- Collateral Imbalance Shield: Pre-empts asymmetric margin liquidation between venues.
- Statistical Convergence Gate: Enforces cointegration & bounded half-life requirements.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from core.intelligence.synthetic_basis_engine import (
    BasisMetrics,
    CointegrationResult,
)

logger = logging.getLogger("ai_quant_sentinel.risk_engine.basis_governor")


class VenueMarginSnapshot(BaseModel):
    """Real-time margin utilization status for a specific venue."""

    venue: str
    total_equity_usd: float = Field(gt=0.0)
    used_margin_usd: float = Field(ge=0.0)
    available_margin_usd: float = Field(ge=0.0)
    maintenance_margin_req_usd: float = Field(ge=0.0)

    @property
    def margin_utilization(self) -> float:
        """Margin utilization ratio [0.0, 1.0]."""
        if self.total_equity_usd <= 0:
            return 1.0
        return min(1.0, max(0.0, self.used_margin_usd / self.total_equity_usd))


class RiskCheckResult(BaseModel):
    """Detailed diagnostic outcome of a specific risk invariant evaluation."""

    check_name: str
    passed: bool
    observed_value: Any
    threshold: Any
    details: str


class BasisRiskVerdict(BaseModel):
    """Machine-readable gate verdict from the BasisRiskGovernor."""

    is_approved: bool
    requested_quantity: float
    approved_quantity: float
    risk_checks: list[RiskCheckResult]
    rejection_reasons: list[str]
    circuit_breaker_active: bool
    circuit_breaker_lockout_remaining_s: float = 0.0
    real_capital_enabled: bool = False  # Constitutional Permanent Firewall
    timestamp_ns: int = Field(default_factory=time.monotonic_ns)


class BasisRiskGovernor:
    """
    Deterministic Quantitative Risk Governor for Synthetic Cross-Arbitrage & Basis Trading.

    Applies monotonic risk gating:
        approved_quantity = min(requested_quantity, risk_cap_quantity)
    and strictly forbids live capital bypass.
    """

    def __init__(
        self,
        max_dislocation_bps: float = 300.0,
        max_margin_utilization: float = 0.80,
        max_margin_asymmetry: float = 0.50,
        max_single_trade_loss_pct: float = 0.015,  # 1.5% max equity risk
        max_ou_half_life_hours: float = 72.0,
        circuit_breaker_lockout_duration_s: float = 3600.0,
    ) -> None:
        self.max_dislocation_bps = max_dislocation_bps
        self.max_margin_utilization = max_margin_utilization
        self.max_margin_asymmetry = max_margin_asymmetry
        self.max_single_trade_loss_pct = max_single_trade_loss_pct
        self.max_ou_half_life_hours = max_ou_half_life_hours
        self.circuit_breaker_lockout_duration_s = circuit_breaker_lockout_duration_s

        # Circuit breaker memory
        self._circuit_breaker_tripped: bool = False
        self._circuit_breaker_trip_timestamp: float = 0.0
        self._trip_reason: str = ""

    def evaluate_synthetic_trade(
        self,
        strategy_id: str,
        requested_quantity: float,
        spot_price: float,
        stop_loss_basis_bps: float,
        portfolio_equity_usd: float,
        basis_metrics: BasisMetrics,
        spot_margin: VenueMarginSnapshot,
        perp_margin: VenueMarginSnapshot,
        cointegration: CointegrationResult | None = None,
        trade_type: str = "CASH_AND_CARRY",
    ) -> BasisRiskVerdict:
        """
        Evaluates a candidate dual-leg synthetic trade against all quantitative risk invariants.
        """
        now = time.monotonic()
        checks: list[RiskCheckResult] = []
        reasons: list[str] = []

        # 0. Check active circuit breaker lockout
        if self._circuit_breaker_tripped:
            elapsed = now - self._circuit_breaker_trip_timestamp
            if elapsed < self.circuit_breaker_lockout_duration_s:
                remaining = self.circuit_breaker_lockout_duration_s - elapsed
                return BasisRiskVerdict(
                    is_approved=False,
                    requested_quantity=requested_quantity,
                    approved_quantity=0.0,
                    risk_checks=[
                        RiskCheckResult(
                            check_name="circuit_breaker_lockout",
                            passed=False,
                            observed_value=f"Locked for {remaining:.1f}s",
                            threshold=f"{self.circuit_breaker_lockout_duration_s}s",
                            details=f"Circuit breaker active: {self._trip_reason}",
                        )
                    ],
                    rejection_reasons=[f"CIRCUIT_BREAKER_ACTIVE: {self._trip_reason}"],
                    circuit_breaker_active=True,
                    circuit_breaker_lockout_remaining_s=remaining,
                    real_capital_enabled=False,
                )
            else:
                # Lockout expired, reset breaker
                self._circuit_breaker_tripped = False
                self._circuit_breaker_trip_timestamp = 0.0
                self._trip_reason = ""

        # Gate 1: Basis Dislocation Shock Breaker
        abs_basis = abs(basis_metrics.raw_basis_bps)
        gate_1_pass = abs_basis <= self.max_dislocation_bps
        checks.append(
            RiskCheckResult(
                check_name="basis_dislocation_shock",
                passed=gate_1_pass,
                observed_value=abs_basis,
                threshold=self.max_dislocation_bps,
                details=f"Absolute basis {abs_basis:.2f} bps vs max {self.max_dislocation_bps:.2f} bps",
            )
        )
        if not gate_1_pass:
            # Trip master breaker on extreme dislocation shock
            self._circuit_breaker_tripped = True
            self._circuit_breaker_trip_timestamp = now
            self._trip_reason = (
                f"BASIS_DISLOCATION_SHOCK: {abs_basis:.2f} bps > {self.max_dislocation_bps:.2f} bps"
            )
            reasons.append(self._trip_reason)

        # Gate 2: Funding Inversion Breaker
        gate_2_pass = True
        if trade_type == "CASH_AND_CARRY":
            # For cash & carry (long spot, short perp), we collect funding; if funding is heavily negative, it's toxic
            if basis_metrics.annualized_funding_yield < -0.05:  # -5% APR inverted funding
                gate_2_pass = False
                reasons.append(
                    f"FUNDING_INVERSION_ALERT: Annualized funding yield is negative ({basis_metrics.annualized_funding_yield * 100:.2f}%)"
                )
        elif trade_type == "REVERSE_CARRY":
            # For reverse carry (short spot, buy perp), we pay funding; if funding is heavily positive, it's toxic
            if basis_metrics.annualized_funding_yield > 0.05:
                gate_2_pass = False
                reasons.append(
                    f"FUNDING_INVERSION_ALERT: Positive funding yield makes reverse carry negative ({basis_metrics.annualized_funding_yield * 100:.2f}%)"
                )

        checks.append(
            RiskCheckResult(
                check_name="funding_inversion_gate",
                passed=gate_2_pass,
                observed_value=basis_metrics.annualized_funding_yield,
                threshold=0.0,
                details=f"Annualized funding yield: {basis_metrics.annualized_funding_yield * 100:.2f}%",
            )
        )

        # Gate 3: Collateral Imbalance Shield
        spot_util = spot_margin.margin_utilization
        perp_util = perp_margin.margin_utilization
        asymmetry = abs(spot_util - perp_util)

        gate_3a_pass = (
            spot_util <= self.max_margin_utilization and perp_util <= self.max_margin_utilization
        )
        gate_3b_pass = asymmetry <= self.max_margin_asymmetry
        gate_3_pass = gate_3a_pass and gate_3b_pass

        checks.append(
            RiskCheckResult(
                check_name="collateral_utilization_limits",
                passed=gate_3a_pass,
                observed_value={"spot_util": spot_util, "perp_util": perp_util},
                threshold=self.max_margin_utilization,
                details=f"Spot util={spot_util:.2%}, Perp util={perp_util:.2%}",
            )
        )
        checks.append(
            RiskCheckResult(
                check_name="collateral_asymmetry_limit",
                passed=gate_3b_pass,
                observed_value=asymmetry,
                threshold=self.max_margin_asymmetry,
                details=f"Margin asymmetry={asymmetry:.2%} vs max {self.max_margin_asymmetry:.2%}",
            )
        )
        if not gate_3_pass:
            reasons.append(
                f"COLLATERAL_IMBALANCE_BREACH: spot={spot_util:.2%}, perp={perp_util:.2%}, asym={asymmetry:.2%}"
            )

        # Gate 4: Cointegration & Half-Life Gate (for statistical mean-reversion)
        gate_4_pass = True
        if cointegration is not None:
            if not cointegration.is_cointegrated:
                gate_4_pass = False
                reasons.append(
                    f"NON_COINTEGRATED_SERIES: ADF t-stat {cointegration.adf_t_stat:.2f} >= -2.86"
                )
            elif cointegration.ou_half_life_hours > self.max_ou_half_life_hours:
                gate_4_pass = False
                reasons.append(
                    f"OU_HALF_LIFE_EXCEEDED: Half-life {cointegration.ou_half_life_hours:.1f}h > {self.max_ou_half_life_hours:.1f}h"
                )

            checks.append(
                RiskCheckResult(
                    check_name="cointegration_mean_reversion_gate",
                    passed=gate_4_pass,
                    observed_value={
                        "is_cointegrated": cointegration.is_cointegrated,
                        "half_life_h": cointegration.ou_half_life_hours,
                    },
                    threshold={
                        "critical_val": -2.86,
                        "max_half_life_h": self.max_ou_half_life_hours,
                    },
                    details=f"Cointegrated={cointegration.is_cointegrated}, Half-life={cointegration.ou_half_life_hours:.1f}h",
                )
            )

        # Gate 5: 1.5% Equity Risk Ceiling & Monotonic Quantity Clamping
        # Max loss dollar amount allowed: portfolio_equity_usd * 0.015
        max_allowed_loss_usd = portfolio_equity_usd * self.max_single_trade_loss_pct

        # Dollar risk per unit quantity at stop loss spread distance:
        # loss_per_unit = spot_price * (stop_loss_basis_bps / 10,000)
        sl_fraction = max(1e-4, stop_loss_basis_bps / 10000.0)
        loss_per_unit_usd = spot_price * sl_fraction

        if loss_per_unit_usd > 0:
            max_risk_quantity = max_allowed_loss_usd / loss_per_unit_usd
        else:
            max_risk_quantity = 0.0

        # Monotonic quantity clamping
        approved_quantity = min(requested_quantity, max_risk_quantity)

        gate_5_pass = approved_quantity > 0.0 and requested_quantity <= max_risk_quantity * 1.001
        checks.append(
            RiskCheckResult(
                check_name="single_trade_equity_risk_cap",
                passed=gate_5_pass,
                observed_value={
                    "requested_qty": requested_quantity,
                    "max_risk_qty": max_risk_quantity,
                    "potential_loss_usd": requested_quantity * loss_per_unit_usd,
                },
                threshold=max_allowed_loss_usd,
                details=f"Max loss allowed ${max_allowed_loss_usd:.2f} (1.5%), requested risk ${requested_quantity * loss_per_unit_usd:.2f}",
            )
        )
        if requested_quantity > max_risk_quantity:
            reasons.append(
                f"EQUITY_RISK_CAP_CLAMPED: Requested {requested_quantity:.4f} clamped to max risk capacity {approved_quantity:.4f}"
            )

        # Overall Approval
        is_approved = (
            gate_1_pass
            and gate_2_pass
            and gate_3_pass
            and gate_4_pass
            and (approved_quantity > 0.0)
            and not self._circuit_breaker_tripped
        )

        final_approved_qty = approved_quantity if is_approved else 0.0

        return BasisRiskVerdict(
            is_approved=is_approved,
            requested_quantity=requested_quantity,
            approved_quantity=final_approved_qty,
            risk_checks=checks,
            rejection_reasons=reasons,
            circuit_breaker_active=self._circuit_breaker_tripped,
            circuit_breaker_lockout_remaining_s=self.circuit_breaker_lockout_duration_s
            if self._circuit_breaker_tripped
            else 0.0,
            real_capital_enabled=False,
            timestamp_ns=time.monotonic_ns(),
        )

    def trigger_emergency_circuit_breaker(self, reason: str) -> None:
        """Manually or externally trips the basis risk circuit breaker."""
        self._circuit_breaker_tripped = True
        self._circuit_breaker_trip_timestamp = time.monotonic()
        self._trip_reason = f"MANUAL_EMERGENCY_TRIP: {reason}"
        logger.critical("BasisRiskGovernor CIRCUIT BREAKER TRIPPED: %s", reason)

    def reset_circuit_breaker(self) -> None:
        """Manually clears the circuit breaker."""
        self._circuit_breaker_tripped = False
        self._circuit_breaker_trip_timestamp = 0.0
        self._trip_reason = ""
        logger.info("BasisRiskGovernor CIRCUIT BREAKER RESET.")
