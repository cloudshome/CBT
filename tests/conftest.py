"""
Pytest Test Configuration & Database Isolation Harness.
Guarantees that test executions NEVER mutate, delete, or connect to the
live production SQLite databases in data/ (trading_logs.db, market_data.db, etc.).
"""

import os
import tempfile
from pathlib import Path

import pytest

from core.cooldown_governor import cooldown_governor


@pytest.fixture(autouse=True)
def _reset_cooldown_governor():
    cooldown_governor.reset()
    old_asset = cooldown_governor.asset_cooldown_sec
    old_loss = cooldown_governor.loss_global_cooldown_sec
    cooldown_governor.asset_cooldown_sec = 0.0
    cooldown_governor.loss_global_cooldown_sec = 0.0
    yield
    cooldown_governor.asset_cooldown_sec = old_asset
    cooldown_governor.loss_global_cooldown_sec = old_loss
    cooldown_governor.reset()

# 1. Create isolated temporary directory for test databases
_TEST_TEMP_DIR = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
_temp_path = Path(_TEST_TEMP_DIR.name)

# 2. Redirect all database environment variables BEFORE any modules import core.database
os.environ["DATA_DIR"] = str(_temp_path)
os.environ["TRADING_LOGS_DB_PATH"] = str(_temp_path / "trading_logs_test.db")
os.environ["MARKET_DB_PATH"] = str(_temp_path / "market_data_test.db")
os.environ["BRAIN_DB_PATH"] = str(_temp_path / "brain_memory_test.db")
os.environ["EXPERIMENT_DB_PATH"] = str(_temp_path / "experiment_store_test.db")
os.environ["SECURITY_DB_PATH"] = str(_temp_path / "security_test.db")

# 3. Test credentials isolation: configure sandbox mock Telegram identity
os.environ["TELEGRAM_CHAT_ID"] = "12345678"
os.environ["TELEGRAM_TRADER_IDS"] = "12345678"

# 4. Rate limiter and portfolio limit test isolation: raise limits so full test suite is not throttled or locked out
os.environ["RATE_LIMIT_MAX"] = "100000"
os.environ["RATE_LIMIT_AUTH_MAX"] = "100000"
os.environ["MAX_PAPER_OPEN_POSITIONS"] = "1000"


def _init_test_subsystem_schemas() -> None:
    """Initializes base database schemas and all subsystem tables in test sandboxes."""
    try:
        from core.database import db_manager

        db_manager.trading_db_path = Path(os.environ["TRADING_LOGS_DB_PATH"])
        db_manager.market_db_path = Path(os.environ["MARKET_DB_PATH"])
        db_manager.brain_db_path = Path(os.environ["BRAIN_DB_PATH"])
        db_manager.experiment_db_path = Path(os.environ["EXPERIMENT_DB_PATH"])
        db_manager.init_all_schemas()

        # 1. Execution Idempotency & Reconciliation & Kill Switch State
        try:
            from core.execution.idempotency import LiveOrderIdempotencyStore
            from core.execution.kill_switch import live_kill_switch

            LiveOrderIdempotencyStore()._init_table()
            live_kill_switch._ensure_schema()
        except Exception:
            pass

        # 2. Intelligence Store
        try:
            from core.intelligence.schema import IntelligenceStore

            IntelligenceStore().init_schema()
        except Exception:
            pass

        # 3. Web3 Watch-Only Wallets & Security Store
        try:
            from core.auth.security_store import security_store
            from core.web3.wallet_store import web3_wallet_store

            security_store._ensure_schema()
            web3_wallet_store._init_db()
        except Exception:
            pass

        # 4. Autonomous Research Storage & Manifest
        try:
            from core.autonomous_research.storage.research_storage import ResearchStorage

            ResearchStorage().init_schemas()
        except Exception:
            pass

        try:
            from core.autonomous_research.storage.storage_manifest import StorageManifest

            StorageManifest().init_schema()
        except Exception:
            pass

        # 5. Telegram & YouTube Subsystems
        try:
            from core.telegram.jobs import TelegramJobManager

            TelegramJobManager()._ensure_table_exists()
        except Exception:
            pass

        try:
            from core.telegram.callbacks import callback_router

            callback_router._ensure_table_exists()
        except Exception:
            pass

        try:
            from core.telegram.idempotency import idempotency_manager

            idempotency_manager._ensure_table_exists()
        except Exception:
            pass

        try:
            from core.youtube.discovery import youtube_discovery

            youtube_discovery._init_crawl_memory()
        except Exception:
            pass

        try:
            from core.telegram.rbac import rbac_registry

            rbac_registry.reset()
        except Exception:
            pass

        try:
            from core.macro_event_reporter import macro_event_reporter

            macro_event_reporter._ensure_table_exists()
            macro_event_reporter._seed_default_macro_releases()
        except Exception:
            pass
    except Exception:
        pass


_init_test_subsystem_schemas()


@pytest.fixture(scope="session", autouse=True)
def isolate_test_databases():
    """Session-wide fixture ensuring complete test isolation from production data."""
    _init_test_subsystem_schemas()
    yield
    # Cleanup temporary directory after test session
    try:
        import logging

        logging.shutdown()
        _TEST_TEMP_DIR.cleanup()
    except Exception:
        pass


def make_ohlcv(
    n: int = 400,
    seed: int = 7,
    start_ts: int = 1_780_000_000_000,
    interval_ms: int = 900_000,
    trend: float = 0.02,
):
    """Deterministic random-walk OHLCV with an upward drift and engineered sweep."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    close = np.zeros(n)
    close[0] = 60_000.0
    for i in range(1, n):
        shock = rng.normal(trend * close[i - 1] / 100, close[i - 1] * 0.004)
        close[i] = max(500, close[i - 1] + shock)
    high = close * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.002, n)))
    high = np.maximum(high, np.maximum(close, low) * 1.001)
    low = np.minimum(low, np.minimum(close, high) * 0.999)

    try:
        from engine.structure import detect_swings

        base = pd.DataFrame(
            {
                "ts": np.arange(n, dtype=np.int64) * interval_ms + start_ts,
                "high": high,
                "low": low,
                "close": close,
            }
        )
        swings = detect_swings(base)
        last_lows = [s for s in swings if s.kind == "low"]
        if last_lows:
            sl = last_lows[-1]
            open_last = close[-2]
            recovered_close = open_last + sl.price * 0.004
            last_low = sl.price * 0.996
            last_high = max(open_last, recovered_close) * 1.002
            high[-1], low[-1], close[-1] = last_high, last_low, recovered_close
    except Exception:
        pass

    volume = rng.uniform(50, 400, n)
    volume[-1] = volume[-1] * 3
    ts = np.arange(n, dtype=np.int64) * interval_ms + start_ts
    return pd.DataFrame(
        {
            "ts": ts,
            "open": np.round(close, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": np.round(volume, 2),
        }
    )


@pytest.fixture
def df():
    return make_ohlcv()


@pytest.fixture
def df_bearish(seed: int = 3):
    """Decisive downtrend for bearish tests."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    n = 400
    close = np.zeros(n)
    close[0] = 60_000.0
    for i in range(1, n):
        close[i] = max(
            500, close[i - 1] + rng.normal(-0.08 * close[i - 1] / 100, close[i - 1] * 0.003)
        )
    high = close * (1 + np.abs(rng.normal(0, 0.0015, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.0015, n)))
    ts = np.arange(n, dtype=np.int64) * 900_000 + 1_780_000_000_000
    return pd.DataFrame(
        {
            "ts": ts,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(50, 400, n),
        }
    )
