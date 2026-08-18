"""P22.3 trusted-signing + clean-target drill contracts.

This checkout still cannot sign or install. The module only:
- publishes the exact operator checklists
- records *human* evidence JSON from a trusted release host
- refuses to mark a drill passed without every required field
- never claims P22 complete from Linux CI or empty files
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import VERSION
from ops.release import signing_readiness

SCHEMA_VERSION = 1
FORBIDDEN_CLAIM_WORDS = (
    "this sandbox signed",
    "ci signed",
    "linux ci installed windows",
    "linux ci installed android",
)

DRILLS: dict[str, dict[str, Any]] = {
    "debian-repo-sign": {
        "platform": "ubuntu",
        "kind": "signing",
        "title": "Sign Debian repository metadata",
        "required": (
            "operator", "host", "key_id_last4", "inrelease_sha256",
            "release_gpg_sha256", "deb_sha256", "verified_on_clean_vm",
        ),
        "steps": (
            "On an isolated Ubuntu signer, import the SKY Debian key (never commit it).",
            "Build the unsigned .deb from the annotated tag; verify SHA-256.",
            "Generate apt repo metadata; produce InRelease and Release.gpg.",
            "Confirm the private key never appears in the .deb, logs, or Git.",
            "On a clean VM, apt-get update against the signed repo and install.",
            "Record key id last-4, checksums, and the clean-VM hostname.",
        ),
    },
    "windows-authenticode": {
        "platform": "windows",
        "kind": "signing",
        "title": "Authenticode-sign Windows companion",
        "required": (
            "operator", "host", "publisher", "timestamp_ok",
            "signed_sha256", "signtool_verify", "clean_windows11",
        ),
        "steps": (
            "Compile packaging/windows/SkyCompanion on a Windows 11 host.",
            "Sign MSIX/EXE with the release certificate (env names only in CI).",
            "signtool verify /pa and confirm a trusted timestamp.",
            "Recompute SHA-256 after signing (bytes change).",
            "Install on a second, clean Windows 11 machine and inspect publisher.",
        ),
    },
    "android-apksigner": {
        "platform": "android",
        "kind": "signing",
        "title": "apksigner-verify Android companion",
        "required": (
            "operator", "host", "keystore_alias", "apk_sha256",
            "apksigner_verify", "device_model", "play_protect_ok",
        ),
        "steps": (
            "Assemble packaging/android/SkyCompanion on a trusted Linux/macOS host.",
            "Sign the APK/AAB with the release keystore (never commit the store).",
            "apksigner verify --verbose --print-certs; record cert SHA-256.",
            "Install on a supported physical device; refuse cleartext Hub URLs.",
            "Confirm Play Protect / unknown-source policy is understood by the owner.",
        ),
    },
    "ubuntu-clean-vm": {
        "platform": "ubuntu",
        "kind": "physical",
        "title": "Clean Ubuntu Hub install / upgrade / restore / rollback",
        "required": (
            "operator", "host", "install_ok", "backup_sha256",
            "upgrade_ok", "restore_ok", "rollback_ok", "doctor_ok",
        ),
        "steps": (
            "Fresh Ubuntu VM: install signed Hub package; bind loopback + TLS proxy.",
            "Create owner; run sky doctor; take SQLite-safe backup; record SHA-256.",
            "Upgrade to the candidate version; doctor still green; data intact.",
            "Restore the pre-upgrade backup to a new path; doctor green.",
            "Rollback to previous stable artifacts; doctor green; no order path.",
        ),
    },
    "windows-clean-target": {
        "platform": "windows",
        "kind": "physical",
        "title": "Clean Windows 11 install / pair / upgrade / rollback",
        "required": (
            "operator", "host", "install_ok", "pair_ok",
            "authorized_paper_ok", "upgrade_ok", "rollback_ok",
            "live_exchange_execution",
        ),
        "steps": (
            "Clean Windows 11: install signed companion; SmartScreen publisher ok.",
            "Pair to Hub over HTTPS with a one-time code; token in Credential Manager.",
            "As operator, submit one authorized paper mutation; it must hit the Hub.",
            "Upgrade in place; pairing survives; Hub still the only brain.",
            "Rollback installer; pairing or re-pair works; live_exchange_execution=false.",
        ),
    },
    "android-clean-target": {
        "platform": "android",
        "kind": "physical",
        "title": "Clean Android install / biometric / pair / upgrade / rollback",
        "required": (
            "operator", "device_model", "install_ok", "biometric_ok",
            "pair_ok", "online_only_ok", "upgrade_ok", "rollback_ok",
            "live_exchange_execution",
        ),
        "steps": (
            "Supported physical device: install signed APK; refuse cleartext.",
            "Biometric re-check fires before an operator mutation.",
            "Pair over HTTPS; token in Android Keystore.",
            "Airplane mode: mutations stay disabled (never queued).",
            "Upgrade and rollback APKs; deep links still open the Hub record.",
        ),
    },
}


class DrillError(ValueError):
    """Evidence is incomplete or a false completion claim."""


def drill_catalog() -> dict[str, Any]:
    items = []
    for drill_id, spec in DRILLS.items():
        items.append({
            "id": drill_id,
            "platform": spec["platform"],
            "kind": spec["kind"],
            "title": spec["title"],
            "required": list(spec["required"]),
            "steps": list(spec["steps"]),
        })
    return {
        "schema": SCHEMA_VERSION,
        "product": "SKY",
        "version": VERSION,
        "live_exchange_execution": False,
        "p22_complete": False,
        "honest_limit": (
            "This source checkout cannot sign or physically install. "
            "Drills pass only with operator evidence from a trusted host."
        ),
        "signing_readiness": signing_readiness(),
        "drills": items,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "ok", "passed")
    return False


def evaluate_evidence(drill_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    if drill_id not in DRILLS:
        raise DrillError(f"unknown drill {drill_id}")
    spec = DRILLS[drill_id]
    def _present(key: str) -> bool:
        value = evidence.get(key, None)
        if value is False or value == 0:
            return True
        return bool(str(value if value is not None else "").strip())

    missing = [key for key in spec["required"] if not _present(key)]
    notes = str(evidence.get("notes") or evidence.get("claim") or "").lower()
    forbidden = [phrase for phrase in FORBIDDEN_CLAIM_WORDS if phrase in notes]
    if "live_exchange_execution" in spec["required"]:
        flag = evidence.get("live_exchange_execution")
        if flag not in (False, "false", "0", "no"):
            missing.append("live_exchange_execution_must_be_false")
    passed = not missing and not forbidden
    # Boolean install/pair flags must actually be true when present.
    for key in spec["required"]:
        if key.endswith("_ok") and key in evidence and not _truthy(evidence[key]):
            passed = False
            if key not in missing:
                missing.append(f"{key}_not_true")
    return {
        "schema": SCHEMA_VERSION,
        "drill": drill_id,
        "title": spec["title"],
        "platform": spec["platform"],
        "kind": spec["kind"],
        "passed": passed,
        "missing": missing,
        "forbidden_claims": forbidden,
        "live_exchange_execution": False,
        "app_version": VERSION,
        "evaluated_at": int(time.time()),
        "note": (
            "passed — attach this JSON to the release review"
            if passed else
            "not passed — do not mark P22 complete"
        ),
    }


def load_evidence(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DrillError(f"cannot read evidence: {exc}") from exc
    if not isinstance(payload, dict):
        raise DrillError("evidence must be a JSON object")
    return payload


def evaluate_file(drill_id: str, path: Path | str) -> dict[str, Any]:
    return evaluate_evidence(drill_id, load_evidence(path))


def p22_status(evidence_dir: Path | str | None = None) -> dict[str, Any]:
    """Summarise catalog + optional evidence files named <drill_id>.json."""
    catalog = drill_catalog()
    results = []
    root = Path(evidence_dir) if evidence_dir else None
    for item in catalog["drills"]:
        row = {"id": item["id"], "passed": False, "status": "pending"}
        if root is not None:
            candidate = root / f"{item['id']}.json"
            if candidate.is_file():
                verdict = evaluate_file(item["id"], candidate)
                row["passed"] = bool(verdict["passed"])
                row["status"] = "passed" if verdict["passed"] else "failed"
                row["missing"] = verdict["missing"]
        results.append(row)
    complete = bool(results) and all(r["passed"] for r in results)
    catalog["results"] = results
    catalog["p22_complete"] = complete
    return catalog


def format_catalog(payload: dict[str, Any]) -> str:
    lines = [
        f"P22.3 release drills — SKY {payload.get('version')}",
        payload.get("honest_limit", ""),
        f"P22 complete: {'YES' if payload.get('p22_complete') else 'NO'}",
        "",
    ]
    for item in payload.get("drills") or []:
        result = next((r for r in payload.get("results") or [] if r["id"] == item["id"]), None)
        mark = "PASS" if result and result.get("passed") else "OPEN"
        lines.append(f"[{mark}] {item['id']} — {item['title']}")
        for step in item["steps"]:
            lines.append(f"      · {step}")
        lines.append(f"      required: {', '.join(item['required'])}")
    return "\n".join(lines)
