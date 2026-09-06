"""web/chart_data.py — the chart workspace feed.

One endpoint payload that a TradingView-grade front end can draw directly:

  * OHLCV candles with epoch-second ``time`` keys (Lightweight Charts format)
  * indicator overlays (EMA 20/50/200, VWAP, Bollinger bands)
  * indicator panes (volume, RSI, MACD, ADX)
  * horizontal levels (support / resistance / pivot)
  * plan overlays (entry / stop-loss / take-profit) when a scan is supplied

Everything is converted to plain Python floats/ints here.  The dashboard's
candle endpoint used to hand Flask raw Pandas/NumPy values straight from
``df.to_dict("records")``, which raises ``TypeError: Object of type int64 is
not JSON serializable`` and left the page with no chart at all.  A single
:func:`_num` funnel makes that class of failure impossible.
"""

from __future__ import annotations

import math
from typing import Any

TF_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "1w": 604800,
    "1M": 2592000,
}


def _num(value: Any) -> float | None:
    """Any Pandas/NumPy/Python scalar → a JSON-safe float (or ``None``).

    Handles ``numpy.float64``, ``numpy.int64``, ``numpy.bool_``, ``Decimal``,
    ``pandas.Timestamp``, ``pandas.NA``/``NaT`` and plain strings. NaN and
    infinities become ``None`` so the chart draws a gap instead of crashing.
    """
    if value is None:
        return None
    try:
        if hasattr(value, "item") and not isinstance(value, (str, bytes)):
            value = value.item()  # numpy scalar → python scalar
    except Exception:  # pragma: no cover — defensive
        pass
    if isinstance(value, bool):
        return float(value)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _epoch_seconds(ts: Any) -> int | None:
    """Candle open time → epoch **seconds** (Lightweight Charts' unit)."""
    raw = _num(ts)
    if raw is None:
        # pandas.Timestamp / datetime
        for attr in ("timestamp",):
            fn = getattr(ts, attr, None)
            if callable(fn):
                try:
                    return int(fn())
                except Exception:  # pragma: no cover
                    return None
        return None
    if raw > 1e12:  # epoch milliseconds
        raw = raw / 1000.0
    elif raw > 1e15:  # epoch microseconds
        raw = raw / 1_000_000.0
    return int(raw)


def _series(frame, column: str, times: list[int]) -> list[dict]:
    """One indicator line as ``[{time, value}, …]`` with NaNs dropped."""
    if column not in frame.columns:
        return []
    out = []
    for t, raw in zip(times, frame[column].tolist()):
        val = _num(raw)
        if t is None or val is None:
            continue
        out.append({"time": t, "value": val})
    return out


def build_chart(
    df, symbol: str, timeframe: str, *, payload: dict | None = None, limit: int = 300
) -> dict:
    """Build the full chart workspace payload from an OHLCV frame.

    ``payload`` is an optional scan payload; when given, its entry / stop /
    take-profit and multi-timeframe key levels become chart overlays.
    """
    from engine.indicators import add_all_indicators

    frame = df.tail(int(limit)).reset_index(drop=True)
    try:
        frame = add_all_indicators(frame)
    except Exception:  # indicators are a display aid, never a hard gate
        pass

    times = [_epoch_seconds(t) for t in frame["ts"].tolist()]
    candles: list[dict] = []
    volume: list[dict] = []
    for i, t in enumerate(times):
        if t is None:
            continue
        o = _num(frame["open"].iloc[i])
        h = _num(frame["high"].iloc[i])
        low = _num(frame["low"].iloc[i])
        c = _num(frame["close"].iloc[i])
        if None in (o, h, low, c):
            continue
        candles.append({"time": t, "open": o, "high": h, "low": low, "close": c})
        vol = _num(frame["volume"].iloc[i]) if "volume" in frame.columns else None
        if vol is not None:
            volume.append(
                {
                    "time": t,
                    "value": vol,
                    "color": "rgba(34,197,94,.55)" if c >= o else "rgba(239,68,68,.55)",
                }
            )

    overlays = {
        "ema20": _series(frame, "ema_20", times),
        "ema50": _series(frame, "ema_50", times),
        "ema200": _series(frame, "ema_200", times),
        "vwap": _series(frame, "vwap", times),
        "bb_upper": _series(frame, "bb_upper", times),
        "bb_lower": _series(frame, "bb_lower", times),
    }
    panes = {
        "volume": volume,
        "rsi": _series(frame, "rsi", times),
        "macd": _series(frame, "macd", times),
        "macd_signal": _series(frame, "macd_signal", times),
        "macd_hist": _series(frame, "macd_hist", times),
        "adx": _series(frame, "adx", times),
    }

    last = candles[-1] if candles else {}
    prev = candles[-2] if len(candles) > 1 else last
    change_pct = None
    if last and prev and prev.get("close"):
        change_pct = round((last["close"] - prev["close"]) / prev["close"] * 100, 3)

    levels = _levels(payload)
    plan = _plan_overlay(payload)
    zones = _zones(payload)
    stats = _stats(frame, candles)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "interval_seconds": TF_SECONDS.get(timeframe, 900),
        "count": len(candles),
        "candles": candles,
        "overlays": overlays,
        "panes": panes,
        "levels": levels,
        "zones": zones,
        "plan": plan,
        "last_price": last.get("close"),
        "change_pct": change_pct,
        "stats": stats,
    }


def _stats(frame, candles: list[dict]) -> dict:
    """Latest indicator readings for the chart's header strip."""
    if not len(frame):
        return {}
    row = frame.iloc[-1]

    def get(name: str) -> float | None:
        return _num(row[name]) if name in frame.columns else None

    highs = [c["high"] for c in candles] or [0.0]
    lows = [c["low"] for c in candles] or [0.0]
    return {
        "rsi": get("rsi"),
        "adx": get("adx"),
        "atr": get("atr"),
        "atr_pct": get("atr_pct"),
        "macd": get("macd"),
        "macd_signal": get("macd_signal"),
        "vwap": get("vwap"),
        "ema20": get("ema_20"),
        "ema50": get("ema_50"),
        "ema200": get("ema_200"),
        "volume": get("volume"),
        "volume_ratio": get("volume_ratio"),
        "range_high": max(highs),
        "range_low": min(lows),
    }


def _levels(payload: dict | None) -> list[dict]:
    """Support / resistance / pivot lines from the scan's MTF key levels."""
    if not payload:
        return []
    out: list[dict] = []
    mtf = payload.get("mtf") or {}
    keys = mtf.get("key_levels") or {}
    for price in (keys.get("support") or [])[:4]:
        val = _num(price)
        if val is not None:
            out.append(
                {
                    "price": val,
                    "kind": "support",
                    "label": "Support",
                    "color": "#22c55e",
                }
            )
    for price in (keys.get("resistance") or [])[:4]:
        val = _num(price)
        if val is not None:
            out.append(
                {
                    "price": val,
                    "kind": "resistance",
                    "label": "Resistance",
                    "color": "#ef4444",
                }
            )
    pivot = _num(mtf.get("pivot"))
    if pivot is not None:
        out.append(
            {"price": pivot, "kind": "pivot", "label": "Pivot", "color": "#f59e0b"}
        )
    return out


def _zones(payload: dict | None) -> dict:
    """W2 — Smart-Money-Concept zone overlays (order blocks, fair-value gaps,
    liquidity pools, sweeps, dealing range) from the scan's market structure.

    ``payload["snapshot"]["structure"]`` already holds this data (``engine/
    structure.MarketStructure.as_dict``); the chart used to leave it as text
    only. Each zone becomes a pair of horizontal levels the front end draws as
    a translucent band. All values funnel through :func:`_num`, so a NumPy
    scalar can never reach Flask and blank the chart.
    """
    if not payload:
        return {}
    structure = (payload.get("snapshot") or {}).get("structure") or {}

    def _band(top, bottom):
        t, b = _num(top), _num(bottom)
        if t is None or b is None:
            return None
        return {"top": max(t, b), "bottom": min(t, b)}

    order_blocks = []
    for ob in (structure.get("order_blocks") or [])[-6:]:
        band = _band(ob.get("top"), ob.get("bottom"))
        if band:
            band.update(
                {
                    "side": ob.get("side"),
                    "tested": bool(ob.get("tested")),
                    "broken": bool(ob.get("broken")),
                    "kind": "order_block",
                }
            )
            order_blocks.append(band)

    fvgs = []
    for f in (structure.get("fvgs") or [])[-6:]:
        band = _band(f.get("top"), f.get("bottom"))
        if band:
            band.update(
                {"side": f.get("side"), "filled": bool(f.get("filled")), "kind": "fvg"}
            )
            fvgs.append(band)

    liquidity = []
    for price in (structure.get("liquidity_above") or [])[:4]:
        val = _num(price)
        if val is not None:
            liquidity.append({"price": val, "side": "above", "kind": "liquidity"})
    for price in (structure.get("liquidity_below") or [])[:4]:
        val = _num(price)
        if val is not None:
            liquidity.append({"price": val, "side": "below", "kind": "liquidity"})

    sweep = None
    s = structure.get("sweep")
    if s and _num(s.get("level")) is not None:
        sweep = {
            "level": _num(s.get("level")),
            "side": s.get("side"),
            "recovered": bool(s.get("recovered")),
            "kind": "sweep",
        }

    dealing_range = None
    pd_ = structure.get("premium_discount")
    if pd_:
        band = _band(pd_.get("top"), pd_.get("bottom"))
        if band:
            band.update(
                {
                    "zone": pd_.get("zone"),
                    "position": _num(pd_.get("position")),
                    "kind": "dealing_range",
                }
            )
            dealing_range = band

    return {
        "order_blocks": order_blocks,
        "fvgs": fvgs,
        "liquidity": liquidity,
        "sweep": sweep,
        "dealing_range": dealing_range,
    }


def _plan_overlay(payload: dict | None) -> dict:
    """Entry / stop / take-profit lines for the live plan."""
    if not payload:
        return {}
    sig = payload.get("signal") or {}
    plans = payload.get("plans") or []
    plan = plans[0] if plans else {}
    tps = [t for t in (plan.get("take_profits") or []) if t is not None]
    entry = _num(sig.get("entry")) or _num(plan.get("entry"))
    stop = _num(sig.get("stop_loss")) or _num(plan.get("stop_loss"))
    take = _num(sig.get("take_profit")) or (_num(tps[0]) if tps else None)
    if entry is None and stop is None and take is None:
        return {}
    return {
        "action": sig.get("action") or plan.get("action"),
        "entry": entry,
        "stop_loss": stop,
        "take_profit": take,
        "take_profits": [_num(t) for t in tps if _num(t) is not None],
        "risk_reward": _num(sig.get("risk_reward")),
        "setup": plan.get("type"),
    }
