"""
core/mbo/iceberg_detector.py
============================
Institutional Iceberg & Algorithmic Reload Order Detector.
Identifies hidden liquidity walls by tracking execution volume vs displayed depth
at discrete price levels without price degradation.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from core.mbo.models import IcebergDetection, MBOSide

logger = logging.getLogger("sky.mbo.iceberg_detector")


class IcebergDetector:
    """Detects institutional hidden reload iceberg orders from L3 order executions."""

    def __init__(
        self,
        min_reload_count: int = 2,
        execution_to_displayed_threshold: float = 1.8,
        decay_window_sec: float = 300.0,
    ) -> None:
        self.min_reload_count = min_reload_count
        self.execution_to_displayed_threshold = execution_to_displayed_threshold
        self.decay_window_sec = decay_window_sec

        # Tracking state: (symbol, venue, side, price) -> state dict
        self._level_states: Dict[Tuple[str, str, MBOSide, float], Dict[str, Any]] = {}
        self._detected_icebergs: Dict[str, IcebergDetection] = {}

    def register_initial_depth(
        self,
        symbol: str,
        venue: str,
        side: MBOSide,
        price: float,
        displayed_size: float,
        timestamp_ns: Optional[int] = None,
    ) -> None:
        """Registers the baseline displayed size for a price level."""
        now_ns = timestamp_ns or int(time.time() * 1e9)
        key = (symbol, venue, side, price)

        if key not in self._level_states:
            self._level_states[key] = {
                "initial_displayed_size": max(0.001, displayed_size),
                "cumulative_executed": 0.0,
                "reloads": 0,
                "first_seen_ns": now_ns,
                "last_exec_ns": now_ns,
                "reload_sizes": [],
            }
        else:
            state = self._level_states[key]
            # If idle for longer than decay window, reset baseline
            if (now_ns - state["last_exec_ns"]) / 1e9 > self.decay_window_sec:
                state["initial_displayed_size"] = max(0.001, displayed_size)
                state["cumulative_executed"] = 0.0
                state["reloads"] = 0
                state["first_seen_ns"] = now_ns
                state["reload_sizes"].clear()

    def record_execution(
        self,
        symbol: str,
        venue: str,
        side: MBOSide,
        price: float,
        executed_qty: float,
        remaining_displayed_qty: float,
        timestamp_ns: Optional[int] = None,
    ) -> Optional[IcebergDetection]:
        """
        Records an execution event at a price level.
        Detects if executed quantity repeatedly replenishes beyond initial displayed size.
        """
        now_ns = timestamp_ns or int(time.time() * 1e9)
        key = (symbol, venue, side, price)

        if key not in self._level_states:
            self.register_initial_depth(symbol, venue, side, price, remaining_displayed_qty + executed_qty, now_ns)

        state = self._level_states[key]
        state["cumulative_executed"] += executed_qty
        state["last_exec_ns"] = now_ns

        d0 = state["initial_displayed_size"]
        cum_exec = state["cumulative_executed"]

        # Check if the level has absorbed more than threshold * d0
        ratio = cum_exec / max(0.001, d0)

        # Reload count estimation
        estimated_reloads = int(ratio)
        if estimated_reloads > state["reloads"]:
            state["reloads"] = estimated_reloads
            state["reload_sizes"].append(executed_qty)

        # Trigger iceberg detection
        if ratio >= self.execution_to_displayed_threshold and state["reloads"] >= self.min_reload_count:
            iceberg_id = f"ICE_{symbol}_{venue}_{side.value}_{int(price)}_{state['first_seen_ns']}"

            # Calculate metrics
            avg_reload = d0
            if state["reload_sizes"]:
                avg_reload = sum(state["reload_sizes"]) / len(state["reload_sizes"])

            # Confidence score rises with number of reloads
            confidence = min(0.98, 0.60 + (0.08 * state["reloads"]))

            # Expected hidden size estimation: typical icebergs maintain 3x to 5x reload depth
            estimated_hidden = max(0.0, avg_reload * (state["reloads"] + 2) - cum_exec)
            total_est = cum_exec + remaining_displayed_qty + estimated_hidden

            detection = IcebergDetection(
                iceberg_id=iceberg_id,
                symbol=symbol,
                venue=venue,
                side=side,
                price=price,
                initial_displayed_size=round(d0, 4),
                cumulative_executed_size=round(cum_exec, 4),
                estimated_reload_size=round(avg_reload, 4),
                estimated_total_hidden_qty=round(estimated_hidden, 4),
                total_estimated_size=round(total_est, 4),
                confidence_score=round(confidence, 3),
                reload_count=state["reloads"],
                first_detected_ns=state["first_seen_ns"],
                last_reload_ns=now_ns,
                is_active=True,
            )

            self._detected_icebergs[iceberg_id] = detection
            return detection

        return None

    def get_active_icebergs(self, symbol: Optional[str] = None) -> List[IcebergDetection]:
        """Returns currently active detected icebergs within the decay window."""
        now_ns = int(time.time() * 1e9)
        active: List[IcebergDetection] = []

        for iceberg in self._detected_icebergs.values():
            if symbol and iceberg.symbol != symbol:
                continue
            age_sec = (now_ns - iceberg.last_reload_ns) / 1e9
            if age_sec <= self.decay_window_sec:
                active.append(iceberg)
            else:
                iceberg.is_active = False

        return sorted(active, key=lambda x: x.cumulative_executed_size, reverse=True)
