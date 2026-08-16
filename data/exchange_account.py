"""data/exchange_account.py — READ-ONLY exchange account connection.

Lets SKY show your **real** balance and **real** open positions next to its
paper book, so the desk is grounded in your actual account instead of a
number you typed into a form.

Hard safety contract
--------------------
This module can only ever *read*:

* the allow-list :data:`READ_ONLY_PATHS` is the complete set of endpoints it
  will sign — account snapshot, open orders, recent trades;
* :meth:`ExchangeAccount._signed_get` is the only request method, and it
  issues **GET** requests exclusively. There is no POST/DELETE path in this
  file, so "place order" and "cancel order" are not merely discouraged, they
  are absent;
* :func:`assert_read_only_key` refuses a key whose exchange permissions
  include spot/margin/futures trading or withdrawals, so a mistakenly pasted
  full-access key is rejected at connection time rather than trusted;
* nothing here is imported by the signal, approval or paper-trading paths.

If a future session adds order placement, it must be a separate, explicitly
named module with its own human confirmation — never an extension of this one.
See ``HANDOVER.md``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests

# Every endpoint this module is permitted to sign. GET-only, read-only.
READ_ONLY_PATHS = {
    "/api/v3/account": "spot balances",
    "/api/v3/openOrders": "open spot orders",
    "/api/v3/myTrades": "recent spot fills",
}

# Exchange permission strings that mean the key can move money. Any of these
# present on the key → refuse the connection.
DANGEROUS_PERMISSIONS = {
    "SPOT_TRADING", "MARGIN_TRADING", "FUTURES_TRADING", "WITHDRAWALS",
    "ENABLE_SPOT_AND_MARGIN_TRADING", "ENABLE_WITHDRAWALS",
    "ENABLE_FUTURES", "ENABLE_MARGIN",
}

RECV_WINDOW = 5000
TIMEOUT = 10


class ExchangeAccountError(RuntimeError):
    """Raised when the account connection is unavailable or unsafe."""


def _demo() -> bool:
    return os.getenv("DEMO_MODE", "0") in ("1", "true", "yes")


class ExchangeAccount:
    """A read-only view of a real Binance spot account.

    ``api_key``/``api_secret`` default to the ``BINANCE_READ_API_KEY`` and
    ``BINANCE_READ_API_SECRET`` environment variables. When they are unset the
    connection simply reports ``configured=False``; nothing raises, and the
    rest of the desk continues on public market data.
    """

    def __init__(self, api_key: str | None = None, api_secret: str | None = None,
                 base_url: str | None = None, timeout: int = TIMEOUT):
        self.api_key = (api_key if api_key is not None
                        else os.getenv("BINANCE_READ_API_KEY", "")).strip()
        self.api_secret = (api_secret if api_secret is not None
                           else os.getenv("BINANCE_READ_API_SECRET", "")).strip()
        self.base_url = (base_url or os.getenv("BINANCE_ACCOUNT_HOST")
                         or "https://api.binance.com").rstrip("/")
        self.timeout = timeout

    # ── plumbing ─────────────────────────────────────────────────────────
    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        signature = hmac.new(self.api_secret.encode(), query.encode(),
                             hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    def _signed_get(self, path: str, params: dict | None = None) -> Any:
        """The ONLY request primitive in this module. GET, allow-listed."""
        if path not in READ_ONLY_PATHS:
            raise ExchangeAccountError(
                f"{path} is not in the read-only allow-list — refusing to sign it")
        if not self.configured:
            raise ExchangeAccountError("no read-only API key configured")
        payload = dict(params or {})
        payload["timestamp"] = int(time.time() * 1000)
        payload["recvWindow"] = RECV_WINDOW
        url = f"{self.base_url}{path}?{self._sign(payload)}"
        try:
            resp = requests.get(url, headers={"X-MBX-APIKEY": self.api_key},
                                timeout=self.timeout)
        except requests.RequestException as exc:
            raise ExchangeAccountError(f"{type(exc).__name__}: {exc}") from exc
        if resp.status_code == 401:
            raise ExchangeAccountError("exchange rejected the key (401) — "
                                       "check the key, secret and IP allow-list")
        if resp.status_code == 418 or resp.status_code == 429:
            raise ExchangeAccountError("rate-limited by the exchange — try again shortly")
        if resp.status_code >= 400:
            raise ExchangeAccountError(
                f"exchange returned {resp.status_code}: {resp.text[:160]}")
        return resp.json()

    # ── read-only reads ──────────────────────────────────────────────────
    def account(self) -> dict:
        """Raw spot account snapshot (balances + permissions)."""
        if _demo():
            return _demo_account()
        return self._signed_get("/api/v3/account")

    def open_orders(self) -> list[dict]:
        """Orders currently resting on the exchange (read-only)."""
        if _demo():
            return []
        data = self._signed_get("/api/v3/openOrders")
        return data if isinstance(data, list) else []

    def balances(self, min_value: float = 0.0) -> list[dict]:
        """Non-dust balances, largest first."""
        acct = self.account()
        out = []
        for row in acct.get("balances", []):
            free = float(row.get("free") or 0)
            locked = float(row.get("locked") or 0)
            total = free + locked
            if total <= min_value:
                continue
            out.append({"asset": row.get("asset"), "free": free,
                        "locked": locked, "total": total})
        out.sort(key=lambda r: r["total"], reverse=True)
        return out

    def snapshot(self) -> dict:
        """Everything the dashboard's Connections card needs, in one call."""
        if not self.configured:
            return {"configured": False, "connected": False,
                    "note": "no read-only API key set — the desk runs on public "
                            "market data only",
                    "balances": [], "open_orders": []}
        try:
            acct = self.account()
            permissions = _permissions(acct)
            safe, danger = _is_read_only(permissions)
            balances = []
            for row in acct.get("balances", []):
                free = float(row.get("free") or 0)
                locked = float(row.get("locked") or 0)
                if free + locked <= 0:
                    continue
                balances.append({"asset": row.get("asset"), "free": free,
                                 "locked": locked, "total": free + locked})
            balances.sort(key=lambda r: r["total"], reverse=True)
            orders = self.open_orders()
            return {
                "configured": True,
                "connected": True,
                "read_only": safe,
                "permissions": sorted(permissions),
                "dangerous_permissions": sorted(danger),
                "can_trade": bool(acct.get("canTrade")),
                "can_withdraw": bool(acct.get("canWithdraw")),
                "account_type": acct.get("accountType"),
                "balances": balances[:25],
                "balance_count": len(balances),
                "open_orders": orders,
                "open_order_count": len(orders),
                "demo": _demo(),
                "warning": (None if safe else
                            "This key can TRADE or WITHDRAW. SKY will not use it "
                            "for anything except reading — but replace it with a "
                            "read-only key."),
            }
        except ExchangeAccountError as exc:
            return {"configured": True, "connected": False, "error": str(exc),
                    "balances": [], "open_orders": []}


def _permissions(account: dict) -> set[str]:
    perms = {str(p).upper() for p in (account.get("permissions") or [])}
    # Older/lite responses omit `permissions` and only expose the booleans.
    if account.get("canTrade"):
        perms.add("SPOT_TRADING")
    if account.get("canWithdraw"):
        perms.add("WITHDRAWALS")
    return perms


def _is_read_only(permissions: set[str]) -> tuple[bool, set[str]]:
    danger = {p for p in permissions if p in DANGEROUS_PERMISSIONS}
    return (not danger), danger


def assert_read_only_key(account: dict) -> None:
    """Raise unless the connected key is genuinely view-only.

    Used by the strict connection test so a full-access key is reported as a
    problem instead of quietly accepted.
    """
    safe, danger = _is_read_only(_permissions(account))
    if not safe:
        raise ExchangeAccountError(
            "this API key has " + ", ".join(sorted(danger)) +
            " permission — create a NEW key with only 'Enable Reading' ticked")


def _demo_account() -> dict:
    """Deterministic offline account so the UI is demonstrable with no key."""
    return {
        "accountType": "SPOT", "canTrade": False, "canWithdraw": False,
        "permissions": ["SPOT_READ"],
        "balances": [
            {"asset": "USDT", "free": "1000.00000000", "locked": "0.00000000"},
            {"asset": "BTC", "free": "0.01500000", "locked": "0.00000000"},
            {"asset": "ETH", "free": "0.25000000", "locked": "0.00000000"},
        ],
    }
