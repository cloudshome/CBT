"""
core/arena/engine.py
====================
Darwinian Specialist Research Arena Engine (Milestone 21).

Orchestrates:
- 10 isolated coin specialists with $100 starting virtual equity each ($1,000 total).
- Live feed evaluation, realistic paper simulation (fees + slippage).
- Mark-to-market equity and asset-specific Buy-and-Hold benchmark alpha.
- Automatic survival state machine transitions (SURVIVING -> PROBATION -> QUARANTINED).
- Complete isolation from the master $10,000 portfolio.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.arena.benchmark import AssetBenchmarkEngine
from core.arena.ledger import ArenaLedger
from core.arena.models import (
    ArenaLeaderboardSnapshot,
    ArenaPosition,
    ArenaSpecialistAccount,
    ArenaTradeRecord,
    SpecialistSurvivalStatus,
)
from core.arena.survival import SurvivalStateMachine

logger = logging.getLogger("sky.arena.engine")

ARENA_DEFAULT_SYMBOLS = [
    ("spec_arena_btc", "BTC/USDT", "concept_pullback_v1"),
    ("spec_arena_eth", "ETH/USDT", "concept_momentum_v1"),
    ("spec_arena_sol", "SOL/USDT", "concept_breakout_v1"),
    ("spec_arena_bnb", "BNB/USDT", "concept_trend_continuation_v1"),
    ("spec_arena_xrp", "XRP/USDT", "concept_volatility_expansion_v1"),
    ("spec_arena_link", "LINK/USDT", "concept_mean_reversion_v1"),
    ("spec_arena_doge", "DOGE/USDT", "concept_momentum_spike_v1"),
    ("spec_arena_avax", "AVAX/USDT", "concept_trend_continuation_v1"),
    ("spec_arena_sui", "SUI/USDT", "concept_breakout_v1"),
    ("spec_arena_zec", "ZEC/USDT", "concept_sweep_reversal_v1"),
]

# Conservative execution friction: 0.05% fee (5 bps) + 0.02% slippage (2 bps) = 7 bps per leg
TAKER_FEE_RATE = 0.0005
SLIPPAGE_RATE = 0.0002


class DarwinianArenaEngine:
    """Execution simulator and tournament manager for the 10 Darwinian Arena Specialists."""

    def __init__(
        self,
        ledger: ArenaLedger | None = None,
        survival_machine: SurvivalStateMachine | None = None,
        initial_capital_per_specialist: float = 100.0,
    ) -> None:
        self.ledger = ledger or ArenaLedger()
        self.survival = survival_machine or SurvivalStateMachine()
        self.initial_capital = initial_capital_per_specialist
        self._ensure_specialists_initialized()

    def _ensure_specialists_initialized(self) -> None:
        """Initializes all 10 specialists in SQLite if not already present."""
        now_ms = int(time.time() * 1000)
        for spec_id, symbol, strat_id in ARENA_DEFAULT_SYMBOLS:
            existing = self.ledger.get_account(spec_id)
            if not existing:
                account = ArenaSpecialistAccount(
                    specialist_id=spec_id,
                    symbol=symbol,
                    initial_equity_usd=self.initial_capital,
                    current_cash_usd=self.initial_capital,
                    current_equity_usd=self.initial_capital,
                    peak_equity_usd=self.initial_capital,
                    active_strategy_id=strat_id,
                    status=SpecialistSurvivalStatus.SURVIVING,
                    last_updated_ms=now_ms,
                )
                self.ledger.upsert_account(account)
                self.ledger.record_event(
                    specialist_id=spec_id,
                    event_type="INITIALIZED",
                    old_status="NONE",
                    new_status=SpecialistSurvivalStatus.SURVIVING.value,
                    reason=f"Specialist initialized with ${self.initial_capital:.2f} virtual sandbox capital",
                )

    def on_market_tick(
        self,
        symbol: str,
        current_price: float,
        timestamp_ms: int | None = None,
    ) -> ArenaSpecialistAccount | None:
        """
        Processes incoming market price tick for an asset:
        1. Updates benchmark buy & hold return.
        2. Updates open position mark-to-market.
        3. Evaluates SL/TP hit conditions.
        4. Evaluates survival state machine.
        """
        now_ms = timestamp_ms or int(time.time() * 1000)
        account = self.get_specialist_by_symbol(symbol)
        if not account:
            return None

        # 1. Update Benchmark Tracking
        if account.benchmark_initial_price is None or account.benchmark_initial_price <= 0:
            account.benchmark_initial_price = current_price
        account.benchmark_current_price = current_price

        # 2. Open Position Management & SL/TP checking
        unrealized = 0.0
        if account.open_position:
            pos = account.open_position
            if pos.direction == "LONG":
                unrealized = (current_price - pos.entry_price) * pos.size_units
                if pos.stop_loss > 0 and current_price <= pos.stop_loss:
                    self.close_position(account.specialist_id, current_price, "STOP_LOSS", now_ms)
                    return self.ledger.get_account(account.specialist_id)
                elif pos.take_profit > 0 and current_price >= pos.take_profit:
                    self.close_position(account.specialist_id, current_price, "TAKE_PROFIT", now_ms)
                    return self.ledger.get_account(account.specialist_id)
            else:  # SHORT
                unrealized = (pos.entry_price - current_price) * pos.size_units
                if pos.stop_loss > 0 and current_price >= pos.stop_loss:
                    self.close_position(account.specialist_id, current_price, "STOP_LOSS", now_ms)
                    return self.ledger.get_account(account.specialist_id)
                elif pos.take_profit > 0 and current_price <= pos.take_profit:
                    self.close_position(account.specialist_id, current_price, "TAKE_PROFIT", now_ms)
                    return self.ledger.get_account(account.specialist_id)

        # 3. Update Equity & Drawdown
        account.unrealized_pnl_usd = round(unrealized, 4)
        account.current_equity_usd = round(account.current_cash_usd + unrealized, 4)
        if account.current_equity_usd > account.peak_equity_usd:
            account.peak_equity_usd = account.current_equity_usd

        if account.peak_equity_usd > 0:
            dd = ((account.peak_equity_usd - account.current_equity_usd) / account.peak_equity_usd) * 100.0
            account.max_drawdown_pct = max(account.max_drawdown_pct, round(dd, 2))

        # 4. Compute Benchmark Metrics
        bench_metrics = AssetBenchmarkEngine.calculate(
            initial_price=account.benchmark_initial_price,
            current_price=current_price,
            initial_equity=account.initial_equity_usd,
            current_equity=account.current_equity_usd,
        )
        account.benchmark_return_pct = bench_metrics.benchmark_return_pct
        account.specialist_return_pct = bench_metrics.specialist_return_pct
        account.alpha_vs_benchmark_pct = bench_metrics.alpha_pct
        account.last_updated_ms = now_ms

        # 5. Evaluate Survival State
        surv_res = self.survival.evaluate(account)
        if surv_res.status_changed:
            self.ledger.record_event(
                specialist_id=account.specialist_id,
                event_type="STATUS_CHANGE",
                old_status=account.status.value,
                new_status=surv_res.new_status.value,
                reason=surv_res.reason,
            )
            account.status = surv_res.new_status
            account.quarantine_reason = surv_res.reason if not surv_res.is_active else None

        self.ledger.upsert_account(account)
        return account

    def open_position(
        self,
        specialist_id: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        fraction_of_equity: float = 0.50,
        strategy_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> ArenaPosition | None:
        """
        Opens a simulated position strictly inside the specialist's sandbox.
        Fails if specialist is QUARANTINED, REJECTED, or already in a position.
        """
        now_ms = timestamp_ms or int(time.time() * 1000)
        account = self.ledger.get_account(specialist_id)
        if not account:
            logger.warning("Specialist %s not found", specialist_id)
            return None

        # Check survival eligibility
        if account.status in (SpecialistSurvivalStatus.QUARANTINED, SpecialistSurvivalStatus.REJECTED):
            logger.warning("Specialist %s is %s; trade blocked", specialist_id, account.status.value)
            return None

        if account.open_position is not None:
            logger.warning("Specialist %s already has an open position", specialist_id)
            return None

        # Sizing: fraction of current cash
        effective_fraction = fraction_of_equity
        if account.status == SpecialistSurvivalStatus.PROBATION:
            effective_fraction *= 0.5  # Sizing halved under probation

        notional_usd = round(account.current_cash_usd * effective_fraction, 2)
        if notional_usd <= 0 or entry_price <= 0:
            return None

        # Apply simulated entry friction (slippage + fee)
        fee = notional_usd * TAKER_FEE_RATE
        account.current_cash_usd -= fee
        account.fees_paid_usd += fee

        effective_entry_price = (
            entry_price * (1.0 + SLIPPAGE_RATE) if direction == "LONG" else entry_price * (1.0 - SLIPPAGE_RATE)
        )
        size_units = notional_usd / effective_entry_price

        pos = ArenaPosition(
            symbol=account.symbol,
            direction=direction,
            entry_price=round(effective_entry_price, 4),
            size_units=round(size_units, 6),
            notional_usd=notional_usd,
            entry_time_ms=now_ms,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy_id=strategy_id or account.active_strategy_id,
            strategy_version=account.active_strategy_version,
        )

        account.open_position = pos
        self.ledger.upsert_account(account)
        return pos

    def close_position(
        self,
        specialist_id: str,
        exit_price: float,
        exit_reason: str,
        timestamp_ms: int | None = None,
    ) -> ArenaTradeRecord | None:
        """Closes an active position, applies friction, records PnL, and evaluates survival."""
        now_ms = timestamp_ms or int(time.time() * 1000)
        account = self.ledger.get_account(specialist_id)
        if not account or not account.open_position:
            return None

        pos = account.open_position

        # Apply simulated exit friction
        effective_exit = (
            exit_price * (1.0 - SLIPPAGE_RATE) if pos.direction == "LONG" else exit_price * (1.0 + SLIPPAGE_RATE)
        )
        exit_notional = pos.size_units * effective_exit
        fee = exit_notional * TAKER_FEE_RATE

        if pos.direction == "LONG":
            gross_pnl = (effective_exit - pos.entry_price) * pos.size_units
        else:
            gross_pnl = (pos.entry_price - effective_exit) * pos.size_units

        net_pnl = gross_pnl - fee
        net_pct = (net_pnl / pos.notional_usd) * 100.0 if pos.notional_usd > 0 else 0.0

        trade_rec = ArenaTradeRecord(
            trade_id=f"trd_arena_{uuid.uuid4().hex[:10]}",
            specialist_id=specialist_id,
            symbol=pos.symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=round(effective_exit, 4),
            size_units=pos.size_units,
            notional_usd=pos.notional_usd,
            gross_pnl_usd=round(gross_pnl, 4),
            fees_usd=round(fee, 4),
            net_pnl_usd=round(net_pnl, 4),
            net_pnl_pct=round(net_pct, 2),
            entry_timestamp_ms=pos.entry_time_ms,
            exit_timestamp_ms=now_ms,
            strategy_id=pos.strategy_id,
            exit_reason=exit_reason,
        )

        self.ledger.record_trade(trade_rec)

        # Update account balances
        account.current_cash_usd = round(account.current_cash_usd + net_pnl, 4)
        account.current_equity_usd = account.current_cash_usd
        account.realized_pnl_usd = round(account.realized_pnl_usd + net_pnl, 4)
        account.fees_paid_usd = round(account.fees_paid_usd + fee, 4)
        account.unrealized_pnl_usd = 0.0
        account.open_position = None
        account.total_trades += 1

        if net_pnl > 0:
            account.winning_trades += 1
            account.consecutive_losses = 0
        else:
            account.losing_trades += 1
            account.consecutive_losses += 1

        if account.current_equity_usd > account.peak_equity_usd:
            account.peak_equity_usd = account.current_equity_usd

        if account.peak_equity_usd > 0:
            dd = ((account.peak_equity_usd - account.current_equity_usd) / account.peak_equity_usd) * 100.0
            account.max_drawdown_pct = max(account.max_drawdown_pct, round(dd, 2))

        # Re-evaluate survival state after closed trade
        surv_res = self.survival.evaluate(account)
        if surv_res.status_changed:
            self.ledger.record_event(
                specialist_id=account.specialist_id,
                event_type="STATUS_CHANGE",
                old_status=account.status.value,
                new_status=surv_res.new_status.value,
                reason=surv_res.reason,
            )
            account.status = surv_res.new_status
            account.quarantine_reason = surv_res.reason if not surv_res.is_active else None

        self.ledger.upsert_account(account)
        return trade_rec

    def get_specialist_by_symbol(self, symbol: str) -> ArenaSpecialistAccount | None:
        """Finds a specialist account matching the asset symbol."""
        for acc in self.ledger.get_all_accounts():
            if acc.symbol == symbol:
                return acc
        return None

    def get_leaderboard(self) -> ArenaLeaderboardSnapshot:
        """Constructs an audited leaderboard snapshot."""
        accounts = self.ledger.get_all_accounts()
        total_equity = sum(a.current_equity_usd for a in accounts)
        active_count = sum(1 for a in accounts if a.status != SpecialistSurvivalStatus.QUARANTINED)
        quarantined_count = sum(1 for a in accounts if a.status == SpecialistSurvivalStatus.QUARANTINED)

        return ArenaLeaderboardSnapshot(
            timestamp_ms=int(time.time() * 1000),
            total_arena_equity_usd=round(total_equity, 2),
            master_desk_equity_usd=10_000.0,
            active_specialists_count=active_count,
            quarantined_specialists_count=quarantined_count,
            specialists=accounts,
        )
