"""
Institutional Signal-Only Shadow Prediction Ledger
==================================================
Provides crash-safe, append-only, tamper-evident forward prediction tracking
with cryptographic hash chaining, precommitted trade boundaries, path-dependent
MFE/MAE recording, and complete execution isolation.

Guarantees:
- ZERO order placement capability (no execution router imports).
- Tamper-evident SHA-256 hash chaining: Each record binds to the cryptographic
  hash of the preceding record.
- Duplicate prevention via unique idempotency keys.
- Restart recovery: Full state reconstruction from ledger disk journal on boot.
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("shadow_ledger")

GENESIS_HASH = "0" * 64


@dataclass
class ShadowPredictionRecord:
    sequence_id: int
    prev_record_sha256: str
    prediction_id: str
    idempotency_key: str
    strategy_id: str
    strategy_fingerprint: str
    symbol: str
    timeframe: str
    direction: str  # "LONG" or "SHORT"
    lifecycle_state: str  # "CREATED", "ACTIVE", "RESOLVED", "INVALIDATED", "EXPIRED"
    event_timestamp_utc: str
    entry_precommitted_price: float
    stop_loss_price: float
    take_profit_price: float
    risk_unit_usd: float
    max_hold_bars: int
    bars_elapsed: int = 0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    exit_timestamp_utc: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "TAKE_PROFIT", "STOP_LOSS", "TIMEOUT_EXPIRED", "INVALIDATED"
    realized_gross_r: Optional[float] = None
    realized_fees_r: Optional[float] = None
    realized_slippage_r: Optional[float] = None
    realized_net_r: Optional[float] = None
    record_sha256: str = ""

    def compute_sha256(self) -> str:
        d = asdict(self)
        d.pop("record_sha256", None)
        canonical_bytes = json.dumps(d, sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()


class ShadowLedgerEngine:
    """
    Append-only shadow tracking engine maintaining state machines
    and cryptographic integrity at rest.
    """
    def __init__(self, ledger_file_path: Path):
        self.ledger_file_path = Path(ledger_file_path)
        self.ledger_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.records: List[ShadowPredictionRecord] = []
        self.active_predictions: Dict[str, ShadowPredictionRecord] = {}
        self.idempotency_set: set = set()
        self.last_hash: str = GENESIS_HASH
        self.next_sequence_id: int = 0
        
        self._load_and_recover()

    def _load_and_recover(self) -> None:
        """Reads ledger sequentially, validating hash chain and recovering state."""
        self.records.clear()
        self.active_predictions.clear()
        self.idempotency_set.clear()
        self.last_hash = GENESIS_HASH
        self.next_sequence_id = 0

        if not self.ledger_file_path.exists():
            return

        with open(self.ledger_file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rec = ShadowPredictionRecord(**data)
                    
                    # Verify cryptographic hash of this record
                    expected_hash = rec.compute_sha256()
                    if rec.record_sha256 != expected_hash:
                        raise ValueError(f"Tamper detected at line {line_no}: hash {rec.record_sha256} != {expected_hash}")
                        
                    # Verify hash chain continuity
                    if rec.prev_record_sha256 != self.last_hash:
                        raise ValueError(f"Broken hash chain at line {line_no}: prev {rec.prev_record_sha256} != {self.last_hash}")

                    self.records.append(rec)
                    self.idempotency_set.add(rec.idempotency_key)
                    self.last_hash = rec.record_sha256
                    self.next_sequence_id = rec.sequence_id + 1

                    # Track active state in an isolated mutable tracking dict
                    if rec.lifecycle_state in ["CREATED", "ACTIVE"]:
                        self.active_predictions[rec.prediction_id] = {
                            "prediction_id": rec.prediction_id,
                            "idempotency_key": rec.idempotency_key,
                            "strategy_id": rec.strategy_id,
                            "strategy_fingerprint": rec.strategy_fingerprint,
                            "symbol": rec.symbol,
                            "timeframe": rec.timeframe,
                            "direction": rec.direction,
                            "entry_precommitted_price": rec.entry_precommitted_price,
                            "stop_loss_price": rec.stop_loss_price,
                            "take_profit_price": rec.take_profit_price,
                            "risk_unit_usd": rec.risk_unit_usd,
                            "max_hold_bars": rec.max_hold_bars,
                            "bars_elapsed": rec.bars_elapsed,
                            "mfe_r": rec.mfe_r,
                            "mae_r": rec.mae_r
                        }
                    elif rec.lifecycle_state in ["RESOLVED", "INVALIDATED", "EXPIRED"]:
                        self.active_predictions.pop(rec.prediction_id, None)

                except Exception as e:
                    logger.error(f"Failed recovering ledger line {line_no}: {e}")
                    raise

        logger.info(f"Shadow Ledger recovered {len(self.records)} records ({len(self.active_predictions)} active).")

    def _append_record(self, record: ShadowPredictionRecord) -> ShadowPredictionRecord:
        """Appends a new record to disk atomically with cryptographic linkage."""
        record.sequence_id = self.next_sequence_id
        record.prev_record_sha256 = self.last_hash
        record.record_sha256 = record.compute_sha256()

        payload = json.dumps(asdict(record), sort_keys=True)
        with open(self.ledger_file_path, "a", encoding="utf-8") as f:
            f.write(payload + "\n")
            f.flush()
            os.fsync(f.fileno())

        self.records.append(record)
        self.last_hash = record.record_sha256
        self.next_sequence_id += 1
        return record

    def precommit_prediction(
        self,
        strategy_id: str,
        strategy_fingerprint: str,
        symbol: str,
        timeframe: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        risk_unit_usd: float,
        max_hold_bars: int,
        timestamp_utc: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Optional[ShadowPredictionRecord]:
        """
        Precommits a signal before the next bar opens.
        Returns the precommitted record, or None if duplicate.
        """
        ts = timestamp_utc or datetime.now(timezone.utc).isoformat()
        key = idempotency_key or f"{strategy_id}_{symbol}_{timeframe}_{direction}_{ts}"

        if key in self.idempotency_set:
            logger.warning(f"Duplicate prediction rejected: {key}")
            return None

        pred_id = f"PRED_{symbol}_{direction}_{ts.replace(':', '').replace('-', '')[:15]}"

        rec = ShadowPredictionRecord(
            sequence_id=0,
            prev_record_sha256="",
            prediction_id=pred_id,
            idempotency_key=key,
            strategy_id=strategy_id,
            strategy_fingerprint=strategy_fingerprint,
            symbol=symbol,
            timeframe=timeframe,
            direction=direction.upper(),
            lifecycle_state="ACTIVE",
            event_timestamp_utc=ts,
            entry_precommitted_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_unit_usd=risk_unit_usd,
            max_hold_bars=max_hold_bars
        )

        committed = self._append_record(rec)
        self.idempotency_set.add(key)
        self.active_predictions[committed.prediction_id] = {
            "prediction_id": committed.prediction_id,
            "idempotency_key": committed.idempotency_key,
            "strategy_id": committed.strategy_id,
            "strategy_fingerprint": committed.strategy_fingerprint,
            "symbol": committed.symbol,
            "timeframe": committed.timeframe,
            "direction": committed.direction,
            "entry_precommitted_price": committed.entry_precommitted_price,
            "stop_loss_price": committed.stop_loss_price,
            "take_profit_price": committed.take_profit_price,
            "risk_unit_usd": committed.risk_unit_usd,
            "max_hold_bars": committed.max_hold_bars,
            "bars_elapsed": 0,
            "mfe_r": 0.0,
            "mae_r": 0.0
        }
        return committed

    def update_bar(
        self,
        symbol: str,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        bar_timestamp_utc: str,
        taker_fee_pct: float = 0.00040,
        maker_fee_pct: float = 0.00020,
        slippage_pct: float = 0.00010
    ) -> List[ShadowPredictionRecord]:
        """
        Updates open shadow positions on bar close, tracking MFE/MAE and resolving outcomes.
        Returns list of newly resolved records.
        """
        resolved_records = []
        active_ids = list(self.active_predictions.keys())

        for pred_id in active_ids:
            pred = self.active_predictions.get(pred_id)
            if not pred or pred["symbol"] != symbol:
                continue

            pred["bars_elapsed"] += 1
            risk = pred["risk_unit_usd"]
            entry = pred["entry_precommitted_price"]
            direction = pred["direction"]

            # Update path-dependent MFE & MAE in R-multiples
            if direction == "LONG":
                favorable_price = bar_high
                adverse_price = bar_low
                cur_mfe = (favorable_price - entry) / risk
                cur_mae = (entry - adverse_price) / risk
            else:
                favorable_price = bar_low
                adverse_price = bar_high
                cur_mfe = (entry - favorable_price) / risk
                cur_mae = (adverse_price - entry) / risk

            pred["mfe_r"] = max(pred["mfe_r"], cur_mfe)
            pred["mae_r"] = max(pred["mae_r"], cur_mae)

            # Check outcome transitions
            exit_price = None
            exit_reason = None

            if direction == "LONG":
                if bar_low <= pred["stop_loss_price"]:
                    exit_price = pred["stop_loss_price"]
                    exit_reason = "STOP_LOSS"
                elif bar_high >= pred["take_profit_price"]:
                    exit_price = pred["take_profit_price"]
                    exit_reason = "TAKE_PROFIT"
                elif pred["bars_elapsed"] >= pred["max_hold_bars"]:
                    exit_price = bar_close
                    exit_reason = "TIMEOUT_EXPIRED"
            else:  # SHORT
                if bar_high >= pred["stop_loss_price"]:
                    exit_price = pred["stop_loss_price"]
                    exit_reason = "STOP_LOSS"
                elif bar_low <= pred["take_profit_price"]:
                    exit_price = pred["take_profit_price"]
                    exit_reason = "TAKE_PROFIT"
                elif pred["bars_elapsed"] >= pred["max_hold_bars"]:
                    exit_price = bar_close
                    exit_reason = "TIMEOUT_EXPIRED"

            if exit_price is not None:
                # Calculate simulated R
                if direction == "LONG":
                    gross_r = (exit_price - entry) / risk
                else:
                    gross_r = (entry - exit_price) / risk

                fees_r = ((taker_fee_pct + (maker_fee_pct if exit_reason == "TAKE_PROFIT" else taker_fee_pct)) * entry) / risk
                slip_r = (slippage_pct * entry) / risk
                net_r = gross_r - fees_r - slip_r

                # Create terminal resolution record
                resolution_rec = ShadowPredictionRecord(
                    sequence_id=0,
                    prev_record_sha256="",
                    prediction_id=pred["prediction_id"],
                    idempotency_key=f"RESOLVE_{pred['idempotency_key']}",
                    strategy_id=pred["strategy_id"],
                    strategy_fingerprint=pred["strategy_fingerprint"],
                    symbol=pred["symbol"],
                    timeframe=pred["timeframe"],
                    direction=pred["direction"],
                    lifecycle_state="RESOLVED",
                    event_timestamp_utc=bar_timestamp_utc,
                    entry_precommitted_price=pred["entry_precommitted_price"],
                    stop_loss_price=pred["stop_loss_price"],
                    take_profit_price=pred["take_profit_price"],
                    risk_unit_usd=pred["risk_unit_usd"],
                    max_hold_bars=pred["max_hold_bars"],
                    bars_elapsed=pred["bars_elapsed"],
                    mfe_r=round(pred["mfe_r"], 4),
                    mae_r=round(pred["mae_r"], 4),
                    exit_timestamp_utc=bar_timestamp_utc,
                    exit_price=round(exit_price, 4),
                    exit_reason=exit_reason,
                    realized_gross_r=round(gross_r, 4),
                    realized_fees_r=round(fees_r, 4),
                    realized_slippage_r=round(slip_r, 4),
                    realized_net_r=round(net_r, 4)
                )

                committed = self._append_record(resolution_rec)
                self.active_predictions.pop(pred["prediction_id"], None)
                resolved_records.append(committed)

        return resolved_records

    def verify_ledger_integrity(self) -> Tuple[bool, str, int]:
        """
        Validates hash-chain and internal cryptographic consistency from genesis.
        Returns: (is_valid, message, verified_record_count)
        """
        if not self.records:
            return True, "Ledger is empty", 0

        current_hash = GENESIS_HASH
        for idx, rec in enumerate(self.records):
            if rec.prev_record_sha256 != current_hash:
                return False, f"Broken chain at index {idx} (seq {rec.sequence_id}): expected prev {current_hash}, got {rec.prev_record_sha256}", idx

            computed = rec.compute_sha256()
            if rec.record_sha256 != computed:
                return False, f"Tampered record at index {idx} (seq {rec.sequence_id}): expected {computed}, got {rec.record_sha256}", idx

            current_hash = rec.record_sha256

        return True, "Cryptographic hash chain 100% verified", len(self.records)

    def export_summary(self) -> Dict[str, Any]:
        """Exports statistical summary of shadow observation records."""
        resolved = [r for r in self.records if r.lifecycle_state == "RESOLVED"]
        net_returns = [r.realized_net_r for r in resolved if r.realized_net_r is not None]
        wins = [r for r in net_returns if r > 0]
        win_rate = round(len(wins) / len(net_returns) * 100.0, 1) if net_returns else 0.0

        return {
            "total_records": len(self.records),
            "total_records_logged": len(self.records),
            "active_predictions": len(self.active_predictions),
            "active_positions_count": len(self.active_predictions),
            "resolved_predictions": len(resolved),
            "resolved_predictions_count": len(resolved),
            "net_realized_r": round(sum(net_returns), 4) if net_returns else 0.0,
            "net_cumulative_r": round(sum(net_returns), 4) if net_returns else 0.0,
            "avg_realized_net_r": round(sum(net_returns) / len(net_returns), 4) if net_returns else 0.0,
            "mean_net_r": round(sum(net_returns) / len(net_returns), 4) if net_returns else 0.0,
            "win_rate_pct": win_rate,
            "mean_mfe_r": round(sum(r.mfe_r for r in resolved) / len(resolved), 4) if resolved else 0.0,
            "mean_mae_r": round(sum(r.mae_r for r in resolved) / len(resolved), 4) if resolved else 0.0,
            "integrity_verified": self.verify_ledger_integrity()[0]
        }

    def export_audit_records(self) -> List[Dict[str, Any]]:
        """Exports all ledger records as dictionaries for auditing."""
        return [asdict(r) for r in self.records]
