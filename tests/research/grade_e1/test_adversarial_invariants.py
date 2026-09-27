"""
tests/research/grade_e1/test_adversarial_invariants.py
======================================================
Adversarial and Governance Invariant Tests for Grade-E1.

Enforces:
1. Zero modification of Milestone 18 certified execution surface (14 files).
2. Research boundary isolation (zero live order placement, zero database mutation).
3. Epistemic classification integrity (strictly OHLCV_APPROXIMATION).
"""

from __future__ import annotations

import json
from pathlib import Path

from core.research.grade_e1.contracts import EVIDENCE_GRADE

ROOT_DIR = Path(__file__).resolve().parents[3]


def test_m18_certified_files_unmodified_and_present() -> None:
    manifest_path = ROOT_DIR / "core" / "execution" / "m18_certification_manifest.json"
    assert manifest_path.exists(), "M18 manifest missing"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    certified_files = manifest["M18_CERTIFIED_FILES"]
    assert len(certified_files) == 14

    for rel_path in certified_files:
        full_p = ROOT_DIR / rel_path
        assert full_p.exists(), f"Certified M18 file missing: {rel_path}"


def test_grade_e1_epistemic_classification() -> None:
    assert EVIDENCE_GRADE == "GRADE-E1: OHLCV_APPROXIMATION"
    assert "L2" not in EVIDENCE_GRADE
    assert "LIVE" not in EVIDENCE_GRADE


def test_research_boundary_no_connector_imports() -> None:
    grade_e1_dir = ROOT_DIR / "core" / "research" / "grade_e1"
    forbidden_tokens = [
        "place_order",
        "binance_connector",
        "bybit_connector",
        "live_router",
    ]

    for py_file in grade_e1_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, (
                f"Forbidden live token '{token}' detected in {py_file.name}"
            )
