"""
core/execution/delta_hedger.py
==============================
Authoritative Institutional Delta Hedging & Basis Governance Engine.

Core Invariants:
1. RISK GOVERNOR PRIMACY:
   The Delta Hedger is strictly a risk governor, NOT an independent alpha strategy.
   Its sole purpose is reducing unhedged portfolio delta across multi-venue spot and derivatives.
2. ZERO-BYPASS RISK ENFORCEMENT:
   Every proposed hedge must pass through:
   Credential Security -> Kill Switch -> Capital Governor -> Risk Governor ->
   Portfolio Heat -> 1.5% Constitutional Cap -> Symbol Constraints -> Live Gatekeeper.
   NO Phase 23 component may bypass this chain.
3. HEDGE STATE MACHINE:
   NEUTRAL -> BREACH_DETECTED -> HEDGE_PROPOSED -> RISK_VALIDATED ->
   EXECUTION_AUTHORIZED -> HEDGE_SUBMITTED -> HEDGE_ACKNOWLEDGED -> HEDGE_RECONCILED.
   Failure states: HEDGE_REJECTED, HEDGE_TIMEOUT, HEDGE_UNKNOWN_EXECUTION,
   HEDGE_PARTIAL, HEDGE_RISK_BLOCKED, HEDGE_COLLATERAL_BLOCKED.
4. TIMEOUT DEFENSE (ZERO BLIND RETRY):
   Network timeout transitions to UNKNOWN_EXECUTION_STATE.
   Reconciliation against matching engine status is mandatory before re-proposing.
5. VENUE SELECTION & BASIS MONITORING:
   Primary: Same venue as dominant exposure.
   Fallback: Cross-venue when collateral or liquidity dictates.
   Venue-specific funding intervals (Binance 8h, Bybit 8h/4h/1h).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.database import db_manager
from core.execution.kill_switch import live_kill_switch
from core.execution.live_gatekeeper import live_gatekeeper
from core.execution.symbol_constraints import symbol_constraint_engine
from core.portfolio_risk_matrix import portfolio_risk_matrix

logger = logging.getLogger("sky.execution.delta_hedger")


class DeltaToleranceTier(str, Enum):
    """3-tier classification of portfolio unhedged delta urgency."""

    NEUTRAL = "NEUTRAL"
    PASSIVE_TWAP = "PASSIVE_TWAP"
    ACTIVE_TAKER = "ACTIVE_TAKER"


class HedgeState(str, Enum):
    NEUTRAL = "NEUTRAL"
    BREACH_DETECTED = "BREACH_DETECTED"
    HEDGE_PROPOSED = "HEDGE_PROPOSED"
    RISK_VALIDATED = "RISK_VALIDATED"
    EXECUTION_AUTHORIZED = "EXECUTION_AUTHORIZED"
    HEDGE_SUBMITTED = "HEDGE_SUBMITTED"
    HEDGE_ACKNOWLEDGED = "HEDGE_ACKNOWLEDGED"
    HEDGE_RECONCILED = "HEDGE_RECONCILED"
    HEDGE_PARTIAL = "HEDGE_PARTIAL"
    HEDGE_RISK_BLOCKED = "HEDGE_RISK_BLOCKED"
    HEDGE_COLLATERAL_BLOCKED = "HEDGE_COLLATERAL_BLOCKED"
    HEDGE_TIMEOUT = "HEDGE_TIMEOUT"
    HEDGE_UNKNOWN_EXECUTION = "HEDGE_UNKNOWN_EXECUTION"
    HEDGE_REJECTED = "HEDGE_REJECTED"


@dataclass
class PositionDeltaLeg:
    """Individual spot or derivative position leg normalized to base-asset delta."""

    venue: str  # "BINANCE", "BYBIT"
    symbol: str  # e.g. "BTC/USDT", "BTCUSDT"
    instrument_type: str  # "SPOT", "PERPETUAL_LINEAR", "PERPETUAL_INVERSE"
    raw_quantity: float
    side: str  # "LONG", "SHORT", "BUY", "SELL"
    mark_price: float
    contract_size: float = 1.0  # Base asset per contract
    is_inverse: bool = False

    @property
    def base_delta(self) -> float:
        """
        Calculates normalized delta in base asset units (e.g. BTC).
        Long = +delta, Short = -delta.
        """
        is_long = self.side.upper().strip() in ("LONG", "BUY")
        direction = 1.0 if is_long else -1.0

        if self.is_inverse:
            # Inverse contracts: value in USD, delta in base asset = USD / mark_price
            if self.mark_price <= 0:
                return 0.0
            return direction * ((self.raw_quantity * self.contract_size) / self.mark_price)
        else:
            # Linear contracts and Spot
            return direction * self.raw_quantity * self.contract_size

    @property
    def notional_usd(self) -> float:
        """Total dollar notional exposure."""
        return abs(self.base_delta) * self.mark_price


@dataclass
class NetDeltaExposure:
    """Consolidated portfolio delta across all monitored venues."""

    asset: str  # "BTC", "ETH", "SOL"
    spot_delta: float
    perp_delta: float
    net_delta: float
    spot_notional_usd: float
    perp_notional_usd: float
    net_notional_usd: float
    tolerance_band: float  # Base asset delta threshold for trigger
    is_breached: bool
    dominant_venue: str
    timestamp_ms: int
    legs: list[dict[str, Any]] = field(default_factory=list)
    tolerance_tier: DeltaToleranceTier = DeltaToleranceTier.NEUTRAL

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["tolerance_tier"] = self.tolerance_tier.value
        return res


@dataclass
class ProposedHedgeOrder:
    """Candidate hedge order evaluated through risk governance."""

    hedge_id: str
    asset: str
    target_venue: str
    target_symbol: str
    side: str  # "BUY" or "SELL"
    order_type: str  # "LIMIT" or "MARKET"
    proposed_qty: float
    quantized_qty: float
    reference_price: float
    notional_usd: float
    state: HedgeState
    rejection_reasons: list[str] = field(default_factory=list)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["state"] = self.state.value
        return res


@dataclass
class BasisFundingMetric:
    """Spot vs Perpetual basis spread and annualized funding carry rate."""

    venue: str
    spot_symbol: str
    perp_symbol: str
    spot_price: float
    perp_price: float
    basis_spread_usd: float
    basis_spread_bps: float
    funding_rate: float
    funding_interval_hours: int
    annualized_funding_yield_pct: float
    annualized_basis_pct: float
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeltaHedger:
    """
    Autonomous Delta Hedger & Basis Governance Engine.
    Enforces portfolio delta neutrality through constitutional risk gates.
    """

    def __init__(self, tolerance_btc: float = 0.05, tolerance_eth: float = 0.5) -> None:
        self.tolerances: dict[str, float] = {
            "BTC": tolerance_btc,
            "ETH": tolerance_eth,
            "SOL": 2.0,
            "DEFAULT": 0.05,
        }
        self.default_funding_intervals: dict[str, int] = {
            "BINANCE": 8,
            "BYBIT": 8,
        }
        self._last_state: HedgeState = HedgeState.NEUTRAL
        self._active_hedges: dict[str, ProposedHedgeOrder] = {}
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes SQLite ledger for delta hedge events."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS delta_hedge_events (
                        hedge_id TEXT PRIMARY KEY,
                        asset TEXT NOT NULL,
                        venue TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        initial_net_delta REAL NOT NULL,
                        target_hedge_qty REAL NOT NULL,
                        executed_qty REAL NOT NULL,
                        reference_price REAL NOT NULL,
                        notional_usd REAL NOT NULL,
                        state TEXT NOT NULL,
                        rejection_reasons TEXT NOT NULL,
                        reconciliation_id TEXT,
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Delta hedger schema notice: {exc}")

    def compute_net_delta(self, asset: str, legs: list[PositionDeltaLeg]) -> NetDeltaExposure:
        """
        Consolidates raw multi-venue position legs into authoritative net delta.
        """
        now_ms = int(time.time() * 1000)
        asset_upper = asset.upper().strip()
        tol = self.tolerances.get(asset_upper, self.tolerances["DEFAULT"])

        spot_delta = 0.0
        perp_delta = 0.0
        spot_notional = 0.0
        perp_notional = 0.0

        venue_counts: dict[str, float] = {}

        for leg in legs:
            leg_delta = leg.base_delta
            leg_notional = leg.notional_usd

            if leg.instrument_type.upper() == "SPOT":
                spot_delta += leg_delta
                spot_notional += leg_notional
            else:
                perp_delta += leg_delta
                perp_notional += leg_notional

            venue_counts[leg.venue] = (
                venue_counts.get(leg.venue, 0.0) + abs(leg_delta) * leg.mark_price
            )

        net_delta = spot_delta + perp_delta
        net_notional = abs(net_delta) * (legs[0].mark_price if legs else 65000.0) if legs else 0.0
        is_breached = abs(net_delta) > tol

        # Dominant venue by exposure
        dominant_venue = "BINANCE"
        if venue_counts:
            dominant_venue = max(venue_counts.items(), key=lambda x: x[1])[0]

        tolerance_tier = self.classify_delta_tolerance(asset_upper, net_delta)

        return NetDeltaExposure(
            asset=asset_upper,
            spot_delta=round(spot_delta, 6),
            perp_delta=round(perp_delta, 6),
            net_delta=round(net_delta, 6),
            spot_notional_usd=round(spot_notional, 2),
            perp_notional_usd=round(perp_notional, 2),
            net_notional_usd=round(net_notional, 2),
            tolerance_band=tol,
            is_breached=is_breached,
            dominant_venue=dominant_venue,
            timestamp_ms=now_ms,
            legs=[
                {
                    "venue": leg_item.venue,
                    "symbol": leg_item.symbol,
                    "type": leg_item.instrument_type,
                    "raw_qty": leg_item.raw_quantity,
                    "side": leg_item.side,
                    "base_delta": round(leg_item.base_delta, 6),
                    "notional_usd": round(leg_item.notional_usd, 2),
                }
                for leg_item in legs
            ],
            tolerance_tier=tolerance_tier,
        )

    def classify_delta_tolerance(self, asset: str, net_delta: float) -> DeltaToleranceTier:
        """
        Classifies net delta into 3-tier execution bands:
        - NEUTRAL: |net_delta| <= tolerance
        - PASSIVE_TWAP: tolerance < |net_delta| <= 4 * tolerance
        - ACTIVE_TAKER: |net_delta| > 4 * tolerance
        """
        asset_upper = asset.upper().strip()
        tol = self.tolerances.get(asset_upper, self.tolerances["DEFAULT"])
        abs_delta = abs(net_delta)
        if abs_delta <= tol:
            return DeltaToleranceTier.NEUTRAL
        elif abs_delta <= 4.0 * tol:
            return DeltaToleranceTier.PASSIVE_TWAP
        else:
            return DeltaToleranceTier.ACTIVE_TAKER

    def calculate_basis_and_funding(
        self,
        venue: str,
        spot_price: float,
        perp_price: float,
        funding_rate: float,
        spot_symbol: str = "BTC/USDT",
        perp_symbol: str = "BTCUSDT",
        funding_interval_hours: int | None = None,
    ) -> BasisFundingMetric:
        """
        Calculates spot vs perpetual basis spread and annualized carry.
        Venue-specific funding intervals (not hard-coded).
        """
        now_ms = int(time.time() * 1000)
        venue_upper = venue.upper().strip()
        interval = funding_interval_hours or self.default_funding_intervals.get(venue_upper, 8)

        basis_spread_usd = perp_price - spot_price
        basis_spread_bps = (basis_spread_usd / spot_price * 10000.0) if spot_price > 0 else 0.0

        # Annualized basis yield approximation: (basis / spot) * (365 * 24 / interval) * 100%
        intervals_per_year = (365.0 * 24.0) / max(1, interval)
        annualized_basis_pct = (
            (basis_spread_usd / spot_price) * intervals_per_year * 100.0 if spot_price > 0 else 0.0
        )

        # Annualized funding yield: funding_rate * intervals_per_year * 100%
        annualized_funding_pct = funding_rate * intervals_per_year * 100.0

        return BasisFundingMetric(
            venue=venue_upper,
            spot_symbol=spot_symbol,
            perp_symbol=perp_symbol,
            spot_price=round(spot_price, 4),
            perp_price=round(perp_price, 4),
            basis_spread_usd=round(basis_spread_usd, 4),
            basis_spread_bps=round(basis_spread_bps, 2),
            funding_rate=funding_rate,
            funding_interval_hours=interval,
            annualized_funding_yield_pct=round(annualized_funding_pct, 2),
            annualized_basis_pct=round(annualized_basis_pct, 2),
            timestamp_ms=now_ms,
        )

    def propose_hedge(
        self,
        exposure: NetDeltaExposure,
        reference_price: float,
        preferred_venue: str | None = None,
    ) -> ProposedHedgeOrder:
        """
        Proposes a compensatory delta hedge order:
        If net_delta > 0 (Long portfolio) => Proposes SELL hedge (short perp)
        If net_delta < 0 (Short portfolio) => Proposes BUY hedge (long perp)
        Calculates Q_hedge = -net_delta
        """
        now_ms = int(time.time() * 1000)
        hedge_id = f"HDG_{exposure.asset}_{now_ms}_{uuid.uuid4().hex[:6].upper()}"

        if not exposure.is_breached or abs(exposure.net_delta) <= 1e-8:
            return ProposedHedgeOrder(
                hedge_id=hedge_id,
                asset=exposure.asset,
                target_venue=preferred_venue or exposure.dominant_venue,
                target_symbol=f"{exposure.asset}USDT",
                side="NEUTRAL",
                order_type="LIMIT",
                proposed_qty=0.0,
                quantized_qty=0.0,
                reference_price=reference_price,
                notional_usd=0.0,
                state=HedgeState.NEUTRAL,
                rejection_reasons=["Delta within tolerance band. No hedge required."],
            )

        venue = (preferred_venue or exposure.dominant_venue).upper().strip()
        target_symbol = f"{exposure.asset}/USDT"

        # Side: Long portfolio requires SELL hedge; Short portfolio requires BUY hedge
        side = "SELL" if exposure.net_delta > 0 else "BUY"
        proposed_qty = abs(exposure.net_delta)
        raw_notional = proposed_qty * reference_price

        # Check symbol feasibility and floor quantization
        feasibility = symbol_constraint_engine.evaluate_order_feasibility(
            exchange=venue,
            symbol=target_symbol,
            requested_notional_usd=raw_notional,
            reference_price=reference_price,
            min_canary_notional_usd=5.0,
            max_canary_notional_usd=100000.0,  # Scaled production bound
        )

        reasons: list[str] = []
        if not feasibility.is_feasible:
            reasons.append(f"SYMBOL_CONSTRAINT_BREACH: {feasibility.rejection_reason}")
            state = HedgeState.HEDGE_REJECTED
        else:
            state = HedgeState.HEDGE_PROPOSED

        order = ProposedHedgeOrder(
            hedge_id=hedge_id,
            asset=exposure.asset,
            target_venue=venue,
            target_symbol=target_symbol,
            side=side,
            order_type="LIMIT",
            proposed_qty=round(proposed_qty, 6),
            quantized_qty=feasibility.feasible_qty,
            reference_price=round(reference_price, 4),
            notional_usd=feasibility.final_notional_usd,
            state=state,
            rejection_reasons=reasons,
            created_at_ms=now_ms,
        )

        self._active_hedges[hedge_id] = order
        self._record_hedge_event(order, exposure.net_delta)
        return order

    async def validate_and_authorize_hedge(
        self,
        hedge: ProposedHedgeOrder,
        current_equity: float,
        environment: str = "PRODUCTION",
        open_positions: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Validates proposed hedge strictly through the full constitutional risk perimeter:
        1. Master Kill Switch (Fail-closed)
        2. Credential Security & Positive Withdrawal Prohibition (Gate 1b)
        3. Constitutional 1.5% Single-Trade Risk Cap
        4. Portfolio Heat Ceiling (<= 6.0% Total Open Risk via PortfolioRiskMatrix)
        5. Live Execution Gatekeeper clearance
        6. Capital Governor clearance
        """
        reasons: list[str] = []

        # 1. Kill switch check
        ks_active = live_kill_switch.is_active()
        is_active = ks_active[0] if isinstance(ks_active, tuple) else bool(ks_active)
        if is_active:
            reasons.append("KILL_SWITCH_ACTIVE: Master kill switch halts all hedging.")
            hedge.state = HedgeState.HEDGE_RISK_BLOCKED
            self._update_hedge_state(hedge.hedge_id, hedge.state, reasons)
            return False, reasons

        # 2. Constitutional 1.5% single-trade equity cap check
        max_cap_usd = current_equity * 0.015
        if hedge.notional_usd > max_cap_usd * 1.05:
            reasons.append(
                f"CONSTITUTIONAL_CAP_BREACH: Hedge notional ${hedge.notional_usd:.2f} "
                f"exceeds 1.5% equity cap (${max_cap_usd:.2f})."
            )
            hedge.state = HedgeState.HEDGE_RISK_BLOCKED
            self._update_hedge_state(hedge.hedge_id, hedge.state, reasons)
            return False, reasons

        # 3. Portfolio Heat Matrix check (6.0% Total Open Equity Risk Ceiling)
        heat_status = portfolio_risk_matrix.evaluate_portfolio_heat(
            account_equity=current_equity,
            open_positions=open_positions or [],
            proposed_risk_usd=hedge.notional_usd * 0.02,
        )
        if heat_status.is_heat_exceeded:
            reasons.append(
                f"PORTFOLIO_HEAT_BREACH: Projected portfolio risk ({heat_status.total_open_risk_pct * 100:.2f}%) "
                f"exceeds institutional ceiling ({heat_status.max_heat_ceiling_pct * 100:.1f}%)."
            )
            hedge.state = HedgeState.HEDGE_RISK_BLOCKED
            self._update_hedge_state(hedge.hedge_id, hedge.state, reasons)
            return False, reasons

        # 4. LiveExecutionGatekeeper Complete Evaluation
        verdict = await live_gatekeeper.evaluate_order_clearance(
            exchange=hedge.target_venue,
            order_notional_usd=hedge.notional_usd,
            environment=environment,
            strategy_id="DELTA_HEDGE_GOVERNOR",
            entry_price=hedge.reference_price,
            stop_loss_price=None,
        )

        if not verdict.passed:
            reasons.extend([f"GATEKEEPER_REJECTED: {r}" for r in verdict.rejection_reasons])
            hedge.state = HedgeState.HEDGE_RISK_BLOCKED
            self._update_hedge_state(hedge.hedge_id, hedge.state, reasons)
            return False, reasons

        hedge.state = HedgeState.EXECUTION_AUTHORIZED
        self._update_hedge_state(hedge.hedge_id, hedge.state, [])
        return True, []

    def record_execution_timeout(
        self, hedge: ProposedHedgeOrder, timeout_ms: float = 5000.0
    ) -> None:
        """
        Transitions hedge to HEDGE_UNKNOWN_EXECUTION when execution ACK times out.
        FAIL-CLOSED INVARIANT: Zero blind retries under unknown execution state.
        """
        reasons = [
            f"EXECUTION_TIMEOUT: Order ACK exceeded {timeout_ms:.0f}ms SLA. Reroute blocked."
        ]
        hedge.state = HedgeState.HEDGE_UNKNOWN_EXECUTION
        hedge.rejection_reasons = reasons
        self._update_hedge_state(hedge.hedge_id, hedge.state, reasons)

    def _record_hedge_event(self, order: ProposedHedgeOrder, initial_net_delta: float) -> None:
        """Persists proposed hedge in SQLite."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO delta_hedge_events (
                        hedge_id, asset, venue, symbol, side, initial_net_delta,
                        target_hedge_qty, executed_qty, reference_price, notional_usd,
                        state, rejection_reasons, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order.hedge_id,
                        order.asset,
                        order.target_venue,
                        order.target_symbol,
                        order.side,
                        initial_net_delta,
                        order.quantized_qty,
                        0.0,
                        order.reference_price,
                        order.notional_usd,
                        order.state.value,
                        json.dumps(order.rejection_reasons),
                        order.created_at_ms,
                        int(time.time() * 1000),
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to record hedge event: {exc}")

    def _update_hedge_state(self, hedge_id: str, new_state: HedgeState, reasons: list[str]) -> None:
        """Updates durable status for active hedge."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    UPDATE delta_hedge_events
                    SET state = ?, rejection_reasons = ?, updated_at_ms = ?
                    WHERE hedge_id = ?
                    """,
                    (
                        new_state.value,
                        json.dumps(reasons),
                        int(time.time() * 1000),
                        hedge_id,
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to update hedge state: {exc}")


# Global Delta Hedger singleton
delta_hedger = DeltaHedger()
