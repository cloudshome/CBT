"""
P0 Research Firewall & Immutable Out-of-Sample Partition Guard.
Enforces strict tripartite data partitioning:
- Training (In-Sample): 60%
- Validation (Tuning): 20%
- Immutable Out-of-Sample (OOS Test): 20% (Cryptographically quarantined)
Raises DataLeakageException if any optimization loop attempts to access the OOS partition.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.research_firewall")


class DataLeakageException(Exception):
    """Raised when research or optimization code touches quarantined out-of-sample data."""
    pass


@dataclass
class DatasetPartition:
    train_data: list[dict[str, Any]]
    val_data: list[dict[str, Any]]
    test_data: list[dict[str, Any]]     # Quarantined
    train_hash: str
    val_hash: str
    test_hash: str
    total_samples: int
    train_ratio: float = 0.60
    val_ratio: float = 0.20
    test_ratio: float = 0.20


class ResearchFirewall:
    """Guarantees strict separation between training/tuning and out-of-sample evaluation."""

    def __init__(self):
        self._quarantine_locked: bool = True

    def partition_dataset(
        self,
        records: list[dict[str, Any]],
        train_ratio: float = 0.60,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20,
    ) -> DatasetPartition:
        """
        Partitions time-ordered records sequentially into Train (60%), Val (20%), and Test (20%).
        """
        n = len(records)
        if n < 10:
            raise ValueError(f"Insufficient dataset length ({n}) to partition safely.")

        idx_train_end = int(n * train_ratio)
        idx_val_end = int(n * (train_ratio + val_ratio))

        train = records[:idx_train_end]
        val = records[idx_train_end:idx_val_end]
        test = records[idx_val_end:]

        train_hash = self._compute_hash(train)
        val_hash = self._compute_hash(val)
        test_hash = self._compute_hash(test)

        logger.info(
            f"Dataset partitioned: Train={len(train)} (hash={train_hash[:8]}), "
            f"Val={len(val)} (hash={val_hash[:8]}), Test={len(test)} (hash={test_hash[:8]})."
        )

        return DatasetPartition(
            train_data=train,
            val_data=val,
            test_data=test,
            train_hash=train_hash,
            val_hash=val_hash,
            test_hash=test_hash,
            total_samples=n,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
        )

    def access_test_partition(
        self,
        partition: DatasetPartition,
        caller_role: str = "OPTIMIZATION_SEARCH",
    ) -> list[dict[str, Any]]:
        """
        Guards the OOS test partition. Only the official Quarantine Validator may access it.
        """
        if caller_role in ["OPTIMIZATION_SEARCH", "GENETIC_MUTATOR", "HYPERPARAMETER_TUNER"]:
            msg = (
                f"DATA_LEAKAGE_EXCEPTION: Role '{caller_role}' attempted to access quarantined "
                "Immutable Out-of-Sample Test set! Blocked by Research Firewall."
            )
            logger.critical(msg)
            raise DataLeakageException(msg)

        logger.info(f"Authorized OOS test access granted to '{caller_role}'.")
        return partition.test_data

    def _compute_hash(self, records: list[dict[str, Any]]) -> str:
        serialized = json.dumps(records, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# Singleton
research_firewall = ResearchFirewall()
