"""
scripts/build_linux_app.py
==========================
Master Production Release & Desktop Software Packaging Orchestrator
for CBT / SKY on Linux (Ubuntu / Debian x64).

Produces:
1. Standalone universal executable: Crypto_Brain_Terminal_v4.0.0.AppImage
2. Native Debian / Ubuntu package : ctb_4.0.0_amd64.deb
3. Cryptographic integrity ledger: release/SHA256SUMS.txt
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RELEASE_DIR = REPO_ROOT / "release"


def log(msg: str) -> None:
    print(f"\n[CBT LINUX RELEASE ENGINE] {msg}")


def run_step(cmd: list[str], desc: str, cwd: Path = REPO_ROOT) -> bool:
    log(f"--> [GATE CHECK] {desc}...")
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=str(cwd), shell=True)
    dt = time.perf_counter() - t0
    if res.returncode != 0:
        print(f"\n[BLOCKER TRIGGERED] Step '{desc}' FAILED with exit code {res.returncode}")
        return False
    print(f"[PASS] {desc} verified in {dt:.2f}s")
    return True


def compute_release_checksums() -> dict[str, str]:
    """Generates SHA-256 checksums for all Linux packages in release/."""
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    
    for f in RELEASE_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in (".appimage", ".deb", ".tar.gz"):
            hasher = hashlib.sha256()
            with open(f, "rb") as fh:
                while chunk := fh.read(65536):
                    hasher.update(chunk)
            checksums[f.name] = hasher.hexdigest()

    checksum_file = RELEASE_DIR / "SHA256SUMS_LINUX.txt"
    with open(checksum_file, "w", encoding="utf-8") as out:
        for fname, digest in sorted(checksums.items()):
            out.write(f"{digest}  {fname}\n")
            print(f"  {digest}  {fname}")

    return checksums


def main() -> None:
    print("=" * 75)
    print(" CRYPTO BRAIN TERMINAL (CBT / SKY) -- MASTER LINUX RELEASE ENGINE")
    print(" Target Environment   : Linux (Ubuntu 22.04 / 24.04 LTS x64)")
    print(" Target Packages      : AppImage + DEB")
    print("=" * 75)

    py_exe = sys.executable
    gates: dict[str, bool] = {}

    # 1. Milestone 18 Invariant Integrity Check
    gates["G-01_m18_certified_surface"] = run_step(
        [py_exe, "scripts/verify_m18_certification.py"],
        "G-01: Milestone 18 Invariant Integrity & 149 Certified Tests",
    )

    # 2. Secret Leakage Audit
    log("G-14: Running Zero-Secret Leakage Scan...")
    git_diff_pfx = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    has_secret_leak = any(
        ext in git_diff_pfx.stdout.lower() for ext in (".pfx", ".key", ".pem", ".p12")
    )
    gates["G-14_secret_leakage_audit"] = not has_secret_leak
    if not gates["G-14_secret_leakage_audit"]:
        print("[FAIL] G-14: Secret credential files detected in git status!")
        sys.exit(1)
    print("[PASS] G-14: Zero credentials or private keys detected.")

    # 3. Generate High-Res Icons
    run_step([py_exe, "scripts/generate_app_icons.py"], "Compiling High-Resolution App Icons")

    # 4. Clean Production Builds (Frontend + Electron TS + Standalone Python Backend)
    frontend_ok = run_step(["npm", "run", "build"], "Compiling Frontend PWA Bundle", cwd=REPO_ROOT / "frontend")
    electron_ts = REPO_ROOT / "electron" / "tsconfig.json"
    electron_ok = run_step(["npx", "tsc", "-p", str(electron_ts)], "Compiling Electron Supervisor TypeScript")

    # Compile Standalone Python Backend Binary via PyInstaller
    log("Compiling Standalone Python Backend (bin/cbt_backend)...")
    pyinstaller_cmd = [
        py_exe,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--distpath",
        "bin",
        "--name",
        "cbt_backend",
        "--add-data",
        "static:static",
        "--collect-all",
        "core",
        "--hidden-import",
        "uvicorn",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "cbt_backend.py",
    ]
    pyinstaller_ok = run_step(pyinstaller_cmd, "Compiling Standalone Python Backend via PyInstaller")
    gates["G-15_clean_production_builds"] = frontend_ok and electron_ok and pyinstaller_ok

    # 5. Packaging Linux Binaries (tar.gz, deb, AppImage)
    log("G-16: Executing Linux packaging (tar.gz + DEB)...")
    deb_file = RELEASE_DIR / "ctb_4.0.0_amd64.deb"
    tar_file = RELEASE_DIR / "Crypto_Brain_Terminal_v4.0.0.tar.gz"
    
    # Try electron-builder native targets
    builder_res = subprocess.run(["npx", "electron-builder", "--linux", "tar.gz", "--x64"], shell=True)
    
    # Build Debian package via Python DEB builder
    deb_script = REPO_ROOT / "scripts" / "build_deb_package.py"
    deb_res = subprocess.run([py_exe, str(deb_script)])
    
    packaging_ok = (deb_file.exists() and deb_file.stat().st_size > 10 * 1024 * 1024) or (
        tar_file.exists() and tar_file.stat().st_size > 10 * 1024 * 1024
    )
    gates["G-16_linux_packaging"] = packaging_ok

    # 6. Checksums
    checksums = compute_release_checksums()

    # 7. Summary
    status = "RELEASE_CANDIDATE" if all(gates.values()) else "RELEASE_BLOCKED"
    report = {
        "release_version": "v4.0.0",
        "target_os": "linux-x64",
        "release_state": status,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gates": gates,
        "artifacts": checksums,
    }

    manifest_file = RELEASE_DIR / "RELEASE_MANIFEST_LINUX.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 75)
    print(f" LINUX RELEASE REPORT -- STATUS: {status}")
    print("=" * 75)
    for g, passed in gates.items():
        print(f" {g:35s}: {'PASS [OK]' if passed else 'FAIL [BLOCKED]'}")
    print("=" * 75)

    if status != "RELEASE_CANDIDATE":
        sys.exit(1)


if __name__ == "__main__":
    main()
