"""
core/risk_engine/collateral_monitor.py
======================================
Milestone 34: Cross-Venue Collateral Telemetry & Dynamic Liquidity Topology.

Mandates:
- Real-time continuous margin utilization tracking across multi-venue accounts.
- Liquidation Distance Buffer (LDB) estimation in basis points:
    LDB_bps = (|P_mark - P_liq| / P_mark) * 10,000
- Multi-tier alert state machine:
    NORMAL -> ELEVATED_RISK -> MARGIN_CALL_WARNING -> CRITICAL_EMERGENCY_DELEVERAGING
- Asymmetric Liquidation Hazard Detection:
    Alerts when one leg of a synthetic basis pair approaches liquidation
    even if the combined net PnL is positive.
- Non-negotiable constitutional capital isolation: real_capital_enabled = False.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger("ai_quant_sentinel.risk_engine.collateral_monitor")


class LiquidationRiskTier(str, Enum):
    """Categorical risk state based on liquidation distance buffer."""

    NORMAL = "NORMAL"  # LDB > 1500 bps (>15%)
    ELEVATED_RISK = "ELEVATED_RISK"  # 800 < LDB <= 1500 bps (8-15%)
    MARGIN_CALL_WARNING = "MARGIN_CALL_WARNING"  # 300 < LDB <= 800 bps (3-8%)
    CRITICAL_EMERGENCY = "CRITICAL_EMERGENCY"  # LDB <= 300 bps (<=3%)


class VenueCollateralTelemetry(BaseModel):
    """Real-time collateral health report for a specific venue."""

    venue: str
    symbol: str
    position_size: float
    entry_price: float
    mark_price: float
    liquidation_price: float
    total_equity_usd: float = Field(gt=0.0)
    used_margin_usd: float = Field(ge=0.0)
    available_margin_usd: float = Field(ge=0.0)
    maintenance_margin_req_usd: float = Field(ge=0.0)
    margin_utilization: float = Field(ge=0.0, le=1.0)
    liquidation_distance_bps: float
    risk_tier: LiquidationRiskTier
    timestamp_ns: int = Field(default_factory=time.monotonic_ns)


class AsymmetricHazardReport(BaseModel):
    """Diagnostic outcome when cross-venue margin parity is dangerously misaligned."""

    synthetic_pair_id: str
    symbol: str
    leg_1_venue: str
    leg_1_ldb_bps: float
    leg_1_risk_tier: LiquidationRiskTier
    leg_2_venue: str
    leg_2_ldb_bps: float
    leg_2_risk_tier: LiquidationRiskTier
    hazard_detected: bool
    asymmetry_ratio: float
    action_required: str
    real_capital_enabled: bool = False
    timestamp_ns: int = Field(default_factory=time.monotonic_ns)


class CollateralHeartbeatMonitor:
    """
    Sub-second Multi-Venue Collateral Heartbeat Monitor.

    Monitors Liquidation Distance Buffers (LDB), margin health, and asymmetric
    liquidation hazards across Binance, Bybit, and Hyperliquid.
    """

    def __init__(
        self,
        normal_ldb_threshold_bps: float = 1500.0,
        warning_ldb_threshold_bps: float = 800.0,
        critical_ldb_threshold_bps: float = 300.0,
        max_asymmetric_hazard_delta_bps: float = 1000.0,
    ) -> None:
        self.normal_ldb_threshold_bps = normal_ldb_threshold_bps
        self.warning_ldb_threshold_bps = warning_ldb_threshold_bps
        self.critical_ldb_threshold_bps = critical_ldb_threshold_bps
        self.max_asymmetric_hazard_delta_bps = max_asymmetric_hazard_delta_bps

        # Telemetry cache: (venue, symbol) -> VenueCollateralTelemetry
        self._telemetry_cache: dict[tuple[str, str], VenueCollateralTelemetry] = {}

    def compute_collateral_telemetry(
        self,
        venue: str,
        symbol: str,
        position_size: float,
        entry_price: float,
        mark_price: float,
        liquidation_price: float,
        total_equity_usd: float,
        used_margin_usd: float,
        maintenance_margin_req_usd: float,
    ) -> VenueCollateralTelemetry:
        """
        Calculates exact Liquidation Distance Buffer (LDB) and categorizes risk tier.
        """
        if total_equity_usd <= 0.0:
            margin_utilization = 1.0
        else:
            margin_utilization = min(1.0, max(0.0, used_margin_usd / total_equity_usd))

        available_margin_usd = max(0.0, total_equity_usd - used_margin_usd)

        # Liquidation Distance Buffer in bps
        if position_size == 0.0 or liquidation_price <= 0.0 or mark_price <= 0.0:
            # Flat position or no liquidation risk
            ldb_bps = 100000.0
            risk_tier = LiquidationRiskTier.NORMAL
        else:
            ldb_bps = (abs(mark_price - liquidation_price) / mark_price) * 10000.0

            if ldb_bps > self.normal_ldb_threshold_bps:
                risk_tier = LiquidationRiskTier.NORMAL
            elif ldb_bps > self.warning_ldb_threshold_bps:
                risk_tier = LiquidationRiskTier.ELEVATED_RISK
            elif ldb_bps > self.critical_ldb_threshold_bps:
                risk_tier = LiquidationRiskTier.MARGIN_CALL_WARNING
            else:
                risk_tier = LiquidationRiskTier.CRITICAL_EMERGENCY

        telemetry = VenueCollateralTelemetry(
            venue=venue,
            symbol=symbol,
            position_size=position_size,
            entry_price=entry_price,
            mark_price=mark_price,
            liquidation_price=liquidation_price,
            total_equity_usd=total_equity_usd,
            used_margin_usd=used_margin_usd,
            available_margin_usd=available_margin_usd,
            maintenance_margin_req_usd=maintenance_margin_req_usd,
            margin_utilization=margin_utilization,
            liquidation_distance_bps=ldb_bps,
            risk_tier=risk_tier,
            timestamp_ns=time.monotonic_ns(),
        )

        self._telemetry_cache[(venue, symbol)] = telemetry
        return telemetry

    def evaluate_asymmetric_hazard(
        self,
        synthetic_pair_id: str,
        symbol: str,
        leg_1_venue: str,
        leg_2_venue: str,
    ) -> AsymmetricHazardReport:
        """
        Evaluates whether a synthetic basis pair suffers from an Asymmetric Liquidation Hazard.

        Hazard Condition:
        One leg has dropped to MARGIN_CALL_WARNING or CRITICAL_EMERGENCY (or LDB delta > threshold),
        threatening one-sided liquidation of an otherwise delta-neutral trade.
        """
        leg_1 = self._telemetry_cache.get((leg_1_venue, symbol))
        leg_2 = self._telemetry_cache.get((leg_2_venue, symbol))

        if leg_1 is None or leg_2 is None:
            return AsymmetricHazardReport(
                synthetic_pair_id=synthetic_pair_id,
                symbol=symbol,
                leg_1_venue=leg_1_venue,
                leg_1_ldb_bps=100000.0,
                leg_1_risk_tier=LiquidationRiskTier.NORMAL,
                leg_2_venue=leg_2_venue,
                leg_2_ldb_bps=100000.0,
                leg_2_risk_tier=LiquidationRiskTier.NORMAL,
                hazard_detected=False,
                asymmetry_ratio=1.0,
                action_required="INSUFFICIENT_TELEMETRY",
                real_capital_enabled=False,
            )

        ldb_1 = leg_1.liquidation_distance_bps
        ldb_2 = leg_2.liquidation_distance_bps
        min_ldb = min(ldb_1, ldb_2)
        max_ldb = max(ldb_1, ldb_2)
        delta_ldb = max_ldb - min_ldb

        asymmetry_ratio = max_ldb / max(1.0, min_ldb)

        hazard_detected = False
        action = "NONE"

        # Check if one leg is at high risk while the other is safe
        if min_ldb <= self.critical_ldb_threshold_bps:
            hazard_detected = True
            vulnerable_venue = leg_1_venue if ldb_1 < ldb_2 else leg_2_venue
            action = f"EMERGENCY_DELEVERAGE_OR_REBALANCE: Venue {vulnerable_venue} LDB <= {self.critical_ldb_threshold_bps:.0f} bps"
        elif (
            min_ldb <= self.warning_ldb_threshold_bps
            and delta_ldb >= self.max_asymmetric_hazard_delta_bps
        ):
            hazard_detected = True
            vulnerable_venue = leg_1_venue if ldb_1 < ldb_2 else leg_2_venue
            action = f"REBALANCE_ADVISORY: Asymmetry delta {delta_ldb:.0f} bps exceeds tolerance {self.max_asymmetric_hazard_delta_bps:.0f} bps"

        return AsymmetricHazardReport(
            synthetic_pair_id=synthetic_pair_id,
            symbol=symbol,
            leg_1_venue=leg_1_venue,
            leg_1_ldb_bps=ldb_1,
            leg_1_risk_tier=leg_1.risk_tier,
            leg_2_venue=leg_2_venue,
            leg_2_ldb_bps=ldb_2,
            leg_2_risk_tier=leg_2.risk_tier,
            hazard_detected=hazard_detected,
            asymmetry_ratio=asymmetry_ratio,
            action_required=action,
            real_capital_enabled=False,
            timestamp_ns=time.monotonic_ns(),
        )
