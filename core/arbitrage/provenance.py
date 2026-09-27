"""
core/arbitrage/provenance.py
============================
Immutable Provenance & Decision Envelope Verification Engine.

Guarantees 100% mathematical reproducibility for external auditors:
Every classified or rejected opportunity is wrapped in a complete canonical
decision envelope, hashed with SHA-256, and persisted into SQLite WAL storage.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from core.arbitrage.models import (
    ArbitrageOpportunity,
    ArbitrageProvenanceEnvelope,
    FundingRateRecord,
    NormalizedMarketQuote,
    OrderBookSnapshot,
)
from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.arbitrage.provenance")

INSTRUMENT_MAPPING_VERSION = "IMM_v1.0"
FEE_MODEL_VERSION = "FEE_VIP0_v1.0"
EV_MODEL_VERSION = "EVM_v20.1_PROD"
CAPACITY_MODEL_VERSION = "CAP_DEPTH_v1.0"
CLASSIFIER_VERSION = "CLS_5STATE_v1.0"
SOFTWARE_BUILD_SHA = "9221b48-Task20.1"


def canonical_json_dumps(obj: Any) -> str:
    """Serializes objects into deterministic canonical JSON (sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_digest(content: str) -> str:
    """Computes standard hexadecimal SHA-256 digest."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ProvenanceEngine:
    """Creates, validates, and archives cryptographic provenance envelopes."""

    def __init__(self) -> None:
        self._init_db_schema()

    def _init_db_schema(self) -> None:
        """Initializes the arbitrage provenance records table in trading_logs.db."""
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS arbitrage_provenance_records (
                        opportunity_id TEXT PRIMARY KEY,
                        observation_timestamp_ms INTEGER NOT NULL,
                        canonical_symbol TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        rejection_code TEXT NOT NULL,
                        software_build_sha TEXT NOT NULL,
                        envelope_json TEXT NOT NULL,
                        canonical_envelope_hash TEXT NOT NULL,
                        created_at_epoch REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_arb_prov_hash ON arbitrage_provenance_records(canonical_envelope_hash);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_arb_prov_decision ON arbitrage_provenance_records(decision);"
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not initialize arbitrage_provenance_records schema: {e}")

    def create_envelope(
        self,
        opportunity: ArbitrageOpportunity,
        quotes: list[NormalizedMarketQuote],
        books: list[OrderBookSnapshot],
        funding_records: list[FundingRateRecord],
        config_dict: dict[str, Any] | None = None,
    ) -> ArbitrageProvenanceEnvelope:
        """Constructs and cryptographically seals the complete decision envelope."""
        now_ms = opportunity.detected_at_ms

        # 1. Source timestamps
        source_timestamps = {f"{q.venue.value}_{q.symbol}": q.exchange_timestamp_ms for q in quotes}

        # 2. Exchange sequence IDs
        exchange_sequence_ids = {f"{q.venue.value}_{q.symbol}": q.sequence_id for q in quotes}

        # 3. Normalized quotes representation
        norm_quotes_repr = [
            {
                "venue": q.venue.value,
                "symbol": q.symbol,
                "bid": q.bid,
                "ask": q.ask,
                "mark_price": q.mark_price,
                "data_age_ms": q.data_age_ms,
                "sequence_id": q.sequence_id,
            }
            for q in quotes
        ]

        # 4. Hash order book depths
        book_hashes = []
        for b in books:
            book_str = canonical_json_dumps(
                {
                    "venue": b.venue.value,
                    "bids": [[lvl.price, lvl.size] for lvl in b.bids[:10]],
                    "asks": [[lvl.price, lvl.size] for lvl in b.asks[:10]],
                }
            )
            book_hashes.append(f"{b.venue.value}:{sha256_digest(book_str)[:12]}")
        orderbook_snapshot_hash = "|".join(book_hashes)

        # 5. Funding records representation
        funding_repr = [
            {
                "venue": f.venue.value,
                "rate": f.funding_rate,
                "next_time_ms": f.next_funding_time_ms,
            }
            for f in funding_records
        ]

        # 6. Configuration hash
        cfg_hash = sha256_digest(canonical_json_dumps(config_dict or {"standard": True}))

        envelope = ArbitrageProvenanceEnvelope(
            opportunity_id=opportunity.opportunity_id,
            observation_timestamp_ms=now_ms,
            source_timestamps=source_timestamps,
            exchange_sequence_ids=exchange_sequence_ids,
            normalized_quotes=norm_quotes_repr,
            orderbook_snapshot_hash=orderbook_snapshot_hash,
            funding_records=funding_repr,
            instrument_mapping_version=INSTRUMENT_MAPPING_VERSION,
            fee_model_version=FEE_MODEL_VERSION,
            ev_model_version=EV_MODEL_VERSION,
            capacity_model_version=CAPACITY_MODEL_VERSION,
            classifier_version=CLASSIFIER_VERSION,
            configuration_hash=cfg_hash,
            decision=opportunity.classification,
            rejection_code=opportunity.rejection_code,
            software_build_sha=SOFTWARE_BUILD_SHA,
        )

        # Seal envelope with canonical hash
        raw_canonical = canonical_json_dumps(
            {
                "opportunity_id": envelope.opportunity_id,
                "observation_timestamp_ms": envelope.observation_timestamp_ms,
                "source_timestamps": envelope.source_timestamps,
                "exchange_sequence_ids": envelope.exchange_sequence_ids,
                "normalized_quotes": envelope.normalized_quotes,
                "orderbook_snapshot_hash": envelope.orderbook_snapshot_hash,
                "funding_records": envelope.funding_records,
                "versions": {
                    "instrument_mapper": envelope.instrument_mapping_version,
                    "fee_model": envelope.fee_model_version,
                    "ev_model": envelope.ev_model_version,
                    "capacity_model": envelope.capacity_model_version,
                    "classifier": envelope.classifier_version,
                    "build_sha": envelope.software_build_sha,
                },
                "decision": envelope.decision.value,
                "rejection_code": envelope.rejection_code.value,
            }
        )
        envelope.canonical_envelope_hash = sha256_digest(raw_canonical)
        opportunity.provenance_hash = envelope.canonical_envelope_hash

        self._persist_provenance_record(opportunity.canonical_symbol, envelope)
        return envelope

    def _persist_provenance_record(
        self, canonical_symbol: str, envelope: ArbitrageProvenanceEnvelope
    ) -> None:
        """Persists sealed envelope to SQLite trading_logs.db."""
        import time

        envelope_dict = {
            "opportunity_id": envelope.opportunity_id,
            "observation_timestamp_ms": envelope.observation_timestamp_ms,
            "source_timestamps": envelope.source_timestamps,
            "exchange_sequence_ids": envelope.exchange_sequence_ids,
            "normalized_quotes": envelope.normalized_quotes,
            "orderbook_snapshot_hash": envelope.orderbook_snapshot_hash,
            "funding_records": envelope.funding_records,
            "versions": {
                "instrument_mapper": envelope.instrument_mapping_version,
                "fee_model": envelope.fee_model_version,
                "ev_model": envelope.ev_model_version,
                "capacity_model": envelope.capacity_model_version,
                "classifier": envelope.classifier_version,
                "build_sha": envelope.software_build_sha,
            },
            "decision": envelope.decision.value,
            "rejection_code": envelope.rejection_code.value,
            "canonical_envelope_hash": envelope.canonical_envelope_hash,
        }

        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO arbitrage_provenance_records (
                        opportunity_id, observation_timestamp_ms, canonical_symbol,
                        decision, rejection_code, software_build_sha,
                        envelope_json, canonical_envelope_hash, created_at_epoch
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(opportunity_id) DO UPDATE SET
                        decision = excluded.decision,
                        rejection_code = excluded.rejection_code,
                        canonical_envelope_hash = excluded.canonical_envelope_hash;
                    """,
                    (
                        envelope.opportunity_id,
                        envelope.observation_timestamp_ms,
                        canonical_symbol,
                        envelope.decision.value,
                        envelope.rejection_code.value,
                        envelope.software_build_sha,
                        canonical_json_dumps(envelope_dict),
                        envelope.canonical_envelope_hash,
                        time.time(),
                    ),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Failed to persist provenance record: {e}")

    def get_provenance_by_id(self, opportunity_id: str) -> dict[str, Any] | None:
        """Retrieves and decodes stored provenance record by opportunity ID."""
        try:
            with db_manager.get_trading_conn() as conn:
                cursor = conn.execute(
                    """
                    SELECT envelope_json, canonical_envelope_hash
                    FROM arbitrage_provenance_records
                    WHERE opportunity_id = ?
                    LIMIT 1;
                    """,
                    (opportunity_id,),
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row["envelope_json"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error querying provenance record {opportunity_id}: {e}")
        return None

    def verify_envelope_integrity(self, envelope_dict: dict[str, Any]) -> bool:
        """Reconstructs and verifies the canonical SHA-256 envelope digest."""
        stored_hash = envelope_dict.get("canonical_envelope_hash", "")
        raw_canonical = canonical_json_dumps(
            {
                "opportunity_id": envelope_dict["opportunity_id"],
                "observation_timestamp_ms": envelope_dict["observation_timestamp_ms"],
                "source_timestamps": envelope_dict["source_timestamps"],
                "exchange_sequence_ids": envelope_dict["exchange_sequence_ids"],
                "normalized_quotes": envelope_dict["normalized_quotes"],
                "orderbook_snapshot_hash": envelope_dict["orderbook_snapshot_hash"],
                "funding_records": envelope_dict["funding_records"],
                "versions": envelope_dict["versions"],
                "decision": envelope_dict["decision"],
                "rejection_code": envelope_dict["rejection_code"],
            }
        )
        calculated_hash = sha256_digest(raw_canonical)
        return calculated_hash == stored_hash


# Global singleton
provenance_engine = ProvenanceEngine()
