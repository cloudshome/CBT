"""sky_agent.monitor_market — continuous market-data poller (cheap, idempotent).

Reads stored Parquet or live public klines, validates via data/quality,
classifies regime, and emits scored events. No LLM in the hot loop.
"""
from __future__ import annotations

import time
from typing import Any

from config import SYMBOLS, TIMEFRAME
from sky_agent.scoring import score_market_event
from sky_agent.memory import ensure_memory_schema, record_regime


def _resolve_symbols() -> list[str]:
    from sky_agent.config import WATCH_SYMBOLS_RAW
    from data.symbols import parse_symbol_list
    if WATCH_SYMBOLS_RAW.strip():
        return parse_symbol_list(WATCH_SYMBOLS_RAW)
    return list(SYMBOLS)


def _resolve_timeframes() -> list[str]:
    from sky_agent.config import WATCH_TIMEFRAMES_RAW
    return [t.strip() for t in WATCH_TIMEFRAMES_RAW.split(",") if t.strip()]


def scan_market_snapshot(*, demo: bool = False) -> list[dict[str, Any]]:
    """One polling pass: fetch → validate → regime → score. Returns scored events."""
    try:
        from data.sample_client import maybe_client
        from data.quality import check_series as _quality  # optional
    except Exception:
        _quality = None  # type: ignore

    from engine.regime import classify_market_regime
    from engine.features import build_features  # if available
    from data.database import SignalDB

    symbols = _resolve_symbols()
    timeframes = _resolve_timeframes()
    events: list[dict[str, Any]] = []
    now = int(time.time())

    client = None
    try:
        from data.sample_client import maybe_client as _mc
        client = _mc()
    except Exception:
        client = None

    for sym in symbols:
        for tf in timeframes:
            try:
                # Prefer stored Parquet; fall back to live fetch (sample in demo)
                df = None
                if client is not None:
                    try:
                        # BinanceClient-style klines
                        raw = client.klines(sym, tf, limit=120)
                        import pandas as pd
                        if raw:
                            df = pd.DataFrame(raw)
                            # Normalise column names if needed
                            if "close" not in df.columns and len(df.columns) >= 6:
                                df.columns = ["open_time", "open", "high", "low", "close", "volume"] + [f"c{i}" for i in range(len(df.columns) - 6)]
                    except Exception:
                        df = None

                if df is None or len(df) < 20:
                    continue

                # Build light features if available
                features: dict[str, Any] = {}
                try:
                    from engine.features import build_features as _bf
                    features = _bf(df) or {}
                except Exception:
                    # Fallback: minimal
                    features = {"adx": 0, "trend": "mixed", "bb_compress": False, "atr_pct": 1.0, "volume_ratio": 1.0}

                regime = classify_market_regime(df, features)

                # Score: volatility expansion or trap → higher urgency
                impact = 7 if regime.get("trap_detected") or regime.get("fake_breakout") else 4
                if regime.get("regime") in ("VOLATILITY_EXPANSION",):
                    impact = 8
                scores = score_market_event(
                    relevance=7,
                    impact=impact,
                    confidence=7,
                    urgency=6 if regime.get("trap_detected") else 3,
                    novel=False,
                    relation=6,
                )
                events.append({
                    "kind": "market_regime",
                    "symbol": sym,
                    "timeframe": tf,
                    "ts": now,
                    "fact": {"close": float(df["close"].iloc[-1]) if "close" in df.columns else None, "regime": regime.get("regime")},
                    "interpretation": regime,
                    "scores": scores,
                    "level": scores.level(),
                })

                # Persist regime log (best-effort)
                try:
                    from data.database import SignalDB
                    with SignalDB() as db:
                        ensure_memory_schema(db)
                        record_regime(db, symbol=sym, timeframe=tf, regime=str(regime.get("regime")), volatility_state=str(regime.get("volatility_state")), details=regime)
                except Exception:
                    pass

            except Exception as exc:
                events.append({"kind": "market_error", "symbol": sym, "timeframe": tf, "error": str(exc), "level": "LOW"})
                continue

    return events
