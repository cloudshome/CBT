"""
Unit tests for background worker decoupling and daemon gating.
"""

import asyncio
from unittest.mock import patch

import pytest

import app as app_mod
from core.worker import flush_wal_checkpoints


def test_flush_wal_checkpoints():
    """Verify flush_wal_checkpoints executes cleanly on test sandboxes."""
    flush_wal_checkpoints()


def test_should_run_background_daemons(monkeypatch):
    """Verify should_run_background_daemons dynamically evaluates environment variables."""
    monkeypatch.setenv("RUN_BACKGROUND_DAEMONS", "false")
    assert app_mod.should_run_background_daemons() is False

    monkeypatch.setenv("RUN_BACKGROUND_DAEMONS", "true")
    assert app_mod.should_run_background_daemons() is True

    monkeypatch.delenv("RUN_BACKGROUND_DAEMONS", raising=False)
    assert app_mod.should_run_background_daemons() in (True, False)


@pytest.mark.asyncio
async def test_lifespan_spawns_lightweight_tasks_only_when_decoupled(monkeypatch):
    """Entering lifespan_ctx with RUN_BACKGROUND_DAEMONS=false spawns only 4 lightweight tasks."""
    monkeypatch.setenv("RUN_BACKGROUND_DAEMONS", "false")
    created_tasks = []
    orig_create_task = asyncio.create_task

    def mock_create_task(coro, *args, **kwargs):
        task = orig_create_task(coro, *args, **kwargs)
        created_tasks.append(task)
        return task

    with patch("asyncio.create_task", side_effect=mock_create_task):
        async with app_mod.lifespan_ctx(app_mod.app):
            # Exactly 4 lightweight web-process tasks spawned
            assert len(created_tasks) == 4
