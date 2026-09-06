"""brain/practice.py — W3.4 practice mode + W3.6 replay tape.

W3.4: a developing trader improves by *committing to a read before seeing
the answer* and then measuring the gap honestly.

1. On the Chart tab the trader writes their own read — bias, the decision
   they would take, and (optionally) their entry / stop / target ladder —
   BEFORE opening the Signal desk.
2. The server computes the desk's current read from the same engine payload
   the desk itself decided on (``web.app.compute_payload``, ``save=False`` —
   a practice attempt never pollutes the scans table or the review queue).
3. :func:`score_attempt` grades the agreement deterministically with every
   component visible — nobody has to trust the letter grade.
4. The attempt is remembered in the ``practice_attempts`` table, and
   :func:`practice_scorecard` turns the history into a calibration mirror.

W3.6: replay hides future bars. The trader commits a read at the last
visible bar; the server walks the *next* ``horizon_bars`` candles (default
16, clamped 4–64) and grades what actually happened. Ladder fills reuse
``data.paper_trading.exit_event`` — the same conservative stop-first rule
the live paper runner uses — so two graders cannot disagree.

Safety invariants held here (the project's standing rules):

* **Practice is not evidence.** Desk agreement and tape outcomes never feed
  the risk gate, graduation, calibration, the live book, or any P12
  surface — the table is coaching memory. Tests pin that the live-book
  population is unchanged by practice rows.
* **The desk is not assumed right.** A high agreement score means "you read
  like the desk" — the desk itself still has to prove its edge in canonical
  paper trading under the unchanged +0.50R / 55% / PF 1.5 / compliance ≥90%
  bar (P12.13/P12.14). Every payload says so in ``disclaimer``.
* **The tape is not paper evidence.** A tape TP_HIT is historical playback,
  never a decided ``paper_trades`` row.
* **Fail-closed validation.** Unknown bias/decision values, partial level
  ladders, missing commit times and unbounded notes are rejected.
* **Read-only with respect to trading.** No threshold is moved, nothing is
  approved, nothing is traded.

Surfaces: ``python main.py practice``, ``GET/POST /api/practice``,
``POST /api/practice/tape``, the Chart tab ✍ PRACTICE card, the Review tab
PRACTICE CALIBRATION card, and the read-only ``practice_scorecard`` /
``cryptobrain_practice`` MCP tools. Same computation everywhere
(invariant #10).
"""

from __future__ import annotations

import time

from data.database import SignalDB

# Closed vocabularies — anything else is rejected fail-closed.
USER_BIASES: tuple[str, ...] = ("bullish", "bearish", "neutral")
USER_DECISIONS: tuple[str, ...] = ("buy", "sell", "no_trade")
TIMEFRAMES: tuple[str, ...] = (
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)

# Component weights (visible in every score payload).
MAX_BIAS = 35
MAX_DECISION = 35
MAX_LEVELS = 30

# The desk's own R:R safety floor — quoted, not moved (trading_intelligence).
RR_FLOOR = 1.5

# Double-submit guard: an identical read for the same symbol+timeframe within
# this window returns the original row instead of a duplicate.
DEDUPE_WINDOW_MS = 120_000

_NOTE_LIMIT = 500

DISCLAIMER = (
    "Practice score = agreement with the desk's current read. It is a study "
    "metric, not evidence the desk is right and never a trading permission: "
    "the desk proves itself only in canonical paper trading under the "
    "unchanged +0.50R / 55% WR / PF 1.5 / compliance ≥90% graduation bar."
)

# W3.6 — replay tape. Separate kind so desk-agreement stats stay desk-only.
TAPE_KIND = "tape"
DEFAULT_HORIZON = 16
MIN_HORIZON = 4
MAX_HORIZON = 64

TAPE_DISCLAIMER = (
    "Tape score = what the hidden future bars did after your commit. "
    "Historical playback only — not live evidence, not paper evidence, "
    "and never a trading permission. The desk proves itself only in "
    "canonical paper trading under the unchanged +0.50R / 55% WR / PF 1.5 "
    "/ compliance ≥90% graduation bar."
)


def _day_key(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))


def _f(value) -> float | None:
    """Loose scalar → float or None (never raises; NaN/inf excluded)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


# ── the desk's read ─────────────────────────────────────────────────────


def desk_read_from_payload(
    payload: dict, symbol: str = "", timeframe: str = ""
) -> dict:
    """Extract the desk's current read from an engine scan payload.

    Never raises: a missing/broken payload yields ``available: False`` and
    the caller must refuse to record the attempt (an unscorable attempt
    would corrupt the calibration history).
    """
    if not isinstance(payload, dict) or not payload:
        return {
            "available": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "reason": "no engine payload",
        }
    try:
        sig = payload.get("signal") or {}
        snap = payload.get("snapshot") or {}
        feats = snap.get("features") or {}
        scores = snap.get("scores") or {}
        bull = _f((scores.get("bull") or {}).get("score"))
        bear = _f((scores.get("bear") or {}).get("score"))
        if bull is None and bear is None:
            bias = None  # genuinely unknown — treated as neutral at scoring
        elif (bull or 0.0) > (bear or 0.0):
            bias = "bullish"
        elif (bear or 0.0) > (bull or 0.0):
            bias = "bearish"
        else:
            bias = "neutral"
        action = str(sig.get("action") or "NO TRADE").upper()
        if action not in ("BUY", "SELL", "NO TRADE"):
            action = "NO TRADE"
        plans = payload.get("plans") or []
        top = None
        for p in plans:
            if isinstance(p, dict) and p.get("primary"):
                top = p
                break
        if top is None and plans and isinstance(plans[0], dict):
            top = plans[0]
        intel = payload.get("intelligence") or {}
        return {
            "available": True,
            "symbol": symbol or str(sig.get("asset") or ""),
            "timeframe": timeframe or str(sig.get("timeframe") or ""),
            "action": action,
            "bias": bias,
            "entry": _f(sig.get("entry")),
            "stop": _f(sig.get("stop_loss")),
            "target": _f(sig.get("take_profit")),
            "risk_reward": _f(sig.get("risk_reward")),
            "confidence": sig.get("confidence"),
            "plan_type": (top or {}).get("plan_type"),
            "regime": feats.get("regime_name") or intel.get("regime_label"),
            "atr": _f(feats.get("atr")),
            "price": _f(feats.get("price")),
            "bull_score": bull,
            "bear_score": bear,
            "signal_id": sig.get("signal_id"),
        }
    except Exception as exc:  # pragma: no cover — defensive
        return {
            "available": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "reason": f"{type(exc).__name__}: {exc}",
        }


# ── validation (fail closed) ────────────────────────────────────────────


def validate_user_read(body: dict) -> dict:
    """Validate one practice-read submission. Raises ``ValueError`` with a
    human reason on anything off the closed vocabulary — nothing is coerced
    into history silently."""
    if not isinstance(body, dict):
        raise ValueError("practice read must be an object")
    symbol = str(body.get("symbol") or "").strip().upper().replace("/", "")
    if not symbol or len(symbol) > 20 or not symbol.isalnum():
        raise ValueError(f"bad symbol {body.get('symbol')!r} — e.g. BTCUSDT")
    tf = str(body.get("tf") or body.get("timeframe") or "").strip()
    if tf not in TIMEFRAMES:
        raise ValueError(f"bad timeframe {tf!r} — allowed: {', '.join(TIMEFRAMES)}")
    bias = str(body.get("bias") or "").strip().lower()
    if bias not in USER_BIASES:
        raise ValueError(f"unknown bias {bias!r} — allowed: {', '.join(USER_BIASES)}")
    decision = str(body.get("decision") or "").strip().lower()
    if decision not in USER_DECISIONS:
        raise ValueError(
            f"unknown decision {decision!r} — allowed: {', '.join(USER_DECISIONS)}"
        )

    entry = _f(body.get("entry"))
    stop = _f(body.get("stop"))
    target = _f(body.get("target"))
    given = [v is not None for v in (entry, stop, target)]
    if any(given) and not all(given):
        raise ValueError(
            "give all three of entry/stop/target or none — a half-plan is not a plan"
        )
    for name, v in (("entry", entry), ("stop", stop), ("target", target)):
        if v is not None and v <= 0:
            raise ValueError(f"{name} must be a positive price")
    confidence = body.get("confidence")
    if confidence in (None, ""):
        confidence = None
    else:
        try:
            confidence = int(confidence)
        except (TypeError, ValueError):
            raise ValueError("confidence must be an integer 0-100")
        if not 0 <= confidence <= 100:
            raise ValueError("confidence must be an integer 0-100")
    note = str(body.get("note") or "").strip()[:_NOTE_LIMIT]
    return {
        "symbol": symbol,
        "tf": tf,
        "bias": bias,
        "decision": decision,
        "entry": entry,
        "stop": stop,
        "target": target,
        "confidence": confidence,
        "note": note,
        "levels_given": all(given),
    }


# ── deterministic scoring ───────────────────────────────────────────────


def _grade_of(total: float) -> str:
    # Same bands as the weekly review's advisory grade (brain/weekly.py).
    return (
        "A"
        if total >= 85
        else "B"
        if total >= 70
        else "C"
        if total >= 50
        else "D"
        if total >= 30
        else "E"
    )


def _decision_of_action(action: str) -> str:
    return {"BUY": "buy", "SELL": "sell"}.get(action, "no_trade")


def score_attempt(user: dict, desk: dict) -> dict:
    """Score one committed read against the desk's read. Deterministic, every
    component visible; the grade letters match the weekly review's bands.

    ``user`` must already be validated (:func:`validate_user_read`).
    ``desk`` comes from :func:`desk_read_from_payload` and must be available.
    """
    if not desk.get("available"):
        raise ValueError("desk read unavailable — attempt is not scored")
    comps: list[dict] = []

    # 1. directional bias (35)
    desk_bias = desk.get("bias") or "neutral"
    if user["bias"] == desk_bias:
        b_pts = MAX_BIAS
        b_detail = f"both {desk_bias}"
    elif "neutral" in (user["bias"], desk_bias):
        b_pts = 15
        b_detail = f"you {user['bias']} vs desk {desk_bias} — one side neutral"
    else:
        b_pts = 0
        b_detail = f"you {user['bias']} vs desk {desk_bias} — opposite"
    comps.append(
        {
            "name": "directional bias",
            "points": b_pts,
            "max": MAX_BIAS,
            "detail": b_detail,
        }
    )

    # 2. the final call (35)
    desk_dec = _decision_of_action(desk.get("action") or "NO TRADE")
    if user["decision"] == desk_dec:
        d_pts = MAX_DECISION
        d_detail = f"both {desk_dec}"
    elif user["decision"] == "no_trade":
        d_pts = 15
        d_detail = (
            f"desk says {desk_dec}, you passed — safe, but missed the desk's trade"
        )
    else:
        d_pts = 0
        d_detail = f"desk says {desk_dec}, you said {user['decision']}" + (
            " — you overruled the desk's NO TRADE filter"
            if desk_dec == "no_trade"
            else " — wrong side of the desk"
        )
    comps.append(
        {
            "name": "final call (buy / sell / no-trade)",
            "points": d_pts,
            "max": MAX_DECISION,
            "detail": d_detail,
        }
    )

    # 3. the ladder (30) — only when you committed levels AND the desk trades
    desk_trade = desk.get("action") in ("BUY", "SELL") and desk.get("entry")
    if user["levels_given"] and desk_trade:
        ref = desk.get("atr") or (0.005 * float(desk["entry"]))
        ref = ref if ref and ref > 0 else 0.005 * float(desk["entry"])
        gap = abs(user["entry"] - float(desk["entry"]))
        e_pts = (
            10 if gap <= 0.5 * ref else 7 if gap <= ref else 4 if gap <= 2 * ref else 0
        )
        long = user["decision"] == "buy"
        side_ok = (
            (user["stop"] < user["entry"]) if long else (user["stop"] > user["entry"])
        )
        s_pts = 10 if side_ok else 0
        risk = abs(user["entry"] - user["stop"])
        reward = (
            (user["target"] - user["entry"])
            if long
            else (user["entry"] - user["target"])
        )
        rr = reward / risk if risk > 0 else 0.0
        r_pts = 10 if rr >= RR_FLOOR else 5 if rr >= 1.0 else 0
        l_pts = e_pts + s_pts + r_pts
        comps.append(
            {
                "name": "the ladder (entry / stop / target)",
                "points": l_pts,
                "max": MAX_LEVELS,
                "detail": (
                    f"entry gap {gap:.6g} vs 1×ref {ref:.6g} → {e_pts}/10 · "
                    f"stop {'right' if side_ok else 'WRONG'} side → {s_pts}/10 · "
                    f"your R:R {rr:.2f} vs ≥{RR_FLOOR} floor → {r_pts}/10"
                ),
            }
        )
        total = b_pts + d_pts + l_pts
        earned_max = MAX_BIAS + MAX_DECISION + MAX_LEVELS
    else:
        why = (
            "you committed no entry/stop/target ladder"
            if not user["levels_given"]
            else "the desk itself is NO TRADE here — no ladder to place against"
        )
        comps.append(
            {
                "name": "the ladder (entry / stop / target)",
                "points": None,
                "max": 0,
                "detail": f"not scored — {why}",
            }
        )
        total = round(100.0 * (b_pts + d_pts) / (MAX_BIAS + MAX_DECISION))
        earned_max = MAX_BIAS + MAX_DECISION

    return {
        "total": int(round(total)),
        "earned_max": earned_max,
        "grade": _grade_of(total),
        "components": comps,
        "bias_match": b_pts == MAX_BIAS,
        "decision_match": d_pts == MAX_DECISION,
        "desk_action": desk.get("action"),
        "desk_bias": desk_bias,
        "disclaimer": DISCLAIMER,
    }


# ── W3.6 replay tape (outcome vs the hidden forward window) ─────────────


def _as_epoch_ms(raw) -> int:
    """Candle open time → epoch milliseconds. Accepts seconds or ms."""
    value = int(float(raw))
    if value < 0:
        raise ValueError("commit_time must be a positive epoch")
    if value < 10**11:  # seconds
        return value * 1000
    return value


def normalize_horizon(raw) -> int:
    """Closed horizon: default 16, clamped 4–64. Fail closed on garbage."""
    if raw in (None, ""):
        return DEFAULT_HORIZON
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"horizon_bars must be an integer {MIN_HORIZON}-{MAX_HORIZON}")
    if n < MIN_HORIZON or n > MAX_HORIZON:
        raise ValueError(f"horizon_bars must be {MIN_HORIZON}-{MAX_HORIZON} (got {n})")
    return n


def frame_to_ohlc(frame) -> list[dict]:
    """DataFrame → list of {ts, open, high, low, close} (ts in epoch-ms)."""
    if frame is None:
        return []
    try:
        empty = bool(getattr(frame, "empty", True))
    except Exception:
        return []
    if empty:
        return []
    out: list[dict] = []
    for row in frame.itertuples(index=False):
        data = row._asdict() if hasattr(row, "_asdict") else dict(row)
        ts = _f(data.get("ts"))
        o, h, low, c = (
            _f(data.get("open")),
            _f(data.get("high")),
            _f(data.get("low")),
            _f(data.get("close")),
        )
        if ts is None or o is None or h is None or low is None or c is None:
            continue
        try:
            ts_ms = _as_epoch_ms(ts)
        except ValueError:
            continue
        out.append({"ts": ts_ms, "open": o, "high": h, "low": low, "close": c})
    out.sort(key=lambda r: r["ts"])
    return out


def load_ohlc(
    symbol: str, timeframe: str, *, bars: int = 500, client=None
) -> list[dict]:
    """Fetch the same series the chart draws (DEMO_MODE stays offline)."""
    if client is None:
        from data.sample_client import maybe_client

        client = maybe_client()
    df = client.klines(symbol, timeframe, max(int(bars), 60))
    return frame_to_ohlc(df)


def locate_commit(candles: list[dict], commit_ms: int) -> int:
    """Index of the commit bar. Fail closed if the bar is not on the series."""
    if not candles:
        raise ValueError("no candles to grade against")
    try:
        commit_ms = _as_epoch_ms(commit_ms)
    except (TypeError, ValueError):
        raise ValueError("commit_time must be a candle open time (epoch seconds or ms)")
    for i, c in enumerate(candles):
        if int(c["ts"]) == int(commit_ms):
            return i
    # Half-bar slack: Lightweight Charts seconds vs store milliseconds.
    for i, c in enumerate(candles):
        if abs(int(c["ts"]) - int(commit_ms)) <= 500:
            return i
    raise ValueError(
        "commit_time is not a loaded candle — freeze replay on a visible bar"
    )


def _atr_proxy(bar: dict) -> float:
    """One-bar range, floored so we never divide by zero."""
    span = abs(float(bar["high"]) - float(bar["low"]))
    floor = 0.001 * abs(float(bar["close"]))
    return span if span > floor else (floor if floor > 0 else 1.0)


def validate_tape_request(body: dict) -> tuple[dict, int, int]:
    """Fail-closed tape payload → (user, commit_ms, horizon)."""
    user = validate_user_read(body)
    raw = body.get("commit_time", body.get("commit_ts"))
    if raw in (None, ""):
        raise ValueError(
            "commit_time is required — freeze replay at the bar you are reading"
        )
    try:
        commit_ms = _as_epoch_ms(raw)
    except (TypeError, ValueError):
        raise ValueError("commit_time must be a candle open time (epoch seconds or ms)")
    if commit_ms <= 0:
        raise ValueError("commit_time must be a positive epoch")
    horizon = normalize_horizon(body.get("horizon_bars"))
    if user["levels_given"] and user["decision"] in ("buy", "sell"):
        from data.paper_trading import PaperTradeError, validate_levels

        side = "BUY" if user["decision"] == "buy" else "SELL"
        try:
            validate_levels(side, user["entry"], user["stop"], user["target"])
        except PaperTradeError as exc:
            raise ValueError(str(exc)) from exc
    return user, commit_ms, horizon


def walk_tape(user: dict, future: list[dict], commit: dict) -> dict:
    """The W3.6 outcome contract. ``future`` is the hidden forward window.

    * no-trade → ATR-normalised close-to-close move (standing aside).
    * buy/sell without a ladder → signed ATR move of the close.
    * buy/sell with a ladder → ``exit_event`` walk, stop-first on ties.
    """
    if not future:
        raise ValueError("no forward window — rewind replay or load more history")
    commit_close = float(commit["close"])
    atr = _atr_proxy(commit)
    end_close = float(future[-1]["close"])
    horizon = len(future)

    if user["decision"] == "no_trade":
        move = abs(end_close - commit_close) / atr
        return {
            "outcome": "STOOD_ASIDE",
            "move_atr": round(move, 3),
            "rr_achieved": None,
            "ambiguous": False,
            "bars_used": horizon,
            "exit_price": end_close,
            "mae": None,
            "mfe": None,
            "atr": atr,
            "commit_close": commit_close,
            "end_close": end_close,
        }

    if not user["levels_given"]:
        delta = end_close - commit_close
        if user["decision"] == "sell":
            delta = -delta
        return {
            "outcome": "DIRECTION",
            "move_atr": round(delta / atr, 3),
            "rr_achieved": None,
            "ambiguous": False,
            "bars_used": horizon,
            "exit_price": end_close,
            "mae": None,
            "mfe": None,
            "atr": atr,
            "commit_close": commit_close,
            "end_close": end_close,
        }

    from data.paper_trading import exit_event

    trade = {
        "action": "BUY" if user["decision"] == "buy" else "SELL",
        "entry": user["entry"],
        "stop_loss": user["stop"],
        "take_profit": user["target"],
    }
    entry = float(user["entry"])
    mae = mfe = 0.0
    for i, candle in enumerate(future):
        if user["decision"] == "buy":
            mae = max(mae, max(0.0, entry - float(candle["low"])))
            mfe = max(mfe, max(0.0, float(candle["high"]) - entry))
        else:
            mae = max(mae, max(0.0, float(candle["high"]) - entry))
            mfe = max(mfe, max(0.0, entry - float(candle["low"])))
        event = exit_event(trade, candle)
        if event is None:
            continue
        return {
            "outcome": event["outcome"],
            "rr_achieved": event["rr_achieved"],
            "ambiguous": bool(event.get("ambiguous")),
            "bars_used": i + 1,
            "exit_price": event["exit_price"],
            "mae": round(mae, 6),
            "mfe": round(mfe, 6),
            "atr": atr,
            "commit_close": commit_close,
            "end_close": float(candle["close"]),
            "move_atr": None,
        }
    return {
        "outcome": "EXPIRED",
        "rr_achieved": 0.0,
        "ambiguous": False,
        "bars_used": horizon,
        "exit_price": end_close,
        "mae": round(mae, 6),
        "mfe": round(mfe, 6),
        "atr": atr,
        "commit_close": commit_close,
        "end_close": end_close,
        "move_atr": None,
    }


def score_tape(user: dict, walk: dict) -> dict:
    """Visible components from a :func:`walk_tape` result. Grade bands match
    the weekly / W3.4 letters so the mirror stays comparable."""
    outcome = walk.get("outcome") or "EXPIRED"
    comps: list[dict] = []
    if outcome == "STOOD_ASIDE":
        move = float(walk.get("move_atr") or 0.0)
        if move < 0.5:
            pts, detail = (
                100,
                (
                    f"price stayed inside 0.5 ATR ({move:.2f}) — "
                    "standing aside was right"
                ),
            )
        elif move < 1.0:
            pts, detail = (
                55,
                (f"price drifted {move:.2f} ATR — chop; standing aside is defensible"),
            )
        else:
            pts, detail = 25, f"price moved {move:.2f} ATR — you missed a move"
        comps.append(
            {"name": "standing aside", "points": pts, "max": 100, "detail": detail}
        )
    elif outcome == "DIRECTION":
        move = float(walk.get("move_atr") or 0.0)
        if move >= 0.5:
            pts, detail = 85, f"price moved {move:.2f} ATR your way"
        elif move > -0.5:
            pts, detail = 45, "price chopped — direction not proven"
        else:
            pts, detail = 0, f"price moved {abs(move):.2f} ATR against you"
        comps.append(
            {
                "name": "direction vs the tape",
                "points": pts,
                "max": 100,
                "detail": detail,
            }
        )
    elif outcome == "TP_HIT":
        rr = walk.get("rr_achieved")
        pts, detail = (
            100,
            (
                f"target hit in {walk.get('bars_used')} bars ({rr:+.2f}R)"
                if rr is not None
                else f"target hit in {walk.get('bars_used')} bars"
            ),
        )
        comps.append(
            {"name": "ladder vs the tape", "points": pts, "max": 100, "detail": detail}
        )
    elif outcome == "STOP_LOSS":
        extra = (
            " — ambiguous candle, conservative stop-first"
            if walk.get("ambiguous")
            else ""
        )
        pts, detail = 0, f"stop hit in {walk.get('bars_used')} bars{extra}"
        comps.append(
            {"name": "ladder vs the tape", "points": pts, "max": 100, "detail": detail}
        )
    else:
        risk = 0.0
        if (
            user.get("levels_given")
            and user.get("entry") is not None
            and user.get("stop") is not None
        ):
            risk = abs(float(user["entry"]) - float(user["stop"]))
        mfe_r = (float(walk.get("mfe") or 0.0) / risk) if risk else 0.0
        if mfe_r >= 1.0:
            pts, detail = (
                40,
                (f"window expired; MFE {mfe_r:.2f}R — right idea, not enough time"),
            )
        else:
            pts, detail = 20, "window expired without target or stop"
        comps.append(
            {"name": "ladder vs the tape", "points": pts, "max": 100, "detail": detail}
        )

    total = int(comps[0]["points"])
    return {
        "kind": TAPE_KIND,
        "total": total,
        "earned_max": 100,
        "grade": _grade_of(total),
        "outcome": outcome,
        "rr_achieved": walk.get("rr_achieved"),
        "ambiguous": bool(walk.get("ambiguous")),
        "bars_used": walk.get("bars_used"),
        "move_atr": walk.get("move_atr"),
        "mae": walk.get("mae"),
        "mfe": walk.get("mfe"),
        "components": comps,
        "disclaimer": TAPE_DISCLAIMER,
    }


def submit_tape_attempt(
    db: SignalDB, body: dict, candles: list[dict], *, now_ms: int | None = None
) -> dict:
    """Validate, walk the hidden window, score and remember one tape read.

    ``candles`` must be the same series the chart loaded (server-fetched —
    the client cannot supply the future). A double-submit of the same read
    at the same commit bar within two minutes returns the original row.
    """
    user, commit_ms, horizon = validate_tape_request(body)
    idx = locate_commit(candles, commit_ms)
    future = candles[idx + 1 : idx + 1 + horizon]
    if len(future) < MIN_HORIZON:
        raise ValueError(
            f"need at least {MIN_HORIZON} hidden bars after the commit "
            f"(have {len(future)}) — rewind replay or load more history"
        )
    commit = candles[idx]
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)

    last = db.latest_practice_attempt(user["symbol"], user["tf"])
    if last and now_ms - int(last["ts"]) <= DEDUPE_WINDOW_MS:
        last_score = last.get("score") or {}
        last_desk = last.get("desk_read") or {}
        if (
            last_score.get("kind") == TAPE_KIND
            and last.get("user_read") == user
            and int(last_desk.get("commit_time") or 0) == int(commit_ms)
        ):
            return {
                "duplicate": True,
                "attempt": last["attempt"],
                "user": last["user_read"],
                "desk": last["desk_read"],
                "score": last["score"],
                "disclaimer": TAPE_DISCLAIMER,
            }

    walk = walk_tape(user, future, commit)
    score = score_tape(user, walk)
    tape = {
        "kind": TAPE_KIND,
        "available": True,
        "symbol": user["symbol"],
        "timeframe": user["tf"],
        "commit_time": commit_ms,
        "commit_close": commit["close"],
        "horizon_bars": horizon,
        "future_bars": len(future),
        "outcome": walk["outcome"],
        "bars_used": walk["bars_used"],
        "rr_achieved": walk.get("rr_achieved"),
        "ambiguous": walk.get("ambiguous"),
        "end_close": walk.get("end_close"),
    }
    attempt_id = db.save_practice_attempt(
        user["symbol"], user["tf"], user, tape, score, ts=now_ms
    )
    attempt = {
        "id": attempt_id,
        "ts": now_ms,
        "day": _day_key(now_ms),
        "symbol": user["symbol"],
        "timeframe": user["tf"],
        "kind": TAPE_KIND,
    }
    return {
        "duplicate": False,
        "attempt": attempt,
        "user": user,
        "desk": tape,
        "score": score,
        "disclaimer": TAPE_DISCLAIMER,
    }


# ── persistence ─────────────────────────────────────────────────────────


def submit_attempt(
    db: SignalDB, body: dict, desk_read: dict, *, now_ms: int | None = None
) -> dict:
    """Validate, score and remember one practice attempt.

    A double-submit (identical read on the same symbol+timeframe within two
    minutes) returns the original row marked ``duplicate`` instead of
    inflating the calibration history.
    """
    user = validate_user_read(body)
    if not desk_read.get("available"):
        raise ValueError("desk read unavailable — attempt not recorded")
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)

    last = db.latest_practice_attempt(user["symbol"], user["tf"])
    if (
        last
        and now_ms - int(last["ts"]) <= DEDUPE_WINDOW_MS
        and last.get("user_read") == user
        and (last.get("score") or {}).get("kind") != TAPE_KIND
    ):
        return {
            "duplicate": True,
            "attempt": last["attempt"],
            "user": last["user_read"],
            "desk": last["desk_read"],
            "score": last["score"],
            "disclaimer": DISCLAIMER,
        }

    score = score_attempt(user, desk_read)
    attempt_id = db.save_practice_attempt(
        user["symbol"], user["tf"], user, desk_read, score, ts=now_ms
    )
    attempt = {
        "id": attempt_id,
        "ts": now_ms,
        "day": _day_key(now_ms),
        "symbol": user["symbol"],
        "timeframe": user["tf"],
    }
    return {
        "duplicate": False,
        "attempt": attempt,
        "user": user,
        "desk": desk_read,
        "score": score,
        "disclaimer": DISCLAIMER,
    }


# ── the calibration mirror ──────────────────────────────────────────────

_COACHING = {
    "bias": (
        "Read direction before setups: your bias diverges from the desk's "
        "weighted bull/bear condition scores. Write the higher-timeframe "
        "structure read first (BOS/CHOCH, premium/discount), then let "
        "indicators confirm — never the other way round."
    ),
    "decision": (
        "Your final buy/sell/stand-aside call diverges even when the "
        "direction is close. A right idea at the wrong trigger is "
        "still a wrong trade — compare your trigger against the IF "
        "condition of the desk's plan before committing."
    ),
    "levels": (
        "Placement is the weak link: stops belong on the far side of "
        "the level that invalidates the idea, and the desk will not "
        f"take less than {RR_FLOOR}R. Rehearse the full ladder — "
        "entry, stop, target — on every read, not just direction."
    ),
}


def _is_tape(row: dict) -> bool:
    return (row.get("score") or {}).get("kind") == TAPE_KIND


def _tape_block(tape_rows: list[dict]) -> dict:
    """Sibling scorecard for W3.6 tape attempts. Never mixed into desk n."""
    n = len(tape_rows)
    scores = [int((r.get("score") or {}).get("total") or 0) for r in tape_rows]
    outcomes: dict[str, int] = {}
    for r in tape_rows:
        key = str((r.get("score") or {}).get("outcome") or "—")
        outcomes[key] = outcomes.get(key, 0) + 1
    decided = outcomes.get("TP_HIT", 0) + outcomes.get("STOP_LOSS", 0)
    wins = outcomes.get("TP_HIT", 0)
    recent = [
        {
            "id": r.get("id"),
            "day": _day_key(int(r.get("ts") or 0)),
            "symbol": r.get("symbol"),
            "timeframe": r.get("timeframe"),
            "user_decision": (r.get("user_read") or {}).get("decision"),
            "outcome": (r.get("score") or {}).get("outcome"),
            "score": (r.get("score") or {}).get("total"),
            "grade": (r.get("score") or {}).get("grade"),
            "kind": TAPE_KIND,
        }
        for r in tape_rows[:10]
    ]
    if n == 0:
        coaching = (
            "No tape reads yet — start Replay on the Chart tab, freeze "
            "at a bar, commit your read, and the hidden future grades you."
        )
    else:
        coaching = (
            "Tape scores measure what the hidden bars did after your "
            "commit. They are historical playback, not paper evidence "
            "and not permission."
        )
    return {
        "n": n,
        "avg_score": round(sum(scores) / n, 1) if n else None,
        "best_score": max(scores) if n else None,
        "worst_score": min(scores) if n else None,
        "outcomes": outcomes,
        "win_rate": round(wins / decided, 3) if decided else None,
        "recent": recent,
        "coaching": coaching,
        "disclaimer": TAPE_DISCLAIMER,
    }


def practice_scorecard(
    db: SignalDB, days: int = 30, *, now_ms: int | None = None
) -> dict:
    """Aggregate practice history into the calibration mirror.

    Read-only coaching memory — no P12 surface ever reads it. ``days`` is the
    window (default 30), ``now_ms`` injects "now" so tests are deterministic.

    Desk-agreement keys (``n``, ``bias_agreement``, …) stay desk-only so a
    tape history cannot rewrite the W3.4 mirror. Tape attempts live under
    the sibling ``tape`` block.
    """
    days = max(1, int(days))
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    since_ts = now_ms - days * 86_400_000
    all_rows = db.practice_attempts(days=days, limit=500)
    rows = [r for r in all_rows if not _is_tape(r)]
    tape_rows = [r for r in all_rows if _is_tape(r)]

    n = len(rows)
    scores = [int((r.get("score") or {}).get("total") or 0) for r in rows]
    bias_hits = sum(1 for r in rows if (r.get("score") or {}).get("bias_match"))
    dec_hits = sum(1 for r in rows if (r.get("score") or {}).get("decision_match"))
    grades: dict[str, int] = {}
    for r in rows:
        g = str((r.get("score") or {}).get("grade") or "—")
        grades[g] = grades.get(g, 0) + 1

    # Component means, normalized to 0..1, so the weakest link is comparable.
    comp_sum = {"bias": 0.0, "decision": 0.0, "levels": 0.0}
    comp_max = {"bias": 0, "decision": 0, "levels": 0}
    for r in rows:
        for c in (r.get("score") or {}).get("components") or []:
            name = str(c.get("name") or "")
            key = (
                "bias"
                if name.startswith("directional")
                else "decision"
                if name.startswith("final call")
                else "levels"
                if name.startswith("the ladder")
                else None
            )
            if key is None or c.get("points") is None or not c.get("max"):
                continue
            comp_sum[key] += float(c["points"])
            comp_max[key] += int(c["max"])
    comp_means = {
        k: (round(comp_sum[k] / comp_max[k], 3) if comp_max[k] else None)
        for k in comp_sum
    }
    weakest = None
    for k, mean in comp_means.items():
        if mean is None:
            continue
        if weakest is None or mean < comp_means[weakest]:
            weakest = k
    # Perfect agreement has no weakest link — say so instead of naming one.
    if weakest is not None and comp_means[weakest] >= 1.0:
        weakest = None

    recent = [
        {
            "id": r.get("id"),
            "day": _day_key(int(r.get("ts") or 0)),
            "symbol": r.get("symbol"),
            "timeframe": r.get("timeframe"),
            "user_bias": (r.get("user_read") or {}).get("bias"),
            "user_decision": (r.get("user_read") or {}).get("decision"),
            "desk_bias": (r.get("score") or {}).get("desk_bias"),
            "desk_action": (r.get("score") or {}).get("desk_action"),
            "score": (r.get("score") or {}).get("total"),
            "grade": (r.get("score") or {}).get("grade"),
            "kind": "desk",
        }
        for r in rows[:10]
    ]

    if n == 0:
        coaching = (
            "No practice attempts yet — on the Chart tab, commit your "
            "own read (bias → call → ladder) BEFORE opening the Signal "
            "desk, and the mirror starts filling in."
        )
    elif weakest is None:
        coaching = (
            "Full agreement on every scored component in this window. "
            "That measures reading like the desk — not that the desk "
            "is right. The desk's own proof stays the canonical paper "
            "book under the unchanged graduation bar."
        )
    else:
        coaching = _COACHING.get(weakest or "bias")

    return {
        "window": {
            "days": days,
            "since_ts": since_ts,
            "until_ts": now_ms,
            "label": f"{_day_key(since_ts)} → {_day_key(now_ms)}",
        },
        "n": n,
        "bias_agreement": round(bias_hits / n, 3) if n else None,
        "decision_agreement": round(dec_hits / n, 3) if n else None,
        "avg_score": round(sum(scores) / n, 1) if n else None,
        "best_score": max(scores) if n else None,
        "worst_score": min(scores) if n else None,
        "grades": grades,
        "component_means": comp_means,
        "weakest_component": weakest,
        "coaching": coaching,
        "recent": recent,
        "tape": _tape_block(tape_rows),
        "disclaimer": DISCLAIMER,
    }


def format_practice_scorecard(sc: dict) -> str:
    """Boxed human report — the text twin of the Review-tab card
    (``python main.py practice``)."""

    def _pct(v):
        return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "n/a"

    w = sc["window"]
    lines = [
        "=" * 74,
        f"PRACTICE CALIBRATION — your read vs the desk  ({w['label']})",
        "-" * 74,
        f"  attempts       {sc['n']}   ·   avg score {_fmt_num(sc['avg_score'])}/100"
        f"   ·   best {_fmt_num(sc['best_score'])}  worst {_fmt_num(sc['worst_score'])}",
        f"  agreement      bias {_pct(sc['bias_agreement'])}   ·   "
        f"final call {_pct(sc['decision_agreement'])}",
    ]
    if sc["grades"]:
        tally = "  ".join(
            f"{g}×{sc['grades'][g]}" for g in "ABCDE" if sc["grades"].get(g)
        )
        lines.append(f"  grades         {tally}")
    means = sc.get("component_means") or {}
    if any(v is not None for v in means.values()):
        lines.append(
            "  components     "
            + "   ·   ".join(
                f"{k} {_pct(v)}" for k, v in means.items() if v is not None
            )
        )
    lines += [
        "-" * 74,
        f"  WEAKEST LINK → {sc.get('weakest_component') or '—'}",
        f"     {sc.get('coaching') or ''}",
    ]
    if sc["recent"]:
        lines.append("-" * 74)
        lines.append("  recent attempts (newest first):")
        for r in sc["recent"]:
            lines.append(
                f"    #{r['id']:<4} {r['day']}  {r['symbol']:<9} {r['timeframe']:<4} "
                f"you {r['user_decision'] or '?'!s:<9} vs desk "
                f"{r['desk_action'] or '?'!s:<9} → {r['score']:>3}/100 ({r['grade']})"
            )
    tape = sc.get("tape") or {}
    if tape.get("n"):
        outs = tape.get("outcomes") or {}
        tally = "  ".join(f"{k}×{outs[k]}" for k in sorted(outs))
        lines += [
            "-" * 74,
            f"  TAPE (replay)  {tape['n']} reads   ·   avg {_fmt_num(tape.get('avg_score'))}/100"
            f"   ·   ladder win rate {_pct(tape.get('win_rate'))}",
            f"  outcomes       {tally or '—'}",
            f"     {tape.get('coaching') or ''}",
        ]
        for r in tape.get("recent") or []:
            lines.append(
                f"    #{r['id']:<4} {r['day']}  {r['symbol']:<9} {r['timeframe']:<4} "
                f"you {r['user_decision'] or '?'!s:<9} → "
                f"{r['outcome'] or '?'!s:<12} {r['score']:>3}/100 ({r['grade']})"
            )
    lines += [
        "-" * 74,
        f"  {sc['disclaimer']}",
        "=" * 74,
    ]
    return "\n".join(lines)


def _fmt_num(v) -> str:
    return str(v) if isinstance(v, (int, float)) else "n/a"
