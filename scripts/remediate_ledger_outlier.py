"""
scripts/remediate_ledger_outlier.py
===================================
Surgically removes the single anomalous sizing artifact trade (POS_BTC_USDT_1791969537008_ec369fae)
from the paper trading ledger and resets the persisted risk lockout to normal operational status.
"""

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def remediate():
    trading_db = REPO_ROOT / "data" / "trading_logs.db"
    brain_db = REPO_ROOT / "data" / "cbt_brain.db"

    outlier_id = "POS_BTC_USDT_1791969537008_ec369fae"

    # 1. Clean trading logs
    conn_t = sqlite3.connect(trading_db)
    cur_t = conn_t.cursor()
    cur_t.execute("DELETE FROM shadow_positions WHERE position_id = ?", (outlier_id,))
    rows_deleted = cur_t.rowcount
    conn_t.commit()
    conn_t.close()
    print(f"[REMEDIATION] Deleted outlier trade '{outlier_id}': {rows_deleted} row(s) removed.")

    # 2. Reset risk lockout in all database files in data/
    for db_file in (REPO_ROOT / "data").glob("*.db"):
        try:
            conn_b = sqlite3.connect(db_file)
            cur_b = conn_b.cursor()
            cur_b.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='system_parameters'"
            )
            if cur_b.fetchone():
                cur_b.execute(
                    "UPDATE system_parameters SET param_value_json = 'null' WHERE param_key = 'risk_lockout_until_ms'"
                )
                conn_b.commit()
                print(f"[REMEDIATION] Reset 'risk_lockout_until_ms' in {db_file.name}.")
            conn_b.close()
        except Exception as e:
            pass

if __name__ == "__main__":
    remediate()
