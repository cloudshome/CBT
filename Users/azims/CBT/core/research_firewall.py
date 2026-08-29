"""
P0 Research Firewall, Dataset Partitioning & Immutable Experiment Registry.
Enforces strict separation between In-Sample Training, Validation Tuning,
and Untouched Out-of-Sample (OOS) Test Data.
Locks parameters/features before OOS evaluation and guards against repeated test snooping.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("ai_quant_sentinel.research_firewall")


class DatasetPartition(str, Enum):
    IN_SAMPLE_TRAIN = "IN_SAMPLE_TRAIN"           # Historical training data (<= 2023-12-31)
    VALIDATION_TUNING = "VALIDATION_TUNING"       # Hyperparameter tuning (2024-01-01 -> 2024-12-31)
    UNTOUCHED_OOS_TEST = "UNTOUCHED_OOS_TEST"     # Strictly locked OOS test data (>= 2025-01-01)


class ResearchFirewallViolation(Exception):
    """Raised when an unauthorized or repeated test set access is attempted."""
    pass


@dataclass
class ExperimentRecord:
    experiment_id: str
    hypothesis_name: str
    asset: str
    parameters: Dict[str, Any]
    feature_set: List[str]
    is_parameters_locked: bool
    is_features_locked: bool
    oos_evaluations_count: int
    max_allowed_oos_evaluations: int
    train_sharpe: float
    validation_sharpe: float
    oos_sharpe: Optional[float] = None
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    locked_at_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchFirewall:
    """
    Guards quantitative research integrity and prevents out-of-sample data snooping.
    """

    def __init__(self, max_oos_evaluations_per_hypothesis: int = 3):
        self.max_oos_evaluations = max_oos_evaluations_per_hypothesis
        self._experiments: Dict[str, ExperimentRecord] = {}

    def register_experiment(
        self,
        hypothesis_name: str,
        asset: str,
        parameters: Dict[str, Any],
        feature_set: List[str],
        train_sharpe: float,
        validation_sharpe: float,
    ) -> ExperimentRecord:
        """
        Creates and registers an immutable experiment definition.
        """
        payload = f"{hypothesis_name}:{asset}:{json.dumps(parameters, sort_keys=True)}:{sorted(feature_set)}"
        exp_id = f"EXP_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"

        record = ExperimentRecord(
            experiment_id=exp_id,
            hypothesis_name=hypothesis_name,
            asset=asset,
            parameters=parameters,
            feature_set=sorted(feature_set),
            is_parameters_locked=False,
            is_features_locked=False,
            oos_evaluations_count=0,
            max_allowed_oos_evaluations=self.max_oos_evaluations,
            train_sharpe=train_sharpe,
            validation_sharpe=validation_sharpe,
        )
        self._experiments[exp_id] = record
        logger.info(f"Registered Experiment {exp_id} for hypothesis '{hypothesis_name}'.")
        return record

    def lock_experiment(self, experiment_id: str) -> None:
        """
        Freezes parameters and features before granting OOS test partition clearance.
        """
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found.")

        exp.is_parameters_locked = True
        exp.is_features_locked = True
        exp.locked_at_ms = int(time.time() * 1000)
        logger.info(f"Experiment {experiment_id} parameters & features LOCKED.")

    def request_oos_clearance(self, experiment_id: str) -> bool:
        """
        Evaluates whether an experiment is authorized to access Untouched OOS Test Data.
        """
        exp = self._experiments.get(experiment_id)
        if not exp:
            raise ResearchFirewallViolation(f"Experiment {experiment_id} does not exist in registry.")

        if not (exp.is_parameters_locked and exp.is_features_locked):
            raise ResearchFirewallViolation(
                f"FIREWALL BLOCKED: Experiment {experiment_id} parameters must be locked before OOS evaluation."
            )

        if exp.oos_evaluations_count >= exp.max_allowed_oos_evaluations:
            raise ResearchFirewallViolation(
                f"FIREWALL BLOCKED: Experiment {experiment_id} has exhausted its OOS evaluation budget "
                f"({exp.oos_evaluations_count}/{exp.max_allowed_oos_evaluations}). "
                "Repeated testing is rejected to prevent data-mining snooping."
            )

        exp.oos_evaluations_count += 1
        return True

    def record_oos_result(self, experiment_id: str, oos_sharpe: float) -> None:
        """
        Records the single-pass OOS test result.
        """
        exp = self._experiments.get(experiment_id)
        if exp:
            exp.oos_sharpe = oos_sharpe
            logger.info(f"Experiment {experiment_id} OOS Sharpe recorded: {oos_sharpe:.2f}")


research_firewall = ResearchFirewall()
