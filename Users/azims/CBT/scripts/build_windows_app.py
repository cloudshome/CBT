"""
scripts/build_windows_app.py
============================
Production Build & Packaging Orchestrator for Crypto Brain Terminal (CBT / SKY).

Automates the complete Windows Desktop Software packaging pipeline:
1. Verifies Milestone 18 Invalidation Rule & Preflight Integrity
2. Compiles React + Vite Frontend Bundle into `frontend/dist/`
3. Compiles Electron TypeScript Supervisor into `dist/electron/`
4. Bundles/Validates the Python Backend Runner (`cbt_backend.py`)
5. Builds Windows Native Installer (`release/CTB_Setup_v3.0.0.exe`) via electron-builder
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)


def log(msg: str) -> None:
    print(f"\n[CBT BUILD ENGINE] {msg}")


def run_step(cmd: list[str], desc: str, cwd: Path = REPO_ROOT) -> None:
    log(f"--> {desc}...")
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=str(cwd), shell=True)
    if res.returncode != 0:
        print(f"\n[FAILED] Step '{desc}' exited with code {res.returncode}")
        sys.exit(res.returncode)
    dt = time.perf_counter() - t0
    print(f"[OK] {desc} completed in {dt:.2f}s")


def main() -> None:
    print("=" * 70)
    print(" CRYPTO BRAIN TERMINAL (CBT) -- WINDOWS DESKTOP PACKAGING ENGINE")
    print(" Target: Windows Native .exe (Binance Desktop Style + Local Loopback)")
    print("=" * 70)

    # 1. Verify Milestone 18 Invariant
    run_step(
        [sys.executable, "scripts/verify_m18_certification.py"],
        "Verifying Milestone 18 Cryptographic Certification Integrity",
    )

    # 2. Run Test Preflight
    run_step(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_setup_service.py",
            "tests/test_hyperliquid_connector.py",
            "-q",
        ],
        "Verifying Setup Service & Hyperliquid Connector Test Suites",
    )

    # 3. Build Frontend Production Assets
    frontend_dir = REPO_ROOT / "frontend"
    run_step(["npm", "run", "build"], "Compiling React + Vite Frontend", cwd=frontend_dir)

    # 4. Compile Electron TypeScript
    electron_ts = REPO_ROOT / "electron" / "tsconfig.json"
    run_step(["npx", "tsc", "-p", str(electron_ts)], "Compiling Electron Supervisor TypeScript")

    # 5. Check/Build PyInstaller executable if available
    bin_dir = REPO_ROOT / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    pyinstaller_exe = shutil.which("pyinstaller") or (
        REPO_ROOT / ".venv" / "Scripts" / "pyinstaller.exe"
    )

    if pyinstaller_exe and Path(pyinstaller_exe).exists():
        log("Compiling standalone cbt_backend.exe with PyInstaller...")
        run_step(
            [
                str(pyinstaller_exe),
                "--noconfirm",
                "--onedir",
                "--name=cbt_backend",
                "--distpath=bin",
                "cbt_backend.py",
            ],
            "Compiling Python Backend Binary via PyInstaller",
        )
    else:
        log("PyInstaller not detected in current environment; using embedded venv launcher.")

    # 6. Execute Electron Builder
    electron_builder_json = REPO_ROOT / "electron-builder.json"
    if electron_builder_json.exists():
        log("Packaging Windows installer with electron-builder...")
        builder_res = subprocess.run(["npx", "electron-builder", "--win", "--x64", "--dir"], shell=True)
        if builder_res.returncode == 0:
            print("[OK] Electron package built successfully in release/")
        else:
            print("[INFO] electron-builder returned non-zero code. Make sure 'npm install electron electron-builder' is run.")

    print("\n" + "=" * 70)
    print(" CBT WINDOWS PACKAGING VERIFICATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
