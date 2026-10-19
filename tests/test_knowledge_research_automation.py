"""
tests/test_knowledge_research_automation.py
===========================================
Test suite for the Zero-Touch Research Automation Orchestrator.

Covers all 5 pipelines with mocked external dependencies so tests run
hermetically (no real backtests, no real Telegram, no real YouTube crawl).
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.database import db_manager
from core.knowledge_os.research_automation_orchestrator import (
    ResearchAutomationOrchestrator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def init_schemas():
    """Ensure all tables exist before each test."""
    db_manager.init_all_schemas()
    yield


@pytest.fixture()
def orch() -> ResearchAutomationOrchestrator:
    """Fresh orchestrator instance (not the singleton) for isolated testing."""
    return ResearchAutomationOrchestrator()


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Helper: insert a queued hypothesis
# ---------------------------------------------------------------------------


def _insert_queued_hypothesis(title: str = "Test Hypothesis") -> str:
    hyp_id = f"HYP_TEST_{uuid.uuid4().hex[:8].upper()}"
    with db_manager.get_brain_conn() as conn:
        # Ensure table exists (created by knowledge_graph_engine)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hypothesis_queue (
                hypothesis_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                null_hypothesis TEXT,
                alt_hypothesis TEXT,
                independent_variable TEXT,
                dependent_variable TEXT,
                claim_id TEXT,
                target_symbol TEXT,
                test_method TEXT,
                control_variables TEXT,
                validation_status TEXT DEFAULT 'QUEUED',
                created_at INTEGER
            );
        """)
        conn.execute(
            """
            INSERT INTO hypothesis_queue
                (hypothesis_id, title, null_hypothesis, alt_hypothesis,
                 independent_variable, dependent_variable, target_symbol,
                 test_method, validation_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?);
            """,
            (
                hyp_id,
                title,
                "H0: No edge",
                "H1: Positive edge after friction",
                "FVG signal",
                "PnL after friction",
                "BTC/USDT",
                "WALK_FORWARD",
                _now_ms(),
            ),
        )
        conn.commit()
    return hyp_id


# ---------------------------------------------------------------------------
# Test 1: DB tables were created
# ---------------------------------------------------------------------------


def test_automation_tables_exist():
    """research_automation_channels and automation_run_log must exist."""
    with db_manager.get_brain_conn() as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        }
    assert "research_automation_channels" in tables, "research_automation_channels table missing"
    assert "automation_run_log" in tables, "automation_run_log table missing"


# ---------------------------------------------------------------------------
# Test 2: get_status returns all 5 pipelines
# ---------------------------------------------------------------------------


def test_orchestrator_get_status(orch):
    status = orch.get_status()
    expected = {
        "hypothesis_backtest",
        "quiz_reminder",
        "youtube_crawler",
        "knowledge_audit",
        "drive_sync",
        "research_feed_crawler",
    }
    assert set(status.keys()) == expected
    for name, ps in status.items():
        assert ps["name"] == name
        assert ps["is_running"] is False
        assert ps["last_run_status"] == "NEVER_RUN"


# ---------------------------------------------------------------------------
# Test 3: Pipeline 1 — hypothesis_backtest (qualified path → PROMOTED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_hypothesis_backtest_promotes(orch):
    """When empirical_tester returns qualified=True with N≥30, hypothesis is promoted."""
    hyp_id = _insert_queued_hypothesis("FVG Retest Edge Test")

    mock_result = {
        "hypothesis_id": hyp_id,
        "qualified": True,
        "gates_passed": 9,
        "total_gates": 9,
        "status": "QUALIFIED",
        "verdict": "SUPPORTED",
        "primary_failure_reason": None,
        "autopsy": None,
        "metrics": {
            "total_trades": 142,
            "win_rate": 0.63,
            "expectancy_r": 0.42,
            "profit_factor": 2.1,
            "sharpe_ratio": 1.8,
            "max_drawdown_pct": 8.2,
            "net_pnl_usd": 3200.0,
            "conservative_pnl_usd": 2800.0,
            "stress_pnl_usd": 1400.0,
            "is_sharpe": 1.6,
            "oos_sharpe": 1.5,
            "deflated_sharpe_ratio": 0.85,
            "dsr_p_value": 0.008,
            "current_regime": "TREND_EXPANSION",
        },
        "backtest_report": {},
    }

    with patch(
        "core.autonomous_research.empirical_tester.EmpiricalTester.run_empirical_test",
        return_value=mock_result,
    ):
        result = await orch._run_hypothesis_backtest()

    assert result["items_processed"] >= 1
    assert result["promoted"] >= 1

    # Verify status updated in DB
    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT validation_status FROM hypothesis_queue WHERE hypothesis_id = ?;",
            (hyp_id,),
        ).fetchone()
    assert row is not None
    assert row["validation_status"] == "EMPIRICALLY_SUPPORTED"


# ---------------------------------------------------------------------------
# Test 4: Pipeline 1 — hypothesis_backtest (failed path → AUTOPSY)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_hypothesis_backtest_rejects(orch):
    """When empirical_tester returns qualified=False, hypothesis archived to autopsy."""
    hyp_id = _insert_queued_hypothesis("Failed Scalp Setup")

    mock_result = {
        "hypothesis_id": hyp_id,
        "qualified": False,
        "gates_passed": 3,
        "total_gates": 9,
        "status": "FAILED",
        "verdict": "REFUTED",
        "primary_failure_reason": "INSUFFICIENT_SAMPLE_SIZE",
        "autopsy": "Only 12 trades. Minimum 30 required.",
        "metrics": {
            "total_trades": 12,
            "win_rate": 0.40,
            "expectancy_r": -0.1,
            "profit_factor": 0.8,
            "sharpe_ratio": 0.3,
            "max_drawdown_pct": 22.0,
            "net_pnl_usd": -400.0,
            "conservative_pnl_usd": -600.0,
            "stress_pnl_usd": -900.0,
            "is_sharpe": 0.2,
            "oos_sharpe": -0.1,
            "deflated_sharpe_ratio": 0.0,
            "dsr_p_value": 0.78,
            "current_regime": "CHOP_COMPRESSION",
        },
        "backtest_report": {},
    }

    with patch(
        "core.autonomous_research.empirical_tester.EmpiricalTester.run_empirical_test",
        return_value=mock_result,
    ):
        result = await orch._run_hypothesis_backtest()

    assert result["rejected"] >= 1

    # Verify hypothesis marked REJECTED
    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT validation_status FROM hypothesis_queue WHERE hypothesis_id = ?;",
            (hyp_id,),
        ).fetchone()
    assert row["validation_status"] == "REJECTED"

    # Verify autopsy appears in rejected_claims_vault
    with db_manager.get_brain_conn() as conn:
        vault_rows = conn.execute(
            "SELECT * FROM rejected_claims_vault WHERE rejection_autopsy LIKE ?;",
            ("%Minimum 30 required%",),
        ).fetchall()
    assert len(vault_rows) >= 1


# ---------------------------------------------------------------------------
# Test 5: Pipeline 2 — quiz_reminder sends quiz for due concepts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_quiz_reminder_sends_due_quizzes(orch):
    """Quiz reminder fires for concepts with next_review <= now."""
    # Insert a due concept directly into learning graph
    past_review = _now_ms() - 86400000  # 24h ago
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO personal_learning_graph
                (concept_id, concept_title, domain, exposure_count,
                 sources_read, explanations_seen, quiz_attempts,
                 correct_answers, incorrect_answers, confidence,
                 mastery_estimate, misconceptions, prerequisite_concepts,
                 dependent_concepts, last_reviewed, next_review, updated_at)
            VALUES ('SMC_BASICS', 'Smart Money Concepts', 'SMC', 1, 0, 1,
                    0, 0, 0, 0.0, 0.3, '[]', '[]', '[]', ?, ?, ?);
        """,
            (_now_ms() - 172800000, past_review, _now_ms()),
        )
        conn.commit()

    mock_quiz = {
        "quiz_id": "QUIZ_TEST_001",
        "question": "What is the primary purpose of a liquidity sweep?",
        "options": [
            "To trigger retail stop-losses and reverse direction",
            "To increase trading volume",
            "To mark session highs",
            "To confirm trend direction",
        ],
        "correct_option_index": 0,
        "explanation": "Market makers sweep liquidity pools to accumulate positions.",
    }

    orch.quiz_reminders_enabled = True
    with patch(
        "core.knowledge_os.human_brain.HumanLearningEngine.generate_quiz",
        return_value=mock_quiz,
    ):
        with patch.object(orch, "_notify", new_callable=AsyncMock) as mock_notify:
            result = await orch._run_quiz_reminder()

    assert result["items_processed"] >= 1
    assert result["reminders_sent"] >= 1
    mock_notify.assert_called()
    notify_text = mock_notify.call_args[0][0]
    assert "Smart Money Concepts" in notify_text or "liquidity" in notify_text.lower()


@pytest.mark.asyncio
async def test_pipeline_quiz_reminder_disabled_by_default(orch):
    """By default, quiz reminders are disabled per user preference."""
    assert orch.quiz_reminders_enabled is False
    with patch.object(orch, "_notify", new_callable=AsyncMock) as mock_notify:
        result = await orch._run_quiz_reminder()
    assert result["status"] == "DISABLED"
    assert result["reminders_sent"] == 0
    mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: Pipeline 3 — youtube_crawler triggers crawl for due channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_youtube_crawler_crawls_due_channels(orch):
    """YouTube crawler fires for channels whose last_crawled_at is past due."""
    # Insert a channel that is overdue
    ch_id = f"CH_TEST_{uuid.uuid4().hex[:8].upper()}"
    past_crawl = _now_ms() - (100 * 3600 * 1000)  # crawled 100h ago (> 72h interval)
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_automation_channels
                (channel_id, url, label, crawl_interval_hours,
                 max_videos_per_crawl, last_crawled_at, is_active, added_at, updated_at)
            VALUES (?, 'https://www.youtube.com/@TestChannel', 'Test Channel',
                    72, 5, ?, 1, ?, ?);
        """,
            (ch_id, past_crawl, _now_ms(), _now_ms()),
        )
        conn.commit()

    with patch(
        "core.youtube.agent.YouTubeExplorationAgent.start_background_exploration",
        return_value="JOB_TEST_12345",
    ):
        with patch.object(orch, "_notify", new_callable=AsyncMock):
            result = await orch._run_youtube_crawler()

    assert result["channels_crawled"] >= 1
    assert result["videos_queued"] >= 1

    # Verify last_crawled_at was updated
    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT last_crawled_at FROM research_automation_channels WHERE channel_id = ?;",
            (ch_id,),
        ).fetchone()
    assert row["last_crawled_at"] > past_crawl


# ---------------------------------------------------------------------------
# Test 7: Pipeline 4 — knowledge_audit fires Telegram on warnings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_knowledge_audit_notifies_on_warnings(orch):
    """Knowledge audit sends Telegram when checks have WARN or FAIL status."""
    mock_audit_dict = {
        "total_checks": 7,
        "passed_checks": 5,
        "overall_status": "WARN",
        "checks": [
            {"check_name": "Orphan Claims", "status": "PASS", "message": "OK"},
            {
                "check_name": "Zero Alpha Default",
                "status": "WARN",
                "message": "3 claims with confidence > 0",
            },
            {"check_name": "Evidence Vault Anchoring", "status": "PASS", "message": "OK"},
            {"check_name": "Contradiction Resolution Rate", "status": "PASS", "message": "OK"},
            {"check_name": "Graph Edge Integrity", "status": "WARN", "message": "2 stale edges"},
            {"check_name": "Book Ingestion Health", "status": "PASS", "message": "OK"},
            {"check_name": "Autopsy Vault Population", "status": "PASS", "message": "OK"},
        ],
    }
    mock_report = MagicMock()
    mock_report.to_dict.return_value = mock_audit_dict

    from core.knowledge_os import knowledge_audit as _ka_mod

    with patch.object(_ka_mod.knowledge_audit_engine, "run_audit", return_value=mock_report):
        with patch.object(orch, "_notify", new_callable=AsyncMock) as mock_notify:
            result = await orch._run_knowledge_audit()

    assert result["warnings"] == 2
    assert result["failures"] == 0
    assert result["overall_status"] == "WARN"
    mock_notify.assert_called_once()
    msg = mock_notify.call_args[0][0]
    assert "Knowledge Audit" in msg
    assert "WARNINGS" in msg


# ---------------------------------------------------------------------------
# Test 8: Pipeline 5 — drive_sync archives and notifies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_drive_sync_archives(orch):
    """Drive sync uploads brain_memory.db snapshot and sends Telegram confirmation."""
    mock_backend = MagicMock()
    mock_backend.ensure_directory_tree.return_value = {"SKY": "/simulated/SKY"}
    mock_backend.upload_file.return_value = MagicMock(drive_file_id="gdrive_sim_test123")
    mock_backend.check_connectivity.return_value = True

    with patch(
        "core.autonomous_research.storage.drive_backend.get_default_drive_backend",
        return_value=mock_backend,
    ):
        with patch.object(orch, "_notify", new_callable=AsyncMock) as mock_notify:
            result = await orch._run_drive_sync()

    assert result["files_synced"] >= 1
    mock_notify.assert_called_once()
    msg = mock_notify.call_args[0][0]
    assert "Drive Archive Sync" in msg


# ---------------------------------------------------------------------------
# Test 9: trigger_pipeline dispatches correct runner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_pipeline_dispatches_correctly(orch):
    """trigger_pipeline('drive_sync') runs drive_sync and returns result dict."""
    with patch.object(
        orch,
        "_run_drive_sync",
        new_callable=AsyncMock,
        return_value={"items_processed": 1, "files_synced": 1, "errors": 0},
    ) as mock_runner:
        result = await orch.trigger_pipeline("drive_sync")

    mock_runner.assert_called_once()
    assert result["triggered"] == "drive_sync"
    assert result["result"]["files_synced"] == 1


@pytest.mark.asyncio
async def test_trigger_pipeline_unknown_returns_error(orch):
    result = await orch.trigger_pipeline("nonexistent_pipeline")
    assert "error" in result


# ---------------------------------------------------------------------------
# Test 10: automation_run_log persists run record
# ---------------------------------------------------------------------------


def test_run_log_persisted(orch):
    """_log_run stores a record in automation_run_log."""
    run_id = f"RUN_TEST_{uuid.uuid4().hex[:8]}"
    orch._log_run(
        run_id=run_id,
        pipeline="knowledge_audit",
        status="OK",
        result={"items_processed": 7, "promoted": 0, "rejected": 0},
        started_at=_now_ms(),
    )

    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT * FROM automation_run_log WHERE run_id = ?;", (run_id,)
        ).fetchone()

    assert row is not None
    assert row["pipeline"] == "knowledge_audit"
    assert row["status"] == "OK"
    assert row["items_processed"] == 7


# ---------------------------------------------------------------------------
# Test 11: Channels CRUD (add, list, deactivate)
# ---------------------------------------------------------------------------


def test_channel_crud():
    """Channels can be inserted, listed, and soft-deleted in the DB."""
    ch_url = f"https://youtube.com/@TestCRUD_{uuid.uuid4().hex[:6]}"
    ch_id = f"CH_CRUD_{uuid.uuid4().hex[:8].upper()}"
    now_ms = _now_ms()

    with db_manager.get_brain_conn() as conn:
        conn.execute(
            """
            INSERT INTO research_automation_channels
                (channel_id, url, label, crawl_interval_hours,
                 max_videos_per_crawl, is_active, added_at, updated_at)
            VALUES (?, ?, 'CRUD Test', 48, 5, 1, ?, ?);
        """,
            (ch_id, ch_url, now_ms, now_ms),
        )
        conn.commit()

    # List — should appear
    with db_manager.get_brain_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM research_automation_channels WHERE channel_id = ?;", (ch_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["is_active"] == 1

    # Deactivate
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            "UPDATE research_automation_channels SET is_active = 0 WHERE channel_id = ?;", (ch_id,)
        )
        conn.commit()

    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT is_active FROM research_automation_channels WHERE channel_id = ?;", (ch_id,)
        ).fetchone()
    assert row["is_active"] == 0
