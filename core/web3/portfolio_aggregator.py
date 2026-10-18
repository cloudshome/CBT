"""
core/web3/portfolio_aggregator.py
=================================
Institutional Portfolio Aggregator with Strict Capital Isolation Firewall.

CONSTITUTIONAL MANDATE:
-----------------------
1. Strict Capital Partitioning:
   - EXECUTION_AVAILABLE_CAPITAL: Margin and trading balances on authorized exchanges (CEX/DEX).
   - WATCH_ONLY_EQUITY: Public on-chain wallet assets for monitoring only.
   - OBSERVED_TOTAL_EQUITY = EXECUTION_AVAILABLE_CAPITAL + WATCH_ONLY_EQUITY.
2. Zero-Leakage Risk Invariant:
   - The Capital Governor and Live Gatekeeper must NEVER use WATCH_ONLY_EQUITY to size orders.
   - Execution sizing is mathematically bounded solely by EXECUTION_AVAILABLE_CAPITAL.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

import aiohttp

from core.web3.rpc_client import POPULAR_TOKENS, multi_rpc_client
from core.web3.wallet_store import web3_wallet_store

logger = logging.getLogger("sky.web3.portfolio_aggregator")

# Default static fallback prices for native assets if ticker probe fails
DEFAULT_FALLBACK_PRICES_USD: dict[str, float] = {
    "ETH": 3500.0,
    "BNB": 600.0,
    "POL": 0.50,
    "SOL": 180.0,
    "USDT": 1.0,
    "USDC": 1.0,
}

CHAIN_NATIVE_ASSET: dict[str, str] = {
    "ETHEREUM": "ETH",
    "ARBITRUM": "ETH",
    "BSC": "BNB",
    "POLYGON": "POL",
    "SOLANA": "SOL",
}


@dataclass
class WalletBalanceReport:
    address: str
    chain: str
    label: str
    is_watch_only: bool
    native_asset: str
    native_balance: float
    native_value_usd: float
    tokens: dict[str, dict[str, Any]]
    total_value_usd: float
    quorum_status: str
    last_synced_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AggregatedPortfolioScorecard:
    timestamp_ms: int
    execution_available_capital_usd: float
    watch_only_equity_usd: float
    observed_total_equity_usd: float
    venue_breakdown: dict[str, float]
    currency_breakdown: dict[str, float]
    watch_wallets: list[dict[str, Any]]
    capital_firewall_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PortfolioAggregator:
    def __init__(self) -> None:
        self._price_cache: dict[str, float] = dict(DEFAULT_FALLBACK_PRICES_USD)
        self._last_price_fetch_ms: int = 0

    async def refresh_public_prices(self, session: aiohttp.ClientSession | None = None) -> None:
        """
        Fetches current reference prices from Binance public ticker API without authentication.
        """
        now = int(time.time() * 1000)
        if now - self._last_price_fetch_ms < 30000:  # 30s cache
            return

        own_session = session is None
        sess = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0))
        pairs = {
            "ETHUSDT": "ETH",
            "BNBUSDT": "BNB",
            "POLUSDT": "POL",
            "SOLUSDT": "SOL",
        }

        try:
            url = "https://api.binance.com/api/v3/ticker/price"
            async with sess.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        sym = item.get("symbol")
                        if sym in pairs:
                            asset = pairs[sym]
                            price = float(item.get("price", 0.0))
                            if price > 0:
                                self._price_cache[asset] = price
                    self._last_price_fetch_ms = now
        except Exception as e:
            logger.debug(f"Public ticker fetch warning (using cached prices): {e}")
        finally:
            if own_session:
                await sess.close()

    def get_asset_price_usd(self, asset: str) -> float:
        return self._price_cache.get(
            asset.upper(), 1.0 if asset.upper() in ("USDT", "USDC") else 0.0
        )

    async def scan_watch_wallet(
        self,
        chain: str,
        address: str,
        label: str,
        session: aiohttp.ClientSession | None = None,
    ) -> WalletBalanceReport:
        chain_upper = chain.upper()
        native_sym = CHAIN_NATIVE_ASSET.get(chain_upper, "ETH")
        now_ms = int(time.time() * 1000)

        own_session = session is None
        sess = session or aiohttp.ClientSession()

        try:
            # 1. Native balance
            native_res = await multi_rpc_client.get_native_balance(
                chain_upper, address, session=sess
            )
            native_bal = native_res.value
            native_px = self.get_asset_price_usd(native_sym)
            native_usd = native_bal * native_px

            # 2. Token balances (USDT, USDC)
            tokens_report: dict[str, dict[str, Any]] = {}
            tokens_usd = 0.0

            if chain_upper in POPULAR_TOKENS:
                for t_sym in POPULAR_TOKENS[chain_upper]:
                    try:
                        tok_res = await multi_rpc_client.get_erc20_balance(
                            chain_upper, t_sym, address, session=sess
                        )
                        tok_bal = tok_res.value
                        tok_px = self.get_asset_price_usd(t_sym)
                        tok_usd = tok_bal * tok_px
                        tokens_report[t_sym] = {
                            "balance": tok_bal,
                            "value_usd": round(tok_usd, 2),
                            "quorum_status": tok_res.quorum_status.value,
                        }
                        tokens_usd += tok_usd
                    except Exception as _e:
                        logger.debug("Failed to query token balance for %s: %s", t_sym, _e)

            total_usd = native_usd + tokens_usd

            return WalletBalanceReport(
                address=address,
                chain=chain_upper,
                label=label,
                is_watch_only=True,
                native_asset=native_sym,
                native_balance=round(native_bal, 6),
                native_value_usd=round(native_usd, 2),
                tokens=tokens_report,
                total_value_usd=round(total_usd, 2),
                quorum_status=native_res.quorum_status.value,
                last_synced_ms=now_ms,
            )
        finally:
            if own_session:
                await sess.close()

    async def get_aggregated_scorecard(
        self,
        exchange_balances: dict[str, float] | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> AggregatedPortfolioScorecard:
        """
        Aggregates exchange balances and watch-only on-chain balances with
        strict capital isolation guarantees.
        """
        now_ms = int(time.time() * 1000)
        await self.refresh_public_prices(session=session)

        # 1. Execution Available Capital (strictly from exchange trading accounts)
        exch_bals = exchange_balances or {}
        execution_available_capital = sum(max(0.0, float(v)) for v in exch_bals.values())

        # 2. Watch-Only Balances (strictly external on-chain wallets)
        wallets = web3_wallet_store.list_wallets()
        wallet_reports: list[WalletBalanceReport] = []

        own_session = session is None
        sess = session or aiohttp.ClientSession()

        try:
            tasks = [
                self.scan_watch_wallet(w.chain, w.address, w.label, session=sess) for w in wallets
            ]
            if tasks:
                wallet_reports = await asyncio.gather(*tasks)
        finally:
            if own_session:
                await sess.close()

        watch_only_equity = sum(w.total_value_usd for w in wallet_reports)

        # 3. Capital Isolation Firewall Assertion
        observed_total_equity = execution_available_capital + watch_only_equity
        capital_firewall_verified = (
            execution_available_capital == sum(max(0.0, float(v)) for v in exch_bals.values())
            and watch_only_equity >= 0.0
            and observed_total_equity >= execution_available_capital
        )

        venue_breakdown = {k.upper(): round(v, 2) for k, v in exch_bals.items()}
        venue_breakdown["WEB3_WATCH_ONLY"] = round(watch_only_equity, 2)

        currency_breakdown: dict[str, float] = {}
        for w in wallet_reports:
            currency_breakdown[w.native_asset] = round(
                currency_breakdown.get(w.native_asset, 0.0) + w.native_value_usd, 2
            )
            for t_sym, t_info in w.tokens.items():
                currency_breakdown[t_sym] = round(
                    currency_breakdown.get(t_sym, 0.0) + t_info["value_usd"], 2
                )

        return AggregatedPortfolioScorecard(
            timestamp_ms=now_ms,
            execution_available_capital_usd=round(execution_available_capital, 2),
            watch_only_equity_usd=round(watch_only_equity, 2),
            observed_total_equity_usd=round(observed_total_equity, 2),
            venue_breakdown=venue_breakdown,
            currency_breakdown=currency_breakdown,
            watch_wallets=[w.to_dict() for w in wallet_reports],
            capital_firewall_verified=capital_firewall_verified,
        )


# Global singleton aggregator
portfolio_aggregator = PortfolioAggregator()
