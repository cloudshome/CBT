"""
SKY Quantitative Platform Preflight Verification Script.
Executes deep pre-merge health checks across database integrity, test suites, and model adapters.
"""

import sys
import os
import subprocess
import sqlite3

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def run_check(name, fn):
    print(f"[*] Running: {name}...", end=" ", flush=True)
    try:
        fn()
        print("[PASS]")
        return True
    except Exception as e:
        print(f"[FAIL] -> {e}")
        return False

def check_db_integrity():
    from core.database import db_manager
    db_manager.init_all_schemas()
    conn = db_manager.get_experiment_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    assert "kronos_forecast_ledger" in tables, "kronos_forecast_ledger table missing"
    conn.close()

def check_pytest():
    res = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, f"Pytest failed:\n{res.stdout}\n{res.stderr}"

def check_jest():
    res = subprocess.run(["npm", "test"], capture_output=True, text=True, shell=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, f"Jest failed:\n{res.stdout}\n{res.stderr}"

def check_frontend_build():
    res = subprocess.run(["npm", "--prefix", "frontend", "run", "build"], capture_output=True, text=True, shell=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, f"Frontend build failed:\n{res.stdout}\n{res.stderr}"

def main():
    print("=" * 60)
    print("SKY / CTB PREFLIGHT SYSTEM VERIFICATION & PRE-MERGE SCORECARD")
    print("=" * 60)

    checks = [
        ("Database Schema Integrity", check_db_integrity),
        ("Pytest Quantitative Test Suite (165 tests)", check_pytest),
        ("Jest Desk & Backend Test Suite (98 tests)", check_jest),
        ("Frontend Vite Production Build", check_frontend_build),
    ]

    all_passed = True
    for name, fn in checks:
        if not run_check(name, fn):
            all_passed = False

    print("=" * 60)
    if all_passed:
        print(">>> ALL 4 PREFLIGHT QUALITY GATES PASSED (100% GREEN) <<<")
        print(">>> BRANCH READY FOR MAIN PULL REQUEST MERGE <<<")
        sys.exit(0)
    else:
        print(">>> PREFLIGHT CHECKS FAILED <<<")
        sys.exit(1)

if __name__ == "__main__":
    main()
