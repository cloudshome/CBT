"""
Real-Time Scenario Collapse & Invalidation Watchdog.
Performs sub-second monitoring of active scenario invalidation prices and catastrophic orderflow breakdowns.
Instantly emits SCENARIO_COLLAPSED_ALERT and aborts pending executions before candle close.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.scenario_engine import MECEScenarioDistribution, Scenario

logger = logging.getLogger("ai_quant_sentinel.scenario_monitor")


@dataclass
class ScenarioCollapseAlert:
    collapsed: bool
    symbol: str
    scenario_id: str
    invalidation_price: float
    current_price: float
    trigger_reason: str
    action_required: str               # "ABORT_PENDING_ORDERS", "RECALCULATE_DISTRIBUTION", "NONE"


class ScenarioMonitor:
    """Watchdog continuously validating live market ticks against active scenario bounds."""

    def __init__(self):
        self._active_scenarios: Dict[str, MECEScenarioDistribution] = {}

    def register_active_distribution(self, symbol: str, dist: MECEScenarioDistribution) -> None:
        self._active_scenarios[symbol] = dist

    def check_tick_invalidation(
        self,
        symbol: str,
        current_tick_price: float,
        current_cvd_delta: float = 0.0,
    ) -> Optional[ScenarioCollapseAlert]:
        """
        Evaluates current price against dominant scenario invalidation thresholds.
        """
        dist = self._active_scenarios.get(symbol)
        if not dist:
            return None

        dom_scenario = next((s for s in dist.scenarios if s.scenario_id == dist.dominant_scenario_id), None)
        if not dom_scenario:
            return None

        # Check Price Breach Invalidation
        is_bullish = "BULLISH" in dom_scenario.name.upper()
        inval_price = dom_scenario.invalidation_price

        breached = False
        reason = ""

        if is_bullish and current_tick_price <= inval_price:
            breached = True
            reason = f"Price breached Bullish Invalidation level (${current_tick_price:,.2f} <= ${inval_price:,.2f})"
        elif not is_bullish and current_tick_price >= inval_price:
            breached = True
            reason = f"Price breached Bearish Invalidation level (${current_tick_price:,.2f} >= ${inval_price:,.2f})"

        # Check Sudden Orderflow Collapse
        if not breached:
            if is_bullish and current_cvd_delta < -0.80:
                breached = True
                reason = f"Catastrophic CVD Orderflow Collapse detected (Delta = {current_cvd_delta:+.2f})"
            elif not is_bullish and current_cvd_delta > 0.80:
                breached = True
                reason = f"Aggressive Contra-CVD Buying Spike detected (Delta = {current_cvd_delta:+.2f})"

        if breached:
            logger.warning(f"SCENARIO_COLLAPSED_ALERT for {symbol}: {reason}. ABORTING PENDING ORDERS.")
            return ScenarioCollapseAlert(
                collapsed=True,
                symbol=symbol,
                scenario_id=dom_scenario.scenario_id,
                invalidation_price=inval_price,
                current_price=current_tick_price,
                trigger_reason=reason,
                action_required="ABORT_PENDING_ORDERS",
            )

        return None


# Singleton
scenario_monitor = ScenarioMonitor()
