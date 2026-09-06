"""output/notifiers.py

Push CryptoBrain signals to Telegram and/or Discord (webhook) channels.
All pushes are best-effort — failures are logged, never raised.
"""

from __future__ import annotations

import requests

from config import DISCORD_ANNOUNCE_WEBHOOK, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def format_signal_message(signal: dict, plans: list | None = None) -> str:
    lines = [
        f"**{signal.get('action')} {signal.get('asset')}** — {signal.get('timeframe')}",
        f"`{signal.get('signal_id')}`  conf: {signal.get('confidence')}",
        f"Entry: {signal.get('entry')}  SL: {signal.get('stop_loss')}  TP: {signal.get('take_profit')}",
        f"RR: {signal.get('risk_reward')}",
        f"Reason: {signal.get('reason')}",
    ]
    if plans:
        lines.append("")
        lines.append("Conditional plans:")
        for p in plans[:4]:
            lines.append(
                f"  • {p['type']} ({p['confidence']}%) — {p['condition'][:120]}"
            )
    lines.append("")
    lines.append("⚠️ Not financial advice. Use stop-losses.")
    return "\n".join(lines)


def notify_telegram(
    signal: dict,
    plans: list | None = None,
    token: str = TELEGRAM_BOT_TOKEN,
    chat_id: str = TELEGRAM_CHAT_ID,
) -> bool:
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": format_signal_message(signal, plans),
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def notify_discord(
    signal: dict, plans: list | None = None, webhook: str = DISCORD_ANNOUNCE_WEBHOOK
) -> bool:
    if not webhook:
        return False
    try:
        r = requests.post(
            webhook, json={"content": format_signal_message(signal, plans)}, timeout=10
        )
        return r.status_code in (200, 204)
    except requests.RequestException:
        return False


def notify_all(signal: dict, plans: list | None = None) -> dict:
    return {
        "telegram": notify_telegram(signal, plans),
        "discord": notify_discord(signal, plans),
    }


TEST_MESSAGE = (
    "✅ *SKY test alert*\n"
    "Your alert channel is connected.\n\n"
    "This is what a signal notification will look like. SKY only ever *tells* "
    "you — it never places an order. You still approve every trade yourself."
)


def send_test_alert(channel: str) -> dict:
    """Send a real test message so the user can confirm alerts reach them.

    ``channel`` is ``telegram`` or ``discord``. Returns a result dict rather
    than raising, so the dashboard's Test button can always render an answer.
    """
    channel = (channel or "").strip().lower()
    if channel == "telegram":
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return {
                "ok": False,
                "channel": channel,
                "error": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set "
                "in your .env",
            }
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": TEST_MESSAGE,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if r.status_code == 200:
                return {
                    "ok": True,
                    "channel": channel,
                    "detail": "sent — check your Telegram",
                }
            return {
                "ok": False,
                "channel": channel,
                "error": f"Telegram returned {r.status_code}: {r.text[:160]}",
            }
        except requests.RequestException as exc:
            return {
                "ok": False,
                "channel": channel,
                "error": f"{type(exc).__name__}: {exc}",
            }
    if channel == "discord":
        if not DISCORD_ANNOUNCE_WEBHOOK:
            return {
                "ok": False,
                "channel": channel,
                "error": "DISCORD_ANNOUNCE_WEBHOOK is not set in your .env",
            }
        try:
            r = requests.post(
                DISCORD_ANNOUNCE_WEBHOOK, json={"content": TEST_MESSAGE}, timeout=10
            )
            if r.status_code in (200, 204):
                return {
                    "ok": True,
                    "channel": channel,
                    "detail": "sent — check your Discord channel",
                }
            return {
                "ok": False,
                "channel": channel,
                "error": f"Discord returned {r.status_code}: {r.text[:160]}",
            }
        except requests.RequestException as exc:
            return {
                "ok": False,
                "channel": channel,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return {
        "ok": False,
        "channel": channel,
        "error": "unknown alert channel — use 'telegram' or 'discord'",
    }
