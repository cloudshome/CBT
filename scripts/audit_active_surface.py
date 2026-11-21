"""scripts/audit_active_surface.py — Active Production Surface & Governance Auditor.

Milestone 74 Active Production Surface Audit:
1. Validates every file listed in ACTIVE_PRODUCTION and RESEARCH_LAB exists on disk.
2. Verifies REAL_CAPITAL_ENABLED = False and CAPITAL_MODE = "TIER_0_PAPER" across:
   - core/strategies/p2_risk_parity.py
   - core/strategies/p2_shadow_runner.py
   - core/ops/p2_shadow_watchdog.py
   - core/ops/market_radar.py
3. Verifies STATIC_FALSIFIED_RECORDS in failure_memory.py contains all 3 canonical IDs:
   - FALSIFIED_M63
   - FALSIFIED_M67
   - FALSIFIED_M72
4. Exits 0 on full pass, non-zero on any drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANIFEST_PATH = ROOT / "core" / "governance" / "active_surface_manifest.json"


def audit_active_surface() -> int:
    """Executes the complete active production surface audit against manifest and governance invariants."""
    print("=" * 72)
    print("SKY / CBT ACTIVE PRODUCTION SURFACE & GOVERNANCE AUDITOR (M74)")
    print(f"Manifest Path: {MANIFEST_PATH.relative_to(ROOT)}")
    print("=" * 72)

    failures: list[str] = []

    # 1. Load Manifest
    if not MANIFEST_PATH.exists():
        print(f"[FAIL] Manifest missing: {MANIFEST_PATH}")
        return 1

    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        print(f"[FAIL] Failed to parse manifest JSON: {exc}")
        return 1

    tiers = manifest.get("TIERS", {})
    active_prod = tiers.get("ACTIVE_PRODUCTION", {}).get("files", [])
    research_lab = tiers.get("RESEARCH_LAB", {}).get("files", [])
    certified_m18 = tiers.get("CERTIFIED_PROTECTED", {})

    print(f"[*] Manifest Version : {manifest.get('MANIFEST_VERSION', 'UNKNOWN')}")
    print(f"[*] Milestone Target : {manifest.get('MILESTONE', 'UNKNOWN')}")
    print(f"[*] Generated At UTC : {manifest.get('GENERATED_AT_UTC', 'UNKNOWN')}")
    print("-" * 72)

    # 2. Check ACTIVE_PRODUCTION Files
    print(f"[*] Auditing ACTIVE_PRODUCTION Tier ({len(active_prod)} registered files)...")
    missing_active: list[str] = []
    for item in active_prod:
        fpath = ROOT / item["path"]
        if not fpath.exists():
            missing_active.append(item["path"])
            print(f"  ✗ MISSING: {item['path']} ({item.get('role', 'Unknown role')})")
        else:
            print(f"  ✓ {item['path']}")

    if missing_active:
        failures.append(f"Missing {len(missing_active)} ACTIVE_PRODUCTION file(s): {missing_active}")

    # 3. Check RESEARCH_LAB Files
    print("-" * 72)
    print(f"[*] Auditing RESEARCH_LAB Tier ({len(research_lab)} registered files)...")
    missing_research: list[str] = []
    for item in research_lab:
        fpath = ROOT / item["path"]
        if not fpath.exists():
            missing_research.append(item["path"])
            print(f"  ✗ MISSING: {item['path']} [{item.get('verdict', 'Unknown')}]")
        else:
            print(f"  ✓ {item['path']} [{item.get('verdict', 'Unknown')}]")

    if missing_research:
        failures.append(f"Missing {len(missing_research)} RESEARCH_LAB file(s): {missing_research}")

    # 4. Check CERTIFIED_PROTECTED Reference
    print("-" * 72)
    m18_ref = certified_m18.get("manifest_reference")
    print(f"[*] Auditing CERTIFIED_PROTECTED Tier ({m18_ref})...")
    if m18_ref:
        m18_path = ROOT / m18_ref
        if not m18_path.exists():
            failures.append(f"Missing M18 certification manifest reference: {m18_ref}")
            print(f"  ✗ MISSING: {m18_ref}")
        else:
            print(f"  ✓ {m18_ref} exists.")
            # Verify the 14 certified files exist
            m18_files = certified_m18.get("files", [])
            missing_m18 = [f for f in m18_files if not (ROOT / f).exists()]
            if missing_m18:
                failures.append(f"Missing {len(missing_m18)} M18 certified file(s): {missing_m18}")
                for mf in missing_m18:
                    print(f"  ✗ MISSING: {mf}")
            else:
                print(f"  ✓ All {len(m18_files)} M18 certified files exist on disk.")

    # 5. Check Governance Invariants in Active Operational Modules
    print("-" * 72)
    print("[*] Verifying Governance Invariants (REAL_CAPITAL_ENABLED=False & CAPITAL_MODE=TIER_0_PAPER)...")
    try:
        import core.ops.market_radar as mr
        import core.ops.p2_shadow_watchdog as p2_wd
        import core.strategies.p2_risk_parity as p2_rp
        import core.strategies.p2_shadow_runner as p2_sr
        import core.strategies.v2b_challenger_shadow as v2b_cs

        op_modules = [
            ("core.strategies.p2_risk_parity", p2_rp),
            ("core.strategies.p2_shadow_runner", p2_sr),
            ("core.strategies.v2b_challenger_shadow", v2b_cs),
            ("core.ops.p2_shadow_watchdog", p2_wd),
            ("core.ops.market_radar", mr),
        ]

        for mod_name, mod in op_modules:
            rc = getattr(mod, "REAL_CAPITAL_ENABLED", None)
            cm = getattr(mod, "CAPITAL_MODE", None)

            if rc is not False:
                failures.append(f"{mod_name}: REAL_CAPITAL_ENABLED is not False ({rc!r})")
                print(f"  ✗ {mod_name}: REAL_CAPITAL_ENABLED={rc!r} (MUST BE False)")
            else:
                print(f"  ✓ {mod_name}: REAL_CAPITAL_ENABLED=False")

            if cm != "TIER_0_PAPER":
                failures.append(f"{mod_name}: CAPITAL_MODE is not 'TIER_0_PAPER' ({cm!r})")
                print(f"  ✗ {mod_name}: CAPITAL_MODE={cm!r} (MUST BE 'TIER_0_PAPER')")
            else:
                print(f"  ✓ {mod_name}: CAPITAL_MODE='TIER_0_PAPER'")

    except Exception as exc:
        failures.append(f"Failed to import operational modules for governance check: {exc}")
        print(f"  ✗ Import error: {exc}")

    # 6. Check Immutable Falsification Memory Archive Completeness
    print("-" * 72)
    print("[*] Auditing Failure Memory Archive (STATIC_FALSIFIED_RECORDS)...")
    try:
        from core.autonomous_research.failure_memory import STATIC_FALSIFIED_RECORDS

        registered_ids = {r.failure_id for r in STATIC_FALSIFIED_RECORDS}
        required_falsified_ids = {"FALSIFIED_M63", "FALSIFIED_M67", "FALSIFIED_M72"}

        missing_ids = required_falsified_ids - registered_ids
        if missing_ids:
            failures.append(f"Missing canonical falsified ID(s) in STATIC_FALSIFIED_RECORDS: {missing_ids}")
            print(f"  ✗ MISSING FALSIFICATION RECORDS: {missing_ids}")
        else:
            for fid in sorted(required_falsified_ids):
                rec = next(r for r in STATIC_FALSIFIED_RECORDS if r.failure_id == fid)
                print(f"  ✓ {fid}: {rec.hypothesis_id} ({rec.metrics.get('status', 'ARCHIVED')})")

    except Exception as exc:
        failures.append(f"Failed to import failure_memory: {exc}")
        print(f"  ✗ Import error: {exc}")

    # 7. Final Verdict
    print("=" * 72)
    if failures:
        print(f"[FAIL] Active Surface Audit failed with {len(failures)} violation(s):")
        for idx, f in enumerate(failures, 1):
            print(f"  {idx}. {f}")
        print("=" * 72)
        return 1

    print("[SUCCESS] ACTIVE SURFACE AUDIT PASSED (0 Drift Detected).")
    print("All production tiers, protected execution surfaces, and governance invariants 100% verified.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(audit_active_surface())
