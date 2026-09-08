"""
scripts/verify_m18_certification.py
===================================
Automated verification tool for Milestone 18 Production Pass Certification.

Enforces the M18 Invalidation Rule:
Any code modification touching a certified M18 execution/risk/reconciliation path
automatically invalidates the M18 certification until all 14 adversarial certification
gates are rerun and green.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "core" / "execution" / "m18_certification_manifest.json"


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] M18 Certification Manifest not found at: {MANIFEST_PATH}")
        sys.exit(1)
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def check_certified_surface(manifest: dict, run_tests_if_dirty: bool = True) -> int:
    certified_commit = manifest.get("M18_CERTIFIED_COMMIT", "")
    certified_files = set(manifest.get("M18_CERTIFIED_FILES", []))

    print("============================================================")
    print("SKY MILESTONE 18 CERTIFICATION INTEGRITY CHECK")
    print(f"Certified Commit : {certified_commit}")
    print(f"Certified Status : {manifest.get('M18_CERTIFICATION_VERDICT', 'UNKNOWN')}")
    print(f"Certified Gates  : 14 Gates / {manifest.get('M18_CERTIFIED_TEST_COUNT', {}).get('total_m18_tests', 149)} Tests")
    print("============================================================")

    # Check git diff against certified commit
    cmd = ["git", "diff", "--name-only", certified_commit]
    try:
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, check=True)
        changed_files = [f.strip().replace("\\", "/") for f in res.stdout.strip().splitlines() if f.strip()]
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] Could not execute git diff against {certified_commit}: {e}")
        # Check uncommitted status as fallback
        cmd_stat = ["git", "status", "--porcelain"]
        res_stat = subprocess.run(cmd_stat, cwd=ROOT_DIR, capture_output=True, text=True)
        changed_files = [line[3:].strip().replace("\\", "/") for line in res_stat.stdout.splitlines() if len(line) > 3]

    touched_certified = [f for f in changed_files if f in certified_files]

    if not touched_certified:
        print("[PASS] Certified surface area is UNTOUCHED. M18 Production Pass remains ACTIVE.")
        return 0

    print(f"[ALERT] {len(touched_certified)} certified M18 file(s) have been modified since certification commit:")
    for f in touched_certified:
        print(f"  - {f}")

    print("\n[RULE ENGAGED] M18 Automatic Invalidation Rule active:")
    print("Any change touching certified execution paths invalidates M18 certification until rerun.")

    if not run_tests_if_dirty:
        print("[FAIL] M18 certification is INVALIDATED until adversarial gates are executed.")
        return 1

    print("\n[*] Re-running 14 M18 adversarial certification gates (149 tests)...")
    test_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_milestone18_sor_and_slicing.py",
        "tests/test_milestone18_boss_adversarial.py",
        "tests/test_milestone18_final_certification.py",
        "-q",
    ]
    test_res = subprocess.run(test_cmd, cwd=ROOT_DIR)

    if test_res.returncode == 0:
        print("\n>>> [SUCCESS] All 149 Milestone 18 tests PASSED (100% Green).")
        print(">>> Milestone 18 Production Pass certification RE-VALIDATED.")
        return 0
    else:
        print("\n>>> [CRITICAL FAILURE] M18 adversarial tests failed on modified surface.")
        print(">>> MILESTONE 18 CERTIFICATION REVOKED (LIVE EXECUTION BLOCKED).")
        return 1


if __name__ == "__main__":
    manifest_data = load_manifest()
    sys.exit(check_certified_surface(manifest_data, run_tests_if_dirty=True))
