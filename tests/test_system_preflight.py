"""Regression tests for the cross-platform preflight command runner."""

import os
import subprocess
from unittest.mock import patch

from scripts import system_preflight


def test_run_npm_preserves_all_arguments():
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with (
        patch.object(system_preflight.shutil, "which", return_value="/usr/bin/npm"),
        patch.object(system_preflight.subprocess, "run", return_value=completed) as run,
    ):
        result = system_preflight.run_npm("--prefix", "frontend", "run", "build")

    assert result is completed
    command = run.call_args.args[0]
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.kwargs["cwd"] == system_preflight.PROJECT_ROOT

    if os.name == "nt":
        assert command[:4] == [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c"]
        assert "--prefix frontend run build" in command[4]
    else:
        assert command == ["/usr/bin/npm", "--prefix", "frontend", "run", "build"]
