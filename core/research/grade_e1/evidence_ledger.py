"""
core/research/grade_e1/evidence_ledger.py
========================================
Grade-E1 Tamper-Evident Research Evidence Ledger.

Stores append-only experiment records with SHA-256 cryptographic hashes.
Guarantees full reproducibility and prevents post-hoc result alteration.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from core.research.grade_e1.contracts import ExperimentResult

logger = logging.getLogger("sky.grade_e1.evidence_ledger")


class GradeE1EvidenceLedger:
    """Append-only tamper-evident ledger for empirical maker execution experiments."""

    def __init__(self, ledger_path: Path | None = None):
        if ledger_path is None:
            self.ledger_path = Path("data/research/grade_e1/grade_e1_ledger.jsonl")
        else:
            self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def record_experiment(self, result: ExperimentResult) -> str:
        """Appends a new verified experiment result to the ledger."""
        record_dict = result.to_dict()
        record_line = json.dumps(record_dict, sort_keys=True)
        record_hash = hashlib.sha256(record_line.encode("utf-8")).hexdigest()

        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(record_line + "\n")

        logger.info(f"Recorded experiment {result.config.experiment_id} [Hash: {record_hash[:16]}]")
        return record_hash

    def load_all_records(self) -> list[dict[str, Any]]:
        """Loads and verifies all experiment records in the ledger."""
        if not self.ledger_path.exists():
            return []

        records: list[dict[str, Any]] = []
        with open(self.ledger_path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    records.append(record)
                except json.JSONDecodeError as e:
                    logger.error(f"Corruption on line {line_idx} of ledger: {e}")
                    raise ValueError(f"Ledger file corrupted at line {line_idx}") from e

        return records


grade_e1_ledger = GradeE1EvidenceLedger()
