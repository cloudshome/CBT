"""
Strategy Cryptographic Fingerprint Engine
=========================================
Binds strategy definitions directly to actual executable source code,
environment dependencies, data/feature schema versions, and git commit identity.

Any modification to executable logic, parameters, or underlying schemas
produces a distinct cryptographic fingerprint, automatically invalidating
prior version certifications.
"""

import hashlib
import inspect
import json
import os
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd
import scipy


def get_current_git_commit(cwd: str | None = None) -> str:
    """Retrieves the current git commit SHA or returns UNTRACKED_SNAPSHOT."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def hash_source_code(code_obj: Any) -> str:
    """
    Computes a deterministic SHA-256 hash of executable python logic.
    Accepts a callable function, class, or raw source string.
    """
    if isinstance(code_obj, str):
        src = code_obj.strip()
    elif callable(code_obj):
        try:
            src = inspect.getsource(code_obj).strip()
        except Exception:
            src = str(code_obj.__code__.co_code)
    else:
        src = repr(code_obj)

    # Normalize line endings to avoid CRLF vs LF divergence
    normalized_src = "\n".join(line.rstrip() for line in src.splitlines() if line.strip())
    return hashlib.sha256(normalized_src.encode("utf-8")).hexdigest()


class StrategyCryptographicFingerprint:
    """
    Encapsulates institutional cryptographic binding for quant strategies.
    """

    def __init__(
        self,
        strategy_id: str,
        canonical_config: dict[str, Any],
        executable_logic: Any,
        data_schema_version: str = "v1.0-derivatives-hourly",
        feature_schema_version: str = "v1.0-oi-atr-bb",
        commit_id: str | None = None,
    ):
        self.strategy_id = strategy_id
        self.canonical_config = canonical_config
        self.executable_code_hash = hash_source_code(executable_logic)
        self.data_schema_version = data_schema_version
        self.feature_schema_version = feature_schema_version
        self.commit_id = commit_id or get_current_git_commit()

        self.dependencies = {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        }

        self.payload = {
            "strategy_id": self.strategy_id,
            "canonical_config": self.canonical_config,
            "executable_code_sha256": self.executable_code_hash,
            "data_schema_version": self.data_schema_version,
            "feature_schema_version": self.feature_schema_version,
            "commit_id": self.commit_id,
            "dependencies": self.dependencies,
        }

        # Canonical JSON serialization for deterministic composite digest
        canonical_bytes = json.dumps(self.payload, sort_keys=True, indent=2).encode("utf-8")
        self.composite_fingerprint = hashlib.sha256(canonical_bytes).hexdigest()
        self.payload["composite_fingerprint"] = self.composite_fingerprint

    def to_dict(self) -> dict[str, Any]:
        return self.payload

    def verify_against(self, current_executable: Any, current_config: dict[str, Any]) -> bool:
        """
        Verifies whether current executable logic or config still matches the fingerprint.
        Returns False if code or parameters have drifted.
        """
        current_code_hash = hash_source_code(current_executable)
        if current_code_hash != self.executable_code_hash:
            return False

        canonical_current_cfg = json.dumps(current_config, sort_keys=True)
        canonical_stored_cfg = json.dumps(self.canonical_config, sort_keys=True)
        if canonical_current_cfg != canonical_stored_cfg:
            return False

        return True
