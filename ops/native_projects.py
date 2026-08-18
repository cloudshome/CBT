"""P22.2 — native Windows / Android project inventory and static lint.

The previous companions shipped Python *contracts*. This module inventories the
real project trees under ``packaging/windows/SkyCompanion`` and
``packaging/android/SkyCompanion`` and fails closed when:

* required project files are missing
* sources mention exchange-order APIs
* signing material (keystore, PFX, PEM private keys) is committed
* a source claims ``live_exchange_execution`` is true

Linux CI can run this lint without MSBuild or Gradle. It does **not** compile
the projects, sign them, or claim a physical-device drill.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import ROOT, VERSION

WINDOWS_ROOT = ROOT / "packaging" / "windows" / "SkyCompanion"
ANDROID_ROOT = ROOT / "packaging" / "android" / "SkyCompanion"

WINDOWS_REQUIRED = (
    "SkyCompanion.csproj",
    "Program.cs",
    "HubClient.cs",
    "AppConfig.cs",
    "README.md",
)
ANDROID_REQUIRED = (
    "settings.gradle.kts",
    "build.gradle.kts",
    "gradle.properties",
    "app/build.gradle.kts",
    "app/src/main/AndroidManifest.xml",
    "app/src/main/java/app/sky/companion/MainActivity.kt",
    "app/src/main/java/app/sky/companion/HubClient.kt",
    "app/src/main/java/app/sky/companion/KeystoreStore.kt",
    "app/src/main/java/app/sky/companion/BiometricGate.kt",
    "README.md",
)

FORBIDDEN_PATTERNS = (
    (re.compile(r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY"), "private key material"),
    (re.compile(r"/api/v3/order|/fapi/v1/order|signedOrder|placeOrder", re.I),
     "exchange order endpoint"),
    (re.compile(r"live_exchange_execution\s*[:=]\s*true", re.I),
     "live_exchange_execution claimed true"),
    (re.compile(r"SKY_WINDOWS_CERT_PASSWORD|SKY_ANDROID_KEYSTORE_PASSWORD"),
     "signing secret name in source"),
)

SECRET_SUFFIXES = (".jks", ".keystore", ".p12", ".pfx", ".pem", ".snk")

DRILL_STEPS = (
    "clean_install",
    "pair_with_hub",
    "authorized_paper_mutation",
    "offline_is_readonly",
    "uninstall",
    "backup_upgrade_rollback",
    "verify_unsigned_then_signed",
)


def _scan_text(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{path.name}: binary/unreadable (not a source file we lint)"]
    for pattern, label in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            try:
                label_path = path.relative_to(ROOT)
            except ValueError:
                label_path = path.name
            issues.append(f"{label_path}: {label}")
    return issues


def _secret_files(root: Path) -> list[str]:
    found: list[str] = []
    if not root.is_dir():
        return found
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SECRET_SUFFIXES:
            try:
                found.append(str(path.relative_to(ROOT)))
            except ValueError:
                found.append(path.name)
    return found


def inspect_windows(root: Path | None = None) -> dict[str, Any]:
    root = root or WINDOWS_ROOT
    missing = [name for name in WINDOWS_REQUIRED if not (root / name).is_file()]
    issues: list[str] = []
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".cs", ".csproj", ".md", ".json"}:
                issues.extend(_scan_text(path))
    issues.extend(f"secret file committed: {p}" for p in _secret_files(root))
    present = root.is_dir() and not missing and not issues
    return {
        "platform": "windows",
        "root": str(root),
        "present": present,
        "missing": missing,
        "issues": issues,
        "signed": False,
        "compiled_here": False,
        "live_exchange_execution": False,
        "note": "SDK-style WebView2 project; compile on a Windows host. Unsigned.",
    }


def inspect_android(root: Path | None = None) -> dict[str, Any]:
    root = root or ANDROID_ROOT
    missing = [name for name in ANDROID_REQUIRED if not (root / name).is_file()]
    issues: list[str] = []
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {
                    ".kt", ".kts", ".xml", ".md", ".properties", ".gradle"}:
                issues.extend(_scan_text(path))
    issues.extend(f"secret file committed: {p}" for p in _secret_files(root))
    present = root.is_dir() and not missing and not issues
    return {
        "platform": "android",
        "root": str(root),
        "present": present,
        "missing": missing,
        "issues": issues,
        "signed": False,
        "compiled_here": False,
        "live_exchange_execution": False,
        "note": "Gradle/Kotlin project; assemble on an Android SDK host. Unsigned.",
    }


def drill_checklist() -> dict[str, Any]:
    """Physical-target drills remain OPEN until a trusted host records them."""
    return {
        "channel": "beta",
        "claimed_complete": False,
        "live_exchange_execution": False,
        "steps": [
            {"id": step, "status": "pending",
             "evidence": None,
             "note": "Requires a clean physical Windows/Android target."}
            for step in DRILL_STEPS
        ],
        "note": "Do not mark P22 complete from this checklist remaining pending.",
    }


def native_status() -> dict[str, Any]:
    windows = inspect_windows()
    android = inspect_android()
    ok = bool(windows["present"] and android["present"])
    return {
        "ok": ok,
        "version": VERSION,
        "windows": windows,
        "android": android,
        "drills": drill_checklist(),
        "signed": False,
        "live_exchange_execution": False,
        "note": (
            "P22.2 inventories real project trees and static-lints them. "
            "It does not compile, sign, or drill physical devices."
        ),
    }


def format_status(payload: dict[str, Any] | None = None) -> str:
    payload = payload or native_status()
    lines = [
        f"SKY native projects {payload['version']}",
        f"  windows  {'present' if payload['windows']['present'] else 'MISSING'}"
        f"  signed=no  compiled_here=no",
        f"  android  {'present' if payload['android']['present'] else 'MISSING'}"
        f"  signed=no  compiled_here=no",
        f"  drills   pending ({len(payload['drills']['steps'])} steps) — not claimed",
        "  live exchange execution  NO",
        f"  {payload['note']}",
    ]
    for name in ("windows", "android"):
        for issue in payload[name].get("issues") or []:
            lines.append(f"  ! {name}: {issue}")
        for miss in payload[name].get("missing") or []:
            lines.append(f"  ! {name} missing {miss}")
    return "\n".join(lines)


def write_status(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(native_status(), indent=2) + "\n", encoding="utf-8")
    return path
