#!/usr/bin/env python3
"""ci/wheel_gate.py — build the wheel, reject duplicates, smoke-test install.

P9 / TODO-3. Agent-Reach has this; SKY did not. Catches duplicate-wheel
bugs and a broken packaged import surface before they ship.

Runnable locally (no GitHub Actions required):

    python ci/wheel_gate.py            # build + duplicate check only
    python ci/wheel_gate.py --install  # also install into a clean venv
                                       # and smoke-test `import cryptobrain`
                                       # + `cryptobrain doctor --json`

The `--install` path needs network (pip will fetch the declared
runtime deps: numpy/pandas/flask/...). The default path is offline
once `build`/`setuptools`/`wheel` are already installed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_duplicate_entries(wheel_path: Path) -> list[str]:
    """Return names that appear more than once inside a wheel zip."""
    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()
    counts = Counter(names)
    return sorted(n for n, c in counts.items() if c > 1)


def build_wheel(out_dir: Path) -> Path:
    """Build a wheel into *out_dir* and return the .whl path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        str(ROOT),
        "-w",
        str(out_dir),
        "--no-deps",
    ]
    subprocess.run(cmd, check=True, cwd=str(ROOT))
    wheels = sorted(out_dir.glob("cryptobrain-*.whl"))
    if not wheels:
        raise SystemExit(f"no cryptobrain-*.whl produced in {out_dir}")
    return wheels[-1]


def smoke_install(wheel_path: Path) -> None:
    """Install the wheel into a fresh venv and run the import + CLI smoke."""
    with tempfile.TemporaryDirectory(prefix="cb-wheel-") as tmp:
        venv = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        pip = venv / ("Scripts" if os.name == "nt" else "bin") / "pip"
        py = venv / ("Scripts" if os.name == "nt" else "bin") / "python"
        cli = venv / ("Scripts" if os.name == "nt" else "bin") / "cryptobrain"
        subprocess.run([str(pip), "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(pip), "install", str(wheel_path)], check=True)
        # 1) import cryptobrain (the P9 definition-of-done contract)
        subprocess.run(
            [
                str(py),
                "-c",
                "import cryptobrain, main, config; "
                "assert cryptobrain.__version__ == config.VERSION; "
                "print('import OK', cryptobrain.__version__)",
            ],
            check=True,
        )
        # 2) CLI smoke — doctor is read-only and never needs a network
        env = dict(os.environ)
        env["DEMO_MODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        subprocess.run(
            [str(cli), "doctor", "--json"],
            check=True,
            env=env,
        )
        print("CLI smoke OK: cryptobrain doctor --json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CryptoBrain wheel-gate")
    ap.add_argument(
        "--install",
        action="store_true",
        help="also install the wheel into a clean venv and smoke-test",
    )
    ap.add_argument(
        "--out", default=None, help="directory to write the wheel (default: a temp dir)"
    )
    args = ap.parse_args(argv)

    tmp = None
    out_dir = Path(args.out) if args.out else None
    if out_dir is None:
        tmp = tempfile.TemporaryDirectory(prefix="cb-wheel-out-")
        out_dir = Path(tmp.name)
    try:
        print(f"building wheel from {ROOT} → {out_dir}")
        wheel = build_wheel(out_dir)
        print(f"built {wheel.name} ({wheel.stat().st_size} bytes)")
        dups = find_duplicate_entries(wheel)
        if dups:
            print("DUPLICATE WHEEL ENTRIES:", file=sys.stderr)
            for name in dups:
                print(f"  {name}", file=sys.stderr)
            return 2
        print("no duplicate entries")
        if args.install:
            smoke_install(wheel)
        print("wheel-gate OK")
        return 0
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
