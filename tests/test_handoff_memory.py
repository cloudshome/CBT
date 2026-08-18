"""Handoff-memory contract.

Arena sessions die. GitHub + SESSION_STATE.md + TODO.md are the
persistent memory. These tests fail if a session ships without the
files a *next* session is told to read first.
"""
from __future__ import annotations

import re
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
    assert "freqtrade" in text, (
        "Freqtrade was reviewed and rejected — the layers doc must "
        "keep saying so or a future session re-adopts the bot"
    )


def test_freqtrade_review_exists_and_records_f_decisions():
    """F1–F8 must survive session death. Do not install the bot."""
    doc = ROOT / "docs" / "FREQTRADE_REVIEW.md"
    assert doc.exists(), "docs/FREQTRADE_REVIEW.md missing — see F1–F8"
    text = doc.read_text(encoding="utf-8")
    lower = text.lower()
    for needle in ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"):
        assert needle in text, f"Freqtrade review must keep decision {needle}"
    assert "freqtrade" in lower
    assert "hyperopt" in lower
    assert "freqai" in lower
    # the binding refusals
    assert "do not add" in lower or "rejected" in lower or "no." in lower
    assert "p12" in lower, "the kept ideas must stay named as P12"


def test_todo_forbids_freqtrade_and_names_p12():
    text = (ROOT / "TODO.md").read_text(encoding="utf-8")
    assert "TODO-13" in text, "P12 must be a real TODO, not a comment"
    assert "FREQTRADE_REVIEW.md" in text
    lower = text.lower()
    assert "freqtrade" in lower
    assert "hyperopt" in lower
    # out-of-scope list must name the bot so it is not re-added
    scope = text.split("Explicitly out of scope", 1)[-1]
    assert "freqtrade" in scope.lower()


def test_architecture_invariant_thirteen_rejects_trading_bots():
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8").lower()
    assert "invariant" in text
    assert "freqtrade" in text
    assert "not a trading bot" in text or "sky is not a trading bot" in text


def test_data_roadmap_rejects_freqtrade_as_backtester():
    text = (ROOT / "docs" / "DATA_INFRASTRUCTURE_ROADMAP.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "freqtrade" in text
    assert "p10.11" in text


def test_backtrader_review_exists_and_records_bt_decisions():
    """BT1–BT8 must survive session death. Do not install a second grader."""
    doc = ROOT / "docs" / "BACKTRADER_REVIEW.md"
    assert doc.exists(), "docs/BACKTRADER_REVIEW.md missing — see BT1–BT8"
    text = doc.read_text(encoding="utf-8")
    lower = text.lower()
    for needle in ("BT1", "BT2", "BT3", "BT4", "BT5", "BT6", "BT7", "BT8"):
        assert needle in text, f"Backtrader review must keep decision {needle}"
    assert "backtrader" in lower
    assert "cerebro" in lower, "the proposed object model must stay named"
    assert "no." in lower or "rejected" in lower
    assert "p12" in lower, "the kept ideas must stay named as P12"


def test_todo_forbids_backtrader_and_names_p12():
    text = (ROOT / "TODO.md").read_text(encoding="utf-8")
    assert "BACKTRADER_REVIEW.md" in text
    lower = text.lower()
    assert "backtrader" in lower
    # out-of-scope list must name it so it is not re-added
    scope = text.split("Explicitly out of scope", 1)[-1]
    assert "backtrader" in scope.lower()


def test_architecture_and_layers_reject_backtrader():
    arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8").lower()
    assert "backtrader" in arch
    layers = (ROOT / "docs" / "INFRASTRUCTURE_LAYERS.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "backtrader" in layers


def test_p12_roadmap_mentions_both_reviews():
    """P12 is defined by the Freqtrade review AND extended by the
    Backtrader review — the roadmap must keep naming both."""
    anatomy = (ROOT / "AI_ANATOMY_ROADMAP.md").read_text(encoding="utf-8")
    assert "FREQTRADE_REVIEW.md" in anatomy
    assert "BACKTRADER_REVIEW.md" in anatomy


def test_needle_review_keeps_router_outside_the_authority_boundary():
    """N1–N8 preserve Needle as a conditional client, never a trader."""
    doc = ROOT / "docs" / "NEEDLE_REVIEW.md"
    assert doc.exists(), "Needle decision record missing — see N1–N8"
    text = doc.read_text(encoding="utf-8")
    lower = text.lower()
    for decision in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8"):
        assert decision in text, f"Needle review must keep decision {decision}"
    assert "external" in lower and "read-only mcp client" in lower
    assert "confidence" in lower and "not authorization" in lower
    assert "no path: needle → approval → exchange" in lower


def test_todo_and_architecture_park_needle_without_installing_it():
    todo = (ROOT / "TODO.md").read_text(encoding="utf-8").lower()
    arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8").lower()
    layers = (ROOT / "docs" / "INFRASTRUCTURE_LAYERS.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "needle_review.md" in todo and "parked" in todo
    assert "cactus-needle" in todo and "do not install" in todo
    assert "needle_review.md" in arch and "tool router is a client" in arch
    assert "needle 2" in layers and "external read-only mcp client" in layers


def test_canonical_roadmap_merges_history_and_production_distribution():
    doc = ROOT / "ROADMAP.md"
    assert doc.exists(), "ROADMAP.md must remain the active merged roadmap"
    text = doc.read_text(encoding="utf-8")
    lower = text.lower()
    for phase in ("P1–P6", "P7–P9", "P10", "P11", "P12", "P17", "P18", "P19", "P20", "P21", "P22"):
        assert phase in text, f"merged roadmap missing {phase}"
    assert "ubuntu sky hub" in lower
    assert "windows companion" in lower and "android companion" in lower
    assert "one database" in lower or "one db" in lower
    assert "do not exist yet" in lower, "roadmap must not claim installers exist"
    assert "authentication and authorization" in lower
    assert "no live order execution" in lower


def test_old_roadmaps_defer_to_the_canonical_roadmap():
    for name in (
        "AI_ANATOMY_ROADMAP.md",
        "ROADMAP_AGENT_REACH_UPGRADE.md",
        "WEB_TRADER_ROADMAP.md",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "ROADMAP.md" in text, f"{name} must point to canonical roadmap"


def test_product_surfaces_state_installers_are_planned_not_shipped():
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8").lower()
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
    todo = (ROOT / "TODO.md").read_text(encoding="utf-8").lower()
    for text in (roadmap, readme, skill, todo):
        assert "windows" in text and ".exe" in text
        assert "android" in text and ".apk" in text
        assert "ubuntu" in text
    assert "not released yet" in readme
    assert "do not exist yet" in skill
    # The load-bearing invariant is the *ordering*: the next code is the current
    # phase after P18, never an installer wrapper around it. Pinning one exact
    # sub-phase number made this fail every time a phase shipped, which trains
    # the next session to edit the test instead of reading it — so pin the rule.
    # After P18.4 the next implementation is P19 (Ubuntu Hub), so allow both.
    assert re.search(r"next implementation is p(18\.\d|19|20)", todo), (
        "TODO.md must name the next production phase (P18.x / P19 / P20)")
    assert "not an installer wrapper" in todo


def test_product_decisions_keep_one_authority_and_server_side_gate():
    decisions = (ROOT / "PROFESSIONAL_PLAN_DECISIONS.md").read_text(
        encoding="utf-8"
    ).lower()
    blueprint = (ROOT / "BLUEPRINT.md").read_text(encoding="utf-8").lower()
    assert all(f"pd{i}" in decisions for i in range(1, 9))
    assert "companion clients" in decisions
    assert "distribution never grants live execution" in decisions
    assert "one user never has three databases" in blueprint
    assert "no remote client can bypass" in blueprint
