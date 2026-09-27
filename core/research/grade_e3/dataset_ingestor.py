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
        self._duplicates_detected: int = 0
        self._out_of_order_detected: int = 0
        self._malformed_packets: int = 0
        self._reconnect_boundaries: int = 0
        self._exclusions: list[dict[str, Any]] = []

    @property
    def raw_data_hash(self) -> str:
        return self._raw_hash

    @property
    def exclusions(self) -> list[dict[str, Any]]:
        return list(self._exclusions)

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
        reject_malformed: bool = True,
    ) -> EvidenceStatus:
        """
        Parses standardized dictionaries into canonical typed records.
        Transitions status from RAW_CAPTURED to PARSED upon success.
        Excludes malformed, negative quantity, or zero-price entries.
        """
        parsed_diffs: list[L2DiffUpdate] = []
        parsed_trades: list[TradeTick] = []

        # Parse L2 Diffs
        for i, d in enumerate(diff_dicts):
            try:
                bids_raw = d.get("bids", [])
                asks_raw = d.get("asks", [])
                bids: list[tuple[float, float]] = []
                asks: list[tuple[float, float]] = []

                has_malformed = False
                for p_raw, q_raw in bids_raw:
                    p, q = float(p_raw), float(q_raw)
                    if p <= 0.0 or q < 0.0:
                        has_malformed = True
                        break
                    bids.append((p, q))

                for p_raw, q_raw in asks_raw:
                    p, q = float(p_raw), float(q_raw)
                    if p <= 0.0 or q < 0.0:
                        has_malformed = True
                        break
                    asks.append((p, q))

                if has_malformed and reject_malformed:
                    self._malformed_packets += 1
                    self._exclusions.append(
                        {
                            "packet_type": "diff",
                            "index": i,
                            "reason": "negative_or_zero_price_or_negative_qty",
                            "data": d,
                        }
                    )
                    continue

                pu_raw = (
                    d.get("prev_last_update_id")
                    if d.get("prev_last_update_id") is not None
                    else d.get("pu")
                )
                prev_last_update_id = int(pu_raw) if pu_raw is not None else None

                u_first = int(d.get("first_update_id", d.get("U", 0)))
                u_last = int(d.get("last_update_id", d.get("u", 0)))

                if u_last < u_first:
                    self._malformed_packets += 1
                    self._exclusions.append(
                        {
                            "packet_type": "diff",
                            "index": i,
                            "reason": "last_update_id_less_than_first",
                            "data": d,
                        }
                    )
                    continue

                diff = L2DiffUpdate(
                    exchange=self.venue,
                    symbol=self.symbol,
                    first_update_id=u_first,
                    last_update_id=u_last,
                    prev_last_update_id=prev_last_update_id,
                    timestamp_ns=int(d.get("timestamp_ns", d.get("E", 0) * 1_000_000)),
                    bids=bids,
                    asks=asks,
                )
                parsed_diffs.append(diff)
            except (ValueError, TypeError) as e:
                self._malformed_packets += 1
                self._exclusions.append(
                    {
                        "packet_type": "diff",
                        "index": i,
                        "reason": f"parse_error_{e}",
                        "data": d,
                    }
                )

        # Parse Trade Ticks
        for j, t in enumerate(trade_dicts):
            try:
                price = float(t.get("price", t.get("p", 0.0)))
                size = float(t.get("size", t.get("q", 0.0)))
                if (price <= 0.0 or size <= 0.0) and reject_malformed:
                    self._malformed_packets += 1
                    self._exclusions.append(
                        {
                            "packet_type": "trade",
                            "index": j,
                            "reason": "non_positive_price_or_size",
                            "data": t,
                        }
                    )
                    continue

                trade = TradeTick(
                    trade_id=t.get("trade_id", t.get("t", 0)),
                    timestamp_ns=int(t.get("timestamp_ns", t.get("T", 0) * 1_000_000)),
                    price=price,
                    size=size,
                    is_buyer_maker=bool(t.get("is_buyer_maker", t.get("m", False))),
                    symbol=self.symbol,
                )
                parsed_trades.append(trade)
            except (ValueError, TypeError) as e:
                self._malformed_packets += 1
                self._exclusions.append(
                    {
                        "packet_type": "trade",
                        "index": j,
                        "reason": f"parse_error_{e}",
                        "data": t,
                    }
                )

        self._diffs = parsed_diffs
        self._trades = parsed_trades
        self.status = EvidenceStatus.PARSED
        logger.info(
            f"Parsed {len(self._diffs)} diffs, {len(self._trades)} trades. Exclusions: {len(self._exclusions)}"
        )
        return self.status

    def validate_sequences(
        self,
        fail_on_gap: bool = False,
        clock_drift_tolerance_ms: float = 100.0,
        handle_reconnect: bool = False,
    ) -> FidelityAuditReport:
        """
        Validates sequence integrity, duplicates, out-of-order events, and clock regressions.
        Transitions status from PARSED to SEQUENCE_VALIDATED if clean.
        """
        if self.status not in (EvidenceStatus.PARSED, EvidenceStatus.RAW_CAPTURED):
            raise ValueError(
                f"Cannot validate sequences from state '{self.status}'. Must be PARSED."
            )

        self._sequence_gaps = 0
        self._clock_regressions = 0
        self._max_clock_drift_ms = 0.0
        self._duplicates_detected = 0
        self._out_of_order_detected = 0

        # 1. Audit Diff Sequences
        prev_u: int | None = None
        prev_time_ns: int | None = None
        seen_update_ranges: set[tuple[int, int]] = set()

        for i, diff in enumerate(self._diffs):
            # Check duplicate range
            u_range = (diff.first_update_id, diff.last_update_id)
            if u_range in seen_update_ranges:
                self._duplicates_detected += 1
            seen_update_ranges.add(u_range)

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
                # Out-of-order check
                if diff.last_update_id < prev_u:
                    self._out_of_order_detected += 1
                    if fail_on_gap:
                        raise SequenceIntegrityError(
                            f"Out-of-order packet at {i}: u={diff.last_update_id} < prev_u={prev_u}"
                        )

                # Binance protocol check:
                # diff.first_update_id <= prev_u + 1 and diff.last_update_id >= prev_u + 1
                if diff.prev_last_update_id is not None:
                    if diff.prev_last_update_id != prev_u:
                        self._sequence_gaps += 1
                        if handle_reconnect:
                            self._reconnect_boundaries += 1
                            prev_u = diff.last_update_id
                            continue
                        elif fail_on_gap:
                            raise SequenceIntegrityError(
                                f"Sequence gap at packet {i}: pu={diff.prev_last_update_id} != prev_u={prev_u}"
                            )
                else:
                    if diff.first_update_id > prev_u + 1:
                        self._sequence_gaps += 1
                        if handle_reconnect:
                            self._reconnect_boundaries += 1
                            prev_u = diff.last_update_id
                            continue
                        elif fail_on_gap:
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
        is_certified = (
            (self._sequence_gaps == 0)
            and (self._clock_regressions == 0)
            and (self._out_of_order_detected == 0)
            and len(self._diffs) > 0
        )
        if is_certified:
            self.status = EvidenceStatus.SEQUENCE_VALIDATED
        else:
            self.status = EvidenceStatus.PARSED

        summary = (
            f"Fidelity Certified: {is_certified} | Diffs: {len(self._diffs)}, Ticks: {len(self._trades)}, "
            f"Gaps: {self._sequence_gaps}, Dups: {self._duplicates_detected}, "
            f"OutOfOrder: {self._out_of_order_detected}, Malformed: {self._malformed_packets}"
        )

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
            duplicates_detected=self._duplicates_detected,
            out_of_order_detected=self._out_of_order_detected,
            malformed_packets=self._malformed_packets,
            reconnect_boundaries=self._reconnect_boundaries,
            exclusions_count=len(self._exclusions),
            audit_summary=summary,
        )

        return report

    def get_diffs(self) -> list[L2DiffUpdate]:
        return list(self._diffs)

    def get_trades(self) -> list[TradeTick]:
        return list(self._trades)

    def generate_integrity_report_markdown(self, report: FidelityAuditReport) -> str:
        """Generates canonical Markdown data fidelity report."""
        status_badge = "✅ CERTIFIED" if report.is_fidelity_certified else "❌ FAILED"
        diff_pass = "PASS" if report.total_diffs > 0 else "FAIL"
        tick_pass = "PASS" if report.total_ticks > 0 else "FAIL"
        gap_pass = "PASS" if report.sequence_gaps == 0 else "FAIL"
        dup_pass = "PASS" if report.duplicates_detected == 0 else "FLAGGED"
        ooo_pass = "PASS" if report.out_of_order_detected == 0 else "FAIL"
        drift_pass = "PASS" if report.clock_drift_p99_ms <= 100.0 else "FAIL"
        mal_pass = "PASS" if report.malformed_packets == 0 else "FLAGGED"
        recon_pass = "PASS" if report.reconnect_boundaries == 0 else "FLAGGED"

        md = f"""# Grade-E3 Data Integrity & Sequence Fidelity Audit Report

> **Venue:** {report.venue}  
> **Symbol:** {report.symbol}  
> **Evidence Status:** `{report.evidence_status.value}`  
> **Fidelity Status:** {status_badge}  
> **Raw SHA-256:** `{report.raw_data_sha256}`  

---

## 1. Sequence & Ingestion Summary
| Metric | Realized Value | Threshold / Tolerance | Verdict |
|---|---|---|---|
| **Total L2 Diffs** | {report.total_diffs:,} | >= 1 | {diff_pass} |
| **Total Trade Ticks** | {report.total_ticks:,} | >= 1 | {tick_pass} |
| **Sequence Gaps** | {report.sequence_gaps} | 0 | {gap_pass} |
| **Duplicate Packets** | {report.duplicates_detected} | 0 (monitored) | {dup_pass} |
| **Out-of-Order Packets** | {report.out_of_order_detected} | 0 | {ooo_pass} |
| **Clock Drift (p99)** | {report.clock_drift_p99_ms:.2f} ms | <= 100.0 ms | {drift_pass} |
| **Malformed / Excluded** | {report.malformed_packets} | 0 | {mal_pass} |
| **Reconnect Boundaries** | {report.reconnect_boundaries} | 0 | {recon_pass} |

---

## 2. Ingestion Forensic Details
- **Summary:** {report.audit_summary}
- **Exclusion Audit:** {len(self._exclusions)} excluded/filtered packets recorded during normalization.
"""
        return md
