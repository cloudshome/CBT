"""
core/arbitrage/shadow_validator.py
==================================
Asynchronous Two-Leg Shadow Reality & Partial-Fill Risk Simulator.

Principles:
- 'The spread existed' != 'The spread was captureable'.
- Simulates independent asynchronous leg dispatches with execution latency drift.
- Explicitly models partial fills (fill ratio < 1.0), unhedged residual exposure,
  and adverse price drift during hedge completion.
- Records predicted Net-EV vs. realized synthetic P&L in SQLite.
"""

from __future__ import annotations

import logging
import random
import time

from core.arbitrage.models import (
    ArbitrageOpportunity,
    FillSimulation,
    FundingRateRecord,
    OrderBookSnapshot,
    ShadowOpportunity,
    Venue,
)
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.arbitrage.shadow_validator")


class ShadowValidator:
    """Simulates realistic asynchronous execution dynamics and tracks synthetic paper P&L."""

    def __init__(self, rng_seed: int = 42) -> None:
        self._rng = random.Random(rng_seed)
        self._active_shadows: dict[str, ShadowOpportunity] = {}
        self._init_db_schema()

    def _init_db_schema(self) -> None:
        """Initializes the shadow validation ledger table in trading_logs.db."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS arbitrage_shadow_ledger (
                        opportunity_id TEXT PRIMARY KEY,
                        canonical_symbol TEXT NOT NULL,
                        opportunity_type TEXT NOT NULL,
                        long_venue TEXT NOT NULL,
                        short_venue TEXT NOT NULL,
                        target_notional_usd REAL NOT NULL,
                        predicted_net_ev_usd REAL NOT NULL,
                        realized_reference_ev_usd REAL,
                        opportunity_duration_ms REAL,
                        unhedged_residual_qty REAL,
                        funding_realized_usd REAL,
                        model_attribution_error_usd REAL,
                        status TEXT NOT NULL,
                        detected_at REAL NOT NULL,
                        qualified_at REAL NOT NULL,
                        expired_at REAL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_arb_shadow_symbol ON arbitrage_shadow_ledger(canonical_symbol);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_arb_shadow_status ON arbitrage_shadow_ledger(status);"
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not initialize arbitrage_shadow_ledger schema: {e}")

    def simulate_entry_execution(
        self,
        opportunity: ArbitrageOpportunity,
        book_long: OrderBookSnapshot,
        book_short: OrderBookSnapshot,
        target_notional: float = 10000.0,
        inter_leg_latency_ms: float = 45.0,
    ) -> ShadowOpportunity:
        """
        Simulates independent two-leg market entry with realistic partial fills
        and inter-exchange network dispatch delay.
        """
        now = time.time()
        ref_mid = (book_long.asks[0].price + book_short.bids[0].price) / 2.0
        requested_qty = target_notional / ref_mid if ref_mid > 0 else 0.1

        # Leg A: Long Order Dispatch
        # Realistic fill ratio between 90% and 100%
        fill_ratio_a = self._rng.uniform(0.92, 1.0)
        filled_qty_a = round(requested_qty * fill_ratio_a, 5)
        residual_a = requested_qty - filled_qty_a
        vwap_price_a = book_long.asks[0].price * (1.0 + (0.0001 * self._rng.uniform(0.5, 1.5)))

        sim_leg_a = FillSimulation(
            leg="LEG_A_LONG",
            venue=opportunity.long_venue,
            side="BUY",
            requested_qty=requested_qty,
            filled_qty=filled_qty_a,
            fill_ratio=fill_ratio_a,
            residual_qty=residual_a,
            vwap_fill_price=vwap_price_a,
            execution_lag_ms=25.0,
            adverse_move_bps=0.5,
        )

        # Leg B: Short Order Dispatch (arrives after inter-leg network lag)
        # Exposure to price drift during inter_leg_latency_ms
        adverse_drift_factor = 1.0 - (
            0.00015 * (inter_leg_latency_ms / 50.0) * self._rng.uniform(0.5, 2.0)
        )
        vwap_price_b = book_short.bids[0].price * adverse_drift_factor

        # Short leg fill ratio (can experience partial fill exhaustion)
        fill_ratio_b = self._rng.uniform(0.85, 1.0)
        filled_qty_b = round(requested_qty * fill_ratio_b, 5)
        residual_b = requested_qty - filled_qty_b

        sim_leg_b = FillSimulation(
            leg="LEG_B_SHORT",
            venue=opportunity.short_venue,
            side="SELL",
            requested_qty=requested_qty,
            filled_qty=filled_qty_b,
            fill_ratio=fill_ratio_b,
            residual_qty=residual_b,
            vwap_fill_price=vwap_price_b,
            execution_lag_ms=25.0 + inter_leg_latency_ms,
            adverse_move_bps=((book_short.bids[0].price - vwap_price_b) / ref_mid) * 10000.0,
        )

        # Net unhedged residual exposure
        unhedged_qty = abs(filled_qty_a - filled_qty_b)

        predicted_ev = (
            opportunity.multi_scenario_ev.base_net_ev_usd if opportunity.multi_scenario_ev else 0.0
        )

        shadow_opp = ShadowOpportunity(
            opportunity_id=opportunity.opportunity_id,
            detected_at=opportunity.detected_at_ms / 1000.0,
            qualified_at=now,
            expired_at=None,
            canonical_symbol=opportunity.canonical_symbol,
            opportunity_type=opportunity.opportunity_type,
            long_venue=opportunity.long_venue,
            short_venue=opportunity.short_venue,
            target_notional_usd=target_notional,
            predicted_net_ev_usd=predicted_ev,
            realized_reference_ev_usd=None,
            opportunity_duration_ms=0.0,
            leg_a_sim=sim_leg_a,
            leg_b_sim=sim_leg_b,
            unhedged_residual_qty=unhedged_qty,
            funding_realized_usd=0.0,
            model_attribution_error_usd=0.0,
            status="OPEN",
        )

        self._active_shadows[opportunity.opportunity_id] = shadow_opp
        self._persist_shadow_opportunity(shadow_opp)
        return shadow_opp

    def resolve_shadow_opportunity(
        self,
        opportunity_id: str,
        current_book_long: OrderBookSnapshot,
        current_book_short: OrderBookSnapshot,
        funding_records: dict[Venue, FundingRateRecord],
        exit_holding_duration_sec: float = 3600.0,
    ) -> ShadowOpportunity | None:
        """Simulates synthetic position exit and reconciles predicted vs realized EV."""
        shadow = self._active_shadows.get(opportunity_id)
        if not shadow or shadow.status != "OPEN":
            return None

        now = time.time()
        shadow.expired_at = now
        shadow.opportunity_duration_ms = (now - shadow.qualified_at) * 1000.0
        shadow.status = "RESOLVED"

        # Synthetic exit: Sell long position at Bid(long_venue), Buy back short at Ask(short_venue)
        exit_bid_long = current_book_long.bids[0].price if current_book_long.bids else 0.0
        exit_ask_short = current_book_short.asks[0].price if current_book_short.asks else 0.0

        qty_long = shadow.leg_a_sim.filled_qty if shadow.leg_a_sim else 0.0
        qty_short = shadow.leg_b_sim.filled_qty if shadow.leg_b_sim else 0.0
        entry_vwap_long = shadow.leg_a_sim.vwap_fill_price if shadow.leg_a_sim else 0.0
        entry_vwap_short = shadow.leg_b_sim.vwap_fill_price if shadow.leg_b_sim else 0.0

        # P&L on Long Leg: (exit_bid - entry_ask) * qty
        pnl_long = (exit_bid_long - entry_vwap_long) * qty_long
        # P&L on Short Leg: (entry_bid - exit_ask) * qty
        pnl_short = (entry_vwap_short - exit_ask_short) * qty_short

        # Fee deduction on exit (standard taker 5 bps average)
        exit_fee_usd = (qty_long * exit_bid_long * 0.0005) + (qty_short * exit_ask_short * 0.0005)

        # Funding realization for duration
        long_f = funding_records.get(shadow.long_venue)
        short_f = funding_records.get(shadow.short_venue)
        long_rate = long_f.funding_rate if long_f else 0.0
        short_rate = short_f.funding_rate if short_f else 0.0

        # Fractional funding accrued based on hold hours
        intervals_held = exit_holding_duration_sec / (8.0 * 3600.0)
        funding_usd = (
            (short_rate * qty_short * exit_ask_short) - (long_rate * qty_long * exit_bid_long)
        ) * intervals_held
        shadow.funding_realized_usd = funding_usd

        realized_ev = pnl_long + pnl_short + funding_usd - exit_fee_usd
        shadow.realized_reference_ev_usd = round(realized_ev, 2)
        shadow.model_attribution_error_usd = round(realized_ev - shadow.predicted_net_ev_usd, 2)

        self._persist_shadow_opportunity(shadow)
        return shadow

    def _persist_shadow_opportunity(self, shadow: ShadowOpportunity) -> None:
        """Upserts shadow opportunity into SQLite."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO arbitrage_shadow_ledger (
                        opportunity_id, canonical_symbol, opportunity_type,
                        long_venue, short_venue, target_notional_usd,
                        predicted_net_ev_usd, realized_reference_ev_usd,
                        opportunity_duration_ms, unhedged_residual_qty,
                        funding_realized_usd, model_attribution_error_usd,
                        status, detected_at, qualified_at, expired_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(opportunity_id) DO UPDATE SET
                        realized_reference_ev_usd = excluded.realized_reference_ev_usd,
                        opportunity_duration_ms = excluded.opportunity_duration_ms,
                        funding_realized_usd = excluded.funding_realized_usd,
                        model_attribution_error_usd = excluded.model_attribution_error_usd,
                        status = excluded.status,
                        expired_at = excluded.expired_at;
                    """,
                    (
                        shadow.opportunity_id,
                        shadow.canonical_symbol,
                        shadow.opportunity_type.value,
                        shadow.long_venue.value,
                        shadow.short_venue.value,
                        shadow.target_notional_usd,
                        shadow.predicted_net_ev_usd,
                        shadow.realized_reference_ev_usd,
                        shadow.opportunity_duration_ms,
                        shadow.unhedged_residual_qty,
                        shadow.funding_realized_usd,
                        shadow.model_attribution_error_usd,
                        shadow.status,
                        shadow.detected_at,
                        shadow.qualified_at,
                        shadow.expired_at,
                    ),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to persist shadow record for {shadow.opportunity_id}: {e}")

    def list_active_shadows(self) -> list[ShadowOpportunity]:
        return list(self._active_shadows.values())


# Global singleton
shadow_validator = ShadowValidator()
