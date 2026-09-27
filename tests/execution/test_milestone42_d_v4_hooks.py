"""
tests/execution/test_milestone42_d_v4_hooks.py
==============================================
Milestone 42-D Test Suite: Uniswap v4 Hook Safety, Dynamic Fee & Volatility Circuit Breaker.

Verification Objectives:
1. Hook permissions bitwise representation and invariant checks.
2. Volatility circuit breaker: normal pass vs. drift > 150 bps trip.
3. Volatility circuit breaker cool-off period and auto-recovery/manual reset.
4. Dynamic fee hook: base fee, volatility scaling, clamping to bounds, fee override in swap engine.
5. HookSandbox exception containment: faulty hook crashes intercepted, fail-closed safety, no pool corruption.
6. HookSandbox after-swap exception containment.
7. After-swap observation recording in circuit breaker.
8. Permanent capital firewall: real_capital_enabled == False.
"""

from core.execution.concentrated_amm.swap_state_machine import (
    ConcentratedPoolState,
    ConcentratedSwapEngine,
)
from core.execution.concentrated_amm.tick_math import (
    REAL_CAPITAL_ENABLED,
    price_to_tick,
)
from core.execution.concentrated_amm.v4_hooks import (
    BaseV4Hook,
    DynamicFeeHook,
    HookPermissions,
    HookResult,
    VolatilityCircuitBreakerHook,
)


def _setup_test_pool(
    price: float = 3000.0, liquidity: int = 10_000_000_000_000_000_000
) -> ConcentratedPoolState:
    """Helper to initialize a deep test pool."""
    tick = price_to_tick(price, decimals_base=18, decimals_quote=6)
    # Align tick to spacing
    aligned_tick = (tick // 60) * 60
    pool = ConcentratedPoolState(
        token0_symbol="WETH",
        token1_symbol="USDC",
        fee_pips=500,  # 5 bps
        decimals0=18,
        decimals1=6,
        tick_spacing=60,
        initial_tick=aligned_tick,
        initial_liquidity=liquidity,
    )
    lower_tick = aligned_tick - 1200
    upper_tick = aligned_tick + 1200
    pool.add_liquidity_position(lower_tick, upper_tick, liquidity)
    return pool


class FaultyHook(BaseV4Hook):
    """Faulty test hook designed to simulate crashes or malicious reverts."""

    def __init__(self, crash_in_before: bool = True, crash_in_after: bool = False) -> None:
        super().__init__(HookPermissions.BEFORE_SWAP | HookPermissions.AFTER_SWAP)
        self.crash_in_before = crash_in_before
        self.crash_in_after = crash_in_after

    def before_swap(
        self,
        sender: str,
        pool_id: str,
        zero_for_one: bool,
        amount_specified: int,
        current_tick: int,
        current_sqrt_price_x96: int,
        timestamp_sec: float | None = None,
        **kwargs,
    ) -> HookResult:
        if self.crash_in_before:
            raise ZeroDivisionError("Simulated division by zero in custom hook!")
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
        **kwargs,
    ) -> HookResult:
        if self.crash_in_after:
            raise RuntimeError("Simulated runtime memory error in after_swap hook!")
        return HookResult(is_success=True)


class TestMilestone42DV4Hooks:
    """Milestone 42-D Test Suite."""

    def test_m42_d_hook_permissions_and_invariants(self):
        """Verifies bitwise permission flags and permanent capital firewall."""
        assert REAL_CAPITAL_ENABLED is False

        flags = HookPermissions.BEFORE_SWAP | HookPermissions.AFTER_SWAP
        assert bool(flags & HookPermissions.BEFORE_SWAP)
        assert bool(flags & HookPermissions.AFTER_SWAP)
        assert not bool(flags & HookPermissions.BEFORE_ADD_LIQUIDITY)

        hook = VolatilityCircuitBreakerHook()
        assert hook.real_capital_enabled is False

        dyn_hook = DynamicFeeHook()
        assert dyn_hook.real_capital_enabled is False

    def test_m42_d_circuit_breaker_normal_operation(self):
        """Verifies that normal price movement (<150 bps) passes through circuit breaker."""
        hook = VolatilityCircuitBreakerHook(max_drift_bps=150.0, window_sec=60.0)
        now = 1000.0
        # 30 bps drift
        hook.record_price(3000.0, timestamp_sec=now - 30)
        hook.record_price(3009.0, timestamp_sec=now)

        pool = _setup_test_pool(price=3000.0)
        engine = ConcentratedSwapEngine()

        # Execute small swap (1 ETH)
        report = engine.execute_swap(
            pool=pool,
            zero_for_one=True,
            amount_specified=10**18,
            hook=hook,
            timestamp_sec=now,
        )

        assert report.is_halted is False
        assert report.is_conservation_verified is True
        assert report.total_amount_in > 0
        assert report.total_amount_out > 0
        assert report.hook_result is not None
        assert report.hook_result.is_success is True

    def test_m42_d_circuit_breaker_trips_on_excess_drift(self):
        """Verifies that price drift exceeding 150 bps trips circuit breaker and halts swap."""
        hook = VolatilityCircuitBreakerHook(max_drift_bps=150.0, window_sec=60.0)
        now = 1000.0
        # 200 bps drift: 3000 -> 3060
        hook.record_price(3000.0, timestamp_sec=now - 20)
        hook.record_price(3065.0, timestamp_sec=now)

        pool = _setup_test_pool(price=3000.0)
        initial_p = pool.sqrt_price_x96
        initial_liq = pool.liquidity

        engine = ConcentratedSwapEngine()
        report = engine.execute_swap(
            pool=pool,
            zero_for_one=True,
            amount_specified=10**18,
            hook=hook,
            timestamp_sec=now,
        )

        assert report.is_halted is True
        assert report.hook_result is not None
        assert report.hook_result.is_circuit_breaker_tripped is True
        assert "Volatility Circuit Breaker Tripped" in report.halt_reason
        assert report.total_amount_in == 0
        assert report.total_amount_out == 0
        assert report.amount_unconsumed == 10**18
        assert report.is_conservation_verified is True

        # Assert pool state was NOT mutated
        assert pool.sqrt_price_x96 == initial_p
        assert pool.liquidity == initial_liq

    def test_m42_d_circuit_breaker_cooloff_and_reset(self):
        """Verifies circuit breaker cool-off period and recovery."""
        hook = VolatilityCircuitBreakerHook(max_drift_bps=100.0, cool_off_sec=300.0)
        now = 1000.0
        hook.record_price(3000.0, timestamp_sec=now - 10)
        hook.record_price(3040.0, timestamp_sec=now)  # ~133 bps drift -> trips

        res1 = hook.before_swap(
            sender="0x123",
            pool_id="pool1",
            zero_for_one=True,
            amount_specified=1000,
            current_tick=0,
            current_sqrt_price_x96=1000,
            timestamp_sec=now,
        )
        assert res1.is_success is False
        assert hook.is_tripped is True

        # Inside cool-off period (now + 100s)
        res2 = hook.before_swap(
            sender="0x123",
            pool_id="pool1",
            zero_for_one=True,
            amount_specified=1000,
            current_tick=0,
            current_sqrt_price_x96=1000,
            timestamp_sec=now + 100.0,
        )
        assert res2.is_success is False
        assert "Cool-off remaining: 200s" in res2.revert_reason

        # Cool-off expired (now + 301s)
        res3 = hook.before_swap(
            sender="0x123",
            pool_id="pool1",
            zero_for_one=True,
            amount_specified=1000,
            current_tick=0,
            current_sqrt_price_x96=1000,
            timestamp_sec=now + 301.0,
        )
        assert res3.is_success is True
        assert hook.is_tripped is False

        # Manual reset verification
        hook.is_tripped = True
        hook.reset_circuit_breaker()
        assert hook.is_tripped is False

    def test_m42_d_dynamic_fee_hook_scaling(self):
        """Verifies dynamic fee scaling under varying realized volatility."""
        hook = DynamicFeeHook(
            base_fee_pips=500,  # 5 bps
            min_fee_pips=100,  # 1 bps
            max_fee_pips=10_000,  # 100 bps
            volatility_scaling_factor=2.0,
        )

        # 0 bps vol -> base fee 500 pips (5 bps)
        assert hook.compute_dynamic_fee(realized_vol_bps=0.0) == 500

        # 10 bps vol -> 500 + 2.0 * 10 * 100 = 2500 pips (25 bps)
        assert hook.compute_dynamic_fee(realized_vol_bps=10.0) == 2500

        # Extreme vol 100 bps -> 500 + 20_000 = clamped to 10_000 pips (100 bps)
        assert hook.compute_dynamic_fee(realized_vol_bps=100.0) == 10_000

        # Test in swap execution engine
        pool = _setup_test_pool(price=3000.0)
        engine = ConcentratedSwapEngine()

        # Swap with high realized volatility (10 bps vol -> 25 bps fee instead of 5 bps)
        report = engine.execute_swap(
            pool=pool,
            zero_for_one=True,
            amount_specified=10**18,
            hook=hook,
            realized_vol_bps=10.0,
        )

        assert report.is_halted is False
        assert report.hook_result.override_fee_pips == 2500
        # In the swap ledger, the fee rate applied should be 2500 pips (0.25%)
        # For 1 ETH, fee should be approximately 0.0025 ETH = 2.5 * 10^15 wei
        assert report.total_fee_amount > 2_000_000_000_000_000
        assert report.is_conservation_verified is True

    def test_m42_d_hook_sandbox_exception_containment(self):
        """Verifies that an unhandled crash inside a hook is safely intercepted without corrupting pool state."""
        faulty = FaultyHook(crash_in_before=True)
        pool = _setup_test_pool(price=3000.0)
        initial_p = pool.sqrt_price_x96

        engine = ConcentratedSwapEngine()
        report = engine.execute_swap(
            pool=pool,
            zero_for_one=True,
            amount_specified=10**18,
            hook=faulty,
        )

        # Must fail closed safely
        assert report.is_halted is True
        assert "ZeroDivisionError" in report.halt_reason
        assert "Hook failure intercepted by sandbox" in report.halt_reason
        assert report.amount_unconsumed == 10**18
        assert report.total_amount_in == 0
        assert pool.sqrt_price_x96 == initial_p

    def test_m42_d_hook_sandbox_after_swap_isolation(self):
        """Verifies that crashes in after_swap hook do not abort successful swap."""
        faulty = FaultyHook(crash_in_before=False, crash_in_after=True)
        pool = _setup_test_pool(price=3000.0)

        engine = ConcentratedSwapEngine()
        report = engine.execute_swap(
            pool=pool,
            zero_for_one=True,
            amount_specified=10**18,
            hook=faulty,
        )

        # The swap itself succeeded, and after_swap error was intercepted
        assert report.is_halted is False
        assert report.total_amount_in > 0
        assert report.is_conservation_verified is True
        assert report.hook_result is not None
        assert "After-swap hook failure intercepted" in report.hook_result.revert_reason

    def test_m42_d_after_swap_price_recording(self):
        """Verifies that after_swap hook records new pool price accurately."""
        hook = VolatilityCircuitBreakerHook()
        pool = _setup_test_pool(price=3000.0)
        now = 2000.0

        engine = ConcentratedSwapEngine()
        _report = engine.execute_swap(
            pool=pool,
            zero_for_one=True,
            amount_specified=10**18,
            hook=hook,
            timestamp_sec=now,
        )

        assert len(hook.observations) == 1
        obs_time, obs_price = hook.observations[0]
        assert obs_time == now
        # Price should be slightly lower than 3000 due to selling token0
        assert 2950.0 < obs_price < 3000.0
