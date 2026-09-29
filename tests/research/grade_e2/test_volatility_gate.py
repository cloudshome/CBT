"""
tests/research/grade_e2/test_volatility_gate.py
==============================================
Unit tests for Grade-E2 Volatility Regime Gate.
"""

from __future__ import annotations

from core.research.grade_e1.contracts import MarketSnapshot
from core.research.grade_e2.contracts import VolatilityRegime
from core.research.grade_e2.volatility_gate import GradeE2VolatilityGate


def test_volatility_gate_detects_volatility_surge() -> None:
    gate = GradeE2VolatilityGate(window_bars=20, percentile_cutoff=85.0)

    # 15 calm baseline bars (vol ~ 10 bps)
    for i in range(15):
        snap = MarketSnapshot(
            timestamp=1000 + (i * 60000),
            bar_index=i,
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.0,
            volume=500.0,
            volatility_bps=10.0,
        )
        gate.update(snap)

    # Explosive bar (vol = 50 bps)
    burst_snap = MarketSnapshot(
        timestamp=20000,
        bar_index=15,
        open=100.0,
        high=105.0,
        low=95.0,
        close=104.0,
        volume=5000.0,
        volatility_bps=50.0,
    )
    safe, vol, regime, reason = gate.is_order_safe(burst_snap)
    assert safe is False
    assert regime in (VolatilityRegime.HIGH_VOLATILITY, VolatilityRegime.EXPLOSIVE)
    assert "VOLATILITY_EXPANSION_REGIME" in (reason or "")
