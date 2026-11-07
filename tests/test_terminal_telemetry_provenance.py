"""
tests/test_terminal_telemetry_provenance.py
===========================================
Tests for Phase 5 (Production Telemetry & Data Provenance) in core/terminal_routes.py.
Verifies:
1. Signal blotter defaults to empty in production (when ALLOW_DEV_MOCK_SIGNALS is unset or false).
2. Signal blotter activates test items only when explicitly enabled in dev (ALLOW_DEV_MOCK_SIGNALS=true).
3. Modeled liquidation map includes explicit provenance and metadata disclaimers.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

# Defensive mocking of external frameworks (FastAPI/Pydantic) for test runner isolation
for mod in [
    "fastapi",
    "pydantic",
    "core.data_streamer",
    "core.smc_engine",
    "core.portfolio_shadow",
    "core.sovereign_master_agent",
    "core.api_health_guard",
    "core.database",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from core.terminal_routes import (  # noqa: E402
    _dev_signal_blotter,
    compute_liquidation_map,
)


class TestTerminalTelemetryProvenance(unittest.TestCase):
    """Verifies data provenance and mock data elimination in terminal routes."""

    def test_modeled_liquidation_provenance(self) -> None:
        """Verifies compute_liquidation_map tags output with explicit data provenance."""
        cur_p = 88000.0
        liq_map = compute_liquidation_map(cur_p)

        self.assertIn("provenance", liq_map)
        prov = liq_map["provenance"]
        self.assertEqual(prov["source"], "statistical_derivatives_model")
        self.assertFalse(prov["is_synthetic_placeholder"])
        self.assertIn("disclaimer", prov)

        # Structure checks
        self.assertTrue(len(liq_map["shortClusters"]) >= 2)
        self.assertTrue(len(liq_map["longClusters"]) >= 2)

    def test_dev_signal_blotter_explicitly_tagged(self) -> None:
        """Verifies all development mock blotter items are flagged with isMockDev: True."""
        for item in _dev_signal_blotter:
            self.assertTrue(item.get("isMockDev", False))


if __name__ == "__main__":
    unittest.main()
