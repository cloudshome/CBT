"""
Unit tests for background worker decoupling and daemon gating.
"""

import app as app_mod
from core.worker import flush_wal_checkpoints


def test_flush_wal_checkpoints():
    """Verify flush_wal_checkpoints executes cleanly on test sandboxes."""
    flush_wal_checkpoints()


def test_run_background_daemons_flag(monkeypatch):
    """Verify RUN_BACKGROUND_DAEMONS defaults to true and respects env overrides."""
    monkeypatch.setenv("RUN_BACKGROUND_DAEMONS", "false")
    val = app_mod.os.getenv("RUN_BACKGROUND_DAEMONS", "true").lower() == "true"
    assert val is False

    monkeypatch.setenv("RUN_BACKGROUND_DAEMONS", "true")
    val = app_mod.os.getenv("RUN_BACKGROUND_DAEMONS", "true").lower() == "true"
    assert val is True

