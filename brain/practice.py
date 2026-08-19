"""brain/practice.py — W3.4 practice mode: your read vs the desk's, scored.

The last W3 item: a developing trader improves by *committing to a read
before seeing the answer* and then measuring the gap honestly. Flow:

1. On the Chart tab the trader writes their own read — bias, the decision
   they would take, and (optionally) their entry / stop / target ladder —
   BEFORE opening the Signal desk.
2. The server computes the desk's current read from the same engine payload
   the desk itself decided on (``web.app.compute_payload``, ``save=False`` —
   a practice attempt never pollutes the scans table or the review queue).
3. :func:`score_attempt` grades the agreement deterministically with every
   component visible — nobody has to trust the letter grade.
4. The attempt is remembered in the ``practice_attempts`` table, and
   :func:`practice_scorecard` turns the history into a calibration mirror:
   how often your bias agrees with the desk, how often your final call does,
   which component is weakest, and one deterministic coaching takeaway.

Safety invariants held here (the project's standing rules):

* **Practice is not evidence.** Agreement with the desk never feeds the risk
  gate, graduation, calibration, the live book, or any P12 surface — the
  table is coaching memory, like the journal and the ritual ticks. Tests pin
  that the live-book population is unchanged by practice rows.
* **The desk is not assumed right.** A high agreement score means "you read
  like the desk" — the desk itself still has to prove its edge in canonical
  paper trading under the unchanged +0.50R / 55% / PF 1.5 / compliance ≥90%
  bar (P12.13/P12.14). Every payload says so in ``disclaimer``.
* **Fail-closed validation.** Unknown bias/decision values, partial level
  ladders and unbounded notes are rejected, never coerced into history.
* **Read-only with respect to trading.** No threshold is moved, nothing is
  approved, nothing is traded.

Surfaces: ``python main.py practice``, ``GET/POST /api/practice``, the Chart
tab ✍ PRACTICE card, the Review tab PRACTICE CALIBRATION card, and the
read-only ``practice_scorecard`` / ``cryptobrain_practice`` MCP tools. Same
computation everywhere (invariant #10).
"""
from __future__ import annotations

import time
from typing import Optional

from data.database import SignalDB

# Closed vocabularies — anything else is rejected fail-closed.
USER_BIASES: tuple[str, ...] = ("bullish", "bearish", "neutral")
USER_DECISIONS: tuple[str, ...] = ("buy", "sell", "no_trade")
TIMEFRAMES: tuple[str, ...] = ("1m", "3m", "5m", "15m", "30m", "1h", "2h",
                               "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M")

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


def _day_key(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))


def _f(value) -> Optional[float]:
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


def desk_read_from_payload(payload: dict, symbol: str = "",
                           timeframe: str = "") -> dict:
    """Extract the desk's current read from an engine scan payload.

    Never raises: a missing/broken payload yields ``available: False`` and
    the caller must refuse to record the attempt (an unscorable attempt
    would corrupt the calibration history).
    """
    if not isinstance(payload, dict) or not payload:
        return {"available": False, "symbol": symbol, "timeframe": timeframe,
                "reason": "no engine payload"}
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
        return {"available": False, "symbol": symbol, "timeframe": timeframe,
                "reason": f"{type(exc).__name__}: {exc}"}


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
            f"unknown decision {decision!r} — allowed: {', '.join(USER_DECISIONS)}")

    entry = _f(body.get("entry"))
    stop = _f(body.get("stop"))
    target = _f(body.get("target"))
    given = [v is not None for v in (entry, stop, target)]
    if any(given) and not all(given):
        raise ValueError(
            "give all three of entry/stop/target or none — a half-plan is not a plan")
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
        "symbol": symbol, "tf": tf, "bias": bias, "decision": decision,
        "entry": entry, "stop": stop, "target": target,
        "confidence": confidence, "note": note,
        "levels_given": all(given),
    }


# ── deterministic scoring ───────────────────────────────────────────────


def _grade_of(total: float) -> str:
    # Same bands as the weekly review's advisory grade (brain/weekly.py).
    return ("A" if total >= 85 else "B" if total >= 70 else
            "C" if total >= 50 else "D" if total >= 30 else "E")


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
    comps.append({"name": "directional bias", "points": b_pts, "max": MAX_BIAS,
                  "detail": b_detail})

    # 2. the final call (35)
    desk_dec = _decision_of_action(desk.get("action") or "NO TRADE")
    if user["decision"] == desk_dec:
        d_pts = MAX_DECISION
        d_detail = f"both {desk_dec}"
    elif user["decision"] == "no_trade":
        d_pts = 15
        d_detail = f"desk says {desk_dec}, you passed — safe, but missed the desk's trade"
    else:
        d_pts = 0
        d_detail = (f"desk says {desk_dec}, you said {user['decision']}"
                    + (" — you overruled the desk's NO TRADE filter" if desk_dec == "no_trade"
                       else " — wrong side of the desk"))
    comps.append({"name": "final call (buy / sell / no-trade)", "points": d_pts,
                  "max": MAX_DECISION, "detail": d_detail})

    # 3. the ladder (30) — only when you committed levels AND the desk trades
    desk_trade = desk.get("action") in ("BUY", "SELL") and desk.get("entry")
    if user["levels_given"] and desk_trade:
        ref = desk.get("atr") or (0.005 * float(desk["entry"]))
        ref = ref if ref and ref > 0 else 0.005 * float(desk["entry"])
        gap = abs(user["entry"] - float(desk["entry"]))
        e_pts = 10 if gap <= 0.5 * ref else 7 if gap <= ref else 4 if gap <= 2 * ref else 0
        long = user["decision"] == "buy"
        side_ok = (user["stop"] < user["entry"]) if long else (user["stop"] > user["entry"])
        s_pts = 10 if side_ok else 0
        risk = abs(user["entry"] - user["stop"])
        reward = (user["target"] - user["entry"]) if long else (user["entry"] - user["target"])
        rr = reward / risk if risk > 0 else 0.0
        r_pts = 10 if rr >= RR_FLOOR else 5 if rr >= 1.0 else 0
        l_pts = e_pts + s_pts + r_pts
        comps.append({
            "name": "the ladder (entry / stop / target)", "points": l_pts,
            "max": MAX_LEVELS,
            "detail": (f"entry gap {gap:.6g} vs 1×ref {ref:.6g} → {e_pts}/10 · "
                       f"stop {'right' if side_ok else 'WRONG'} side → {s_pts}/10 · "
                       f"your R:R {rr:.2f} vs ≥{RR_FLOOR} floor → {r_pts}/10")})
        total = b_pts + d_pts + l_pts
        earned_max = MAX_BIAS + MAX_DECISION + MAX_LEVELS
    else:
        why = ("you committed no entry/stop/target ladder"
               if not user["levels_given"] else
               "the desk itself is NO TRADE here — no ladder to place against")
        comps.append({"name": "the ladder (entry / stop / target)", "points": None,
                      "max": 0, "detail": f"not scored — {why}"})
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


# ── persistence ─────────────────────────────────────────────────────────


def submit_attempt(db: SignalDB, body: dict, desk_read: dict,
                   *, now_ms: Optional[int] = None) -> dict:
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
    if last and now_ms - int(last["ts"]) <= DEDUPE_WINDOW_MS and \
            last.get("user_read") == user:
        return {"duplicate": True, "attempt": last["attempt"],
                "user": last["user_read"], "desk": last["desk_read"],
                "score": last["score"], "disclaimer": DISCLAIMER}

    score = score_attempt(user, desk_read)
    attempt_id = db.save_practice_attempt(
        user["symbol"], user["tf"], user, desk_read, score, ts=now_ms)
    attempt = {"id": attempt_id, "ts": now_ms, "day": _day_key(now_ms),
               "symbol": user["symbol"], "timeframe": user["tf"]}
    return {"duplicate": False, "attempt": attempt, "user": user,
            "desk": desk_read, "score": score, "disclaimer": DISCLAIMER}


# ── the calibration mirror ──────────────────────────────────────────────

_COACHING = {
    "bias": ("Read direction before setups: your bias diverges from the desk's "
             "weighted bull/bear condition scores. Write the higher-timeframe "
             "structure read first (BOS/CHOCH, premium/discount), then let "
             "indicators confirm — never the other way round."),
    "decision": ("Your final buy/sell/stand-aside call diverges even when the "
                 "direction is close. A right idea at the wrong trigger is "
                 "still a wrong trade — compare your trigger against the IF "
                 "condition of the desk's plan before committing."),
    "levels": ("Placement is the weak link: stops belong on the far side of "
               "the level that invalidates the idea, and the desk will not "
               f"take less than {RR_FLOOR}R. Rehearse the full ladder — "
               "entry, stop, target — on every read, not just direction."),
}


def practice_scorecard(db: SignalDB, days: int = 30,
                       *, now_ms: Optional[int] = None) -> dict:
    """Aggregate practice history into the calibration mirror.

    Read-only coaching memory — no P12 surface ever reads it. ``days`` is the
    window (default 30), ``now_ms`` injects "now" so tests are deterministic.
    """
    days = max(1, int(days))
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    since_ts = now_ms - days * 86_400_000
    rows = db.practice_attempts(days=days, limit=500)

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
            key = ("bias" if name.startswith("directional") else
                   "decision" if name.startswith("final call") else
                   "levels" if name.startswith("the ladder") else None)
            if key is None or c.get("points") is None or not c.get("max"):
                continue
            comp_sum[key] += float(c["points"])
            comp_max[key] += int(c["max"])
    comp_means = {k: (round(comp_sum[k] / comp_max[k], 3) if comp_max[k] else None)
                  for k in comp_sum}
    weakest = None
    for k, mean in comp_means.items():
        if mean is None:
            continue
        if weakest is None or mean < comp_means[weakest]:
            weakest = k
    # Perfect agreement has no weakest link — say so instead of naming one.
    if weakest is not None and comp_means[weakest] >= 1.0:
        weakest = None

    recent = [{
        "id": r.get("id"), "day": _day_key(int(r.get("ts") or 0)),
        "symbol": r.get("symbol"), "timeframe": r.get("timeframe"),
        "user_bias": (r.get("user_read") or {}).get("bias"),
        "user_decision": (r.get("user_read") or {}).get("decision"),
        "desk_bias": (r.get("score") or {}).get("desk_bias"),
        "desk_action": (r.get("score") or {}).get("desk_action"),
        "score": (r.get("score") or {}).get("total"),
        "grade": (r.get("score") or {}).get("grade"),
    } for r in rows[:10]]

    if n == 0:
        coaching = ("No practice attempts yet — on the Chart tab, commit your "
                    "own read (bias → call → ladder) BEFORE opening the Signal "
                    "desk, and the mirror starts filling in.")
    elif weakest is None:
        coaching = ("Full agreement on every scored component in this window. "
                    "That measures reading like the desk — not that the desk "
                    "is right. The desk's own proof stays the canonical paper "
                    "book under the unchanged graduation bar.")
    else:
        coaching = _COACHING.get(weakest or "bias")

    return {
        "window": {"days": days, "since_ts": since_ts, "until_ts": now_ms,
                   "label": f"{_day_key(since_ts)} → {_day_key(now_ms)}"},
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
        tally = "  ".join(f"{g}×{sc['grades'][g]}" for g in "ABCDE" if sc["grades"].get(g))
        lines.append(f"  grades         {tally}")
    means = sc.get("component_means") or {}
    if any(v is not None for v in means.values()):
        lines.append("  components     " + "   ·   ".join(
            f"{k} {_pct(v)}" for k, v in means.items() if v is not None))
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
                f"you {str(r['user_decision'] or '?'):<9} vs desk "
                f"{str(r['desk_action'] or '?'):<9} → {r['score']:>3}/100 ({r['grade']})")
    lines += [
        "-" * 74,
        f"  {sc['disclaimer']}",
        "=" * 74,
    ]
    return "\n".join(lines)


def _fmt_num(v) -> str:
    return str(v) if isinstance(v, (int, float)) else "n/a"
