#!/usr/bin/env python3
"""
SKY / CBT — Python 3.13 Verification Environment Setup & Reproducibility Harness

Ensures that the verification environment strictly adheres to the project CI specification
(Python 3.13 as defined in .github/workflows/ci.yml:46) and eliminates CPython 3.13/3.14 ABI mismatch.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_VENV = PROJECT_ROOT / ".venv-m18-verify"
LOCAL_PYTHON313 = PROJECT_ROOT / ".python313" / "bin" / "python3"


def find_python313() -> Path | None:
    """Locates a Python 3.13 executable across standard system and uv toolchains."""
    # 1. Local workspace distribution
    if LOCAL_PYTHON313.exists() and os.access(LOCAL_PYTHON313, os.X_OK):
        return LOCAL_PYTHON313

    # 2. System PATH python3.13
    which_py = shutil.which("python3.13")
    if which_py:
        return Path(which_py)

    # 3. uv-managed toolchains
    uv_path = Path.home() / ".local" / "share" / "uv" / "python"
    if uv_path.exists():
        candidates = sorted(uv_path.glob("cpython-3.13*/bin/python3"), reverse=True)
        if candidates and os.access(candidates[0], os.X_OK):
            return candidates[0]

    # 4. Check current interpreter
    if sys.version_info[:2] == (3, 13):
        return Path(sys.executable)

    return None


def run_cmd(cmd: list[str], check: bool = True, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess:
    """Executes a command and echoes output."""
    print(f"[*] Executing: {' '.join(str(c) for c in cmd)}")
    res = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and res.returncode != 0:
        print(f"[!] Error (exit {res.returncode}):\n{res.stdout}\n{res.stderr}", file=sys.stderr)
        sys.exit(res.returncode)
    return res


def main() -> int:
    print("=" * 65)
    print("SKY / CBT — PYTHON 3.13 VERIFICATION ENVIRONMENT SETUP")
    print("=" * 65)

    py313 = find_python313()
    if not py313:
        print(
            "[ERROR] Python 3.13 executable not found.\n"
            "CI and Milestone 18 certification require Python 3.13 ABI.\n"
            "Install Python 3.13 or run: uv python install 3.13",
            file=sys.stderr,
        )
        return 1

    print(f"[+] Found Python 3.13 executable: {py313}")
    v_out = subprocess.check_output([str(py313), "--version"], text=True).strip()
    print(f"[+] Version: {v_out}")

    # Create target virtualenv if missing
    venv_py = TARGET_VENV / "bin" / "python"
    if not venv_py.exists():
        print(f"[+] Creating isolated verification environment at: {TARGET_VENV}")
        run_cmd([str(py313), "-m", "venv", str(TARGET_VENV)])
    else:
        print(f"[+] Existing verification environment found at: {TARGET_VENV}")

    # Validate ABI compatibility
    print("[*] Validating CPython 3.13 ABI compatibility & pydantic_core import...")
    check_code = (
        "import sys; "
        "assert sys.version_info[:2] == (3, 13), f'Expected 3.13, got {sys.version}'; "
        "from pydantic_core._pydantic_core import ArgsKwargs; "
        "import cryptography; "
        "print('>>> ABI Integrity Validated: pydantic_core & cryptography successfully imported.')"
    )
    res = subprocess.run([str(venv_py), "-c", check_code], text=True, capture_output=True)
    if res.returncode != 0:
        print("[!] Dependencies missing or ABI mismatch in .venv-m18-verify. Synchronizing packages...")
        # Populate site-packages from existing .venv or install requirements
        orig_site = PROJECT_ROOT / ".venv" / "lib" / "python3.13" / "site-packages"
        target_site = TARGET_VENV / "lib" / "python3.13" / "site-packages"
        if orig_site.exists() and target_site.exists():
            print(f"[+] Copying certified site-packages from {orig_site} to {target_site}...")
            shutil.copytree(orig_site, target_site, dirs_exist_ok=True)

        res2 = subprocess.run([str(venv_py), "-c", check_code], text=True, capture_output=True)
        if res2.returncode != 0:
            print(f"[!] Verification failed:\n{res2.stderr}", file=sys.stderr)
            return 1

    print(res.stdout.strip() if res.stdout else ">>> Verification Environment Ready.")
    print("=" * 65)
    print("Environment setup COMPLETE.")
    print(f"To run M18 Certification: {venv_py} scripts/verify_m18_certification.py")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
