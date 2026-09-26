"""
core/execution/concentrated_amm/tick_bitmap.py
=============================================
Milestone 42-B1 & M42-B2: Tick Bitmap, Initialized-Tick Traversal & Liquidity-Net State Machine.

Architectural Declarations:
---------------------------
1. Microstructure simulation engine only (NOT an execution engine).
2. Permanent capital firewall: real_capital_enabled = False.
3. Every state transition is strictly deterministic and replayable.

Mathematical Specifications:
-----------------------------
When crossing an initialized tick t:
- If zero_for_one == True (price decreasing, moving right-to-left):
    L_after = L_before - liquidity_net(t)
- If zero_for_one == False (price increasing, moving left-to-right):
    L_after = L_before + liquidity_net(t)
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.execution.concentrated_amm.tick_math import (
    MAX_TICK,
    MIN_TICK,
    REAL_CAPITAL_ENABLED,
    is_valid_tick_for_spacing,
    nearest_valid_tick,
)


@dataclass
class TickInfo:
    """Microstructure state stored at an initialized tick."""
    tick: int
    liquidity_gross: int = 0
    liquidity_net: int = 0
    initialized: bool = False
    real_capital_enabled: bool = False

    def update(self, liquidity_delta: int, is_upper: bool) -> None:
        """
        Updates liquidity gross and net for position addition/removal.
        """
        self.liquidity_gross += abs(liquidity_delta)
        if is_upper:
            self.liquidity_net -= liquidity_delta
        else:
            self.liquidity_net += liquidity_delta

        self.initialized = self.liquidity_gross > 0


class TickTable:
    """
    Deterministic sparse tick index supporting O(log N) next-initialized-tick queries
    and exact liquidity-net crossing transitions.
    """

    def __init__(self, tick_spacing: int = 60) -> None:
        if tick_spacing <= 0:
            raise ValueError("tick_spacing must be strictly positive")
        self.tick_spacing = tick_spacing
        self.ticks: Dict[int, TickInfo] = {}
        self._sorted_initialized_ticks: List[int] = []
        self.real_capital_enabled: bool = False

    @property
    def initialized_tick_count(self) -> int:
        return len(self._sorted_initialized_ticks)

    def get_tick(self, tick: int) -> TickInfo:
        return self.ticks.get(tick, TickInfo(tick=tick))

    def insert_position(
        self,
        tick_lower: int,
        tick_upper: int,
        liquidity_delta: int,
    ) -> None:
        """
        Inserts or modifies a concentrated liquidity position [tick_lower, tick_upper].
        """
        if tick_lower >= tick_upper:
            raise ValueError(f"tick_lower ({tick_lower}) must be strictly less than tick_upper ({tick_upper})")
        if not (MIN_TICK <= tick_lower <= MAX_TICK and MIN_TICK <= tick_upper <= MAX_TICK):
            raise ValueError(f"Ticks out of allowable bounds [{MIN_TICK}, {MAX_TICK}]")
        if not is_valid_tick_for_spacing(tick_lower, self.tick_spacing):
            raise ValueError(f"tick_lower {tick_lower} must align to tick_spacing {self.tick_spacing}")
        if not is_valid_tick_for_spacing(tick_upper, self.tick_spacing):
            raise ValueError(f"tick_upper {tick_upper} must align to tick_spacing {self.tick_spacing}")

        # Update lower tick
        if tick_lower not in self.ticks:
            self.ticks[tick_lower] = TickInfo(tick=tick_lower)
        self.ticks[tick_lower].update(liquidity_delta, is_upper=False)

        # Update upper tick
        if tick_upper not in self.ticks:
            self.ticks[tick_upper] = TickInfo(tick=tick_upper)
        self.ticks[tick_upper].update(liquidity_delta, is_upper=True)

        self._rebuild_sorted_index()

    def _rebuild_sorted_index(self) -> None:
        """Maintains sorted index of strictly initialized ticks."""
        self._sorted_initialized_ticks = sorted(
            tick for tick, info in self.ticks.items() if info.initialized
        )

    def next_initialized_tick(
        self,
        current_tick: int,
        zero_for_one: bool,
    ) -> Tuple[int, bool]:
        """
        Finds the next initialized tick in the swap direction.
        
        Args:
            current_tick: active pool tick.
            zero_for_one: True if price decreasing (moving down/left), False if price increasing (moving up/right).
            
        Returns:
            (next_tick, is_initialized):
            - If found: (next_tick, True)
            - If no initialized tick remains before boundary: (boundary_tick, False)
        """
        if not self._sorted_initialized_ticks:
            boundary = MIN_TICK if zero_for_one else MAX_TICK
            return boundary, False

        if zero_for_one:
            # Moving left/down (<= current_tick)
            idx = bisect.bisect_right(self._sorted_initialized_ticks, current_tick) - 1
            if idx >= 0:
                return self._sorted_initialized_ticks[idx], True
            else:
                return MIN_TICK, False
        else:
            # Moving right/up (> current_tick)
            idx = bisect.bisect_right(self._sorted_initialized_ticks, current_tick)
            if idx < len(self._sorted_initialized_ticks):
                return self._sorted_initialized_ticks[idx], True
            else:
                return MAX_TICK, False

    def cross_tick(
        self,
        tick: int,
        current_liquidity: int,
        zero_for_one: bool,
    ) -> int:
        """
        Executes exact liquidity-net transition when crossing tick boundary:
        - zero_for_one == True: L_new = L_curr - liquidity_net(tick)
        - zero_for_one == False: L_new = L_curr + liquidity_net(tick)
        """
        tick_info = self.ticks.get(tick)
        if not tick_info:
            return current_liquidity

        if zero_for_one:
            new_liquidity = current_liquidity - tick_info.liquidity_net
        else:
            new_liquidity = current_liquidity + tick_info.liquidity_net

        if new_liquidity < 0:
            raise ValueError(
                f"Negative liquidity encountered after crossing tick {tick}: {new_liquidity}"
            )
        return new_liquidity
