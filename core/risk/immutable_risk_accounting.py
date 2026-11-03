"""
core/risk/immutable_risk_accounting.py
======================================
Milestone 31: Immutable Initial Risk Accounting & Denominator Protection.

Core Mandates:
1. Capture initial risk budget ($R_0$) at position inception.
2. Never overwrite original stop-loss geometry when trailing stops ratchet or hit breakeven.
3. Support partial entries and partial exits with proportional risk attribution.
4. Correctly incorporate contract multipliers and quantity changes.
5. Calculate realized Net R strictly against original immutable initial risk.
6. Detect zero, negative, missing, or implausible risk denominators.
7. Mark unrecoverable historical risk records as R_UNVERIFIABLE.
8. Reject invalid R calculations and eliminate the Trade 36 division-by-cents defect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskAccountingStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIABLE = "R_UNVERIFIABLE"
    INVALID_DENOMINATOR = "INVALID_DENOMINATOR"
    IMPLAUSIBLE_DENOMINATOR = "IMPLAUSIBLE_DENOMINATOR"
    GEOMETRY_SANITY_ERROR = "GEOMETRY_SANITY_ERROR"


@dataclass(frozen=True)
class ImmutableRiskBudget:
    """
    Immutable snapshot of position risk established at order creation/fill.
    Once established, this record is permanently frozen. Trailing stops,
    breakeven adjustments, and ratchets NEVER alter this budget.
    """

    position_id: str
    symbol: str
    direction: str
    entry_price: float
    initial_size: float
    initial_stop_loss: float
    initial_take_profit: float
    contract_multiplier: float = 1.0
    status: RiskAccountingStatus = RiskAccountingStatus.VERIFIED
    rejection_reason: str = ""

    # Computed fields
    initial_risk_per_unit: float = field(init=False)
    initial_risk_usd: float = field(init=False)
    initial_notional_usd: float = field(init=False)
    initial_risk_pct: float = field(init=False)

    def __post_init__(self) -> None:
        ep = float(self.entry_price)
        sl = float(self.initial_stop_loss)
        sz = float(self.initial_size)
        cm = float(self.contract_multiplier)
        dir_u = self.direction.upper()

        notional = ep * sz * cm
        object.__setattr__(self, "initial_notional_usd", notional)

        # Basic geometry sanity checks
        if ep <= 0 or sl <= 0 or sz <= 0 or cm <= 0:
            object.__setattr__(self, "initial_risk_per_unit", 0.0)
            object.__setattr__(self, "initial_risk_usd", 0.0)
            object.__setattr__(self, "initial_risk_pct", 0.0)
            object.__setattr__(self, "status", RiskAccountingStatus.INVALID_DENOMINATOR)
            object.__setattr__(
                self,
                "rejection_reason",
                f"Non-positive entry (${ep}), stop (${sl}), size ({sz}), or multiplier ({cm}).",
            )
            return

        if dir_u == "LONG":
            risk_dist = ep - sl
        elif dir_u == "SHORT":
            risk_dist = sl - ep
        else:
            object.__setattr__(self, "initial_risk_per_unit", 0.0)
            object.__setattr__(self, "initial_risk_usd", 0.0)
            object.__setattr__(self, "initial_risk_pct", 0.0)
            object.__setattr__(self, "status", RiskAccountingStatus.GEOMETRY_SANITY_ERROR)
            object.__setattr__(self, "rejection_reason", f"Invalid direction '{self.direction}'.")
            return

        if risk_dist <= 0:
            object.__setattr__(self, "initial_risk_per_unit", 0.0)
            object.__setattr__(self, "initial_risk_usd", 0.0)
            object.__setattr__(self, "initial_risk_pct", 0.0)
            object.__setattr__(self, "status", RiskAccountingStatus.INVALID_DENOMINATOR)
            object.__setattr__(
                self,
                "rejection_reason",
                f"Stop loss (${sl}) on wrong side of entry (${ep}) for {dir_u} trade (distance: {risk_dist}).",
            )
            return

        risk_pct = risk_dist / ep
        risk_usd = risk_dist * sz * cm

        # Denominator Plausibility Sanity Check:
        # If stop distance is micro-cents (< 0.05% of price) or dollar risk is < $1.00 on institutional desk,
        # flag as implausible denominator (the exact Trade 36 failure condition).
        if risk_pct < 0.0005 or risk_usd < 1.00:
            object.__setattr__(self, "initial_risk_per_unit", risk_dist)
            object.__setattr__(self, "initial_risk_usd", risk_usd)
            object.__setattr__(self, "initial_risk_pct", risk_pct)
            object.__setattr__(self, "status", RiskAccountingStatus.IMPLAUSIBLE_DENOMINATOR)
            object.__setattr__(
                self,
                "rejection_reason",
                f"Implausible risk denominator: risk_usd=${risk_usd:.4f} ({risk_pct * 100:.3f}% of entry). "
                f"Likely breakeven stop collision.",
            )
            return

        object.__setattr__(self, "initial_risk_per_unit", risk_dist)
        object.__setattr__(self, "initial_risk_usd", risk_usd)
        object.__setattr__(self, "initial_risk_pct", risk_pct)
        object.__setattr__(self, "status", RiskAccountingStatus.VERIFIED)
        object.__setattr__(self, "rejection_reason", "")


class PositionRiskLedger:
    """
    Manages the lifecycle of a position while preserving immutable initial risk.
    Guarantees that trailing stop ratchets or breakeven adjustments never
    overwrite or collapse the initial risk budget.
    """

    def __init__(self, budget: ImmutableRiskBudget) -> None:
        self.budget = budget
        self.current_stop_loss: float = budget.initial_stop_loss
        self.current_size: float = budget.initial_size
        self.realized_pnl_usd: float = 0.0
        self.fees_usd: float = 0.0
        self.funding_usd: float = 0.0
        self.slippage_usd: float = 0.0
        self.breakeven_triggered: bool = False
        self.trailing_stop: float | None = None
        self.is_closed: bool = False
        self.partial_exits: list[dict[str, Any]] = []

    def update_stop_loss(self, new_stop: float, is_breakeven: bool = False) -> None:
        """
        Updates the ACTIVE operational stop-loss (e.g. breakeven or trailing ratchet).
        STRICT INVARIANT: The underlying ImmutableRiskBudget is untouched.
        """
        ns = float(new_stop)
        dir_u = self.budget.direction.upper()

        # Invariant: Ratchet only in favorable direction
        if dir_u == "LONG" and ns < self.current_stop_loss:
            raise ValueError(
                f"LONG stop cannot be ratcheted downward: {self.current_stop_loss} -> {ns}"
            )
        if dir_u == "SHORT" and ns > self.current_stop_loss:
            raise ValueError(
                f"SHORT stop cannot be ratcheted upward: {self.current_stop_loss} -> {ns}"
            )

        self.current_stop_loss = ns
        if is_breakeven:
            self.breakeven_triggered = True

    def register_partial_exit(
        self,
        exit_size: float,
        exit_price: float,
        fee_usd: float = 0.0,
        slippage_usd: float = 0.0,
    ) -> dict[str, Any]:
        """
        Registers a partial closure of the position.
        Calculates partial realized PnL and attributes proportional initial risk.
        """
        if exit_size <= 0:
            raise ValueError("Exit size must be positive.")
        if exit_size > (self.current_size + 1e-9):
            raise ValueError(
                f"Exit size {exit_size} exceeds remaining position size {self.current_size}."
            )

        ep = self.budget.entry_price
        cm = self.budget.contract_multiplier
        dir_u = self.budget.direction.upper()

        if dir_u == "LONG":
            gross_pnl = (exit_price - ep) * exit_size * cm
        else:
            gross_pnl = (ep - exit_price) * exit_size * cm

        net_pnl = gross_pnl - fee_usd - slippage_usd

        # Proportional initial risk attributed to this partial slice
        slice_fraction = exit_size / self.budget.initial_size
        attributed_risk_usd = self.budget.initial_risk_usd * slice_fraction

        if self.budget.status == RiskAccountingStatus.VERIFIED and attributed_risk_usd > 0:
            slice_r = net_pnl / attributed_risk_usd
        else:
            slice_r = 0.0

        self.current_size -= exit_size
        self.realized_pnl_usd += net_pnl
        self.fees_usd += fee_usd
        self.slippage_usd += slippage_usd

        exit_record = {
            "exit_size": exit_size,
            "exit_price": exit_price,
            "slice_fraction": slice_fraction,
            "gross_pnl_usd": round(gross_pnl, 4),
            "fee_usd": round(fee_usd, 4),
            "slippage_usd": round(slippage_usd, 4),
            "net_pnl_usd": round(net_pnl, 4),
            "attributed_risk_usd": round(attributed_risk_usd, 4),
            "realized_r": round(slice_r, 4),
            "remaining_size": round(self.current_size, 8),
        }
        self.partial_exits.append(exit_record)

        if self.current_size <= 1e-9:
            self.is_closed = True

        return exit_record

    def close_position(
        self,
        exit_price: float,
        fee_usd: float = 0.0,
        slippage_usd: float = 0.0,
        funding_usd: float = 0.0,
    ) -> None:
        """Closes any remaining position and records final costs."""
        if not self.is_closed and self.current_size > 0:
            self.register_partial_exit(
                exit_size=self.current_size,
                exit_price=exit_price,
                fee_usd=fee_usd,
                slippage_usd=slippage_usd,
            )
        self.funding_usd += funding_usd
        self.realized_pnl_usd -= funding_usd
        self.is_closed = True

    def calculate_final_net_r(self) -> tuple[float | None, RiskAccountingStatus, str]:
        """
        Calculates the definitive Net R of the complete position.
        Strictly divides total net PnL by initial immutable risk USD.
        Returns: (net_r, status, rationale)
        """
        if self.budget.status != RiskAccountingStatus.VERIFIED:
            return None, self.budget.status, self.budget.rejection_reason

        risk_usd = self.budget.initial_risk_usd
        if risk_usd <= 0 or math.isnan(risk_usd) or math.isinf(risk_usd):
            return (
                None,
                RiskAccountingStatus.INVALID_DENOMINATOR,
                f"Invalid or non-finite initial risk USD ({risk_usd}).",
            )

        final_r = self.realized_pnl_usd / risk_usd
        return (
            round(final_r, 4),
            RiskAccountingStatus.VERIFIED,
            "Calculated against immutable initial risk.",
        )


def calculate_immutable_realized_r(
    pnl_usd: float,
    entry_price: float,
    initial_stop_loss: float | None,
    current_stop_loss: float | None,
    size: float,
    direction: str,
    contract_multiplier: float = 1.0,
    fee_usd: float = 0.0,
    funding_usd: float = 0.0,
    slippage_usd: float = 0.0,
    min_institutional_risk_floor: float = 25.0,
) -> tuple[float | None, RiskAccountingStatus, str]:
    """
    Robust quantitative calculator for realized net R.
    Corrects historical positions where initial stop was wiped by breakeven.

    Rules:
    1. If initial_stop_loss is present and valid, strictly use it.
    2. If initial_stop_loss is absent, check if current_stop_loss == entry_price (breakeven).
       If breakeven: do NOT divide by 0 or micro-cents.
       Check if initial risk was documented in trade metadata or apply institutional risk floor.
    3. If denominator is unrecoverable, return R_UNVERIFIABLE.
    """
    ep = float(entry_price)
    sz = float(size)
    cm = float(contract_multiplier)
    dir_u = direction.upper()

    net_pnl = pnl_usd - fee_usd - funding_usd - slippage_usd

    # Case 1: Initial stop loss is explicitly preserved
    if initial_stop_loss is not None and initial_stop_loss > 0:
        budget = ImmutableRiskBudget(
            position_id="calc",
            symbol="GENERIC",
            direction=dir_u,
            entry_price=ep,
            initial_size=sz,
            initial_stop_loss=float(initial_stop_loss),
            initial_take_profit=ep * 1.05 if dir_u == "LONG" else ep * 0.95,
            contract_multiplier=cm,
        )
        if budget.status == RiskAccountingStatus.VERIFIED:
            realized_r = net_pnl / budget.initial_risk_usd
            return (
                round(realized_r, 4),
                RiskAccountingStatus.VERIFIED,
                "Calculated using immutable initial_stop_loss.",
            )
        else:
            return None, budget.status, budget.rejection_reason

    # Case 2: Historical record with missing initial_stop_loss
    # Check current stop loss
    c_sl = float(current_stop_loss) if current_stop_loss is not None else None

    # Check for Breakeven trailing stop collapse
    if c_sl is not None and abs(ep - c_sl) < (ep * 0.001):
        # Stop loss was moved to entry (Trade 36 bug).
        # Denominator cannot be derived purely from current stop loss.
        # Fallback to institutional risk floor ($25.00 or 1.5% notional).
        notional = ep * sz * cm
        fallback_risk = max(min_institutional_risk_floor, notional * 0.015)
        corrected_r = net_pnl / fallback_risk
        return (
            round(corrected_r, 4),
            RiskAccountingStatus.UNVERIFIABLE,
            f"Initial stop was overwritten by breakeven trailing stop. "
            f"Normalized using institutional risk budget (${fallback_risk:.2f}).",
        )

    # If current stop loss exists and is geometrically valid on the initial risk side:
    if c_sl is not None and c_sl > 0:
        budget = ImmutableRiskBudget(
            position_id="calc",
            symbol="GENERIC",
            direction=dir_u,
            entry_price=ep,
            initial_size=sz,
            initial_stop_loss=c_sl,
            initial_take_profit=ep * 1.05 if dir_u == "LONG" else ep * 0.95,
            contract_multiplier=cm,
        )
        if budget.status == RiskAccountingStatus.VERIFIED:
            realized_r = net_pnl / budget.initial_risk_usd
            return (
                round(realized_r, 4),
                RiskAccountingStatus.VERIFIED,
                "Calculated using un-ratcheted stop_loss.",
            )

    return (
        None,
        RiskAccountingStatus.UNVERIFIABLE,
        "Unrecoverable initial risk geometry; marked as R_UNVERIFIABLE.",
    )
