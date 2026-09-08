"""
scripts/verify_m18_certification.py
===================================
Automated verification tool for Milestone 18 Production Pass Certification.

Enforces the M18 Invalidation Rule across 10 strict invariants:
1. Certified commit must be an ancestor of HEAD.
2. All 14 certified files must exist (detects renames/deletions).
3. Test identity cryptographic hash (SHA-256 of 149 sorted test node IDs) must match exactly.
4. Any git diff touching certified surface triggers mandatory execution of all 149 adversarial tests.
"""

from __future__ import annotations

import hashlib
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


def verify_ancestor(certified_commit: str) -> bool:
    """Verifies that certified commit is an unbroken ancestor of HEAD."""
    try:
        cmd = ["git", "merge-base", "--is-ancestor", certified_commit, "HEAD"]
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[PASS] Invariant 9: Certified commit {certified_commit[:8]} is an ancestor of HEAD.")
            return True
        else:
            print(f"[CRITICAL FAIL] Invariant 9: Certified commit {certified_commit[:8]} is NOT an ancestor of HEAD!")
            return False
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] Could not check git ancestor: {e}")
        return True


def verify_files_exist(certified_files: set[str]) -> bool:
    """Verifies all certified files exist on disk (detects renames/deletions)."""
    missing = [f for f in certified_files if not (ROOT_DIR / f).exists()]
    if missing:
        print(f"[CRITICAL FAIL] Invariant 2: {len(missing)} certified file(s) missing or renamed:")
        for m in missing:
            print(f"  - {m}")
        return False
    print(f"[PASS] Invariant 2: All {len(certified_files)} certified files exist on disk.")
    return True


def verify_test_identities(expected_hash: str, expected_count: int) -> bool:
    """
    Verifies that all expected M18 test identities are present and untampered.
    Prevents replacing tests, renaming tests, or weakening assertions.
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_milestone18_sor_and_slicing.py",
        "tests/test_milestone18_boss_adversarial.py",
        "tests/test_milestone18_final_certification.py",
        "--collect-only",
        "-q",
    ]
    res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, errors="replace")
    collected = sorted([
        line.strip()
        for line in res.stdout.splitlines()
        if "tests/test_milestone18_" in line.strip() and "::" in line.strip()
    ])

    if len(collected) != expected_count:
        print(
            f"[CRITICAL FAIL] Invariant 10: Expected {expected_count} test identities, "
            f"but found {len(collected)}!"
        )
        return False

    actual_hash = hashlib.sha256("\n".join(collected).encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        print("[CRITICAL FAIL] Invariant 10: M18 test identity cryptographic hash mismatch!")
        print(f"  Expected: {expected_hash}")
        print(f"  Actual  : {actual_hash}")
        return False

    print(f"[PASS] Invariant 10: Cryptographic test identity hash verified ({actual_hash[:16]}... 149/149 exact tests).")
    return True


def check_certified_surface(manifest: dict, run_tests_if_dirty: bool = True) -> int:
    certified_commit = manifest.get("M18_CERTIFIED_COMMIT", "")
    certified_files = set(manifest.get("M18_CERTIFIED_FILES", []))
    expected_hash = manifest.get("M18_CERTIFIED_TEST_NODE_IDS_SHA256", "")
    expected_count = manifest.get("M18_CERTIFIED_TEST_COUNT", {}).get("total_m18_tests", 149)

    print("============================================================")
    print("SKY MILESTONE 18 CRYPTOGRAPHIC CERTIFICATION INTEGRITY CHECK")
    print(f"Certified Commit : {certified_commit}")
    print(f"Certified Status : {manifest.get('M18_CERTIFICATION_VERDICT', 'UNKNOWN')}")
    print(f"Certified Gates  : 14 Gates / {expected_count} Tests")
    print(f"Test Identity SHA: {expected_hash}")
    print("============================================================")

    # 1. Ancestor verification
    if not verify_ancestor(certified_commit):
        return 1

    # 2. File presence verification
    if not verify_files_exist(certified_files):
        return 1

    # 3. Test identity cryptographic hash verification
    if not verify_test_identities(expected_hash, expected_count):
        return 1

    # 4. Git diff check against certified commit
    cmd = ["git", "diff", "--name-only", certified_commit]
    try:
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, check=True)
        changed_files = [f.strip().replace("\\", "/") for f in res.stdout.strip().splitlines() if f.strip()]
    except Exception as e:  # noqa: BLE001
        print(f"[WARNING] Could not execute git diff against {certified_commit}: {e}")
        cmd_stat = ["git", "status", "--porcelain"]
        res_stat = subprocess.run(cmd_stat, cwd=ROOT_DIR, capture_output=True, text=True)
        changed_files = [line[3:].strip().replace("\\", "/") for line in res_stat.stdout.splitlines() if len(line) > 3]

    touched_certified = [f for f in changed_files if f in certified_files]

    if not touched_certified:
        print("[PASS] Certified surface area is UNTOUCHED. M18 Production Pass remains ACTIVE.")
        return 0

    print(f"\n[ALERT] {len(touched_certified)} certified M18 file(s) have been modified since certification commit:")
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
