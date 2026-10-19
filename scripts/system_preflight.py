"""
SKY Quantitative Platform Preflight Verification Script.
Executes deep pre-merge health checks across database integrity, test suites, and model adapters.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure repository root is on sys.path
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure Windows consoles don't crash on UTF-8 test output characters (bullets, ticks, etc.)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_python_executable() -> str:
    """Finds active or local virtualenv python executable on Windows or Linux."""
    if os.name == "nt":
        venv_py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def run_check(name, fn):
    print(f"[*] Running: {name}...", end=" ", flush=True)
    try:
        fn()
        print("[PASS]")
        return True
    # A preflight failure must not prevent the remaining independent gates from running.
    except Exception as e:
        err_msg = (
            str(e)
            .encode(sys.stdout.encoding or "utf-8", errors="replace")
            .decode(sys.stdout.encoding or "utf-8", errors="replace")
        )
        print(f"[FAIL] -> {err_msg}")
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
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run(
        [get_python_executable(), "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert res.returncode == 0, f"Pytest failed:\n{res.stdout}\n{res.stderr}"


def run_npm(*args: str) -> subprocess.CompletedProcess[str]:
    """Run npm reliably on POSIX and Windows without a shell on POSIX.

    Passing an argument list together with ``shell=True`` causes POSIX shells to
    receive only the first item (``npm``), silently dropping commands such as
    ``test`` or ``run build``. Windows npm is commonly a ``.cmd`` shim, so invoke
    it through ``cmd.exe`` there while retaining a fully quoted argument string.
    """
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm executable not found on PATH")

    command: list[str]
    if os.name == "nt":
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        command = [comspec, "/d", "/s", "/c", subprocess.list2cmdline([npm, *args])]
    else:
        command = [npm, *args]

    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )


def check_jest():
    res = run_npm("test")
    assert res.returncode == 0, f"Jest failed:\n{res.stdout}\n{res.stderr}"


def check_frontend_build():
    res = run_npm("--prefix", "frontend", "run", "build")
    assert res.returncode == 0, f"Frontend build failed:\n{res.stdout}\n{res.stderr}"


def check_m18_certification():
    verify_script = PROJECT_ROOT / "scripts" / "verify_m18_certification.py"
    if not verify_script.exists():
        return
    res = subprocess.run(
        [get_python_executable(), str(verify_script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0, f"M18 Certification Check Failed:\n{res.stdout}\n{res.stderr}"


def check_ruff():
    # 1. Ruff lint check on core/ and tests/ matching CI
    res_lint = subprocess.run(
        [get_python_executable(), "-m", "ruff", "check", "core/", "tests/"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res_lint.returncode == 0, (
        f"Ruff lint check failed:\n{res_lint.stdout}\n{res_lint.stderr}"
    )

    # 2. Ruff formatting check on core/ and tests/ matching CI
    res_fmt = subprocess.run(
        [get_python_executable(), "-m", "ruff", "format", "--check", "core/", "tests/"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res_fmt.returncode == 0, (
        f"Ruff formatting check failed:\n{res_fmt.stdout}\n{res_fmt.stderr}"
    )


def check_eslint():
    res = run_npm("run", "lint")
    assert res.returncode == 0, f"ESLint check failed:\n{res.stdout}\n{res.stderr}"


def main():
    print("=" * 60)
    print("SKY / CTB PREFLIGHT SYSTEM VERIFICATION & PRE-MERGE SCORECARD")
    print("=" * 60)

    checks = [
        ("Database Schema Integrity", check_db_integrity),
        ("M18 Certification Integrity", check_m18_certification),
        ("Python Linter & Formatter (Ruff)", check_ruff),
        ("TypeScript Linter (ESLint)", check_eslint),
        ("Pytest Quantitative Test Suite", check_pytest),
        ("Jest Desk & Backend Test Suite", check_jest),
        ("Frontend Vite Production Build", check_frontend_build),
    ]

    all_passed = True
    for name, fn in checks:
        if not run_check(name, fn):
            all_passed = False

    print("=" * 60)
    if all_passed:
        print(f">>> ALL {len(checks)} PREFLIGHT QUALITY GATES PASSED (100% GREEN) <<<")
        print(">>> BRANCH READY FOR MAIN PULL REQUEST MERGE <<<")
        sys.exit(0)
    else:
        print(">>> PREFLIGHT CHECKS FAILED <<<")
        sys.exit(1)


if __name__ == "__main__":
    main()
