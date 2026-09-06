"""Tests for the P9 wheel-gate (TODO-3).

The full `python ci/wheel_gate.py --install` path builds a wheel and
installs it into a clean venv — that is the CI job. These unit tests
cover the pieces that must stay true even when we are not building:

  * pyproject.toml exists and names the package
  * `import cryptobrain` works from the source tree
  * duplicate-entry detection flags a bad zip and passes a clean one
  * `main.main([...])` accepts an argv list (the smoke-test contract)
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_toml_exists_and_names_cryptobrain():
    pyproject = ROOT / "pyproject.toml"
    assert pyproject.exists(), "pyproject.toml is required for the wheel-gate"
    text = pyproject.read_text(encoding="utf-8")
    assert 'name = "cryptobrain"' in text
    assert 'cryptobrain = "main:main"' in text
    assert "requires-python" in text


def test_cryptobrain_package_imports():
    import cryptobrain
    from config import VERSION

    assert cryptobrain.__version__ == VERSION
    assert VERSION  # non-empty


def test_find_duplicate_entries_flags_bad_zip(tmp_path):
    from ci.wheel_gate import find_duplicate_entries

    bad = tmp_path / "dup.whl"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("cryptobrain/__init__.py", "x = 1\n")
        zf.writestr("cryptobrain/__init__.py", "x = 2\n")
        zf.writestr("main.py", "pass\n")
    dups = find_duplicate_entries(bad)
    assert "cryptobrain/__init__.py" in dups


def test_find_duplicate_entries_clean_zip(tmp_path):
    from ci.wheel_gate import find_duplicate_entries

    good = tmp_path / "clean.whl"
    with zipfile.ZipFile(good, "w") as zf:
        zf.writestr("cryptobrain/__init__.py", "x = 1\n")
        zf.writestr("main.py", "pass\n")
    assert find_duplicate_entries(good) == []


def test_main_accepts_argv_list(monkeypatch, tmp_path):
    """The wheel-gate smoke test calls `main.main(['desk', '--json'])`."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "wheel.db"))
    import main as main_mod

    # argparse writes to stdout; we just need it not to raise and to
    # return an int. desk is read-only and offline-safe.
    rc = main_mod.main(["desk", "--json"])
    assert rc == 0
