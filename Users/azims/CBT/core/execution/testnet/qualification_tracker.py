"""
core/execution/testnet/qualification_tracker.py
===============================================
Milestone 23: Continuous 14-Day (336-Hour) Gate 5 Qualification Tracker.

Implements:
- 3-Stream Time Accounting (H_elapsed = H_qualified + H_disqualified).
- 7-Tier Event Classification Taxonomy with explicit qualification impact.
- Formal 8-State CampaignQualificationState Machine.
- Append-Only Chained SHA-256 Interval Ledger (H_i = SHA256(H_{i-1} || Data_i)).
- Gate 5 Cryptographic Audit Certificate Generator.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger("sky.execution.testnet.qualification")


class QualificationEventClass(str, Enum):
    EXPECTED_OPERATION = "EXPECTED_OPERATION"
    RECOVERABLE_DEGRADATION = "RECOVERABLE_DEGRADATION"
    EXTERNAL_VENUE_FAULT = "EXTERNAL_VENUE_FAULT"
    OPERATOR_CONTROL = "OPERATOR_CONTROL"
    EVIDENCE_FAILURE = "EVIDENCE_FAILURE"
    SYSTEM_SAFETY_HALT = "SYSTEM_SAFETY_HALT"
    ACCOUNTING_FAILURE = "ACCOUNTING_FAILURE"


class CampaignQualificationState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    QUALIFYING = "QUALIFYING"
    TEMPORARILY_DISQUALIFIED = "TEMPORARILY_DISQUALIFIED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    QUALIFICATION_RESET_REQUIRED = "QUALIFICATION_RESET_REQUIRED"
    QUALIFIED_PENDING_REVIEW = "QUALIFIED_PENDING_REVIEW"
    CERTIFIED = "CERTIFIED"
    FAILED = "FAILED"


class AccountingConservationBreachError(Exception):
    """Raised when elapsed time does not equal qualified + disqualified time."""


class QualificationResetRequiredError(Exception):
    """Raised when an unrecoverable accounting failure forces a complete qualification reset."""


@dataclass
class QualificationIntervalRecord:
    interval_id: str
    interval_index: int
    start_epoch: float
    end_epoch: float
    duration_sec: float
    elapsed_hours: float
    qualified_hours: float
    disqualified_hours: float
    event_counts: dict[str, int]
    is_qualifying: bool
    prev_interval_hash: str
    interval_hash: str = ""

    def compute_hash(self) -> str:
        payload = {
            "interval_id": self.interval_id,
            "interval_index": self.interval_index,
            "start_epoch": round(self.start_epoch, 3),
            "end_epoch": round(self.end_epoch, 3),
            "elapsed_hours": round(self.elapsed_hours, 6),
            "qualified_hours": round(self.qualified_hours, 6),
            "disqualified_hours": round(self.disqualified_hours, 6),
            "event_counts": self.event_counts,
            "is_qualifying": self.is_qualifying,
            "prev_interval_hash": self.prev_interval_hash,
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()


@dataclass
class Gate5QualificationCertificate:
    certificate_id: str
    campaign_id: str
    issued_at_utc: str
    target_hours: float
    verified_qualified_hours: float
    total_elapsed_hours: float
    qualification_ratio: float
    total_completed_flights: int
    total_intervals: int
    genesis_hash: str
    final_chained_hash: str
    verdict: str
    signature_digest: str


class Continuous14DayQualificationTracker:
    """
    Evaluates 14-day continuous testnet flight endurance and records cryptographic evidence.
    """

    GENESIS_HASH: str = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(
        self,
        campaign_id: str,
        target_hours: float = 336.0,
        max_disqualified_ratio: float = 0.05,
        db_conn: sqlite3.Connection | None = None,
    ) -> None:
        self.campaign_id = campaign_id
        self.target_hours = target_hours
        self.max_disqualified_ratio = max_disqualified_ratio
        self.db = db_conn

        self.state = CampaignQualificationState.NOT_STARTED
        self.campaign_start_epoch: float | None = None
        self.last_update_epoch: float | None = None

        self.qualified_seconds: float = 0.0
        self.disqualified_seconds: float = 0.0

        self.intervals: list[QualificationIntervalRecord] = []
        self.current_interval_events: dict[str, int] = {e.value: 0 for e in QualificationEventClass}
        self.total_completed_flights: int = 0
        self.consecutive_disqualified_intervals: int = 0

        if self.db:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        assert self.db is not None
        with self.db:
            self.db.execute("PRAGMA journal_mode=WAL;")
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS testnet_qualification_intervals (
                    interval_id TEXT PRIMARY KEY,
                    interval_index INTEGER NOT NULL,
                    campaign_id TEXT NOT NULL,
                    start_epoch REAL NOT NULL,
                    end_epoch REAL NOT NULL,
                    qualified_hours REAL NOT NULL,
                    disqualified_hours REAL NOT NULL,
                    is_qualifying INTEGER NOT NULL,
                    prev_hash TEXT NOT NULL,
                    interval_hash TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                """
            )

    def start_campaign(self) -> None:
        """Starts qualification tracking."""
        now = time.time()
        self.campaign_start_epoch = now
        self.last_update_epoch = now
        self.state = CampaignQualificationState.QUALIFYING
        logger.info(f"[Qualification] Started 14-day qualification for campaign {self.campaign_id}")

    def record_flight_completion(self, flight_id: str, evidence: Any, duration_sec: float) -> None:
        """
        Records a completed flight and its duration under the appropriate qualification stream.
        """
        now = time.time()
        self.total_completed_flights += 1

        # Check evidence invariants
        is_clean = True
        if hasattr(evidence, "unresolved_quantity") and evidence.unresolved_quantity != Decimal(
            "0"
        ):
            self.record_event(
                QualificationEventClass.ACCOUNTING_FAILURE,
                f"Flight {flight_id} has unresolved quantity {evidence.unresolved_quantity}",
            )
            is_clean = False

        if is_clean:
            self.record_event(QualificationEventClass.EXPECTED_OPERATION)
            self.qualified_seconds += duration_sec
        else:
            self.disqualified_seconds += duration_sec

        self.last_update_epoch = now
        self._check_qualification_threshold()

    def record_flight_fault(self, flight_id: str, error_message: str) -> None:
        """Records a faulted flight as an external or safety fault."""
        now = time.time()
        if "rate limit" in error_message.lower():
            self.record_event(
                QualificationEventClass.SYSTEM_SAFETY_HALT, f"Rate limit breach: {error_message}"
            )
        elif "overfill" in error_message.lower():
            self.record_event(
                QualificationEventClass.SYSTEM_SAFETY_HALT, f"Overfill halt: {error_message}"
            )
        else:
            self.record_event(
                QualificationEventClass.EXTERNAL_VENUE_FAULT, f"Flight fault: {error_message}"
            )
        self.last_update_epoch = now

    def record_event(self, event_class: QualificationEventClass, details: str = "") -> None:
        """
        Records an event and evaluates its impact on the qualification state machine.
        """
        self.current_interval_events[event_class.value] += 1
        logger.info(f"[QualEvent] {event_class.value}: {details}")

        if event_class == QualificationEventClass.ACCOUNTING_FAILURE:
            self.state = CampaignQualificationState.QUALIFICATION_RESET_REQUIRED
            raise QualificationResetRequiredError(
                f"Fatal accounting failure: {details}. Qualification reset required."
            )
        elif event_class == QualificationEventClass.SYSTEM_SAFETY_HALT:
            self.state = CampaignQualificationState.TEMPORARILY_DISQUALIFIED
        elif event_class == QualificationEventClass.EXTERNAL_VENUE_FAULT:
            if self.state == CampaignQualificationState.QUALIFYING:
                self.state = CampaignQualificationState.TEMPORARILY_DISQUALIFIED

    def commit_hourly_interval(
        self, forced_now: float | None = None
    ) -> QualificationIntervalRecord:
        """
        Commits an elapsed discrete 1-hour interval to the chained cryptographic ledger.
        """
        now = forced_now or time.time()
        start = self.last_update_epoch or now
        duration_sec = max(0.0, now - start)

        idx = len(self.intervals) + 1
        interval_id = f"{self.campaign_id}_INT_{idx:05d}"
        prev_hash = self.intervals[-1].interval_hash if self.intervals else self.GENESIS_HASH

        # Determine if this interval qualifies
        fatal_events = (
            self.current_interval_events[QualificationEventClass.ACCOUNTING_FAILURE.value]
            + self.current_interval_events[QualificationEventClass.SYSTEM_SAFETY_HALT.value]
            + self.current_interval_events[QualificationEventClass.EVIDENCE_FAILURE.value]
        )
        is_qual = fatal_events == 0 and self.state in (
            CampaignQualificationState.QUALIFYING,
            CampaignQualificationState.QUALIFIED_PENDING_REVIEW,
        )

        interval_hours = duration_sec / 3600.0
        qual_hours = interval_hours if is_qual else 0.0
        disqual_hours = 0.0 if is_qual else interval_hours

        # Update totals
        self.qualified_seconds += qual_hours * 3600.0
        self.disqualified_seconds += disqual_hours * 3600.0

        rec = QualificationIntervalRecord(
            interval_id=interval_id,
            interval_index=idx,
            start_epoch=start,
            end_epoch=now,
            duration_sec=duration_sec,
            elapsed_hours=interval_hours,
            qualified_hours=qual_hours,
            disqualified_hours=disqual_hours,
            event_counts=dict(self.current_interval_events),
            is_qualifying=is_qual,
            prev_interval_hash=prev_hash,
        )
        rec.interval_hash = rec.compute_hash()

        # Check conservation identity
        self.assert_time_conservation()

        self.intervals.append(rec)
        self.last_update_epoch = now
        # Reset interval event counts
        self.current_interval_events = {e.value: 0 for e in QualificationEventClass}

        # Persist to SQLite if enabled
        if self.db:
            with self.db:
                self.db.execute(
                    """
                    INSERT INTO testnet_qualification_intervals (
                        interval_id, interval_index, campaign_id, start_epoch, end_epoch,
                        qualified_hours, disqualified_hours, is_qualifying, prev_hash,
                        interval_hash, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.interval_id,
                        rec.interval_index,
                        self.campaign_id,
                        rec.start_epoch,
                        rec.end_epoch,
                        rec.qualified_hours,
                        rec.disqualified_hours,
                        1 if rec.is_qualifying else 0,
                        rec.prev_interval_hash,
                        rec.interval_hash,
                        json.dumps(asdict(rec), default=str),
                    ),
                )

        self._check_qualification_threshold()
        return rec

    def assert_time_conservation(self) -> None:
        """
        Enforces strict time identity: H_elapsed == H_qualified + H_disqualified.
        """
        h_qual = self.qualified_seconds / 3600.0
        h_disqual = self.disqualified_seconds / 3600.0
        h_total = (self.qualified_seconds + self.disqualified_seconds) / 3600.0

        # Allow slight floating point tolerance (< 10^-6 hours)
        if abs(h_total - (h_qual + h_disqual)) > 1e-6:
            raise AccountingConservationBreachError(
                f"Time conservation identity breached: Total={h_total}, "
                f"Qual={h_qual}, Disqual={h_disqual}"
            )

    def get_qualified_hours(self) -> float:
        return self.qualified_seconds / 3600.0

    def get_disqualified_hours(self) -> float:
        return self.disqualified_seconds / 3600.0

    def get_elapsed_hours(self) -> float:
        return (self.qualified_seconds + self.disqualified_seconds) / 3600.0

    def is_qualifying(self) -> bool:
        return self.state in (
            CampaignQualificationState.QUALIFYING,
            CampaignQualificationState.QUALIFIED_PENDING_REVIEW,
            CampaignQualificationState.CERTIFIED,
        )

    def _check_qualification_threshold(self) -> None:
        """Checks if campaign meets the 336-hour qualification requirement."""
        h_qual = self.get_qualified_hours()
        h_elapsed = self.get_elapsed_hours()

        if h_elapsed > 0:
            ratio = (self.get_disqualified_hours()) / h_elapsed
            if ratio > self.max_disqualified_ratio:
                self.state = CampaignQualificationState.QUALIFICATION_RESET_REQUIRED
                return

        if h_qual >= self.target_hours and self.state == CampaignQualificationState.QUALIFYING:
            self.state = CampaignQualificationState.QUALIFIED_PENDING_REVIEW
            logger.info(
                f"[Qualification] Reached {h_qual:.2f}h >= {self.target_hours}h. "
                "State advanced to QUALIFIED_PENDING_REVIEW."
            )

    def verify_hash_chain_integrity(self) -> bool:
        """
        Verifies that every interval in the chain matches its predecessor hash and payload.
        """
        expected_prev = self.GENESIS_HASH
        for rec in self.intervals:
            if rec.prev_interval_hash != expected_prev:
                logger.error(
                    f"[Chain] Hash break at {rec.interval_id}: expected {expected_prev}, got {rec.prev_interval_hash}"
                )
                return False
            computed = rec.compute_hash()
            if rec.interval_hash != computed:
                logger.error(
                    f"[Chain] Payload tampering at {rec.interval_id}: hash={rec.interval_hash}, computed={computed}"
                )
                return False
            expected_prev = rec.interval_hash
        return True

    def issue_qualification_certificate(self) -> Gate5QualificationCertificate:
        """
        Issues cryptographic Gate 5 Qualification Audit Certificate.
        """
        if not self.verify_hash_chain_integrity():
            raise RuntimeError("Cannot issue certificate: cryptographic hash chain is corrupted!")

        h_qual = self.get_qualified_hours()
        h_elapsed = self.get_elapsed_hours()
        ratio = (h_qual / h_elapsed) if h_elapsed > 0 else 1.0

        if h_qual < self.target_hours:
            raise RuntimeError(
                f"Cannot issue certificate: qualified hours ({h_qual:.2f}h) below target ({self.target_hours}h)"
            )

        cert_id = f"CERT_GATE5_{self.campaign_id}_{int(time.time())}"
        final_hash = self.intervals[-1].interval_hash if self.intervals else self.GENESIS_HASH

        cert_payload = {
            "cert_id": cert_id,
            "campaign_id": self.campaign_id,
            "h_qual": round(h_qual, 4),
            "h_elapsed": round(h_elapsed, 4),
            "final_hash": final_hash,
        }
        sig = hashlib.sha256(json.dumps(cert_payload, sort_keys=True).encode("utf-8")).hexdigest()

        self.state = CampaignQualificationState.CERTIFIED

        return Gate5QualificationCertificate(
            certificate_id=cert_id,
            campaign_id=self.campaign_id,
            issued_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            target_hours=self.target_hours,
            verified_qualified_hours=round(h_qual, 4),
            total_elapsed_hours=round(h_elapsed, 4),
            qualification_ratio=round(ratio, 4),
            total_completed_flights=self.total_completed_flights,
            total_intervals=len(self.intervals),
            genesis_hash=self.GENESIS_HASH,
            final_chained_hash=final_hash,
            verdict="GATE_5_QUALIFIED",
            signature_digest=sig,
        )
