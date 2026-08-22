"""cli/common.py — shared helpers for the ``python main.py`` command layer.

Refactor step 2a of the main.py maintainability debt (ROADMAP §19): the
module-level helpers and the shared ``run_scan`` pipeline used to live inline
in ``main.py``; they live here now, byte-identical, and ``main`` re-exports
them so ``from main import run_scan`` (used by ``ai/mcp_server.py``) keeps
working unchanged.
"""

from __future__ import annotations

from config import SYMBOL, SYMBOLS
from data.binance_client import BinanceClient
from data.sample_client import maybe_client
from data.symbols import normalize_symbol, parse_symbol_list
from output.signal_schema import validate_output


def _client() -> BinanceClient:
    return maybe_client()


def _sym(value: str | None) -> str:
    """Normalize BTC/ETH/XAU aliases before storing or filtering signals."""
    return normalize_symbol(value or SYMBOL)


def _symbols(value: str | None) -> list[str]:
    """Parse comma-separated assets using the configured BTC/ETH/XAU watchlist."""
    return parse_symbol_list(value, default=SYMBOLS)


def _source_key_arg(value: str | None) -> str | None:
    """Resolve a ``--source-key`` CLI value into a P12.11 source key.

    ``None``/``all``  → every source (pooled, and the report says so)
    ``live``/``canonical`` → the canonical live Binance spot series (``""``)
    anything else     → parsed as ``exchange:market[:price_type]``
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("", "all", "any", "*"):
        return None
    if text in ("live", "canonical", "binance", "default"):
        from data.provenance import LIVE_SOURCE_KEY
        return LIVE_SOURCE_KEY
    from data.provenance import parse_source_key, source_key
    return source_key(*parse_source_key(text))


def _load_calibration() -> dict:
    """Load the self-improvement profile from the DB (empty dict when unused)."""
    try:
        from data.database import SignalDB
        with SignalDB() as db:
            return db.load_calibration()
    except Exception:
        return {}


def run_scan(symbol: str, timeframe: str, bars: int, with_context: bool = True,
             with_llm: bool = False, save_db: bool = True,
             auto_approve: bool = False) -> dict:
    from brain.full_pipeline import analyze_full
    symbol = _sym(symbol)
    payload = analyze_full(symbol, timeframe, bars,
                           with_context=with_context, with_memory=True)

    if with_llm:
        from ai.llm_brain import LLMBrain
        payload["llm"] = LLMBrain().generate(payload)

    payload["validation"] = validate_output(payload)

    # P15/P16 — the sentiment colour reading rides on every scan path (CLI,
    # web, MCP) so the learning store always holds the signal-time colour.
    try:
        from engine.sentiment import current_sentiment_safe
        payload["sentiment"] = current_sentiment_safe(symbol, timeframe, payload)
    except Exception:  # pragma: no cover — sentiment is a display/learning aid
        pass

    if save_db:
        from data.database import SignalDB
        from engine.lifecycle import reviewable
        with SignalDB() as db:
            sig = payload.get("signal", {})
            decision = payload.get("decision") or {}
            # Desk-first (decision A4): a signal the desk vetoed never enters
            # the human approval queue — it is recorded as a research scan.
            desk_ok = decision.get("action") in ("BUY", "SELL")
            status_override = None if desk_ok else "CREATED"
            existing = db.conn.execute(
                "SELECT id, status FROM scans WHERE signal_id=?",
                (sig.get("signal_id"),)).fetchone()
            if existing:
                scan_id = existing["id"]
                status = existing["status"]
            else:
                scan_id = db.save_scan(payload, status_override=status_override)
                status = "PENDING_REVIEW" if reviewable(sig) and desk_ok else "CREATED"
            payload["scan_id"] = scan_id
            if auto_approve and reviewable(sig) and desk_ok:
                db.update_status(scan_id, "APPROVED", note="auto-approve", reviewer="auto")
                payload["lifecycle"] = {"status": "APPROVED",
                                        "note": "auto-approved (--auto-approve)"}
            else:
                payload["lifecycle"] = {
                    "status": status,
                    "note": ("awaiting human approval — `python main.py review`"
                             if status == "PENDING_REVIEW" else
                             "monitor-only signal (no action required)" if status == "CREATED"
                             and not decision.get("blocked_by") else
                             "DESK BLOCKED — " + "; ".join(decision.get("blocked_by", []))
                             if status == "CREATED" and decision.get("blocked_by") else
                             f"current state: {status}"),
                }
    return payload
