"""
tests/execution/test_milestone45_r_evidence_hardening.py
=========================================================
Milestone 45-R Adversarial Evidence Hardening Suite:
Decentralized MEV Mitigation & Fair Sequencing Simulation.

Verifies the 8 institutional proof obligations:
- OBL-1: Sandwich Vulnerability Quantification & Searcher Profitability Hurdle
- OBL-2: Dynamic Slippage Boundary Invariant
- OBL-3: Proposer-Builder Separation (PBS) Auction Ordering Determinism
- OBL-4: Fair Sequencing Batch Clearing & Zero-MEV Proof
- OBL-5: Constitutional Half-Kelly & 1.5% Single-Path Equity Cap
- OBL-6: Mandatory Private Mempool Shielding for Vulnerable Orders
- OBL-7: Fail-Closed Exception Containment & Malformed Input Isolation
- OBL-8: Permanent Capital Firewall & Milestone 18 Certified Surface Area Isolation
"""

from __future__ import annotations

import pytest

from scripts.research.run_m45_r_qualification import evaluate_m45_r_obligations


def test_m45_r_all_8_proof_obligations():
    """Execute the full Milestone 45-R qualification suite and assert 8/8 PASS."""
    results = evaluate_m45_r_obligations()

    assert len(results) == 8, f"Expected 8 obligations, got {len(results)}"

    failed_obligations = []
    for obl_id, obl in results.items():
        if not obl["passed"]:
            failed_obligations.append((obl_id, obl["title"], obl["details"]))

    assert not failed_obligations, f"M45-R Obligations failed: {failed_obligations}"
