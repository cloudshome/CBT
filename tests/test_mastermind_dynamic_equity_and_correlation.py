"""
tests/test_mastermind_dynamic_equity_and_correlation.py
======================================================
Automated test suite verifying Phase 6 (Dynamic Equity Injection)
and Phase 7 (Empirical Rolling Correlation vs Priors) in Mastermind Arbiter Council.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import MagicMock

# Mock external ML/database dependencies for fast, isolated test execution
for mod in [
    "numpy",
    "pandas",
    "core.database",
    "core.cooldown_governor",
    "core.portfolio_shadow",
    "core.risk_manager",
    "core.sky_intelligence",
    "core.sky_intelligence.types",
    "core.sky_intelligence.orchestrator",
    "core.sky_orchestrator",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import core.mastermind.specialists as spec_mod  # noqa: E402
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil  # noqa: E402
from core.sky_intelligence.types import DecisionAction  # noqa: E402


class TestMastermindDynamicEquityAndCorrelation(unittest.TestCase):
    """Verifies Phase 6 and Phase 7 requirements."""

    def test_dynamic_equity_forwarding(self) -> None:
        """Phase 6: Verifies evaluate_market accepts and forwards dynamic account equity to orchestrator."""
        mock_decision = MagicMock()
        mock_decision.decision = DecisionAction.NO_TRADE
        mock_decision.setup_qualified = None
        mock_decision.net_ev_r = 0.0

        spec_mod.sky_orchestrator.analyze_market.return_value = mock_decision

        agent = spec_mod.BtcMacroSpecialist(target_symbol="BTC/USDT")
        candles = [
            {
                "timestamp": 1000,
                "open": 50000,
                "high": 50500,
                "low": 49500,
                "close": 50000,
                "volume": 100,
            }
        ]

        # Call with dynamic equity $45,000
        asyncio.run(
            agent.evaluate_market(
                candles_15m=candles,
                multi_tf_candles={},
                account_equity_usd=45000.0,
            )
        )

        called_kwargs = spec_mod.sky_orchestrator.analyze_market.call_args.kwargs
        self.assertEqual(called_kwargs.get("account_equity_usd"), 45000.0)

    def test_empirical_correlation_computation(self) -> None:
        """Phase 7: Verifies calculate_pairwise_correlation calculates empirical rolling Pearson correlation."""
        council = MastermindArbiterCouncil.__new__(MastermindArbiterCouncil)

        # 1. Identity correlation for same asset
        self.assertEqual(council.calculate_pairwise_correlation("BTC/USDT", "BTC/USDT"), 1.0)

        # 2. Perfect positive correlation synthetic aligned candles
        candles_a = []
        candles_b = []
        for i in range(25):
            ts = 1000 + i * 900
            p_a = 100.0 + i * 2.0
            p_b = 50.0 + i * 1.0
            candles_a.append(
                {"timestamp": ts, "open": p_a, "high": p_a, "low": p_a, "close": p_a, "volume": 10}
            )
            candles_b.append(
                {"timestamp": ts, "open": p_b, "high": p_b, "low": p_b, "close": p_b, "volume": 10}
            )

        market_data = {
            "BTC/USDT": {"15m": candles_a},
            "ETH/USDT": {"15m": candles_b},
        }

        corr = council.calculate_pairwise_correlation("BTC/USDT", "ETH/USDT", market_data)
        self.assertAlmostEqual(corr, 1.0, places=2)

        # 3. Fallback when market data is unavailable -> uses empirical prior
        prior_corr = council.calculate_pairwise_correlation("BTC/USDT", "ETH/USDT", None)
        self.assertEqual(prior_corr, 0.85)


if __name__ == "__main__":
    unittest.main()
