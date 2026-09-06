"""engine/sentiment.py

Market-sentiment colour engine — the "mood ring" behind the dashboard's
colour signal.

The desk wants to read the market from ONE colour:

    market turning bullish  →  green, deepening to DEEP green the longer
                               the same bullish sentiment persists
    market turning bearish  →  red, deepening to STRONG red the longer
                               the same bearish sentiment persists
    no clear condition      →  neutral slate (no colour = no trade)

So sentiment has two axes:

  strength    — how far the composite score is from zero (0..1)
  persistence — how long the SAME direction has held (0..1, full after
                ``DEEP_AFTER_MIN`` minutes)

and the displayed depth is

    intensity = strength × (0.6 + 0.4 × persistence)

A fresh, strong reading paints a BRIGHT colour; only time spent in the
same condition paints it DEEP. That matches the requested behaviour:
"green to deep greener as per sentimental time duration … red to strong
red".

The composite score blends what the engine already computes:

    engine scores (bull − bear)      weight 0.50
    MTF alignment score              weight 0.20
    trend × ADX strength             weight 0.10
    funding rate sign                weight 0.05
    news sentiment tally             weight 0.05
    fear & greed index               weight 0.05
    signal action × confidence       weight 0.05
                                  ─────────
                                     1.00

History is persisted in the learning DB (``sentiment_history`` table) so
the duration clock survives dashboard restarts — persistence is about the
MARKET holding a condition, not about a browser staying open.
"""

from __future__ import annotations

import json
import time

NEUTRAL_BAND = 10.0  # |score| below this = no colour (slate)
DEEP_AFTER_MIN = 180.0  # minutes of the same direction → deepest colour
GAP_CAP_MIN = 15.0  # a history gap longer than this doesn't count as persistence
_HISTORY_WINDOW_MIN = 720  # how far back duration can reach

# Colour buckets (P16): the same thresholds as the strip labels, so the
# legend the desk sees is exactly the bucket the grader measures.
BUCKETS = ("deep_bull", "bull", "slate", "bear", "deep_bear")
BUCKET_LABELS = {
    "deep_bull": "DEEP GREEN",
    "bull": "GREEN",
    "slate": "SLATE",
    "bear": "RED",
    "deep_bear": "DEEP RED",
    "UNKNOWN": "UNKNOWN",
}

# ── helpers ────────────────────────────────────────────────────────────────


def _clamp(v: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _num(value, default: float = 0.0) -> float:
    try:
        f = float(value)
        return f if f == f else default  # NaN guard
    except (TypeError, ValueError):
        return default


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


# ── labels & colours ───────────────────────────────────────────────────────


def label(score: float) -> str:
    """Human-readable name for a composite score in [-100, +100]."""
    if score >= 65:
        return "STRONG BULLISH"
    if score >= 30:
        return "BULLISH"
    if score >= NEUTRAL_BAND:
        return "LEANING BULLISH"
    if score <= -65:
        return "STRONG BEARISH"
    if score <= -30:
        return "BEARISH"
    if score <= -NEUTRAL_BAND:
        return "LEANING BEARISH"
    return "NEUTRAL"


def direction_of(score: float) -> str:
    if score >= NEUTRAL_BAND:
        return "bullish"
    if score <= -NEUTRAL_BAND:
        return "bearish"
    return "neutral"


def bucket(score: float) -> str:
    """Colour bucket for a composite score — the exact bins the strip paints."""
    if score >= 65:
        return "deep_bull"
    if score >= NEUTRAL_BAND:
        return "bull"
    if score <= -65:
        return "deep_bear"
    if score <= -NEUTRAL_BAND:
        return "bear"
    return "slate"


def bucket_label(b: str) -> str:
    return BUCKET_LABELS.get(b, "UNKNOWN")


def colour(score: float, intensity: float) -> str:
    """CSS colour for the mood: hue green(142)/red(0), darker as intensity
    grows. Neutral returns slate — no colour means no trade."""
    if abs(score) < NEUTRAL_BAND or intensity <= 0:
        return "#5f6d84"
    hue = 142 if score > 0 else 0
    sat = 62 + 18 * _clamp(intensity, 0.0, 1.0)
    light = 55 - 28 * _clamp(intensity, 0.0, 1.0)
    return f"hsl({hue},{round(sat)}%,{round(light)}%)"


def duration_text(minutes: float) -> str:
    minutes = max(0.0, minutes)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{round(minutes)}m"
    h, m = int(minutes // 60), int(round(minutes % 60))
    return f"{h}h {m:02d}m" if m else f"{h}h"


# ── composite score ────────────────────────────────────────────────────────


def _confidence_value(conf_label) -> float:
    return {"HIGH": 90.0, "MEDIUM": 70.0, "LOW": 45.0}.get(str(conf_label).upper(), 0.0)


def _news_contribution(context: dict) -> float:
    """-100..100 from the news headline sentiment tally in the payload."""
    news = context.get("news") or {}
    headlines = news.get("headlines") or []
    if not headlines:
        return 0.0
    bull = sum(1 for h in headlines if str(h.get("sentiment", "")).lower() == "bullish")
    bear = sum(1 for h in headlines if str(h.get("sentiment", "")).lower() == "bearish")
    return _safe_div((bull - bear), len(headlines)) * 100.0


def _funding_contribution(market_context: dict) -> float:
    """Funding rate pct → -100..100 (0.05% fully bearish-flushed → strong
    bullish reading via the sign convention: extreme positive funding is a
    crowded-long warning, extreme negative is a squeeze-worthy short pile)."""
    fr = _num(market_context.get("funding_rate_pct"))
    if fr is None or fr == 0.0:
        return 0.0
    # typical |funding| ≈ 0.01% — scale so 0.05% saturates
    return _clamp(-fr * 2000.0)


def _trend_contribution(features: dict) -> float:
    trend = str(features.get("trend", "")).lower()
    bias = str(features.get("trend_bias", "")).lower()
    raw = (
        1.0
        if trend == "bullish"
        else -1.0
        if trend == "bearish"
        else (0.6 if bias == "bullish" else -0.6 if bias == "bearish" else 0.0)
    )
    if raw == 0.0:
        return 0.0
    adx = _num(features.get("adx"), 20.0)
    strength = _clamp(adx / 25.0, 0.0, 1.0)  # ADX 25+ = full-strength trend
    return raw * strength * 100.0


def compute(payload: dict) -> dict:
    """Stateless composite sentiment for one scan payload.

    Returns score ∈ [-100, +100], direction, label, strength, and the
    weighted per-input breakdown (``parts``) for full transparency.
    """
    snap = payload.get("snapshot") or {}
    scores = snap.get("scores") or {}
    features = snap.get("features") or {}
    mtf = payload.get("mtf") or {}
    alignment = mtf.get("alignment") or {}
    context = payload.get("context") or {}
    market_context = payload.get("market_context") or {}
    signal = payload.get("signal") or {}

    bull = _num((scores.get("bull") or {}).get("score"))
    bear = _num((scores.get("bear") or {}).get("score"))
    parts: list[dict] = []

    def _part(name: str, weight: float, raw: float, detail: str = "") -> None:
        parts.append(
            {
                "name": name,
                "weight": weight,
                "raw": round(_clamp(raw), 1),
                "detail": detail,
            }
        )

    # 1. engine scores (the brain's core read) — 50%
    engine_raw = _clamp(bull - bear)
    _part(
        "engine bull − bear scores",
        0.50,
        engine_raw,
        f"bull {round(bull)} vs bear {round(bear)} / 100",
    )

    # 2. multi-timeframe alignment — 20%
    align_raw = _clamp(_num(alignment.get("score")))
    _part(
        "MTF alignment",
        0.20,
        align_raw,
        f"HTF {mtf.get('htf_bias', '—')} · LTF {mtf.get('ltf_bias', '—')} "
        f"· {alignment.get('label', '—')}",
    )

    # 3. trend × ADX strength — 10%
    trend_raw = _trend_contribution(features)
    _part(
        "trend × ADX",
        0.10,
        trend_raw,
        f"trend {features.get('trend', '—')} · ADX {_num(features.get('adx'), 20):.1f}",
    )

    # 4. funding — 5%
    funding_raw = _funding_contribution(market_context)
    _part(
        "funding (crowding)",
        0.05,
        funding_raw,
        f"{_num(market_context.get('funding_rate_pct')) * 100:.3f}%/8h "
        f"({market_context.get('note', '—')[:44]})"
        if market_context.get("funding_rate_pct") is not None
        else "no futures context",
    )

    # 5. news sentiment tally — 5%
    news_raw = _news_contribution(context)
    headlines = (context.get("news") or {}).get("headlines") or []
    _part("news headlines", 0.05, news_raw, f"{len(headlines)} headlines")

    # 6. fear & greed — 5%
    fng = context.get("fear_greed") or {}
    fng_raw = (
        _clamp((_num(fng.get("value"), 50.0) - 50.0) * 2.0)
        if fng.get("available")
        else 0.0
    )
    _part(
        "fear & greed",
        0.05,
        fng_raw,
        f"{fng.get('value', '—')} {fng.get('label', '')}".strip()
        if fng.get("available")
        else "unavailable",
    )

    # 7. signal action × confidence — 5%
    action = str(signal.get("action", "")).upper()
    sig_raw = 0.0
    sig_detail = f"action {signal.get('action', '—')}"
    if action == "BUY":
        sig_raw = _confidence_value(signal.get("confidence"))
    elif action == "SELL":
        sig_raw = -_confidence_value(signal.get("confidence"))
    _part("signal action", 0.05, sig_raw, sig_detail)

    score = _clamp(sum(p["weight"] * p["raw"] for p in parts))
    for p in parts:
        p["contrib"] = round(p["weight"] * p["raw"], 1)

    n_used = sum(1 for p in parts if p["raw"] != 0.0)
    available = n_used > 0
    direction = direction_of(score) if available else "neutral"
    strength = min(abs(score) / 100.0, 1.0) if available else 0.0
    return {
        "available": available,
        "score": round(score, 1),
        "direction": direction,
        "bucket": bucket(score) if available else "slate",
        "label": label(score) if available else "NO DATA",
        "strength": round(strength, 3),
        "parts": parts,
        "sources_used": n_used,
    }


# ── historical (offline) sentiment — the P16 walk-forward proof ───────────
#
# A backtest can only know what was knowable at signal time, so the
# historical score uses the inputs the engine had on that exact bar slice:
#
#   engine bull − bear scores   weight 0.50
#   trend × ADX strength        weight 0.10
#   signal action × confidence  weight 0.05
#
# and renormalises over the available weights (0.65), keeping the same
# direction semantics as the live composite. Funding/news/fear&greed/MTF are
# live-time inputs and are deliberately absent from the offline mirror —
# the proof must not use data the walk couldn't see.

_HISTORICAL_WEIGHTS = {
    "engine": 0.50,
    "trend": 0.10,
    "signal": 0.05,
}


def compute_historical(
    bull_score: float,
    bear_score: float,
    features: dict | None = None,
    signal_action: str = "NO TRADE",
    signal_confidence: str = "",
) -> float:
    """Sentiment score from bar-slice inputs only, renormalised over the
    weights available offline. Returns a value in [-100, +100]."""
    features = features or {}
    raw = {
        "engine": _clamp(_num(bull_score) - _num(bear_score)),
        "trend": _trend_contribution(features),
        "signal": 0.0,
    }
    action = str(signal_action or "").upper()
    if action == "BUY":
        raw["signal"] = _confidence_value(signal_confidence)
    elif action == "SELL":
        raw["signal"] = -_confidence_value(signal_confidence)
    total_w = sum(_HISTORICAL_WEIGHTS.values())
    score = sum(_HISTORICAL_WEIGHTS[k] * raw[k] for k in raw) / total_w
    return round(_clamp(score), 1)


class SentimentClock:
    """Chronological persistence clock for a complete-data walk.

    Mirrors the live clock (`duration_of`) with one honest difference: the
    walk has no downtime, so elapsed bar time between two consecutive
    same-direction steps accrues in full instead of being capped at
    ``GAP_CAP_MIN``. A direction flip — or a neutral reading — resets the
    clock, exactly as the live strip does.
    """

    def __init__(self, deep_after_min: float = DEEP_AFTER_MIN):
        self.deep_after_min = deep_after_min
        self.last_ts_ms: int | None = None
        self.last_direction: str | None = None
        self.persistence_min = 0.0

    def tick(self, ts_ms: int, direction: str) -> float:
        """Register one reading; returns the persistence in minutes AFTER the
        update (0.0 when the condition broke)."""
        if (
            direction != "neutral"
            and direction == self.last_direction
            and self.last_ts_ms is not None
        ):
            self.persistence_min += max(0.0, (ts_ms - self.last_ts_ms) / 60000.0)
        else:
            self.persistence_min = 0.0
        self.last_ts_ms = ts_ms
        self.last_direction = direction
        return self.persistence_min

    def reading(self, score: float, ts_ms: int) -> dict:
        """Full sentiment tag for one walked bar: bucket, score, persistence
        and the same depth formula the dashboard paints."""
        direction = direction_of(score)
        persistence = self.tick(ts_ms, direction)
        strength = min(abs(score) / 100.0, 1.0) if direction != "neutral" else 0.0
        persistence_frac = min(persistence / self.deep_after_min, 1.0)
        intensity = (
            _depth(strength, persistence_frac) if direction != "neutral" else 0.0
        )
        return {
            "score": float(score),
            "bucket": bucket(score) if direction != "neutral" else "slate",
            "direction": direction,
            "persistence_min": round(persistence, 1),
            "persistence": round(persistence_frac, 3),
            "intensity": intensity,
        }


# ── persistence (duration clock survives restarts) ────────────────────────


def record(symbol: str, timeframe: str, result: dict) -> bool:
    """Store one sentiment reading (one row per symbol/timeframe/minute)."""
    try:
        from data.database import SignalDB

        with SignalDB() as db:
            db.save_sentiment(
                symbol=symbol,
                timeframe=timeframe,
                ts=int(time.time() * 1000),
                score=result["score"],
                direction=result["direction"],
                label=result["label"],
                parts_json=json.dumps(result.get("parts", []), default=str),
            )
        return True
    except Exception:
        return False


def history(
    symbol: str, timeframe: str, minutes: int = _HISTORY_WINDOW_MIN
) -> list[dict]:
    """Recent persisted readings, oldest first."""
    try:
        from data.database import SignalDB

        with SignalDB() as db:
            return db.sentiment_history(symbol, timeframe, minutes=minutes)
    except Exception:
        return []


def duration_of(
    rows: list[dict], direction: str, now_ms: int | None = None
) -> float:
    """Minutes the current direction has held UNINTERRUPTED, walking back
    through the history. Gaps longer than ``GAP_CAP_MIN`` don't count —
    the desk only knows the market held the condition while it watched it.

    A neutral row breaks the run: going flat resets the colour clock.
    """
    if not rows or direction == "neutral":
        return 0.0
    now_ms = now_ms or int(time.time() * 1000)
    run = 0.0
    prev_ms = now_ms
    for row in reversed(rows):
        if (row.get("direction") or "") != direction:
            break
        gap_min = max(0.0, (prev_ms - row["ts"]) / 60000.0)
        run += min(gap_min, GAP_CAP_MIN)
        prev_ms = row["ts"]
    return run


def _depth(strength: float, persistence: float) -> float:
    """Displayed colour depth: strong + persistent = deep, fresh = bright."""
    return round(strength * (0.6 + 0.4 * persistence), 3)


def current_sentiment(symbol: str, timeframe: str, payload: dict) -> dict:
    """Full pipeline for the dashboard: compute → record → measure how long
    the same sentiment has held → strength/persistence/depth → colour."""
    result = compute(payload)
    now_ms = int(time.time() * 1000)
    record(symbol, timeframe, result)
    rows = history(symbol, timeframe)
    duration = duration_of(rows, result["direction"], now_ms)
    persistence = min(duration / DEEP_AFTER_MIN, 1.0) if result["available"] else 0.0
    intensity = _depth(result["strength"], persistence) if result["available"] else 0.0

    # compact history for a sparkline (one point per minute bucket, last 90)
    spark: list[dict] = []
    last_bucket = None
    for row in rows[-180:]:
        bucket = row["ts"] // 60000
        if bucket == last_bucket:
            spark[-1] = {"ts": row["ts"], "score": row["score"]}
        else:
            spark.append({"ts": row["ts"], "score": row["score"]})
            last_bucket = bucket
        if len(spark) >= 90:
            spark = spark[-90:]

    return {
        **result,
        "symbol": symbol,
        "timeframe": timeframe,
        "duration_min": round(duration, 1),
        "duration_text": duration_text(duration) if result["available"] else "—",
        "persistence": round(persistence, 3),
        "intensity": intensity,
        "color": colour(result["score"], intensity),
        "deepening": result["direction"] != "neutral" and duration > 0,
        "history": spark,
        "updated_at": now_ms,
    }


def current_sentiment_safe(symbol: str, timeframe: str, payload: dict) -> dict:
    """Never-raise wrapper for embedding into the web payload paths."""
    try:
        return current_sentiment(symbol, timeframe, payload)
    except Exception as exc:  # pragma: no cover — defensive only
        return {
            "available": False,
            "score": 0.0,
            "direction": "neutral",
            "label": "NO DATA",
            "strength": 0.0,
            "duration_min": 0.0,
            "duration_text": "—",
            "persistence": 0.0,
            "intensity": 0.0,
            "color": "#5f6d84",
            "parts": [],
            "history": [],
            "deepening": False,
            "error": str(exc),
        }
