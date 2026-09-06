"""
tests/test_autonomous_trader_and_hardening.py
=============================================
Verification suite for:
1. TTLCache LRU capacity bounding and active purge_expired sweep.
2. SemanticVectorStore SQLite binary BLOB persistence and vectorized search.
3. TelegramJobManager orphaned job reconciliation on startup.
4. APIHealthGuard disk space monitoring circuit breaker.
5. AutonomousTrader autonomous scanning and risk-governed paper execution.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
import pytest
import numpy as np

from core.api_health_guard import api_health_guard
from core.autonomous_trader import autonomous_trader
from core.database import db_manager
from core.memory_vault import SemanticVectorStore
from core.portfolio_shadow import portfolio_shadow
from core.telegram.jobs import job_manager
from core.ttl_cache import TTLCache


def test_ttl_cache_lru_bounding():
    """Verifies that TTLCache strictly respects maxsize and evicts oldest keys."""
    cache = TTLCache(default_ttl_sec=10.0, maxsize=50)
    for i in range(100):
        cache.set(f"key_{i}", f"val_{i}")
    
    stats = cache.stats()
    assert stats["active_keys"] == 50
    assert stats["maxsize"] == 50
    # Oldest keys (0..49) must have been evicted
    assert cache.get("key_0") is None
    assert cache.get("key_10") is None
    # Latest keys (50..99) must be present
    assert cache.get("key_99") == "val_99"
    assert cache.get("key_75") == "val_75"


def test_ttl_cache_active_purge():
    """Verifies active purge_expired reclaims expired keys without calling .get()."""
    cache = TTLCache(default_ttl_sec=0.05, maxsize=100)
    for i in range(20):
        cache.set(f"exp_{i}", i, ttl_sec=0.05)
    
    time.sleep(0.08)
    # Without calling get, purge_expired must clean them all
    purged = cache.purge_expired()
    assert purged == 20
    assert cache.stats()["active_keys"] == 0


def test_semantic_vector_store_sqlite_persistence(tmp_path):
    """Verifies SemanticVectorStore stores vectors as compact BLOBs in SQLite and executes matrix queries."""
    store = SemanticVectorStore(tmp_path)
    store.add_document("doc_test_1", "Bullish fair value gap with liquidity sweep on Bitcoin", {"sym": "BTC"})
    store.add_document("doc_test_2", "Bearish order block rejection with negative CVD delta", {"sym": "ETH"})
    
    # Query
    results = store.query("liquidity sweep fair value gap", top_k=2)
    assert len(results) == 2
    assert results[0]["document"] == "Bullish fair value gap with liquidity sweep on Bitcoin"
    assert results[0]["score"] > results[1]["score"]
    
    # Verify in SQLite database
    with db_manager.get_brain_conn() as conn:
        row = conn.execute("SELECT doc_id, text, embedding FROM semantic_vectors WHERE doc_id = 'doc_test_1'").fetchone()
        assert row is not None
        assert row[0] == "doc_test_1"
        assert len(row[2]) == 128 * 4  # 128 float32 bytes = 512 bytes


def test_job_manager_orphaned_reconciliation():
    """Verifies that ungracefully terminated jobs are marked INTERRUPTED upon reconciliation."""
    job = job_manager.create_job("TEST_TASK", "user_123", "chat_456", "Simulated In-Flight Job")
    assert job.status == "RUNNING"
    
    reconciled_count = job_manager.reconcile_orphaned_jobs()
    assert reconciled_count >= 1
    
    updated = job_manager.get_job(job.job_id)
    assert updated is not None
    assert updated.status == "INTERRUPTED"
    assert "Process terminated" in updated.error_message


def test_api_health_guard_disk_check():
    """Verifies that disk capacity check returns structured vitals and safe boolean."""
    vitals = api_health_guard.check_disk_space(min_free_gb=0.1)
    assert "is_safe" in vitals
    assert "free_gb" in vitals
    assert "status" in vitals
    assert vitals["free_gb"] > 0


@pytest.mark.asyncio
async def test_autonomous_trader_scan_and_status():
    """Verifies AutonomousTrader status report and non-crashing market scan."""
    status = autonomous_trader.get_status()
    assert "is_running" in status
    assert "active_symbols" in status
    assert "BTC/USDT" in status["active_symbols"]
    
    # Execute a single market scan
    executed = await autonomous_trader.scan_and_execute()
    assert isinstance(executed, list)
    
    # Verify open positions can be queried
    open_pos = portfolio_shadow.get_open_positions()
    assert isinstance(open_pos, list)


@pytest.mark.asyncio
async def test_autonomous_trader_candle_deduplication():
    """Verifies that AutonomousTrader does not open duplicate trades on the exact same candle bar."""
    from unittest.mock import AsyncMock, patch
    from core.autonomous_trader import AutonomousTrader

    trader = AutonomousTrader(active_symbols=["ETH/USDT"], max_open_positions=5)
    trader._last_traded_candle_ts["ETH/USDT"] = 1788696900000

    with patch("core.data_streamer.data_streamer.fetch_external_ohlcv", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {"timestamp": 1788696900000, "close": 2500.0, "open": 2490.0, "high": 2510.0, "low": 2480.0, "volume": 100.0}
            for _ in range(20)
        ]
        trades = await trader.scan_and_execute()
        assert trades == []  # Guard prevented trade on same candle bar

