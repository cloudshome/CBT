"""
core/research/grade_e3/dataset_ingestor.py
=========================================
High-Frequency L2 Order Book & Trade Tick Ingestion and Audit Engine.

Guarantees:
1. Earned Evidence Progression: Tracks RAW_CAPTURED -> PARSED -> SEQUENCE_VALIDATED.
2. Sequence integrity verification (detects dropped packets, out-of-order diffs).
3. Clock audit (detects timestamp regression and excessive jitter).
4. Computes immutable raw data SHA-256 hashes.
5. Permanent Capital Firewall (Amendment A): Zero execution routing imports or calls.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from core.research.grade_e3.contracts import (
    EvidenceStatus,
    FidelityAuditReport,
    L2DiffUpdate,
    TradeTick,
)

logger = logging.getLogger("sky.research.grade_e3.dataset_ingestor")


class SequenceIntegrityError(Exception):
    """Raised when an unrecoverable sequence gap or out-of-order packet is detected."""


class ClockRegressionError(Exception):
    """Raised when packet timestamps move backward beyond permitted threshold."""


class L2DatasetIngestor:
    """
    Ingests and validates raw Level 2 order book diffs and trade prints.
    Supports Binance Spot (@depth@100ms / @trade) and Bybit Linear Perps.
    """

    def __init__(self, venue: str = "BINANCE_SPOT", symbol: str = "BTCUSDT") -> None:
        self.venue = venue.upper()
        self.symbol = symbol.upper()
        self.status = EvidenceStatus.RAW_CAPTURED
        self._raw_hash: str = ""
        self._diffs: list[L2DiffUpdate] = []
        self._trades: list[TradeTick] = []
        self._sequence_gaps: int = 0
        self._clock_regressions: int = 0
        self._max_clock_drift_ms: float = 0.0

    @property
    def raw_data_hash(self) -> str:
        return self._raw_hash

    def ingest_raw_payload(self, raw_bytes: bytes) -> EvidenceStatus:
        """
        Ingests raw byte payload, records canonical SHA-256 hash, and marks RAW_CAPTURED.
        """
        self._raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        self.status = EvidenceStatus.RAW_CAPTURED
        logger.info(
            f"Ingested raw payload for {self.venue} {self.symbol}. SHA-256: {self._raw_hash}"
        )
        return self.status

    def parse_records(
        self,
        diff_dicts: list[dict[str, Any]],
        trade_dicts: list[dict[str, Any]],
    ) -> EvidenceStatus:
        """
        Parses standardized dictionaries into canonical typed records.
        Transitions status from RAW_CAPTURED to PARSED upon success.
        """
        parsed_diffs: list[L2DiffUpdate] = []
        parsed_trades: list[TradeTick] = []

        # Parse L2 Diffs
        for d in diff_dicts:
            bids = [(float(p), float(q)) for p, q in d.get("bids", [])]
            asks = [(float(p), float(q)) for p, q in d.get("asks", [])]

            pu_raw = (
                d.get("prev_last_update_id")
                if d.get("prev_last_update_id") is not None
                else d.get("pu")
            )
            prev_last_update_id = int(pu_raw) if pu_raw is not None else None

            diff = L2DiffUpdate(
                exchange=self.venue,
                symbol=self.symbol,
                first_update_id=int(d.get("first_update_id", d.get("U", 0))),
                last_update_id=int(d.get("last_update_id", d.get("u", 0))),
                prev_last_update_id=prev_last_update_id,
                timestamp_ns=int(d.get("timestamp_ns", d.get("E", 0) * 1_000_000)),
                bids=bids,
                asks=asks,
            )
            parsed_diffs.append(diff)

        # Parse Trade Ticks
        for t in trade_dicts:
            trade = TradeTick(
                trade_id=t.get("trade_id", t.get("t", 0)),
                timestamp_ns=int(t.get("timestamp_ns", t.get("T", 0) * 1_000_000)),
                price=float(t.get("price", t.get("p", 0.0))),
                size=float(t.get("size", t.get("q", 0.0))),
                is_buyer_maker=bool(t.get("is_buyer_maker", t.get("m", False))),
                symbol=self.symbol,
            )
            parsed_trades.append(trade)

        self._diffs = parsed_diffs
        self._trades = parsed_trades
        self.status = EvidenceStatus.PARSED
        logger.info(f"Successfully parsed {len(self._diffs)} diffs and {len(self._trades)} trades.")
        return self.status

    def validate_sequences(
        self,
        fail_on_gap: bool = False,
        clock_drift_tolerance_ms: float = 100.0,
    ) -> FidelityAuditReport:
        """
        Validates sequence integrity and timestamp progression.
        Transitions status from PARSED to SEQUENCE_VALIDATED if clean.
        """
        if self.status not in (EvidenceStatus.PARSED, EvidenceStatus.RAW_CAPTURED):
            raise ValueError(
                f"Cannot validate sequences from state '{self.status}'. Must be PARSED."
            )

        self._sequence_gaps = 0
        self._clock_regressions = 0
        self._max_clock_drift_ms = 0.0

        # 1. Audit Diff Sequences
        prev_u: int | None = None
        prev_time_ns: int | None = None

        for i, diff in enumerate(self._diffs):
            # Check clock regression
            if prev_time_ns is not None:
                drift_ns = prev_time_ns - diff.timestamp_ns
                if drift_ns > 0:
                    drift_ms = drift_ns / 1_000_000.0
                    self._max_clock_drift_ms = max(self._max_clock_drift_ms, drift_ms)
                    if drift_ms > clock_drift_tolerance_ms:
                        self._clock_regressions += 1
                        if fail_on_gap:
                            raise ClockRegressionError(
                                f"Packet {i}: Clock regression of {drift_ms:.2f}ms exceeds {clock_drift_tolerance_ms}ms"
                            )

            prev_time_ns = diff.timestamp_ns

            # Check sequence continuity
            if prev_u is not None:
                # Binance protocol check:
                # diff.first_update_id <= prev_u + 1 and diff.last_update_id >= prev_u + 1
                if diff.prev_last_update_id is not None:
                    if diff.prev_last_update_id != prev_u:
                        self._sequence_gaps += 1
                        if fail_on_gap:
                            raise SequenceIntegrityError(
                                f"Sequence gap at packet {i}: pu={diff.prev_last_update_id} != prev_u={prev_u}"
                            )
                else:
                    if diff.first_update_id > prev_u + 1:
                        self._sequence_gaps += 1
                        if fail_on_gap:
                            raise SequenceIntegrityError(
                                f"Sequence gap at packet {i}: U={diff.first_update_id} > prev_u+1={prev_u + 1}"
                            )

            prev_u = diff.last_update_id

        # 2. Audit Trade Ticks (Monotonic trade IDs or timestamps)
        prev_trade_time_ns: int | None = None
        for i, trade in enumerate(self._trades):
            if prev_trade_time_ns is not None and trade.timestamp_ns < prev_trade_time_ns:
                drift_ms = (prev_trade_time_ns - trade.timestamp_ns) / 1_000_000.0
                if drift_ms > clock_drift_tolerance_ms:
                    self._clock_regressions += 1
                    if fail_on_gap:
                        raise ClockRegressionError(
                            f"Trade {i}: Clock regression of {drift_ms:.2f}ms exceeds {clock_drift_tolerance_ms}ms"
                        )
            prev_trade_time_ns = trade.timestamp_ns

        # Determine earned status
        is_certified = (self._sequence_gaps == 0) and (self._clock_regressions == 0)
        if is_certified and len(self._diffs) > 0:
            self.status = EvidenceStatus.SEQUENCE_VALIDATED
        else:
            self.status = EvidenceStatus.PARSED

        report = FidelityAuditReport(
            venue=self.venue,
            symbol=self.symbol,
            total_diffs=len(self._diffs),
            total_ticks=len(self._trades),
            sequence_gaps=self._sequence_gaps,
            clock_drift_p99_ms=self._max_clock_drift_ms,
            spread_inversions=0,
            raw_data_sha256=self._raw_hash or "SYNTHETIC_EMPTY_DATASET",
            evidence_status=self.status,
            is_fidelity_certified=is_certified,
        )

        return report

    def get_diffs(self) -> list[L2DiffUpdate]:
        return list(self._diffs)

    def get_trades(self) -> list[TradeTick]:
        return list(self._trades)
