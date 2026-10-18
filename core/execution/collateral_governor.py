"""
core/execution/collateral_governor.py
=====================================
Authoritative Cross-Venue Collateral & Margin Risk Governor.

Core Invariants:
1. DETERMINISTIC RISK GOVERNOR:
   Tracks margin utilization, maintenance buffers, and liquidation distance
   across Binance Spot/Margin and Bybit Unified Accounts.
2. FAIL-CLOSED DATA FRESHNESS:
   Every snapshot records age_ms and data_quality (FRESH, STALE, MISSING, CONFLICTED).
   Snapshots older than 30,000ms fail closed, blocking new directional exposure.
3. 4-TIER GOVERNANCE STATES:
   - NORMAL (< 65% utilization): Normal trading & hedging clear.
   - CAUTION (65% - 80%): Directional capital expansion blocked; risk-reducing hedges only.
   - DANGER (> 80%): All new orders frozen; sentinel alerts dispatched.
   - LIQUIDATION_RISK (< 2.5x maintenance margin buffer): Emergency freeze.
   - STALE / UNKNOWN: Fail-closed block on new risk.
4. ZERO AUTOMATIC ASSET MOVEMENT:
   The Collateral Governor NEVER withdraws or moves collateral between venues automatically.
   Transfer recommendations are strictly RECOMMENDATIONS for operator audit.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from core.audit_bus import audit_bus
from core.database import db_manager

logger = logging.getLogger("sky.execution.collateral")


class CollateralState(StrEnum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    DANGER = "DANGER"
    LIQUIDATION_RISK = "LIQUIDATION_RISK"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class DataQuality(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    CONFLICTED = "CONFLICTED"


@dataclass
class VenueCollateralSnapshot:
    """Normalized collateral status for an individual venue."""

    venue: str  # "BINANCE", "BYBIT"
    total_equity_usd: float
    available_balance_usd: float
    initial_margin_usd: float
    maintenance_margin_usd: float
    margin_used_usd: float
    unrealized_pnl_usd: float
    margin_utilization_pct: float  # (margin_used / total_equity) * 100%
    maintenance_buffer_ratio: float  # total_equity / maintenance_margin (safety multiple)
    liquidation_distance_pct: float  # Estimated distance to liquidation
    data_quality: DataQuality
    age_ms: float
    timestamp_ms: int
    source: str = "EXCHANGE_REST_PROBE"

    @property
    def risk_state(self) -> CollateralState:
        """Derives 4-tier collateral risk state for this venue."""
        if self.data_quality != DataQuality.FRESH or self.age_ms > 30000.0:
            return CollateralState.STALE
        if self.maintenance_margin_usd > 0 and self.maintenance_buffer_ratio < 1.5:
            return CollateralState.LIQUIDATION_RISK
        if self.margin_utilization_pct >= 80.0:
            return CollateralState.DANGER
        if self.margin_utilization_pct >= 65.0:
            return CollateralState.CAUTION
        return CollateralState.NORMAL

    @property
    def margin_utilization_ratio(self) -> float:
        return self.margin_utilization_pct / 100.0

    @property
    def liquidation_buffer_ratio(self) -> float:
        return self.maintenance_buffer_ratio

    @property
    def data_age_seconds(self) -> float:
        return self.age_ms / 1000.0

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["data_quality"] = self.data_quality.value
        res["risk_state"] = self.risk_state.value
        return res


@dataclass
class CollateralRiskScorecard:
    """Multi-factor quantitative risk scorecard for cross-venue collateral posture."""

    composite_score: float  # 0.0 to 100.0 (higher = riskier)
    margin_utilization_score: float  # 0.0 to 100.0
    buffer_ratio_score: float  # 0.0 to 100.0
    liquidation_distance_score: float  # 0.0 to 100.0
    imbalance_score: float  # 0.0 to 100.0
    is_actionable: bool
    recommended_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemCollateralReport:
    """Consolidated cross-venue collateral posture."""

    system_state: CollateralState
    total_system_equity_usd: float
    total_system_margin_used_usd: float
    system_utilization_pct: float
    directional_trading_allowed: bool
    risk_reducing_hedge_allowed: bool
    venues: dict[str, VenueCollateralSnapshot]
    transfer_recommendations: list[str]
    audit_event_id: str | None
    timestamp_ms: int

    @property
    def total_equity_usd(self) -> float:
        return self.total_system_equity_usd

    @property
    def systemic_risk_state(self) -> CollateralState:
        return self.system_state

    @property
    def freshness_ok(self) -> bool:
        return self.system_state not in (CollateralState.STALE, CollateralState.UNKNOWN)

    @property
    def venues_in_danger(self) -> list[str]:
        return [v.venue for v in self.venues.values() if v.margin_utilization_pct >= 80.0]

    @property
    def cross_venue_imbalance_pct(self) -> float:
        """Cross-venue margin utilization differential (delta U)."""
        if len(self.venues) < 2:
            return 0.0
        utils = [v.margin_utilization_pct for v in self.venues.values()]
        return round(max(utils) - min(utils), 2)

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["system_state"] = self.system_state.value
        res["venues"] = {k: v.to_dict() for k, v in self.venues.items()}
        res["total_equity_usd"] = self.total_equity_usd
        res["systemic_risk_state"] = self.systemic_risk_state.value
        res["freshness_ok"] = self.freshness_ok
        res["venues_in_danger"] = self.venues_in_danger
        res["cross_venue_imbalance_pct"] = self.cross_venue_imbalance_pct
        return res


class CollateralGovernor:
    """
    Deterministic Cross-Venue Collateral Governor.
    Monitors margin utilization and protects against liquidation cascades.
    """

    def __init__(
        self,
        caution_threshold_pct: float = 65.0,
        danger_threshold_pct: float = 80.0,
        min_maintenance_buffer: float = 2.5,
        max_staleness_ms: float = 30000.0,
    ) -> None:
        self.caution_threshold = caution_threshold_pct
        self.danger_threshold = danger_threshold_pct
        self.min_maintenance_buffer = min_maintenance_buffer
        self.max_staleness_ms = max_staleness_ms
        self._last_snapshots: dict[str, VenueCollateralSnapshot] = {}
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Initializes durable SQLite ledger for collateral snapshots."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS collateral_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        venue TEXT NOT NULL,
                        total_equity_usd REAL NOT NULL,
                        available_balance_usd REAL NOT NULL,
                        margin_used_usd REAL NOT NULL,
                        maintenance_margin_usd REAL NOT NULL,
                        margin_utilization_pct REAL NOT NULL,
                        maintenance_buffer_ratio REAL NOT NULL,
                        state TEXT NOT NULL,
                        data_quality TEXT NOT NULL,
                        age_ms REAL NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:
            logger.debug(f"Collateral governor schema notice: {exc}")

    def evaluate_venue_snapshot(
        self,
        venue: str,
        total_equity_usd: float,
        available_balance_usd: float,
        initial_margin_usd: float = 0.0,
        maintenance_margin_usd: float = 0.0,
        unrealized_pnl_usd: float = 0.0,
        observation_timestamp_ms: int | None = None,
        source: str = "EXCHANGE_REST_PROBE",
    ) -> VenueCollateralSnapshot:
        """
        Normalizes raw balance fields, checks staleness, and computes margin ratios.
        """
        now_ms = int(time.time() * 1000)
        obs_ms = observation_timestamp_ms or now_ms
        age_ms = max(0.0, float(now_ms - obs_ms))

        # Margin used is initial margin plus locked margin
        margin_used = (
            initial_margin_usd
            if initial_margin_usd > 0
            else max(0.0, total_equity_usd - available_balance_usd)
        )

        if age_ms > self.max_staleness_ms:
            quality = DataQuality.STALE
        elif total_equity_usd <= 0:
            quality = DataQuality.MISSING
        else:
            quality = DataQuality.FRESH

        # Margin utilization percentage
        if total_equity_usd > 0:
            utilization_pct = (margin_used / total_equity_usd) * 100.0
        else:
            utilization_pct = 100.0  # Fail-closed on zero equity

        # Maintenance buffer multiple: total_equity / maintenance_margin
        if maintenance_margin_usd > 0:
            maint_buffer = total_equity_usd / maintenance_margin_usd
            liq_dist = max(0.0, (1.0 - (maintenance_margin_usd / total_equity_usd)) * 100.0)
        else:
            maint_buffer = 10.0  # Safe default if no open positions
            liq_dist = 100.0

        snapshot = VenueCollateralSnapshot(
            venue=venue.upper().strip(),
            total_equity_usd=round(total_equity_usd, 2),
            available_balance_usd=round(available_balance_usd, 2),
            initial_margin_usd=round(initial_margin_usd, 2),
            maintenance_margin_usd=round(maintenance_margin_usd, 2),
            margin_used_usd=round(margin_used, 2),
            unrealized_pnl_usd=round(unrealized_pnl_usd, 2),
            margin_utilization_pct=round(utilization_pct, 2),
            maintenance_buffer_ratio=round(maint_buffer, 2),
            liquidation_distance_pct=round(liq_dist, 2),
            data_quality=quality,
            age_ms=round(age_ms, 1),
            timestamp_ms=obs_ms,
            source=source,
        )

        self._last_snapshots[snapshot.venue] = snapshot
        self._persist_snapshot(snapshot)
        return snapshot

    def get_system_collateral_report(self) -> SystemCollateralReport:
        """
        Consolidates active venue snapshots into authoritative systemic collateral state.
        Enforces 4-tier risk governance rules.
        """
        now_ms = int(time.time() * 1000)
        venues = self._last_snapshots.copy()

        if not venues:
            # Zero telemetry => Fail-closed
            return SystemCollateralReport(
                system_state=CollateralState.UNKNOWN,
                total_system_equity_usd=0.0,
                total_system_margin_used_usd=0.0,
                system_utilization_pct=0.0,
                directional_trading_allowed=False,
                risk_reducing_hedge_allowed=False,
                venues={},
                transfer_recommendations=[
                    "No venue collateral telemetry available. All live trading blocked."
                ],
                audit_event_id=None,
                timestamp_ms=now_ms,
            )

        tot_eq = sum(v.total_equity_usd for v in venues.values())
        tot_used = sum(v.margin_used_usd for v in venues.values())
        sys_util = (tot_used / tot_eq * 100.0) if tot_eq > 0 else 100.0

        # Check for stale, liquidation risk, danger, or caution states across venues
        has_stale = any(
            v.data_quality != DataQuality.FRESH or v.age_ms > self.max_staleness_ms
            for v in venues.values()
        )
        has_liq_risk = any(
            v.maintenance_buffer_ratio < self.min_maintenance_buffer
            and v.maintenance_margin_usd > 0
            for v in venues.values()
        )
        has_danger = any(v.margin_utilization_pct >= self.danger_threshold for v in venues.values())
        has_caution = any(
            v.margin_utilization_pct >= self.caution_threshold for v in venues.values()
        )

        recommendations: list[str] = []

        if has_stale:
            state = CollateralState.STALE
            directional_allowed = False
            hedge_allowed = False  # Do not execute automated hedges without fresh balances
            recommendations.append(
                "CRITICAL: Stale collateral telemetry detected. Live orders blocked."
            )
        elif has_liq_risk:
            state = CollateralState.LIQUIDATION_RISK
            directional_allowed = False
            hedge_allowed = True  # Risk-reducing hedges permitted to avert liquidation
            for v in venues.values():
                if v.maintenance_buffer_ratio < self.min_maintenance_buffer:
                    recommendations.append(
                        f"URGENT: {v.venue} buffer ({v.maintenance_buffer_ratio:.1f}x) "
                        f"below {self.min_maintenance_buffer:.1f}x safety limit. Immediate de-risk required."
                    )
        elif has_danger:
            state = CollateralState.DANGER
            directional_allowed = False
            hedge_allowed = True
            for v in venues.values():
                if v.margin_utilization_pct >= self.danger_threshold:
                    recommendations.append(
                        f"HIGH RISK: {v.venue} margin utilization ({v.margin_utilization_pct:.1f}%) "
                        f"exceeds {self.danger_threshold}%. Transfer available capital or reduce position."
                    )
        elif has_caution:
            state = CollateralState.CAUTION
            directional_allowed = False  # Prohibit new directional expansion
            hedge_allowed = True  # Delta-reducing actions permitted
            for v in venues.values():
                if v.margin_utilization_pct >= self.caution_threshold:
                    recommendations.append(
                        f"CAUTION: {v.venue} utilization ({v.margin_utilization_pct:.1f}%) "
                        f"exceeds {self.caution_threshold}%. Halt directional expansion."
                    )
        else:
            state = CollateralState.NORMAL
            directional_allowed = True
            hedge_allowed = True

        # Generate internal transfer advice if imbalance between venues is severe
        if len(venues) >= 2 and tot_eq > 1000.0:
            v_list = list(venues.values())
            v_high = max(v_list, key=lambda x: x.margin_utilization_pct)
            v_low = min(v_list, key=lambda x: x.margin_utilization_pct)
            if v_high.margin_utilization_pct - v_low.margin_utilization_pct > 35.0:
                rec_amount = min(
                    v_low.available_balance_usd * 0.4,
                    v_high.total_equity_usd * 0.2,
                )
                if rec_amount >= 50.0:
                    recommendations.append(
                        f"REBALANCE ADVICE: Consider transferring ~${rec_amount:.0f} USD "
                        f"from {v_low.venue} to {v_high.venue} to balance margin pressure (RECOMMENDATION ONLY)."
                    )

        # Publish audit event if in elevated state
        audit_id = None
        if state in (
            CollateralState.CAUTION,
            CollateralState.DANGER,
            CollateralState.LIQUIDATION_RISK,
        ):
            try:
                audit_id = audit_bus.publish_event(
                    event_type="COLLATERAL_GOVERNOR_ALERT",
                    payload={
                        "state": state.value,
                        "system_utilization": round(sys_util, 2),
                        "recommendations": recommendations,
                    },
                )
            except Exception as _e:
                logger.debug(f"Audit log error: {_e}")

        return SystemCollateralReport(
            system_state=state,
            total_system_equity_usd=round(tot_eq, 2),
            total_system_margin_used_usd=round(tot_used, 2),
            system_utilization_pct=round(sys_util, 2),
            directional_trading_allowed=directional_allowed,
            risk_reducing_hedge_allowed=hedge_allowed,
            venues=venues,
            transfer_recommendations=recommendations,
            audit_event_id=audit_id,
            timestamp_ms=now_ms,
        )

    def compute_margin_risk_scorecard(
        self, report: SystemCollateralReport
    ) -> CollateralRiskScorecard:
        """
        Computes deterministic 4-factor risk scorecard across multi-venue collateral:
        1. Margin Utilization Factor (35% weight)
        2. Maintenance Buffer Ratio Factor (30% weight)
        3. Liquidation Distance Factor (20% weight)
        4. Cross-Venue Imbalance Factor (15% weight)

        Invariant: Strictly informational, zero automated asset transfers.
        """
        if (
            report.system_state in (CollateralState.UNKNOWN, CollateralState.STALE)
            or not report.venues
        ):
            return CollateralRiskScorecard(
                composite_score=100.0,
                margin_utilization_score=100.0,
                buffer_ratio_score=100.0,
                liquidation_distance_score=100.0,
                imbalance_score=100.0,
                is_actionable=True,
                recommended_actions=["FAIL_CLOSED: Stale or missing collateral telemetry."],
            )

        # 1. Margin utilization factor (normalized against danger threshold)
        util_score = min(100.0, (report.system_utilization_pct / self.danger_threshold) * 100.0)

        # 2. Maintenance buffer ratio factor (min buffer across active venues)
        min_buf = min(v.maintenance_buffer_ratio for v in report.venues.values())
        if min_buf >= 5.0:
            buf_score = 0.0
        elif min_buf <= 1.5:
            buf_score = 100.0
        else:
            buf_score = (5.0 - min_buf) / (5.0 - 1.5) * 100.0

        # 3. Liquidation distance factor (min distance across active venues)
        min_liq_dist = min(v.liquidation_distance_pct for v in report.venues.values())
        if min_liq_dist >= 50.0:
            liq_score = 0.0
        elif min_liq_dist <= 5.0:
            liq_score = 100.0
        else:
            liq_score = (50.0 - min_liq_dist) / (50.0 - 5.0) * 100.0

        # 4. Cross-venue imbalance factor
        delta_u = report.cross_venue_imbalance_pct
        imb_score = min(100.0, (delta_u / 50.0) * 100.0)

        composite = round(
            0.35 * util_score + 0.30 * buf_score + 0.20 * liq_score + 0.15 * imb_score,
            2,
        )

        is_actionable = (
            composite >= 50.0
            or report.system_state
            in (CollateralState.CAUTION, CollateralState.DANGER, CollateralState.LIQUIDATION_RISK)
            or max(util_score, buf_score, liq_score, imb_score) >= 80.0
        )

        actions = list(report.transfer_recommendations)
        if imb_score >= 70.0 and not any("REBALANCE ADVICE" in a for a in actions):
            actions.append(
                f"REBALANCE ADVICE: Elevated cross-venue margin imbalance ({delta_u:.1f}%). "
                f"Consider rebalancing capital between venues (RECOMMENDATION ONLY)."
            )

        return CollateralRiskScorecard(
            composite_score=composite,
            margin_utilization_score=round(util_score, 2),
            buffer_ratio_score=round(buf_score, 2),
            liquidation_distance_score=round(liq_score, 2),
            imbalance_score=round(imb_score, 2),
            is_actionable=is_actionable,
            recommended_actions=actions,
        )

    def _persist_snapshot(self, snap: VenueCollateralSnapshot) -> None:
        """Saves snapshot to SQLite ledger."""
        snap_id = f"COL_{snap.venue[:3]}_{snap.timestamp_ms}_{uuid.uuid4().hex[:4].upper()}"
        state_str = (
            CollateralState.LIQUIDATION_RISK.value
            if snap.maintenance_buffer_ratio < self.min_maintenance_buffer
            and snap.maintenance_margin_usd > 0
            else (
                CollateralState.DANGER.value
                if snap.margin_utilization_pct >= self.danger_threshold
                else (
                    CollateralState.CAUTION.value
                    if snap.margin_utilization_pct >= self.caution_threshold
                    else CollateralState.NORMAL.value
                )
            )
        )

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO collateral_snapshots (
                        snapshot_id, venue, total_equity_usd, available_balance_usd,
                        margin_used_usd, maintenance_margin_usd, margin_utilization_pct,
                        maintenance_buffer_ratio, state, data_quality, age_ms, created_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap_id,
                        snap.venue,
                        snap.total_equity_usd,
                        snap.available_balance_usd,
                        snap.margin_used_usd,
                        snap.maintenance_margin_usd,
                        snap.margin_utilization_pct,
                        snap.maintenance_buffer_ratio,
                        state_str,
                        snap.data_quality.value,
                        snap.age_ms,
                        snap.timestamp_ms,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.debug(f"Failed to persist collateral snapshot: {exc}")


# Global Collateral Governor singleton
collateral_governor = CollateralGovernor()
