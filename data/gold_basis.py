"""Read-only PAXG-vs-XAU basis and promotion-evidence audit.

This module deliberately does not pool histories, write calibration state, record
human approval, or place orders.  It measures exact-time overlap between two
separately stored series and inspects the existing sealed validation envelope.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from data.store import DEFAULT_ROOT as DEFAULT_STORE_ROOT, CandleStore
from data.validation import DEFAULT_SEAL_DIR, GRADUATION_CRITERIA


DEFAULT_MIN_OVERLAP = 100
PAXG_SOURCE = {"exchange": "binance", "market": "spot", "symbol": "PAXGUSDT"}
XAU_SOURCE = {"exchange": "dukascopy", "market": "spot", "symbol": "XAUUSD"}


def _number(value: Any, digits: int = 8) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return round(result, digits)


def _iso_ms(value: Any) -> Optional[str]:
    try:
        timestamp = pd.to_datetime(int(value), unit="ms", utc=True)
    except (TypeError, ValueError, OverflowError):
        return None
    return timestamp.isoformat().replace("+00:00", "Z")


def _source_label(source: Dict[str, str]) -> str:
    return f"{source['exchange']}:{source['market']}:{source['symbol']}"


def _clean_series(frame: pd.DataFrame, source: Dict[str, str]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Validate one stored series without interpolating or changing timestamps."""
    label = _source_label(source)
    meta: Dict[str, Any] = {
        "source": dict(source),
        "source_key": label,
        "input_rows": int(len(frame)) if frame is not None else 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "duplicate_timestamps_removed": 0,
        "price_type": "unspecified",
        "missing_price_type_rows": 0,
        "errors": [],
    }
    if frame is None or frame.empty:
        meta["errors"].append(f"No stored candles for {label}")
        return pd.DataFrame(columns=["ts", "close"]), meta

    missing = sorted({"ts", "close"} - set(frame.columns))
    if missing:
        meta["errors"].append(f"{label} is missing columns: {', '.join(missing)}")
        return pd.DataFrame(columns=["ts", "close"]), meta

    cleaned = frame.loc[:, ["ts", "close"]].copy()
    cleaned["ts"] = pd.to_numeric(cleaned["ts"], errors="coerce")
    cleaned["close"] = pd.to_numeric(cleaned["close"], errors="coerce")
    valid = cleaned["ts"].notna() & cleaned["close"].notna() & (cleaned["close"] > 0)
    meta["invalid_rows"] = int((~valid).sum())

    # Price provenance is evaluated over the observations that can actually
    # enter the alignment.  Invalid rows are already excluded and cannot make
    # a clean one-sided series look mixed; every included XAU row must still
    # name its side explicitly (enforced by ``measure_gold_basis`` below).
    if "price_type" in frame.columns:
        raw_price_types = frame.loc[valid, "price_type"]
        normalized = raw_price_types.map(
            lambda value: "" if pd.isna(value) else str(value).strip().lower()
        )
        meta["missing_price_type_rows"] = int((normalized == "").sum())
        price_types = sorted(set(normalized[normalized != ""].tolist()))
        if len(price_types) > 1:
            meta["errors"].append(
                f"{label} mixes price types ({', '.join(price_types)}); basis provenance is ambiguous"
            )
        elif price_types:
            meta["price_type"] = price_types[0]
    else:
        meta["missing_price_type_rows"] = int(valid.sum())

    cleaned = cleaned.loc[valid].copy()
    cleaned["ts"] = cleaned["ts"].astype("int64")
    duplicates = int(cleaned.duplicated(subset=["ts"], keep="last").sum())
    meta["duplicate_timestamps_removed"] = duplicates
    cleaned = cleaned.drop_duplicates(subset=["ts"], keep="last").sort_values("ts").reset_index(drop=True)
    meta["valid_rows"] = int(len(cleaned))
    if cleaned.empty:
        meta["errors"].append(f"No valid positive-price candles for {label}")
    return cleaned, meta


def _fingerprint(aligned: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for row in aligned.itertuples(index=False):
        digest.update(f"{int(row.ts)},{float(row.paxg_close):.12g},{float(row.xau_close):.12g}\n".encode())
    return digest.hexdigest()


def _correlation(left: pd.Series, right: pd.Series) -> Optional[float]:
    """Return correlation only when both vectors contain actual variation."""
    if len(left) < 2 or len(right) < 2:
        return None
    if float(left.std(ddof=0)) == 0.0 or float(right.std(ddof=0)) == 0.0:
        return None
    return _number(left.corr(right))


def measure_gold_basis(
    paxg: pd.DataFrame,
    xau: pd.DataFrame,
    *,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
    paxg_source: Optional[Dict[str, str]] = None,
    xau_source: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Measure exact-timestamp PAXG/XAU basis without filling or resampling.

    ``ok`` means the minimum overlap needed for a meaningful measurement was
    present.  It never means the series has been approved for trading.
    """
    if min_overlap < 1:
        raise ValueError("min_overlap must be at least 1")
    paxg_source = dict(paxg_source or PAXG_SOURCE)
    xau_source = dict(xau_source or XAU_SOURCE)
    paxg_clean, paxg_meta = _clean_series(paxg, paxg_source)
    xau_clean, xau_meta = _clean_series(xau, xau_source)
    errors = [*paxg_meta["errors"], *xau_meta["errors"]]
    if xau_meta["price_type"] not in ("bid", "ask"):
        errors.append(
            f"{xau_meta['source_key']} must declare one-sided bid or ask provenance"
        )
    if xau_meta["missing_price_type_rows"]:
        errors.append(
            f"{xau_meta['source_key']} has {xau_meta['missing_price_type_rows']} valid rows "
            "without price_type provenance"
        )

    aligned = paxg_clean.rename(columns={"close": "paxg_close"}).merge(
        xau_clean.rename(columns={"close": "xau_close"}), on="ts", how="inner", validate="one_to_one"
    )
    aligned = aligned.sort_values("ts").reset_index(drop=True)
    matched = int(len(aligned))
    status = "MEASURED" if matched >= min_overlap and not errors else "INSUFFICIENT_EVIDENCE"
    if matched < min_overlap:
        errors.append(f"Exact-time overlap {matched} is below required minimum {min_overlap}")

    report: Dict[str, Any] = {
        "ok": status == "MEASURED",
        "status": status,
        "research_only": True,
        "alignment": "exact_timestamp_inner_join",
        "resampled": False,
        "forward_filled": False,
        "minimum_overlap": int(min_overlap),
        "matched_rows": matched,
        "start": _iso_ms(aligned["ts"].iloc[0]) if matched else None,
        "end": _iso_ms(aligned["ts"].iloc[-1]) if matched else None,
        "paxg": paxg_meta,
        "xau": xau_meta,
        "coverage": {
            "paxg_matched_pct": _number(100.0 * matched / len(paxg_clean)) if len(paxg_clean) else None,
            "xau_matched_pct": _number(100.0 * matched / len(xau_clean)) if len(xau_clean) else None,
            "paxg_unmatched_rows": int(max(0, len(paxg_clean) - matched)),
            "xau_unmatched_rows": int(max(0, len(xau_clean) - matched)),
        },
        "basis": None,
        "tracking": None,
        "data_fingerprint_sha256": _fingerprint(aligned) if matched else None,
        "errors": errors,
        "caveats": [
            "PAXGUSDT is quoted in USDT while XAUUSD is quoted in USD; the measured spread includes that quote-currency basis.",
            "Only exact stored timestamps are compared; no gap fill, interpolation, or calendar synthesis is performed.",
            "A measured basis is research evidence, not a promotion threshold or trading approval.",
        ],
    }
    if not matched:
        return report

    basis_usd = aligned["paxg_close"] - aligned["xau_close"]
    basis_pct = 100.0 * basis_usd / aligned["xau_close"]
    basis_bps = 10000.0 * basis_usd / aligned["xau_close"]
    median_bps = float(basis_bps.median())
    report["basis"] = {
        "formula": "(PAXGUSDT_close - XAUUSD_close) / XAUUSD_close",
        "mean_usd": _number(basis_usd.mean()),
        "median_usd": _number(basis_usd.median()),
        "mean_pct": _number(basis_pct.mean()),
        "median_pct": _number(basis_pct.median()),
        "mean_bps": _number(basis_bps.mean()),
        "median_bps": _number(median_bps),
        "std_bps": _number(basis_bps.std(ddof=0)),
        "mad_bps": _number((basis_bps - median_bps).abs().median()),
        "p05_bps": _number(basis_bps.quantile(0.05)),
        "p25_bps": _number(basis_bps.quantile(0.25)),
        "p75_bps": _number(basis_bps.quantile(0.75)),
        "p95_bps": _number(basis_bps.quantile(0.95)),
        "min_bps": _number(basis_bps.min()),
        "max_bps": _number(basis_bps.max()),
        "max_abs_bps": _number(basis_bps.abs().max()),
    }

    paxg_returns = np.log(aligned["paxg_close"]).diff()
    xau_returns = np.log(aligned["xau_close"]).diff()
    return_pairs = pd.DataFrame({"paxg": paxg_returns, "xau": xau_returns}).dropna()
    level_corr = _correlation(aligned["paxg_close"], aligned["xau_close"])
    return_corr = _correlation(return_pairs["paxg"], return_pairs["xau"])
    tracking_error = (return_pairs["paxg"] - return_pairs["xau"]).std(ddof=0) * 10000.0 if len(return_pairs) else None
    report["tracking"] = {
        "price_level_correlation": level_corr,
        "log_return_correlation": return_corr,
        "tracking_error_bps": _number(tracking_error),
        "return_pairs": int(len(return_pairs)),
    }
    return report


def _seal_path(seal_dir: Path, seal_key: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in seal_key)
    return seal_dir / f"{safe}.json"


def inspect_sealed_oos(
    seal_dir: Path,
    seal_key: str,
    *,
    expected_symbol: str = "XAUUSD",
    expected_timeframe: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspect, but never create or reseal, the latest validation envelope."""
    path = _seal_path(Path(seal_dir), seal_key)
    if expected_timeframe is None:
        expected_timeframe = seal_key.rsplit("_", 1)[-1]
    base: Dict[str, Any] = {
        "available": False,
        "clears_unchanged_bar": False,
        "status": "MISSING",
        "seal_key": seal_key,
        "seal_file": str(path),
        "history_entries": 0,
        "reseal_count": 0,
        "ever_resealed": False,
        "latest_created_at": None,
        "latest_resealed": None,
        "criteria_match": False,
        "source_match": False,
        "seal_key_match": False,
        "envelope_integrity": False,
        "expected_source": {"symbol": expected_symbol, "timeframe": expected_timeframe},
        "verdict": None,
        "reasons": [],
    }
    if not path.exists():
        base["reasons"].append("No sealed validation envelope found for the Dukascopy XAU series")
        return base
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        base.update(status="INVALID")
        base["reasons"].append(f"Could not read sealed validation envelope: {exc}")
        return base

    history = raw.get("history") if isinstance(raw, dict) else None
    if not isinstance(history, list) or not history:
        base.update(status="INVALID")
        base["reasons"].append("Sealed validation envelope has no history entries")
        return base
    if not isinstance(history[-1], dict):
        base.update(status="INVALID")
        base["reasons"].append("Latest seal history entry is not an object")
        return base
    latest = history[-1]
    payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
    verdict = payload.get("verdicts", {}).get("ALL", {}) if isinstance(payload.get("verdicts"), dict) else {}
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    criteria = meta.get("criteria", {}) if isinstance(meta.get("criteria"), dict) else {}
    source_match = (
        str(meta.get("symbol", "")).upper() == str(expected_symbol).upper()
        and str(meta.get("timeframe", "")) == str(expected_timeframe)
    )
    expected = dict(GRADUATION_CRITERIA)
    criteria_match = criteria == expected
    windows = payload.get("windows", {}) if isinstance(payload.get("windows"), dict) else {}
    window_bar_met = all(
        isinstance(windows.get(name), dict) and windows[name].get("bar_met") is True
        for name in ("train", "val", "oos", "recent")
    )

    # ``data.validation.write_seal`` stores the config fingerprint at the
    # envelope root and again under the latest payload's ``seal`` record.  A
    # copied, stale, or malformed payload must never clear this audit.
    payload_seal = payload.get("seal") if isinstance(payload.get("seal"), dict) else {}
    envelope_fingerprint = raw.get("fingerprint")
    envelope_integrity = bool(
        isinstance(envelope_fingerprint, str)
        and envelope_fingerprint
        and payload_seal.get("fingerprint") == envelope_fingerprint
    )
    seal_key_match = raw.get("seal_key") == seal_key
    combined_verdict_pass = bool(
        verdict.get("status") == "PASS"
        and verdict.get("oos_met") is True
        and verdict.get("recent_met") is True
    )
    clears = bool(
        payload.get("ok") is True
        and combined_verdict_pass
        and window_bar_met
        and criteria_match
        and source_match
        and seal_key_match
        and envelope_integrity
    )
    reasons = []
    if not source_match:
        reasons.append("Envelope metadata does not match the expected XAU symbol/timeframe")
    if not seal_key_match:
        reasons.append("Envelope seal key does not match the requested XAU evidence key")
    if not envelope_integrity:
        reasons.append("Envelope fingerprint and latest payload seal do not match")
    if not criteria_match:
        reasons.append("Envelope criteria do not exactly match the current unchanged graduation bar")
    if payload.get("ok") is not True:
        reasons.append("Latest sealed validation payload is not a successful protocol run")
    if not window_bar_met:
        reasons.append("At least one train/validation/sealed-OOS/recent window misses the bar")
    if not combined_verdict_pass:
        reasons.append("Combined verdict does not pass both sealed OOS and recent checks")

    reseal_count = sum(
        1 for entry in history if isinstance(entry, dict) and entry.get("reseal") is True
    )
    base.update(
        available=True,
        clears_unchanged_bar=clears,
        status=(
            "CLEARS_BAR"
            if clears
            else "INVALID"
            if not envelope_integrity or not seal_key_match
            else "MISSES_BAR"
        ),
        history_entries=len(history),
        reseal_count=reseal_count,
        ever_resealed=bool(reseal_count),
        latest_created_at=latest.get("at"),
        latest_resealed=latest.get("reseal") is True,
        criteria_match=criteria_match,
        source_match=source_match,
        seal_key_match=seal_key_match,
        envelope_integrity=envelope_integrity,
        verdict=verdict or None,
        reasons=reasons,
    )
    return base


def build_xau_evidence_dossier(
    *,
    store_root: Path = DEFAULT_STORE_ROOT,
    seal_dir: Path = DEFAULT_SEAL_DIR,
    timeframe: str = "15m",
    bars: int = 12000,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
) -> Dict[str, Any]:
    """Build a research-only dossier from separately stored PAXG and XAU data."""
    if bars < 1:
        raise ValueError("bars must be at least 1")
    store = CandleStore(root=Path(store_root))
    paxg = store.read(**PAXG_SOURCE, timeframe=timeframe)
    xau = store.read(**XAU_SOURCE, timeframe=timeframe)
    if len(paxg) > bars:
        paxg = paxg.tail(bars).reset_index(drop=True)
    if len(xau) > bars:
        xau = xau.tail(bars).reset_index(drop=True)
    basis = measure_gold_basis(paxg, xau, min_overlap=min_overlap)
    seal_key = f"dukascopy_spot_XAUUSD_{timeframe}"
    sealed_oos = inspect_sealed_oos(Path(seal_dir), seal_key)
    eligible = bool(basis.get("ok") and sealed_oos.get("clears_unchanged_bar"))
    return {
        "ok": bool(basis.get("ok")),
        "status": "RESEARCH_ONLY",
        "timeframe": timeframe,
        "bars_requested_per_series": int(bars),
        "store_root": str(Path(store_root)),
        "basis_measurement": basis,
        "sealed_oos": sealed_oos,
        "requirements": {
            "basis_measured_not_assumed": bool(basis.get("ok")),
            "sealed_oos_clears_unchanged_bar": bool(sealed_oos.get("clears_unchanged_bar")),
            "explicit_human_approval": False,
        },
        "decision": {
            "eligible_for_human_review": eligible,
            "human_approval": "OPEN",
            "xau_tradeable": False,
            "micro_live_unlocked": False,
            "reason": (
                "Evidence is ready for explicit human review; no approval is recorded by this command."
                if eligible
                else "One or more evidence gates remain open."
            ),
        },
    }
