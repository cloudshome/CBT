"""brain/connections.py — the real-world connection registry.

One honest answer to "what is SKY actually connected to right now?".

Each entry describes a real-world link, whether it is configured, whether it
is *live* (probed just now), what it gives you, and the exact steps to switch
it on. The dashboard's **Connections** tab renders this directly, so the
trader can see and test every link by clicking instead of reading docs.

Tiers
-----
``core``      market data — the desk cannot form an opinion without it.
``context``   news / macro / sentiment — improves the read.
``alerts``    Telegram / Discord — reach you when you are away from the screen.
``ai``        LLM narrative — plain-language explanation.
``account``   READ-ONLY exchange account — your real balance and positions.

Every probe is read-only, individually timed out and exception-isolated: a
dead endpoint degrades one card, never the page.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

PROBE_TIMEOUT = 6


def _demo() -> bool:
    return os.getenv("DEMO_MODE", "0") in ("1", "true", "yes")


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


# ── individual probes ────────────────────────────────────────────────────
def _probe_http(url: str, headers: dict | None = None) -> tuple[bool, str]:
    import requests
    try:
        r = requests.get(url, timeout=PROBE_TIMEOUT,
                         headers=headers or {"User-Agent": "SKY/1.0"})
        if r.status_code < 400:
            return True, f"HTTP {r.status_code}"
        return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}"


def _probe_market_data() -> dict:
    """Public Binance spot candles — the desk's primary sense organ."""
    if _demo():
        return {"configured": True, "live": True, "mode": "demo",
                "detail": "DEMO_MODE=1 — synthetic candles, not the real market"}
    ok, detail = _probe_http("https://data-api.binance.vision/api/v3/ping")
    if not ok:
        ok2, detail2 = _probe_http("https://api.binance.com/api/v3/ping")
        ok, detail = ok2, (detail2 if ok2 else f"{detail} / {detail2}")
    return {"configured": True, "live": ok, "mode": "live", "detail": detail}


def _probe_derivatives() -> dict:
    """Funding, open interest and long/short ratio (futures endpoints)."""
    if _demo():
        return {"configured": True, "live": True, "mode": "demo",
                "detail": "DEMO_MODE=1 — synthetic derivatives"}
    ok, detail = _probe_http("https://fapi.binance.com/fapi/v1/ping")
    return {"configured": True, "live": ok, "mode": "live",
            "detail": detail if ok else
            f"{detail} — futures endpoints are geo-blocked in some regions; "
            "the desk degrades gracefully without them"}


def _probe_news() -> dict:
    if _demo():
        return {"configured": True, "live": True, "mode": "demo",
                "detail": "DEMO_MODE=1 — no live feeds"}
    ok, detail = _probe_http("https://cointelegraph.com/rss")
    return {"configured": True, "live": ok, "detail": detail}


def _probe_fear_greed() -> dict:
    if _demo():
        return {"configured": True, "live": True, "mode": "demo",
                "detail": "DEMO_MODE=1"}
    ok, detail = _probe_http("https://api.alternative.me/fng/?limit=1")
    return {"configured": True, "live": ok, "detail": detail}


def _probe_macro() -> dict:
    if _demo():
        return {"configured": True, "live": True, "mode": "demo",
                "detail": "DEMO_MODE=1"}
    ok, detail = _probe_http(
        "https://stooq.com/q/l/?s=^spx&f=sd2t2ohlcv&h&e=csv",
        headers={"User-Agent": "Mozilla/5.0"})
    return {"configured": True, "live": ok, "detail": detail}


def _probe_dominance() -> dict:
    if _demo():
        return {"configured": True, "live": True, "mode": "demo",
                "detail": "DEMO_MODE=1"}
    ok, detail = _probe_http("https://api.coingecko.com/api/v3/global")
    return {"configured": True, "live": ok, "detail": detail}


def _probe_telegram() -> dict:
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return {"configured": False, "live": False,
                "detail": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"}
    ok, detail = _probe_http(f"https://api.telegram.org/bot{token}/getMe")
    return {"configured": True, "live": ok,
            "detail": "bot reachable" if ok else detail}


def _probe_discord() -> dict:
    hook = _env("DISCORD_ANNOUNCE_WEBHOOK") or _env("DISCORD_WEBHOOK_URL")
    if not hook:
        return {"configured": False, "live": False,
                "detail": "DISCORD_WEBHOOK_URL not set"}
    return {"configured": True, "live": True,
            "detail": "webhook configured (not pinged — posting is the only test)"}


def _probe_llm() -> dict:
    provider = (_env("LLM_PROVIDER") or "off").lower()
    if provider in ("", "off", "none"):
        return {"configured": False, "live": False,
                "detail": "LLM_PROVIDER=off — the desk uses its rule-based "
                          "explanation, which needs no key"}
    if provider == "gemini":
        if not _env("GEMINI_API_KEY"):
            return {"configured": False, "live": False, "detail": "GEMINI_API_KEY not set"}
        return {"configured": True, "live": True, "detail": "Gemini key present"}
    if not _env("OPENAI_API_KEY"):
        return {"configured": False, "live": False, "detail": "OPENAI_API_KEY not set"}
    return {"configured": True, "live": True,
            "detail": f"{provider} key present ({_env('OPENAI_BASE_URL') or 'default host'})"}


def _probe_account() -> dict:
    from data.exchange_account import ExchangeAccount
    acct = ExchangeAccount()
    if not acct.configured:
        return {"configured": False, "live": False,
                "detail": "BINANCE_READ_API_KEY / _SECRET not set — SKY shows "
                          "its paper book only"}
    snap = acct.snapshot()
    if not snap.get("connected"):
        return {"configured": True, "live": False,
                "detail": snap.get("error", "could not reach the exchange")}
    detail = f"{snap.get('balance_count', 0)} funded asset(s)"
    if not snap.get("read_only", True):
        detail += " · ⚠ key has trade/withdraw permission"
    return {"configured": True, "live": True, "detail": detail,
            "read_only": snap.get("read_only", True)}


# ── the registry ─────────────────────────────────────────────────────────
CONNECTIONS: list[dict] = [
    {
        "id": "market_data", "tier": "core", "label": "Binance market data",
        "gives": "Live candles for BTC, ETH, gold proxy and any USDT pair. "
                 "This is what every signal is computed from.",
        "needs": "Nothing — public data, no account and no API key.",
        "how": ["Set DEMO_MODE=0 in your .env (or delete the line).",
                "Restart: python3 main.py"],
        "probe": _probe_market_data,
    },
    {
        "id": "derivatives", "tier": "core", "label": "Futures: funding / OI / long-short",
        "gives": "Funding rate, open interest and the long/short ratio — how "
                 "crowded and how leveraged the market is.",
        "needs": "Nothing — public futures endpoints.",
        "how": ["Set DEMO_MODE=0.",
                "If your region blocks fapi.binance.com the desk simply omits "
                "these inputs; it never guesses them."],
        "probe": _probe_derivatives,
    },
    {
        "id": "news", "tier": "context", "label": "Crypto news feeds",
        "gives": "CoinTelegraph / CoinDesk / Decrypt headlines and a naive "
                 "sentiment read, used by the context layer.",
        "needs": "Nothing — public RSS.",
        "how": ["Set DEMO_MODE=0.", "Click Refresh sources in the Command center."],
        "probe": _probe_news,
    },
    {
        "id": "fear_greed", "tier": "context", "label": "Fear & Greed index",
        "gives": "The crowd's emotional temperature — a contrarian input.",
        "needs": "Nothing — public API.",
        "how": ["Set DEMO_MODE=0."],
        "probe": _probe_fear_greed,
    },
    {
        "id": "macro", "tier": "context", "label": "Equities / macro (S&P 500)",
        "gives": "Risk-on vs risk-off context from traditional markets.",
        "needs": "Nothing — public CSV endpoint.",
        "how": ["Set DEMO_MODE=0."],
        "probe": _probe_macro,
    },
    {
        "id": "dominance", "tier": "context", "label": "Market cap & BTC dominance",
        "gives": "Total market cap and BTC dominance — is money rotating into "
                 "or out of alts.",
        "needs": "Nothing — public CoinGecko API.",
        "how": ["Set DEMO_MODE=0."],
        "probe": _probe_dominance,
    },
    {
        "id": "telegram", "tier": "alerts", "label": "Telegram alerts",
        "gives": "A message on your phone the moment a signal needs your "
                 "decision, so you do not have to watch the screen.",
        "needs": "A free Telegram bot token and your chat id.",
        "how": ["Message @BotFather on Telegram and send /newbot.",
                "Copy the token into TELEGRAM_BOT_TOKEN in your .env.",
                "Message your new bot once, then open "
                "https://api.telegram.org/bot<TOKEN>/getUpdates and copy the "
                "chat id into TELEGRAM_CHAT_ID.",
                "Restart SKY and press Test on this card."],
        "probe": _probe_telegram,
    },
    {
        "id": "discord", "tier": "alerts", "label": "Discord alerts",
        "gives": "The same alerts posted into a Discord channel you own.",
        "needs": "A channel webhook URL.",
        "how": ["In Discord: Server Settings → Integrations → Webhooks → New.",
                "Copy the URL into DISCORD_ANNOUNCE_WEBHOOK in your .env.",
                "Restart SKY and press Test on this card."],
        "probe": _probe_discord,
    },
    {
        "id": "llm", "tier": "ai", "label": "AI narrative (LLM)",
        "gives": "Plain-language explanation of the setup. Optional — the desk "
                 "already explains itself with rules and never depends on an LLM "
                 "for a decision.",
        "needs": "An API key from Groq (free tier), OpenAI or Gemini.",
        "how": ["Get a key, e.g. a free one at console.groq.com.",
                "Set LLM_PROVIDER=groq and OPENAI_API_KEY=<key> in your .env.",
                "Restart SKY."],
        "probe": _probe_llm,
    },
    {
        "id": "account", "tier": "account", "label": "Exchange account (READ-ONLY)",
        "gives": "Your real balance and real open orders shown beside the paper "
                 "book, so position sizing uses your true equity.",
        "needs": "A Binance API key with ONLY 'Enable Reading' ticked.",
        "how": ["Binance → API Management → Create API key.",
                "Tick ONLY 'Enable Reading'. Leave every trading and withdrawal "
                "permission OFF.",
                "Restrict access to your IP address.",
                "Put it in BINANCE_READ_API_KEY / BINANCE_READ_API_SECRET.",
                "Restart SKY and press Test on this card."],
        "safety": "SKY signs GET requests only and refuses any endpoint outside "
                  "its read-only allow-list. It cannot place or cancel an order.",
        "probe": _probe_account,
    },
]

TIER_LABELS = {
    "core": "Market data — required for a real signal",
    "context": "Context — improves the read",
    "alerts": "Alerts — reach you away from the screen",
    "ai": "AI narrative — optional explanation",
    "account": "Your account — read-only",
}


def probe_one(connection_id: str) -> dict:
    """Probe a single connection by id (used by the Test button)."""
    entry = next((c for c in CONNECTIONS if c["id"] == connection_id), None)
    if entry is None:
        raise ValueError(f"unknown connection: {connection_id}")
    started = time.time()
    try:
        result = entry["probe"]()
    except Exception as exc:
        result = {"configured": False, "live": False,
                  "detail": f"probe crashed: {type(exc).__name__}: {exc}"}
    result["latency_ms"] = int((time.time() - started) * 1000)
    return {**{k: v for k, v in entry.items() if k != "probe"}, **result}


def probe_all(ids: Optional[list[str]] = None) -> dict:
    """Probe every connection in parallel and summarise the result."""
    wanted = [c for c in CONNECTIONS if ids is None or c["id"] in ids]
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(wanted))) as pool:
        futures = {pool.submit(probe_one, c["id"]): c["id"] for c in wanted}
        for fut, cid in futures.items():
            try:
                results[cid] = fut.result()
            except Exception as exc:   # pragma: no cover — probe_one is guarded
                results[cid] = {"id": cid, "configured": False, "live": False,
                                "detail": f"{type(exc).__name__}: {exc}"}
    ordered = [results[c["id"]] for c in wanted if c["id"] in results]
    live = [c for c in ordered if c.get("live")]
    core_live = [c for c in ordered if c["tier"] == "core" and c.get("live")]
    core_total = sum(1 for c in ordered if c["tier"] == "core")
    demo = _demo()
    if demo:
        headline = ("DEMO MODE — synthetic data. Set DEMO_MODE=0 in .env and "
                    "restart for the real market.")
        level = "degraded"
    elif len(core_live) == core_total:
        headline = f"Connected to the real market · {len(live)}/{len(ordered)} links live"
        level = "ok"
    elif core_live:
        headline = ("Partially connected — some market data is unreachable; "
                    "the desk degrades rather than guessing")
        level = "degraded"
    else:
        headline = "No live market data — check your internet connection"
        level = "down"
    return {
        "connections": ordered,
        "tiers": TIER_LABELS,
        "demo_mode": demo,
        "live_count": len(live),
        "total": len(ordered),
        "level": level,
        "headline": headline,
    }
