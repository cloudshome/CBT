"""Handoff-memory contract.

Arena sessions die. GitHub + SESSION_STATE.md + TODO.md are the
persistent memory. These tests fail if a session ships without the
files a *next* session is told to read first.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_session_state_has_required_headers():
    text = (ROOT / "SESSION_STATE.md").read_text(encoding="utf-8")
    for needle in (
        "Last updated:",
        "Branch:",
        "HEAD commit:",
        "Current phase",
        "Remaining work",
        "Last successful test command",
        "Start-of-session recipe",
        "End-of-session checklist",
    ):
        assert needle in text, f"SESSION_STATE.md missing {needle!r}"


def test_todo_lists_human_and_parked_items():
    text = (ROOT / "TODO.md").read_text(encoding="utf-8")
    assert "TODO-7" in text
    assert "TODO-8" in text
    assert "TODO-9" in text  # Dify — parked
    assert "TODO-10" in text  # LibreChat — parked
    assert "OpenHands" in text or "INFRASTRUCTURE_LAYERS" in text


def test_human_actions_doc_exists():
    doc = ROOT / "docs" / "HUMAN_ACTIONS.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "TODO-7" in text and "TODO-8" in text
    assert "settings/branches" in text


def test_data_infrastructure_roadmap_exists_and_keeps_constraints():
    """P10 is the next major milestone — its plan must survive session death.

    Guards the load-bearing constraints, not the prose: a future session
    must not quietly re-adopt Postgres/Redis/React, forget that the
    engine stays credential-free, or lose the milestone ladder.
    """
    doc = ROOT / "docs" / "DATA_INFRASTRUCTURE_ROADMAP.md"
    assert doc.exists(), "P10 roadmap missing — see TODO-12"
    text = doc.read_text(encoding="utf-8")

    # the phase ladder must stay intact
    for milestone in ("P10.1", "P10.5", "P10.12"):
        assert milestone in text, f"roadmap must keep milestone {milestone}"

    # read-only posture — the invariant that keeps this project safe
    lower = text.lower()
    assert "no api keys" in lower or "no trading credentials" in lower
    assert "demo_mode" in lower, "offline determinism must stay a constraint"

    # the corrections that stop the plan from bloating SKY
    for correction in ("PostgreSQL", "Redis", "React", "FastAPI"):
        assert correction in text, (
            f"roadmap must record why {correction} was rejected — "
            f"otherwise a future session re-adopts it"
        )

    # ordering: prove the edge before building infrastructure
    assert "P11" in text, "roadmap must state that the paper proof comes first"


def test_todo_points_at_the_data_roadmap():
    """TODO.md must route a new session to the P10 plan, not restate it."""
    text = (ROOT / "TODO.md").read_text(encoding="utf-8")
    assert "TODO-12" in text
    assert "DATA_INFRASTRUCTURE_ROADMAP.md" in text


def test_infrastructure_layers_doc_exists_and_forbids_vendoring():
    doc = ROOT / "docs" / "INFRASTRUCTURE_LAYERS.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8").lower()
    assert "not" in text and "dependenc" in text
    assert "dify" in text and "librechat" in text and "openhands" in text
    assert "graduation" in text
