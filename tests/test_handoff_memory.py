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


def test_infrastructure_layers_doc_exists_and_forbids_vendoring():
    doc = ROOT / "docs" / "INFRASTRUCTURE_LAYERS.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8").lower()
    assert "not" in text and "dependenc" in text
    assert "dify" in text and "librechat" in text and "openhands" in text
    assert "graduation" in text
