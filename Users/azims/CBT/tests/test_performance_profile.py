"""
Unit tests for the Performance & Memory Profiler tool.
"""

import pytest
from deploy.performance_profile import run_latency_and_memory_profile


def test_performance_profile_execution():
    report = run_latency_and_memory_profile(iterations=25)
    assert report["iterations"] == 25
    assert report["latency_p50_ms"] > 0
    assert report["latency_p95_ms"] > 0
    assert report["is_memory_healthy"] is True
    assert "sla_passed" in report
