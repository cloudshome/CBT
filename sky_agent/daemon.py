"""sky_agent.daemon — main 24/7 loop (systemd supervised, no LLM in idle).

Survives: terminal close, SSH disconnect, reboot (systemd), network/API failures,
rate limits, crashes, stale data, disk pressure. Every tick is idempotent.

Usage:
  python -m sky_agent.daemon          # foreground (systemd ExecStart)
  python main.py agent run --demo     # same loop in demo/offline mode
"""

from __future__ import annotations

import os
import signal
import time
from typing import Any

from sky_agent.config import (
    DERIVATIVES_POLL_SECONDS,
    EDGAR_POLL_SECONDS,
    MARKET_POLL_SECONDS,
    NEWS_POLL_SECONDS,
    SYSTEM_POLL_SECONDS,
)
from sky_agent.memory import ensure_memory_schema

_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False


try:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
except (ValueError, OSError):
    # Not in main thread (tests / MCP import) — graceful fallback
    pass


def _tick_market(demo: bool = False) -> dict[str, Any]:
    try:
        from sky_agent.monitor_market import scan_market_snapshot

        events = scan_market_snapshot(demo=demo)
        # Dispatch HIGH/CRITICAL
        for ev in events:
            lvl = ev.get("level", "LOW")
            if lvl in ("HIGH", "CRITICAL"):
                try:
                    from sky_agent.notifications import dispatch
                    from sky_agent.recommendation import (
                        build_recommendation,
                        format_alert,
                    )

                    rec = build_recommendation(
                        asset=ev.get("symbol", "BTCUSDT"),
                        timeframe=ev.get("timeframe", "15m"),
                        regime=str(
                            ev.get("interpretation", {}).get("regime", "unknown")
                        ),
                        detected=f"Market regime: {ev.get('interpretation', {}).get('regime')}",
                        evidence=[
                            f"regime={ev.get('interpretation', {}).get('regime')}",
                            f"vol={ev.get('interpretation', {}).get('volatility_state')}",
                        ],
                        expectancy_R=None,
                        sample_n=None,
                        risk_status="UNKNOWN",
                        confidence="MEDIUM",
                        kind="INTERPRETATION",
                        invalidation="Regime flip or volatility expansion",
                        sources=["SKY store"],
                    )
                    dispatch(
                        level=lvl,
                        title=f"SKY {lvl}: {ev.get('symbol')} {ev.get('timeframe')} {ev.get('interpretation', {}).get('regime')}",
                        body=format_alert(rec),
                        payload=ev,
                    )
                except Exception:
                    pass
        return {"events": len(events), "levels": [e.get("level") for e in events]}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def _tick_derivatives(demo: bool = False) -> dict[str, Any]:
    try:
        if os.getenv("DEMO_MODE") == "1" or demo:
            return {"demo": True, "metrics": ["funding_rate", "open_interest"]}

        return {"ok": True}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def _tick_news(demo: bool = False) -> dict[str, Any]:
    try:
        from sky_agent.collectors.news import collect_news

        items = collect_news(limit=10)
        return {"items": len(items)}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def _tick_edgar(demo: bool = False) -> dict[str, Any]:
    try:
        from sky_agent.collectors.edgar import ingest_recent_filings, upsert_filings

        rows = ingest_recent_filings(
            tickers=["AAPL", "MSTR", "COIN"] if not demo else None,
            demo=demo or os.getenv("DEMO_MODE") == "1",
        )
        n = upsert_filings(rows)
        # Score and notify HIGH
        for r in rows:
            try:
                from sky_agent.notifications import dispatch
                from sky_agent.scoring import score_edgar_event

                sev = int(r.get("severity", 2))
                s = score_edgar_event(severity=sev, novel=True, relevance=7)
                if s.level() in ("HIGH", "CRITICAL"):
                    dispatch(
                        level=s.level(),
                        title=f"EDGAR {r.get('form')} {r.get('ticker') or r.get('cik')} — {r.get('event_type')}",
                        body=f"{r.get('url')}\nseverity {sev} direction {r.get('direction')}",
                        payload=r,
                    )
            except Exception:
                continue
        return {"filings": n}
    except Exception as exc:
        return {"error": str(exc)[:400]}


def _tick_system(demo: bool = False) -> dict[str, Any]:
    try:
        from sky_agent.monitor_system import probe_system

        snap = probe_system()
        if snap.get("level") in ("HIGH", "CRITICAL"):
            try:
                from sky_agent.notifications import dispatch

                dispatch(
                    level=snap["level"],
                    title=f"SKY System {snap['level']}",
                    body="Alerts: " + "; ".join(snap.get("alerts", []))
                    or "system threshold crossed",
                    payload=snap,
                )
            except Exception:
                pass
        return snap
    except Exception as exc:
        return {"error": str(exc)[:300]}


def run_forever(*, demo: bool = False, max_ticks: int | None = None) -> dict[str, Any]:
    """Run the daemon loop. max_ticks is for tests (None = forever)."""
    # Ensure schema
    try:
        from data.database import SignalDB

        with SignalDB() as db:
            ensure_memory_schema(db)
    except Exception:
        pass

    ticks = 0
    # Stagger timers so not all fire at once
    last_market = 0.0
    last_deriv = 0.0
    last_news = 0.0
    last_edgar = 0.0
    last_system = 0.0

    # Backoff state
    backoff: dict[str, float] = {}

    while _running:
        now = time.monotonic()
        results: dict[str, Any] = {}

        def _due(key: str, interval: float, last: float) -> bool:
            b = backoff.get(key, 0)
            return (now - last) >= max(interval, b)

        if _due("market", MARKET_POLL_SECONDS, last_market):
            r = _tick_market(demo=demo)
            results["market"] = r
            last_market = now
            backoff["market"] = 60 if "error" in r else 0

        if _due("derivatives", DERIVATIVES_POLL_SECONDS, last_deriv):
            r = _tick_derivatives(demo=demo)
            results["derivatives"] = r
            last_deriv = now

        if _due("news", NEWS_POLL_SECONDS, last_news):
            r = _tick_news(demo=demo)
            results["news"] = r
            last_news = now

        if _due("edgar", EDGAR_POLL_SECONDS, last_edgar):
            r = _tick_edgar(demo=demo)
            results["edgar"] = r
            last_edgar = now
            backoff["edgar"] = 60 if "error" in r else 0

        if _due("system", SYSTEM_POLL_SECONDS, last_system):
            r = _tick_system(demo=demo)
            results["system"] = r
            last_system = now

        # Heartbeat (cheap log so journald shows liveness)
        if ticks % 12 == 0 and results:
            try:
                from data.database import SignalDB

                with SignalDB() as db:
                    db.record_agent_run(
                        "sky_agent_daemon",
                        "COMPLETED",
                        summary=f"tick {ticks}: {list(results.keys())}",
                        payload=results,
                    )
            except Exception:
                pass

        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            return {"ticks": ticks, "last_results": results}
        # Sleep 5s granularity (cheap idle)
        for _ in range(5):
            if not _running:
                break
            time.sleep(1)

    return {"ticks": ticks, "stopped": True}
