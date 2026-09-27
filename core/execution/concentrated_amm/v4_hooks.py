"""
core/execution/concentrated_amm/v4_hooks.py
==========================================
Milestone 42-D: Uniswap v4 Hook Safety, Dynamic Fee & Volatility Circuit Breaker.

Architectural Declarations:
---------------------------
1. Microstructure simulation only (NOT an AMM execution engine).
2. Permanent capital firewall: real_capital_enabled = False.
3. Hook Failure Isolation: Hook crashes or malicious behavior cannot corrupt pool state.
4. Deterministic evaluation: Bit-identical decisions given identical inputs.

Hook Lifecycle:
---------------
- beforeSwap: pre-trade inspection, dynamic fee override, volatility circuit breaker.
- afterSwap: post-trade analytics, volume tracking, price velocity recording.
- beforeAddLiquidity / afterAddLiquidity
- beforeRemoveLiquidity / afterRemoveLiquidity
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntFlag
from typing import Dict, Final, List, Optional, Tuple

from core.execution.concentrated_amm.tick_math import (
    REAL_CAPITAL_ENABLED,
)

logger = logging.getLogger("concentrated_amm.v4_hooks")


class HookPermissions(IntFlag):
    """Uniswap v4 14-bit permission flags encoded in hook address."""
    NONE = 0
    BEFORE_INITIALIZE = 1 << 13
    AFTER_INITIALIZE = 1 << 12
    BEFORE_ADD_LIQUIDITY = 1 << 11
    AFTER_ADD_LIQUIDITY = 1 << 10
    BEFORE_REMOVE_LIQUIDITY = 1 << 9
    AFTER_REMOVE_LIQUIDITY = 1 << 8
    BEFORE_SWAP = 1 << 7
    AFTER_SWAP = 1 << 6
    BEFORE_DONATE = 1 << 5
    AFTER_DONATE = 1 << 4
    BEFORE_SWAP_RETURNS_DELTA = 1 << 3
    AFTER_SWAP_RETURNS_DELTA = 1 << 2
    AFTER_ADD_LIQUIDITY_RETURNS_DELTA = 1 << 1
    AFTER_REMOVE_LIQUIDITY_RETURNS_DELTA = 1 << 0


@dataclass
class HookResult:
    """Outcome of a hook execution."""
    is_success: bool
    revert_reason: Optional[str] = None
    override_fee_pips: Optional[int] = None
    is_circuit_breaker_tripped: bool = False
    action_narrative: str = "Hook execution passed"
    real_capital_enabled: bool = False


class BaseV4Hook(ABC):
    """Abstract Base Class for Uniswap v4 Simulation Hooks."""

    def __init__(self, permissions: HookPermissions) -> None:
        self.permissions = permissions
        self.real_capital_enabled: bool = False

    def before_swap(
        self,
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_specified: int,
        current_tick: int,
        current_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        """Invoked immediately prior to swap step computation."""
        return HookResult(is_success=True)

    def after_swap(
        self,
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_in: int,
        amount_out: int,
        fee_amount: int,
        final_tick: int,
        final_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        """Invoked immediately after swap completion."""
        return HookResult(is_success=True)


    def before_add_liquidity(
        self,
        sender: str,
        pool_id: str,
        tick_lower: int,
        tick_upper: int,
        liquidity_delta: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        """Invoked prior to adding liquidity."""
        return HookResult(is_success=True)

    def after_add_liquidity(
        self,
        sender: str,
        pool_id: str,
        tick_lower: int,
        tick_upper: int,
        liquidity_delta: int,
        amount0: int,
        amount1: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        """Invoked after adding liquidity."""
        return HookResult(is_success=True)

    def before_remove_liquidity(
        self,
        sender: str,
        pool_id: str,
        tick_lower: int,
        tick_upper: int,
        liquidity_delta: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        """Invoked prior to removing liquidity."""
        return HookResult(is_success=True)

    def after_remove_liquidity(
        self,
        sender: str,
        pool_id: str,
        tick_lower: int,
        tick_upper: int,
        liquidity_delta: int,
        amount0: int,
        amount1: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        """Invoked after removing liquidity."""
        return HookResult(is_success=True)


class VolatilityCircuitBreakerHook(BaseV4Hook):
    """
    Uniswap v4 Pre-Swap Volatility Circuit Breaker Hook.
    Monitors localized price velocity (bps/sec) and rolling drift.
    Trips circuit breaker to reject swaps if instantaneous volatility exceeds safety limit.
    """

    def __init__(
        self,
        max_drift_bps: float = 150.0,       # 150 bps max price drift
        window_sec: float = 60.0,           # 60s observation window
        cool_off_sec: float = 300.0,        # 5 minutes cool-off when tripped
    ) -> None:
        super().__init__(HookPermissions.BEFORE_SWAP | HookPermissions.AFTER_SWAP)
        self.max_drift_bps = max_drift_bps
        self.window_sec = window_sec
        self.cool_off_sec = cool_off_sec

        self.observations: List[Tuple[float, float]] = []  # (timestamp_sec, price)
        self.is_tripped: bool = False
        self.tripped_timestamp_sec: float = 0.0
        self.trip_reason: Optional[str] = None

    def record_price(self, price: float, timestamp_sec: float | None = None) -> None:
        """Records an external or pool price tick."""
        t = timestamp_sec if timestamp_sec is not None else time.time()
        self.observations.append((t, price))
        # Prune old observations
        cutoff = t - self.window_sec
        self.observations = [obs for obs in self.observations if obs[0] >= cutoff]

    def reset_circuit_breaker(self) -> None:
        """Manually or programmatically resets circuit breaker."""
        self.is_tripped = False
        self.tripped_timestamp_sec = 0.0
        self.trip_reason = None

    def before_swap(
        self,
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_specified: int,
        current_tick: int,
        current_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
    ) -> HookResult:
        now = timestamp_sec if timestamp_sec is not None else time.time()

        # Check if already tripped and in cool-off period
        if self.is_tripped:
            if now < (self.tripped_timestamp_sec + self.cool_off_sec):
                remaining = (self.tripped_timestamp_sec + self.cool_off_sec) - now
                return HookResult(
                    is_success=False,
                    revert_reason=f"Volatility Circuit Breaker ACTIVE: {self.trip_reason} (Cool-off remaining: {remaining:.0f}s)",
                    is_circuit_breaker_tripped=True,
                    action_narrative="Swap reverted by active volatility circuit breaker",
                    real_capital_enabled=False,
                )
            else:
                # Cool-off expired, auto-recover
                self.reset_circuit_breaker()

        # Evaluate rolling drift across observation window
        cutoff = now - self.window_sec
        recent_obs = [obs for obs in self.observations if obs[0] >= cutoff]

        if len(recent_obs) >= 2:
            min_price = min(obs[1] for obs in recent_obs)
            max_price = max(obs[1] for obs in recent_obs)
            if min_price > 0:
                drift_bps = ((max_price - min_price) / min_price) * 10_000.0
                if drift_bps > self.max_drift_bps:
                    self.is_tripped = True
                    self.tripped_timestamp_sec = now
                    self.trip_reason = (
                        f"Price drift {drift_bps:.1f} bps exceeded max threshold {self.max_drift_bps:.1f} bps in {self.window_sec:.0f}s"
                    )
                    logger.critical(f"Circuit Breaker Tripped on Pool {pool_id}: {self.trip_reason}")
                    return HookResult(
                        is_success=False,
                        revert_reason=f"Volatility Circuit Breaker Tripped: {self.trip_reason}",
                        is_circuit_breaker_tripped=True,
                        action_narrative="Swap reverted due to excessive short-term volatility",
                        real_capital_enabled=False,
                    )

        return HookResult(is_success=True)

    def after_swap(
        self,
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_in: int,
        amount_out: int,
        fee_amount: int,
        final_tick: int,
        final_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
        price_decimal: float | None = None,
        **kwargs,
    ) -> HookResult:
        now = timestamp_sec if timestamp_sec is not None else time.time()
        if price_decimal is not None:
            price = price_decimal
        else:
            price = (final_sqrt_price_x96 / (1 << 96)) ** 2
        self.record_price(price, timestamp_sec=now)
        return HookResult(is_success=True)



class DynamicFeeHook(BaseV4Hook):
    """
    Uniswap v4 Dynamic Fee Adaptation Hook.
    Adapts pool swap fee dynamically as a function of instantaneous realized volatility,
    protecting passive liquidity providers against toxic order flow and adverse selection.
    """

    def __init__(
        self,
        base_fee_pips: int = 500,     # 5 bps (0.05%) default
        min_fee_pips: int = 100,      # 1 bps (0.01%) minimum floor
        max_fee_pips: int = 10000,    # 100 bps (1.00%) maximum ceiling
        volatility_scaling_factor: float = 2.0,
    ) -> None:
        super().__init__(HookPermissions.BEFORE_SWAP)
        self.base_fee_pips = base_fee_pips
        self.min_fee_pips = min_fee_pips
        self.max_fee_pips = max_fee_pips
        self.vol_scale = volatility_scaling_factor

    def compute_dynamic_fee(self, realized_vol_bps: float) -> int:
        """
        Computes dynamic fee: fee = base_fee + vol_scale * realized_vol_bps
        Bounded strictly within [min_fee, max_fee].
        """
        additive_pips = int(realized_vol_bps * 100.0 * self.vol_scale)
        computed_fee = self.base_fee_pips + additive_pips
        return max(self.min_fee_pips, min(self.max_fee_pips, computed_fee))

    def before_swap(
        self,
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_specified: int,
        current_tick: int,
        current_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
        realized_vol_bps: float = 0.0,
        **kwargs,
    ) -> HookResult:
        dynamic_fee = self.compute_dynamic_fee(realized_vol_bps)
        return HookResult(
            is_success=True,
            override_fee_pips=dynamic_fee,
            action_narrative=f"Dynamic fee adjusted to {dynamic_fee} pips ({dynamic_fee / 100.0:.1f} bps)",
            real_capital_enabled=False,
        )


class HookSandbox:
    """
    Fail-Safe Execution Sandbox for Uniswap v4 Hooks.
    Guarantees isolation: unhandled exceptions in hook logic are safely intercepted
    and prevent pool state corruption.
    """

    @staticmethod
    def execute_before_swap_safely(
        hook: Optional[BaseV4Hook],
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_specified: int,
        current_tick: int,
        current_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
        **kwargs,
    ) -> HookResult:
        """
        Executes before_swap with complete failure containment.
        If hook throws an exception, fails closed safely.
        """
        if hook is None:
            return HookResult(is_success=True)

        if not (hook.permissions & HookPermissions.BEFORE_SWAP):
            return HookResult(is_success=True)

        try:
            return hook.before_swap(
                sender=sender,
                pool_id=pool_id,
                zero_for_one=zero_for_one,
                amount_specified=amount_specified,
                current_tick=current_tick,
                current_sqrt_price_x96=current_sqrt_price_x96,
                timestamp_sec=timestamp_sec,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Hook Sandbox Intercepted Exception in before_swap: {e}", exc_info=True)
            return HookResult(
                is_success=False,
                revert_reason=f"Hook failure intercepted by sandbox ({e.__class__.__name__}): {str(e)}",
                is_circuit_breaker_tripped=False,
                action_narrative="Hook threw unhandled exception; failed closed safely",
                real_capital_enabled=False,
            )


    @staticmethod
    def execute_after_swap_safely(
        hook: Optional[BaseV4Hook],
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_in: int,
        amount_out: int,
        fee_amount: int,
        final_tick: int,
        final_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
        **kwargs,
    ) -> HookResult:
        """
        Executes after_swap with complete failure containment.
        If hook throws an exception, logs and reports safely without failing the swap.
        """
        if hook is None:
            return HookResult(is_success=True)

        if not (hook.permissions & HookPermissions.AFTER_SWAP):
            return HookResult(is_success=True)

        try:
            return hook.after_swap(
                sender=sender,
                pool_id=pool_id,
                zero_for_one=zero_for_one,
                amount_in=amount_in,
                amount_out=amount_out,
                fee_amount=fee_amount,
                final_tick=final_tick,
                final_sqrt_price_x96=final_sqrt_price_x96,
                timestamp_sec=timestamp_sec,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Hook Sandbox Intercepted Exception in after_swap: {e}", exc_info=True)
            return HookResult(
                is_success=False,
                revert_reason=f"After-swap hook failure intercepted: {str(e)}",
                action_narrative="After-swap hook failed safely in sandbox",
                real_capital_enabled=False,
            )

