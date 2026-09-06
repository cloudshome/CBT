"""
Pytest Test Configuration & Database Isolation Harness.
Guarantees that test executions NEVER mutate, delete, or connect to the
live production SQLite databases in data/ (trading_logs.db, market_data.db, etc.).
"""

import os
import tempfile
from pathlib import Path

import pytest

# 1. Create isolated temporary directory for test databases
_TEST_TEMP_DIR = tempfile.TemporaryDirectory()
_temp_path = Path(_TEST_TEMP_DIR.name)

# 2. Redirect all database environment variables BEFORE any modules import core.database
os.environ["DATA_DIR"] = str(_temp_path)
os.environ["TRADING_LOGS_DB_PATH"] = str(_temp_path / "trading_logs_test.db")
os.environ["MARKET_DB_PATH"] = str(_temp_path / "market_data_test.db")
os.environ["BRAIN_DB_PATH"] = str(_temp_path / "brain_memory_test.db")
os.environ["EXPERIMENT_DB_PATH"] = str(_temp_path / "experiment_store_test.db")

# 3. Test credentials isolation: configure sandbox mock Telegram identity
os.environ["TELEGRAM_CHAT_ID"] = "12345678"
os.environ["TELEGRAM_TRADER_IDS"] = "12345678"

# Force re-init of db_manager paths if already imported
try:
    from core.database import db_manager

    db_manager.trading_db_path = Path(os.environ["TRADING_LOGS_DB_PATH"])
    db_manager.market_db_path = Path(os.environ["MARKET_DB_PATH"])
    db_manager.brain_db_path = Path(os.environ["BRAIN_DB_PATH"])
    db_manager.experiment_db_path = Path(os.environ["EXPERIMENT_DB_PATH"])
    db_manager.init_all_schemas()

    from core.telegram.rbac import rbac_registry

    rbac_registry.reset()
except Exception:  # noqa: BLE001, S110 — best-effort fallback, never raise
    pass


@pytest.fixture(scope="session", autouse=True)
def isolate_test_databases():
    """Session-wide fixture ensuring complete test isolation from production data."""
    yield
    # Cleanup temporary directory after test session
    try:
        _TEST_TEMP_DIR.cleanup()
    except Exception:  # noqa: BLE001, S110 — best-effort fallback, never raise
        pass
