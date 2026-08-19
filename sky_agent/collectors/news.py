"""sky_agent.collectors.news — thin wrapper over existing data/sources/news.py"""
from __future__ import annotations

from typing import Any


def collect_news(*, limit: int = 20) -> list[dict[str, Any]]:
    """Return scored news items. Offline-safe (DEMO_MODE returns empty)."""
    try:
        from data.sources.news import fetch_news  # type: ignore
        items = fetch_news(limit=limit)  # type: ignore
        # Normalise to agent event shape
        from sky_agent.scoring import Scores
        events = []
        for it in items or []:
            title = it.get("title") or it.get("headline") or ""
            # naive scoring: crypto keywords → higher relevance
            rel = 8 if any(k in title.lower() for k in ("bitcoin", "btc", "ethereum", "eth", "etf", "sec", "fed", "cpi")) else 4
            events.append({"title": title, "url": it.get("url") or it.get("link"), "relevance": rel, "raw": it})
        return events
    except Exception:
        return []
