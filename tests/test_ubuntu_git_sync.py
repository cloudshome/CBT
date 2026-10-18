"""
Tests for Ubuntu Scheduled Git Sync & Crontab Automation
Verifies script permissions, bash syntax integrity, and scheduled cron times.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "ubuntu_git_sync.sh"
CRON_FILE = REPO_ROOT / "deploy" / "crontab_ubuntu_sync.cron"


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="POSIX file permissions require Linux/Ubuntu environment",
)
def test_sync_script_exists_and_executable():
    assert SCRIPT_PATH.exists(), f"{SCRIPT_PATH} does not exist"
    assert os.access(SCRIPT_PATH, os.X_OK), f"{SCRIPT_PATH} is not executable"


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="Bash syntax check runs natively on Ubuntu/Linux environments",
)
def test_sync_script_bash_syntax():
    """Verify script contains zero syntax errors using bash -n."""
    result = subprocess.run(["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True)
    assert result.returncode == 0, f"Bash syntax error in {SCRIPT_PATH}: {result.stderr}"


def test_crontab_file_contains_all_seven_times():
    """
    Verify crontab contains all 7 user-specified times:
    12:01 PM, 12:30 PM, 1:30 PM, 2:30 PM, 3:30 PM, 4:30 PM, 11:55 PM
    """
    assert CRON_FILE.exists(), f"{CRON_FILE} does not exist"
    cron_content = CRON_FILE.read_text()

    required_times = [
        "1 12 * * *",  # 12:01 PM
        "30 12 * * *",  # 12:30 PM
        "30 13 * * *",  # 1:30 PM
        "30 14 * * *",  # 2:30 PM
        "30 15 * * *",  # 3:30 PM
        "30 16 * * *",  # 4:30 PM
        "55 23 * * *",  # 11:55 PM
    ]

    for timing in required_times:
        assert timing in cron_content, f"Missing timing pattern '{timing}' in {CRON_FILE}"
