"""brain/ritual.py — W3.2: the daily ritual that remembers what you finished.

P14 gave the desk its 10-minute daily ritual (``python main.py daily`` →
readiness → loop → gate → act). This module makes that checklist *stateful*:
each tick is remembered server-side in the ``ritual_checks`` table for the
current UTC day, so a browser refresh — or the morning after — shows exactly
what was and was not done. A new day starts empty by construction
(``PRIMARY KEY(day, name)``): yesterday's discipline never pretends to be
today's.

The step list itself is not duplicated here: it is the same payload
``brain.agent.loop_health()`` ships in ``ritual``. We only attach the
persisted ``done`` flags. Read-only with respect to trading; marking a tick
is a human note, never a permission, never a threshold.
"""
from __future__ import annotations

import time
from typing import Optional

from data.database import SignalDB

# The closed vocabulary of tickable steps. These mirror the four steps
# loop_health() publishes; anything else is rejected fail-closed.
RITUAL_STEPS: tuple[str, ...] = ("readiness", "loop", "gate", "act")


def _today(now: Optional[int] = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(
        now if now is not None else time.time()))


def ritual_today(db: SignalDB, *, now: Optional[int] = None) -> dict:
    """Today's ritual checklist: the four loop-health steps + persisted ticks.

    Returns a JSON-safe payload. If ``loop_health()`` cannot be evaluated the
    checklist still renders with the persisted state and an honest error —
    the memory must never mask an unhealthy desk.
    """
    day = _today(now)
    ticks = db.ritual_state(day)
    steps: list[dict] = []
    health_error: str | None = None
    try:
        from brain.agent import loop_health
        health = loop_health()
        raw = health.get("ritual") or []
    except Exception as exc:  # never 500 — degrade gracefully
        raw, health_error = [], f"{type(exc).__name__}: {exc}"
    # Keep server order (1..4) and attach tick state; unknown names dropped.
    for r in raw:
        name = str(r.get("name") or "")
        if name not in RITUAL_STEPS:
            continue
        tick = ticks.get(name) or {}
        steps.append({
            "step": r.get("step"),
            "name": name,
            "ok": bool(r.get("ok")),
            "label": r.get("label") or "",
            "command": r.get("command") or "",
            "done": bool(tick.get("done")),
            "done_ts": tick.get("ts"),
        })
    # If loop_health had nothing (or failed), still show the four canonical
    # steps so the user can tick off a manual ritual honestly.
    if not steps:
        for i, name in enumerate(RITUAL_STEPS, start=1):
            tick = ticks.get(name) or {}
            steps.append({
                "step": i, "name": name, "ok": None,
                "label": "(loop health unavailable — tick only what you really did)",
                "command": "",
                "done": bool(tick.get("done")), "done_ts": tick.get("ts"),
            })
    complete = all(s["done"] for s in steps)
    payload = {
        "day": day,
        "steps": steps,
        "done": sum(1 for s in steps if s["done"]),
        "total": len(steps),
        "complete": complete,
        "note": ("Ticks are a human memory, not permission — the risk gate "
                 "and graduation bar do not read them. Each UTC day starts fresh."),
    }
    if health_error:
        payload["health_error"] = health_error
    return payload


def ritual_set(db: SignalDB, name: str, done: bool, *, now: Optional[int] = None) -> dict:
    """Tick (or untick) one canonical step for today. Fail closed on unknown
    names so a client can never invent ritual history."""
    name = str(name or "").strip().lower()
    if name not in RITUAL_STEPS:
        raise ValueError(f"unknown ritual step {name!r} — allowed: {', '.join(RITUAL_STEPS)}")
    day = _today(now)
    db.ritual_mark(day, name, bool(done))
    return ritual_today(db, now=now)
