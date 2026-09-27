"""
tests/execution/test_milestone44_r_evidence_hardening.py
=========================================================
Milestone 44-R Adversarial Evidence Hardening Suite:
Liquidity Surface Geometry & High-Frequency Toxic Flow Analytics.

Verifies the 8 institutional proof obligations:
- OBL-1: Continuous Order Book Surface Reconstruction & Geometry Invariants
- OBL-2: Non-Linear Market Impact Curvature (Kyle's Lambda & Square-Root Law)
- OBL-3: Volume-Synchronized Probability of Toxicity (VPIN) Mathematical Precision
- OBL-4: Hawkes Self-Excitation Intensity & Flow Clustering Dynamics
- OBL-5: Constitutional Half-Kelly & 1.5% Single-Path Equity Cap
- OBL-6: Microstructure Toxicity Circuit Breaker (VPIN >= 0.85 Immediate Halt)
- OBL-7: Dynamic Urgency Adaptation & Dark Pool Liquidity Allocation
- OBL-8: Permanent Capital Firewall & Milestone 18 Certified Surface Area Isolation
"""

from __future__ import annotations

import pytest

from scripts.research.run_m44_r_qualification import evaluate_m44_r_obligations


def test_m44_r_all_8_proof_obligations():
    """Execute the full Milestone 44-R qualification suite and assert 8/8 PASS."""
    results = evaluate_m44_r_obligations()

    assert len(results) == 8, f"Expected 8 obligations, got {len(results)}"

    failed_obligations = []
    for obl_id, obl in results.items():
        if not obl["passed"]:
            failed_obligations.append((obl_id, obl["title"], obl["details"]))

    assert not failed_obligations, f"M44-R Obligations failed: {failed_obligations}"
