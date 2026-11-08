"""
tests/test_shadow_runner_process_lock.py
========================================
Verification suite for P0: ProcessLock Single-Instance Advisory Locking.
Enforces non-blocking mutual exclusion, kernel cleanup, and lockfile persistence.
"""

from __future__ import annotations

import errno
import multiprocessing
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.research.run_prospective_shadow_runner import ProcessLock


def _hold_lock_process(lock_path_str: str, duration_sec: float) -> None:
    """Helper worker that acquires lock, holds it for duration, and exits."""
    lock = ProcessLock(Path(lock_path_str))
    if lock.acquire():
        time.sleep(duration_sec)
        lock.release()
    else:
        sys.exit(1)


def test_process_lock_basic_mutual_exclusion(tmp_path: Path):
    """Verifies two instances in same process observe non-blocking mutual exclusion."""
    lock_file = tmp_path / "test_shadow_runner.lock"
    lock1 = ProcessLock(lock_file)
    lock2 = ProcessLock(lock_file)

    # 1. Lock1 acquires successfully
    assert lock1.acquire() is True
    assert lock1.acquired is True
    assert lock_file.exists()

    # 2. Lock2 attempts non-blocking acquisition and must fail fast
    assert lock2.acquire() is False
    assert lock2.acquired is False

    # 3. Lock1 releases; lock2 can now acquire
    lock1.release()
    assert lock1.acquired is False
    assert lock_file.exists(), "Lockfile must never be deleted upon release"

    assert lock2.acquire() is True
    assert lock2.acquired is True
    lock2.release()
    assert lock_file.exists(), "Lockfile must never be deleted upon release"


def test_process_lock_context_manager(tmp_path: Path):
    """Verifies context manager acquisition and release semantics."""
    lock_file = tmp_path / "test_ctx.lock"

    with ProcessLock(lock_file) as l1:
        assert l1.acquired is True
        # Second instance within context block must fail
        with ProcessLock(lock_file) as l2:
            assert l2.acquired is False

    # After context exit, descriptor is released
    with ProcessLock(lock_file) as l3:
        assert l3.acquired is True


def test_process_lock_cross_process_kernel_cleanup(tmp_path: Path):
    """Verifies OS kernel automatically releases lock when child process terminates."""
    lock_file = tmp_path / "test_cross_proc.lock"

    # Start child process holding the lock for 0.5s
    p = multiprocessing.Process(target=_hold_lock_process, args=(str(lock_file), 0.5))
    p.start()

    # Give child a moment to acquire
    time.sleep(0.1)

    parent_lock = ProcessLock(lock_file)
    # While child is active, parent must be locked out
    assert parent_lock.acquire() is False

    # Wait for child to exit
    p.join(timeout=3.0)
    assert not p.is_alive()

    # Now parent must acquire immediately
    assert parent_lock.acquire() is True
    parent_lock.release()
    assert lock_file.exists()


def test_runner_cli_skips_when_lock_held(tmp_path: Path):
    """Verifies run_prospective_shadow_runner CLI exits with code 0 when lock is held."""
    # Hold the project's actual lockfile or custom lockfile
    repo_root = Path(__file__).resolve().parent.parent
    runner_script = repo_root / "scripts" / "research" / "run_prospective_shadow_runner.py"
    actual_lock = repo_root / "data" / "shadow_runner.lock"

    actual_lock.parent.mkdir(parents=True, exist_ok=True)
    with ProcessLock(actual_lock) as held_lock:
        assert held_lock.acquired is True

        # Run shadow runner script in separate subprocess while lock is held
        res = subprocess.run(
            [sys.executable, str(runner_script), "--poll-once"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        # Must exit cleanly with code 0 (skip overlap) and log warning
        assert res.returncode == 0
        assert "Another instance of ProspectiveShadowRunner is currently active" in res.stderr


def test_process_lock_genuine_filesystem_error_raises_not_masked(tmp_path: Path):
    """Verifies filesystem errors (e.g. permission denied) raise and are not masked as active process."""
    readonly_dir = tmp_path / "readonly_dir"
    readonly_dir.mkdir(parents=True, exist_ok=True)
    readonly_dir.chmod(0o555)
    lock_file = readonly_dir / "unwritable.lock"
    lock = ProcessLock(lock_file)

    try:
        with pytest.raises(PermissionError):
            lock.acquire()
        assert lock.acquired is False
        assert lock.file_obj is None
    finally:
        readonly_dir.chmod(0o755)


def test_process_lock_genuine_flock_failure_raises_not_masked(tmp_path: Path):
    """Verifies genuine locking subsystem errors (e.g. ENOLCK) raise and are not treated as contention."""
    lock_file = tmp_path / "flock_fail.lock"
    lock = ProcessLock(lock_file)

    # Simulate ENOLCK (No locks available in system)
    with patch("fcntl.flock", side_effect=OSError(errno.ENOLCK, "No locks available")):
        with pytest.raises(OSError) as excinfo:
            lock.acquire()
        assert excinfo.value.errno == errno.ENOLCK
        assert lock.acquired is False
        assert lock.file_obj is None
