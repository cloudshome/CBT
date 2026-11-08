"""
core/research/portfolio_accounting_reconciler.py
=================================================
P0 Forensic Accounting Reconciliation & Invariant Engine.

Implements an independent double-entry mathematical accounting auditor for
discrete-event portfolio replay simulations.

Accounting Convention: Cash-Reserved Portfolio Model
---------------------------------------------------
In this model, when a position is opened:
  1. Cash is decremented by notional plus entry frictions:
       cash_t = cash_{t-1} - (notional + entry_frictions)
  2. While active, the position holds reserved notional plus mark-to-market unrealized PnL:
       position_value_i = notional_i + unrealized_pnl_i
  3. Total portfolio mark-to-market equity is:
       Equity_t = Cash_t + sum_{i in Open}(notional_i + unrealized_pnl_i)
  4. Conservation of Capital Invariant:
       Equity_t == InitialCash + RealizedGross_t + sum_{i in Open}(unrealized_pnl_i) - TotalFrictions_t - TotalFunding_t
     where:
       TotalFrictions_t = sum_{k in Closed}(entry_frictions_k + exit_frictions_k) + sum_{i in Open}(entry_frictions_i)

This module operates independently from the simulation engine to verify
every ledger state transition with Decimal precision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional, Tuple
import math


ROUNDING_TOLERANCE_USD = Decimal("0.001")


def to_dec(val: float | int | str | Decimal) -> Decimal:
    """Converts input to Decimal with string grounding to prevent float precision drift."""
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (float, int)):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Invalid non-finite numerical value: {val}")
        return Decimal(str(round(val, 8)))
    return Decimal(str(val))


@dataclass
class PositionLedgerItem:
    position_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_ts: int
    entry_price: Decimal
    size: Decimal
    notional: Decimal
    allocated_risk_usd: Decimal
    entry_frictions: Decimal
    current_price: Decimal = Decimal("0.0")
    unrealized_pnl: Decimal = Decimal("0.0")
    accumulated_funding: Decimal = Decimal("0.0")


@dataclass
class ClosedTradeRecord:
    position_id: str
    symbol: str
    direction: str
    entry_ts: int
    exit_ts: int
    entry_price: Decimal
    exit_price: Decimal
    size: Decimal
    notional: Decimal
    gross_pnl: Decimal
    entry_frictions: Decimal
    exit_frictions: Decimal
    total_frictions: Decimal
    funding_paid: Decimal
    net_pnl: Decimal
    exit_reason: str


@dataclass
class ReconciliationCheckpoint:
    timestamp: int
    reported_cash: Decimal
    reported_equity: Decimal
    reconciled_cash: Decimal
    reconciled_equity: Decimal
    discrepancy_usd: Decimal
    is_valid: bool
    open_positions_count: int
    total_unrealized_pnl: Decimal
    total_realized_gross: Decimal
    total_frictions: Decimal
    total_funding: Decimal


class PortfolioAccountingReconciler:
    """
    Independent Institutional Portfolio Accounting Reconciler.
    Enforces Conservation of Capital across every event transition.
    """

    def __init__(self, initial_cash: float | Decimal = 10_000.0) -> None:
        self.initial_cash = to_dec(initial_cash)
        if self.initial_cash <= Decimal("0.0"):
            raise ValueError(f"Initial cash must be strictly positive: {initial_cash}")

        self.cash: Decimal = self.initial_cash
        self.open_positions: Dict[str, PositionLedgerItem] = {}
        self.closed_trades: List[ClosedTradeRecord] = []
        self.checkpoints: List[ReconciliationCheckpoint] = []

        self.total_realized_gross: Decimal = Decimal("0.0")
        self.total_frictions_paid: Decimal = Decimal("0.0")
        self.total_funding_paid: Decimal = Decimal("0.0")
        self.last_timestamp: int = -1

    def open_position(
        self,
        position_id: str,
        symbol: str,
        direction: str,
        entry_ts: int,
        entry_price: float | Decimal,
        size: float | Decimal,
        allocated_risk_usd: float | Decimal,
        friction_rate_bps: float | Decimal = 0.0007,
    ) -> PositionLedgerItem:
        """Records position opening under cash-reserved convention."""
        if entry_ts < self.last_timestamp:
            raise ValueError(f"Out-of-order timestamp: {entry_ts} < {self.last_timestamp}")
        self.last_timestamp = entry_ts

        if position_id in self.open_positions:
            raise ValueError(f"Duplicate position ID rejected: {position_id}")

        p_entry = to_dec(entry_price)
        p_size = to_dec(size)
        p_risk = to_dec(allocated_risk_usd)
        p_fric_rate = to_dec(friction_rate_bps)

        if p_entry <= Decimal("0.0") or p_size <= Decimal("0.0"):
            raise ValueError(f"Invalid entry price or size: price={p_entry}, size={p_size}")

        notional = p_size * p_entry
        entry_frictions = notional * p_fric_rate
        total_required_cash = notional + entry_frictions

        if total_required_cash > self.cash:
            raise ValueError(
                f"Insufficient cash for position {position_id}: required={total_required_cash}, available={self.cash}"
            )

        # Cash decrement
        self.cash -= total_required_cash
        self.total_frictions_paid += entry_frictions

        item = PositionLedgerItem(
            position_id=position_id,
            symbol=symbol,
            direction=direction.upper(),
            entry_ts=entry_ts,
            entry_price=p_entry,
            size=p_size,
            notional=notional,
            allocated_risk_usd=p_risk,
            entry_frictions=entry_frictions,
            current_price=p_entry,
            unrealized_pnl=Decimal("0.0"),
            accumulated_funding=Decimal("0.0"),
        )
        self.open_positions[position_id] = item
        return item

    def update_mark_to_market(
        self,
        timestamp: int,
        current_prices: Dict[str, float | Decimal],
    ) -> None:
        """Updates open position valuations and unrealized PnL."""
        if timestamp < self.last_timestamp:
            raise ValueError(f"Out-of-order timestamp in MTM update: {timestamp} < {self.last_timestamp}")
        self.last_timestamp = timestamp

        for pos in self.open_positions.values():
            if pos.symbol in current_prices:
                curr_p = to_dec(current_prices[pos.symbol])
                if curr_p <= Decimal("0.0"):
                    raise ValueError(f"Non-positive mark price for {pos.symbol}: {curr_p}")
                pos.current_price = curr_p
                if pos.direction == "LONG":
                    pos.unrealized_pnl = (curr_p - pos.entry_price) * pos.size
                elif pos.direction == "SHORT":
                    pos.unrealized_pnl = (pos.entry_price - curr_p) * pos.size
                else:
                    raise ValueError(f"Invalid direction: {pos.direction}")

    def apply_funding(
        self,
        timestamp: int,
        position_id: str,
        funding_rate: float | Decimal,
    ) -> Decimal:
        """
        Applies perpetual funding settlement to an open position.
        Funding fee = mark_notional * funding_rate (positive rate: longs pay shorts).
        """
        if position_id not in self.open_positions:
            raise KeyError(f"Position {position_id} not found for funding settlement")

        pos = self.open_positions[position_id]
        f_rate = to_dec(funding_rate)
        mark_notional = pos.size * pos.current_price
        
        # Long pays when funding is positive; Short receives when funding is positive
        if pos.direction == "LONG":
            payment = mark_notional * f_rate
        else:
            payment = -(mark_notional * f_rate)

        # Deduct payment from cash (if payment is negative, cash increases)
        self.cash -= payment
        pos.accumulated_funding += payment
        self.total_funding_paid += payment
        return payment

    def close_position(
        self,
        position_id: str,
        exit_ts: int,
        exit_price: float | Decimal,
        exit_reason: str = "SIGNAL",
        friction_rate_bps: float | Decimal = 0.0007,
    ) -> ClosedTradeRecord:
        """Closes an open position and returns reserved notional + gross PnL - exit frictions to cash."""
        if position_id not in self.open_positions:
            raise KeyError(f"Position {position_id} not found in open positions")

        pos = self.open_positions.pop(position_id)
        p_exit = to_dec(exit_price)
        p_fric_rate = to_dec(friction_rate_bps)

        if p_exit <= Decimal("0.0"):
            raise ValueError(f"Non-positive exit price for {position_id}: {p_exit}")

        if pos.direction == "LONG":
            gross_pnl = (p_exit - pos.entry_price) * pos.size
        elif pos.direction == "SHORT":
            gross_pnl = (pos.entry_price - p_exit) * pos.size
        else:
            raise ValueError(f"Invalid direction: {pos.direction}")

        exit_notional = p_exit * pos.size
        exit_frictions = exit_notional * p_fric_rate
        total_trade_frictions = pos.entry_frictions + exit_frictions
        net_pnl = gross_pnl - total_trade_frictions - pos.accumulated_funding

        # Cash return: notional + gross PnL - exit frictions
        self.cash += pos.notional + gross_pnl - exit_frictions
        self.total_realized_gross += gross_pnl
        self.total_frictions_paid += exit_frictions

        record = ClosedTradeRecord(
            position_id=pos.position_id,
            symbol=pos.symbol,
            direction=pos.direction,
            entry_ts=pos.entry_ts,
            exit_ts=exit_ts,
            entry_price=pos.entry_price,
            exit_price=p_exit,
            size=pos.size,
            notional=pos.notional,
            gross_pnl=gross_pnl,
            entry_frictions=pos.entry_frictions,
            exit_frictions=exit_frictions,
            total_frictions=total_trade_frictions,
            funding_paid=pos.accumulated_funding,
            net_pnl=net_pnl,
            exit_reason=exit_reason,
        )
        self.closed_trades.append(record)
        return record

    def partial_close(
        self,
        position_id: str,
        exit_ts: int,
        exit_price: float | Decimal,
        closed_size: float | Decimal,
        exit_reason: str = "PARTIAL_TP",
        friction_rate_bps: float | Decimal = 0.0007,
    ) -> ClosedTradeRecord:
        """Executes a partial position close, updating remaining notional and size."""
        if position_id not in self.open_positions:
            raise KeyError(f"Position {position_id} not found in open positions")

        pos = self.open_positions[position_id]
        c_size = to_dec(closed_size)
        p_exit = to_dec(exit_price)
        p_fric = to_dec(friction_rate_bps)

        if c_size <= Decimal("0.0") or c_size >= pos.size:
            raise ValueError(f"Partial close size {c_size} must be in (0, {pos.size})")

        closed_fraction = c_size / pos.size
        closed_notional = pos.notional * closed_fraction
        closed_entry_frictions = pos.entry_frictions * closed_fraction

        if pos.direction == "LONG":
            gross_pnl = (p_exit - pos.entry_price) * c_size
        else:
            gross_pnl = (pos.entry_price - p_exit) * c_size

        exit_notional = p_exit * c_size
        exit_frictions = exit_notional * p_fric
        trade_frictions = closed_entry_frictions + exit_frictions
        net_pnl = gross_pnl - trade_frictions

        # Return closed portion to cash
        self.cash += closed_notional + gross_pnl - exit_frictions
        self.total_realized_gross += gross_pnl
        self.total_frictions_paid += exit_frictions

        # Update remaining position
        pos.size -= c_size
        pos.notional -= closed_notional
        pos.entry_frictions -= closed_entry_frictions
        pos.allocated_risk_usd *= (Decimal("1.0") - closed_fraction)
        if pos.direction == "LONG":
            pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.size
        elif pos.direction == "SHORT":
            pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.size

        record = ClosedTradeRecord(
            position_id=f"{pos.position_id}_PARTIAL",
            symbol=pos.symbol,
            direction=pos.direction,
            entry_ts=pos.entry_ts,
            exit_ts=exit_ts,
            entry_price=pos.entry_price,
            exit_price=p_exit,
            size=c_size,
            notional=closed_notional,
            gross_pnl=gross_pnl,
            entry_frictions=closed_entry_frictions,
            exit_frictions=exit_frictions,
            total_frictions=trade_frictions,
            funding_paid=Decimal("0.0"),
            net_pnl=net_pnl,
            exit_reason=exit_reason,
        )
        self.closed_trades.append(record)
        return record

    def calculate_current_equity(self) -> Decimal:
        """
        Computes mark-to-market equity via the cash-reserved convention:
          Equity = Cash + sum(notional_i + unrealized_pnl_i)
        """
        open_value = sum(
            (pos.notional + pos.unrealized_pnl) for pos in self.open_positions.values()
        )
        return self.cash + open_value

    def calculate_invariant_equity(self) -> Decimal:
        """
        Computes equity independently via the Conservation of Capital Invariant:
          Equity = InitialCash + RealizedGross + TotalUnrealized - TotalFrictions - TotalFunding
        """
        total_unrealized = sum(pos.unrealized_pnl for pos in self.open_positions.values())
        return (
            self.initial_cash
            + self.total_realized_gross
            + total_unrealized
            - self.total_frictions_paid
            - self.total_funding_paid
        )

    def verify_reconciliation(
        self,
        timestamp: int,
        reported_cash: float | Decimal,
        reported_equity: float | Decimal,
        fail_closed: bool = True,
    ) -> ReconciliationCheckpoint:
        """
        Performs exhaustive mathematical reconciliation between:
          1. Reconciler Cash vs Reported Cash
          2. Reconciler Mark-to-Market Equity vs Reported Equity
          3. Reconciler Mark-to-Market Equity vs Conservation of Capital Invariant
        """
        rep_cash = to_dec(reported_cash)
        rep_eq = to_dec(reported_equity)
        calc_eq = self.calculate_current_equity()
        inv_eq = self.calculate_invariant_equity()

        # Invariant self-check (reconciler internal consistency)
        inv_diff = abs(calc_eq - inv_eq)
        if inv_diff > ROUNDING_TOLERANCE_USD:
            msg = (
                f"[CRITICAL ACCOUNTING FAILURE] Reconciler internal invariant violated at ts={timestamp}: "
                f"MTM_Equity={calc_eq}, Invariant_Equity={inv_eq}, Diff={inv_diff}"
            )
            if fail_closed:
                raise AssertionError(msg)

        # Check against reported values
        cash_diff = abs(self.cash - rep_cash)
        eq_diff = abs(calc_eq - rep_eq)
        total_diff = max(cash_diff, eq_diff)
        is_valid = total_diff <= ROUNDING_TOLERANCE_USD

        if not is_valid and fail_closed:
            msg = (
                f"[RECONCILIATION DISCREPANCY] at ts={timestamp}:\n"
                f"  Reported Cash:   {rep_cash} | Reconciled Cash:   {self.cash} (Diff: {cash_diff})\n"
                f"  Reported Equity: {rep_eq} | Reconciled Equity: {calc_eq} (Diff: {eq_diff})\n"
                f"  Open Positions:  {len(self.open_positions)}"
            )
            raise AssertionError(msg)

        checkpoint = ReconciliationCheckpoint(
            timestamp=timestamp,
            reported_cash=rep_cash,
            reported_equity=rep_eq,
            reconciled_cash=self.cash,
            reconciled_equity=calc_eq,
            discrepancy_usd=total_diff,
            is_valid=is_valid,
            open_positions_count=len(self.open_positions),
            total_unrealized_pnl=sum(p.unrealized_pnl for p in self.open_positions.values()),
            total_realized_gross=self.total_realized_gross,
            total_frictions=self.total_frictions_paid,
            total_funding=self.total_funding_paid,
        )
        self.checkpoints.append(checkpoint)
        return checkpoint
