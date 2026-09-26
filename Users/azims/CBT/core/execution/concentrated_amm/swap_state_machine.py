"""
core/execution/concentrated_amm/swap_state_machine.py
====================================================
Milestone 42-B4 & M42-B6: Multi-Tick Swap State Machine & Replay Microstructure Ledger.

Architectural Declarations:
---------------------------
1. Microstructure simulation only (NOT an execution engine).
2. Permanent capital firewall: real_capital_enabled = False.
3. Every swap state transition is fully explainable from:
   (sqrtPriceX96, tick, liquidity, initialized ticks, amount remaining, fee parameters)
   with zero hidden state.
4. Qualification constraint: QUALIFICATION_MAX_PRICE_IMPACT_BPS = 5.0 (0.05% max price impact).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, List, Optional, Tuple

from core.execution.concentrated_amm.swap_math import (
    compute_swap_step,
)
from core.execution.concentrated_amm.tick_bitmap import (
    TickTable,
)
from core.execution.concentrated_amm.tick_math import (
    MAX_SQRT_RATIO,
    MAX_TICK,
    MIN_SQRT_RATIO,
    MIN_TICK,
    QUALIFICATION_MAX_PRICE_IMPACT_BPS,
    REAL_CAPITAL_ENABLED,
    evaluate_price_impact_constraint,
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
    sqrt_ratio_x96_to_price,
)
from core.execution.concentrated_amm.v4_hooks import (
    BaseV4Hook,
    HookResult,
    HookSandbox,
)



@dataclass
class SwapStepRecord:
    """
    Replayable microstructure ledger entry capturing exact state transitions
    for every discrete tick boundary traversal during a multi-tick swap.
    """
    step_index: int
    tick_before: int
    sqrt_price_before: int
    liquidity_before: int
    amount_remaining_before: int

    next_initialized_tick: int
    target_sqrt_price: int
    amount_in: int
    fee_amount: int
    amount_out: int

    tick_after: int
    sqrt_price_after: int
    liquidity_after: int
    amount_remaining_after: int
    crossed_tick: bool = False
    real_capital_enabled: bool = False


@dataclass
class SwapExecutionReport:
    """
    Comprehensive analytical report of a simulated concentrated liquidity swap.
    """
    zero_for_one: bool
    amount_specified: int
    exact_in: bool

    initial_tick: int
    final_tick: int
    initial_sqrt_price_x96: int
    final_sqrt_price_x96: int
    initial_liquidity: int
    final_liquidity: int

    total_amount_in: int
    total_amount_out: int
    total_fee_amount: int
    amount_unconsumed: int

    initial_price_decimal: float
    final_price_decimal: float
    effective_execution_price: float
    price_impact_bps: float
    is_price_impact_qualified: bool
    price_impact_narrative: str

    step_ledger: List[SwapStepRecord] = field(default_factory=list)
    real_capital_enabled: bool = False
    hook_result: Optional[HookResult] = None
    is_halted: bool = False
    halt_reason: Optional[str] = None

    @property
    def step_count(self) -> int:
        return len(self.step_ledger)

    @property
    def is_conservation_verified(self) -> bool:
        """
        Verifies conservation invariant:
        input_specified == total_amount_in + amount_unconsumed + total_fee_amount
        """
        if self.exact_in:
            return self.amount_specified == (
                self.total_amount_in + self.amount_unconsumed + self.total_fee_amount
            )
        else:
            return self.total_amount_out <= abs(self.amount_specified)


class ConcentratedPoolState:
    """
    State of a concentrated liquidity AMM pool for microstructure simulation.
    """

    def __init__(
        self,
        token0_symbol: str = "WETH",
        token1_symbol: str = "USDC",
        decimals0: int = 18,
        decimals1: int = 6,
        fee_pips: int = 500,       # 500 = 5 bps = 0.05%
        tick_spacing: int = 10,
        initial_tick: int = 0,
        initial_liquidity: int = 0,
    ) -> None:
        self.token0 = token0_symbol
        self.token1 = token1_symbol
        self.token0_symbol = token0_symbol
        self.token1_symbol = token1_symbol
        self.decimals0 = decimals0
        self.decimals1 = decimals1
        self.fee_pips = fee_pips
        self.tick_spacing = tick_spacing

        self.tick = initial_tick
        self.sqrt_price_x96 = get_sqrt_ratio_at_tick(initial_tick)
        self.liquidity = initial_liquidity
        self.tick_table = TickTable(tick_spacing=tick_spacing)
        self.real_capital_enabled: bool = False

    def add_liquidity_position(
        self,
        tick_lower: int,
        tick_upper: int,
        liquidity_delta: int,
    ) -> None:
        """
        Adds a concentrated liquidity position [tick_lower, tick_upper].
        If current tick is within [tick_lower, tick_upper), active liquidity increases.
        """
        self.tick_table.insert_position(tick_lower, tick_upper, liquidity_delta)
        if tick_lower <= self.tick < tick_upper:
            self.liquidity += liquidity_delta


class ConcentratedSwapEngine:
    """
    Microstructure Swap State Machine executing multi-tick traversals
    and compiling a replayable step ledger.
    """

    def __init__(
        self,
        max_price_impact_bps: float = QUALIFICATION_MAX_PRICE_IMPACT_BPS,
    ) -> None:
        self.max_price_impact_bps = max_price_impact_bps
        self.real_capital_enabled: bool = False

    def execute_swap(
        self,
        pool: ConcentratedPoolState,
        zero_for_one: bool,
        amount_specified: int,
        sqrt_price_limit_x96: int | None = None,
        hook: Optional[BaseV4Hook] = None,
        timestamp_sec: float | None = None,
        sender: str = "0x0000000000000000000000000000000000000000",
        **hook_kwargs,
    ) -> SwapExecutionReport:
        """
        Executes an exact multi-tick swap traversal across discrete tick boundaries.
        
        Args:
            pool: Active concentrated pool state.
            zero_for_one: True if token0 -> token1 (price down), False if token1 -> token0 (price up).
            amount_specified: Positive integer for exact-in.
            sqrt_price_limit_x96: Optional slippage limit price in Q64.96.
            hook: Optional Uniswap v4 hook instance.
            timestamp_sec: Optional timestamp for hook evaluations.
            sender: Simulated sender address.
            
        Returns:
            SwapExecutionReport containing complete replay ledger and qualification status.
        """
        if amount_specified <= 0:
            raise ValueError("amount_specified must be strictly positive for simulation")

        # Resolve price limits
        if sqrt_price_limit_x96 is None:
            sqrt_price_limit_x96 = (
                MIN_SQRT_RATIO + 1 if zero_for_one else MAX_SQRT_RATIO - 1
            )
        else:
            if zero_for_one:
                if not (MIN_SQRT_RATIO < sqrt_price_limit_x96 < pool.sqrt_price_x96):
                    raise ValueError(
                        f"Price limit {sqrt_price_limit_x96} must be in ({MIN_SQRT_RATIO}, {pool.sqrt_price_x96})"
                    )
            else:
                if not (pool.sqrt_price_x96 < sqrt_price_limit_x96 < MAX_SQRT_RATIO):
                    raise ValueError(
                        f"Price limit {sqrt_price_limit_x96} must be in ({pool.sqrt_price_x96}, {MAX_SQRT_RATIO})"
                    )

        # Snapshot initial state
        initial_tick = pool.tick
        initial_sqrt_p = pool.sqrt_price_x96
        initial_liquidity = pool.liquidity
        initial_price_dec = sqrt_ratio_x96_to_price(
            initial_sqrt_p, decimals_base=pool.decimals0, decimals_quote=pool.decimals1
        )

        # Pre-swap hook invocation
        hook_res: Optional[HookResult] = None
        effective_fee_pips = pool.fee_pips
        if hook is not None:
            hook_res = HookSandbox.execute_before_swap_safely(
                hook=hook,
                sender=sender,
                pool_id=f"{pool.token0_symbol}/{pool.token1_symbol}/{pool.fee_pips}",
                zero_for_one=zero_for_one,
                amount_specified=amount_specified,
                current_tick=pool.tick,
                current_sqrt_price_x96=pool.sqrt_price_x96,
                timestamp_sec=timestamp_sec,
                **hook_kwargs,
            )
            if not hook_res.is_success:
                return SwapExecutionReport(
                    zero_for_one=zero_for_one,
                    amount_specified=amount_specified,
                    exact_in=True,
                    initial_tick=initial_tick,
                    final_tick=initial_tick,
                    initial_sqrt_price_x96=initial_sqrt_p,
                    final_sqrt_price_x96=initial_sqrt_p,
                    initial_liquidity=initial_liquidity,
                    final_liquidity=initial_liquidity,
                    total_amount_in=0,
                    total_amount_out=0,
                    total_fee_amount=0,
                    amount_unconsumed=amount_specified,
                    initial_price_decimal=initial_price_dec,
                    final_price_decimal=initial_price_dec,
                    effective_execution_price=initial_price_dec,
                    price_impact_bps=0.0,
                    is_price_impact_qualified=False,
                    price_impact_narrative=f"Swap halted by hook: {hook_res.revert_reason}",
                    step_ledger=[],
                    real_capital_enabled=False,
                    hook_result=hook_res,
                    is_halted=True,
                    halt_reason=hook_res.revert_reason,
                )
            if hook_res.override_fee_pips is not None:
                effective_fee_pips = hook_res.override_fee_pips

        amount_remaining = amount_specified
        total_amount_in = 0
        total_amount_out = 0
        total_fee_amount = 0
        step_ledger: List[SwapStepRecord] = []
        step_idx = 0

        # Iterative Multi-Tick Traversal
        while amount_remaining > 0 and pool.sqrt_price_x96 != sqrt_price_limit_x96:
            step_tick_before = pool.tick
            step_sqrt_p_before = pool.sqrt_price_x96
            step_liquidity_before = pool.liquidity
            step_remaining_before = amount_remaining

            # 1. Find next initialized tick in direction
            next_tick, is_initialized = pool.tick_table.next_initialized_tick(
                current_tick=pool.tick,
                zero_for_one=zero_for_one,
            )

            # Clamp next tick to valid bounds
            next_tick = max(MIN_TICK, min(MAX_TICK, next_tick))
            sqrt_price_next_tick_x96 = get_sqrt_ratio_at_tick(next_tick)

            # 2. Determine target sqrt price for this step
            if zero_for_one:
                target_sqrt_p = max(sqrt_price_next_tick_x96, sqrt_price_limit_x96)
            else:
                target_sqrt_p = min(sqrt_price_next_tick_x96, sqrt_price_limit_x96)

            # 3. Compute single swap step
            next_sqrt_p, step_in, step_out, step_fee = compute_swap_step(
                sqrt_ratio_current_x96=pool.sqrt_price_x96,
                sqrt_ratio_target_x96=target_sqrt_p,
                liquidity=pool.liquidity,
                amount_remaining=amount_remaining,
                fee_pips=effective_fee_pips,
            )

            # Update amounts
            total_amount_in += step_in
            total_amount_out += step_out
            total_fee_amount += step_fee
            amount_consumed_this_step = step_in + step_fee
            amount_remaining -= amount_consumed_this_step

            # 4. Update pool price and tick
            pool.sqrt_price_x96 = next_sqrt_p
            pool.tick = get_tick_at_sqrt_ratio(next_sqrt_p)

            # 5. Check if tick boundary was crossed
            crossed = False
            if pool.sqrt_price_x96 == sqrt_price_next_tick_x96:
                if is_initialized:
                    pool.liquidity = pool.tick_table.cross_tick(
                        tick=next_tick,
                        current_liquidity=pool.liquidity,
                        zero_for_one=zero_for_one,
                    )
                    crossed = True
                # Move tick pointer across boundary
                pool.tick = next_tick - 1 if zero_for_one else next_tick
            elif pool.sqrt_price_x96 != step_sqrt_p_before:
                pool.tick = get_tick_at_sqrt_ratio(pool.sqrt_price_x96)

            # Record step in ledger
            record = SwapStepRecord(
                step_index=step_idx,
                tick_before=step_tick_before,
                sqrt_price_before=step_sqrt_p_before,
                liquidity_before=step_liquidity_before,
                amount_remaining_before=step_remaining_before,
                next_initialized_tick=next_tick,
                target_sqrt_price=target_sqrt_p,
                amount_in=step_in,
                fee_amount=step_fee,
                amount_out=step_out,
                tick_after=pool.tick,
                sqrt_price_after=pool.sqrt_price_x96,
                liquidity_after=pool.liquidity,
                amount_remaining_after=amount_remaining,
                crossed_tick=crossed,
                real_capital_enabled=False,
            )
            step_ledger.append(record)
            step_idx += 1

            # Termination condition: if liquidity is zero and cannot move further
            if pool.liquidity == 0 and pool.sqrt_price_x96 == target_sqrt_p:
                break

        # Final pricing and impact
        final_price_dec = sqrt_ratio_x96_to_price(
            pool.sqrt_price_x96, decimals_base=pool.decimals0, decimals_quote=pool.decimals1
        )

        # Post-swap hook invocation
        if hook is not None:
            after_hook_res = HookSandbox.execute_after_swap_safely(
                hook=hook,
                sender=sender,
                pool_id=f"{pool.token0_symbol}/{pool.token1_symbol}/{pool.fee_pips}",
                zero_for_one=zero_for_one,
                amount_in=total_amount_in,
                amount_out=total_amount_out,
                fee_amount=total_fee_amount,
                final_tick=pool.tick,
                final_sqrt_price_x96=pool.sqrt_price_x96,
                timestamp_sec=timestamp_sec,
                price_decimal=final_price_dec,
                **hook_kwargs,
            )
            if hook_res is None or not after_hook_res.is_success:
                hook_res = after_hook_res


        # Effective execution price
        if total_amount_in > 0 and total_amount_out > 0:
            if zero_for_one:
                # Sold token0 for token1: price = out1 / in0
                eff_price = (total_amount_out * (10**pool.decimals0)) / (
                    total_amount_in * (10**pool.decimals1)
                )
            else:
                # Sold token1 for token0: price = in1 / out0
                eff_price = (total_amount_in * (10**pool.decimals0)) / (
                    total_amount_out * (10**pool.decimals1)
                )
        else:
            eff_price = initial_price_dec

        # Qualification constraint check
        is_qual, impact_bps, narrative = evaluate_price_impact_constraint(
            initial_price=initial_price_dec,
            execution_price=eff_price,
            max_allowed_impact_bps=self.max_price_impact_bps,
        )

        return SwapExecutionReport(
            zero_for_one=zero_for_one,
            amount_specified=amount_specified,
            exact_in=True,
            initial_tick=initial_tick,
            final_tick=pool.tick,
            initial_sqrt_price_x96=initial_sqrt_p,
            final_sqrt_price_x96=pool.sqrt_price_x96,
            initial_liquidity=initial_liquidity,
            final_liquidity=pool.liquidity,
            total_amount_in=total_amount_in,
            total_amount_out=total_amount_out,
            total_fee_amount=total_fee_amount,
            amount_unconsumed=amount_remaining,
            initial_price_decimal=initial_price_dec,
            final_price_decimal=final_price_dec,
            effective_execution_price=eff_price,
            price_impact_bps=impact_bps,
            is_price_impact_qualified=is_qual,
            price_impact_narrative=narrative,
            step_ledger=step_ledger,
            real_capital_enabled=False,
            hook_result=hook_res,
            is_halted=False,
            halt_reason=None,
        )
