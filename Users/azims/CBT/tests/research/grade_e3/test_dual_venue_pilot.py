"""
tests/research/grade_e3/test_dual_venue_pilot.py
================================================
Unit tests for Grade-E3 Dual-Venue Pilot Feasibility Auditor.
"""

from __future__ import annotations

from core.research.grade_e3.contracts import VenueFeasibilityStatus
from core.research.grade_e3.dual_venue_pilot import DualVenuePilotAuditor


def test_dual_venue_feasibility_audit() -> None:
    auditor = DualVenuePilotAuditor()
    report = auditor.conduct_feasibility_audit()

    assert report.binance_feasibility == VenueFeasibilityStatus.SUPPORTED
    assert report.bybit_feasibility == VenueFeasibilityStatus.PARTIALLY_SUPPORTED
    assert len(report.dimensions) == 11
    assert "Binance Spot" in report.recommendation

    data = report.to_dict()
    assert data["binance_feasibility"] == "SUPPORTED"
    assert data["bybit_feasibility"] == "PARTIALLY_SUPPORTED"
    assert "empirical_metrics" in data
