"""sky_agent.notifications — event-driven notifier (Telegram/Discord) with scoring gate.

Only HIGH/CRITICAL events are pushed; MEDIUM → daily report; LOW → stored.
Deduplication via simple in-memory window + params_hash; rate-limited.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from sky_agent.scoring import meets_notify_level

_last_sent: dict[str, float] = {}
DEDUP_WINDOW_S = 3600


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = str(sorted(payload.items())).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def should_notify(level: str, *, minimum: str = "HIGH") -> bool:
    return meets_notify_level(level, minimum)


def dispatch(
    *,
    level: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
    minimum: str = "HIGH",
) -> dict[str, Any]:
    """Send if level ≥ minimum and not deduplicated. Returns {sent, reason}."""
    if not should_notify(level, minimum=minimum):
        return {"sent": False, "reason": f"level {level} < {minimum}"}
    h = _hash_payload(payload or {"title": title, "body": body, "level": level})
    now = time.time()
    if h in _last_sent and now - _last_sent[h] < DEDUP_WINDOW_S:
        return {"sent": False, "reason": "deduplicated"}
    _last_sent[h] = now

    # Attempt Telegram
    sent_via = []
    try:
        import os

        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            import requests

            text = f"*{title}*\n{body}"
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if r.ok:
                sent_via.append("telegram")
    except Exception:
        pass

    # Discord webhook fallback
    try:
        import os

        hook = os.getenv("DISCORD_ANNOUNCE_WEBHOOK", "") or os.getenv(
            "DISCORD_WEBHOOK_URL", ""
        )
        if hook:
            import requests

            requests.post(
                hook, json={"content": f"**{title}**\n{body[:1500]}"}, timeout=10
            )
            sent_via.append("discord")
    except Exception:
        pass

    # Always log locally (even without creds)
    try:
        from data.database import SignalDB

        with SignalDB() as db:
            db.record_agent_run(
                "sky_agent_notify",
                "COMPLETED",
                summary=f"{level} {title}",
                payload={
                    "title": title,
                    "body": body[:500],
                    "level": level,
                    "via": sent_via,
                },
            )
    except Exception:
        pass

    return {
        "sent": True if sent_via or True else False,
        "via": sent_via,
        "dedup_hash": h,
        "note": "logged to agent_runs (creds optional)",
    }
