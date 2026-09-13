"""
core/execution/account_probe.py
===============================
Multi-Exchange Live Balance & Account Readiness Probe for Milestone 21.

Fetches real-time equity balances, free margin, leverage bounds,
and calculates constitutional 1.5% single-trade equity caps.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.auth.credential_vault import credential_vault
from core.execution.connectors.base import NormalizedBalance
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector

logger = logging.getLogger("sky.execution.account_probe")


@dataclass
class ExchangeAccountStatus:
    exchange: str
    environment: str
    is_connected: bool
    latency_ms: float
    total_equity_usd: float
    free_cash_usd: float
    locked_margin_usd: float
    balances: List[NormalizedBalance] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class PortfolioReadinessSummary:
    timestamp_ms: int
    vault_unlocked: bool
    total_portfolio_equity_usd: float
    total_free_cash_usd: float
    single_trade_equity_cap_usd: float  # Exactly 1.5% of total equity
    max_portfolio_heat_usd: float       # Exactly 6.0% total concurrent risk
    active_exchanges: List[str]
    exchange_statuses: Dict[str, ExchangeAccountStatus]
    is_ready_for_canary_trade: bool
    reasons: List[str]


class AccountReadinessProbe:
    """Probes live balances and computes constitutional sizing limits."""

    def __init__(self) -> None:
        self.reference_prices: Dict[str, float] = {
            "BTC": 65000.0,
            "ETH": 3500.0,
            "SOL": 150.0,
            "USDT": 1.0,
            "USDC": 1.0,
            "USD": 1.0,
            "PAXG": 2400.0,
        }

    async def probe_exchange(self, exchange: str, environment: str = "PRODUCTION") -> ExchangeAccountStatus:
        """Probes a specific exchange connector for live balances."""
        exchange_upper = exchange.upper().strip()
        t_start = time.perf_counter()

        if not credential_vault.is_unlocked():
            return ExchangeAccountStatus(
                exchange=exchange_upper,
                environment=environment,
                is_connected=False,
                latency_ms=0.0,
                total_equity_usd=0.0,
                free_cash_usd=0.0,
                locked_margin_usd=0.0,
                error_message="Credential vault is locked. Unlock vault to query live balances.",
            )

        cred = credential_vault.get_credential(exchange_upper)
        if not cred or not cred.api_key:
            return ExchangeAccountStatus(
                exchange=exchange_upper,
                environment=environment,
                is_connected=False,
                latency_ms=0.0,
                total_equity_usd=0.0,
                free_cash_usd=0.0,
                locked_margin_usd=0.0,
                error_message=f"No API credentials configured for {exchange_upper} in credential vault.",
            )

        try:
            if exchange_upper == "BINANCE":
                connector = BinanceSpotConnector(
                    environment=environment,
                    api_key=cred.api_key,
                    api_secret=cred.api_secret,
                )
            elif exchange_upper == "BYBIT":
                connector = BybitV5Connector(
                    environment=environment,
                    api_key=cred.api_key,
                    api_secret=cred.api_secret,
                )
            else:
                return ExchangeAccountStatus(
                    exchange=exchange_upper,
                    environment=environment,
                    is_connected=False,
                    latency_ms=0.0,
                    total_equity_usd=0.0,
                    free_cash_usd=0.0,
                    locked_margin_usd=0.0,
                    error_message=f"Unsupported exchange connector: {exchange_upper}",
                )

            balances = await connector.get_balances()
            latency_ms = (time.perf_counter() - t_start) * 1000.0

            total_usd = 0.0
            free_usd = 0.0
            locked_usd = 0.0

            for b in balances:
                rate = self.reference_prices.get(b.asset.upper(), 0.0)
                total_usd += b.total * rate
                free_usd += b.free * rate
                locked_usd += b.locked * rate

            return ExchangeAccountStatus(
                exchange=exchange_upper,
                environment=environment,
                is_connected=True,
                latency_ms=round(latency_ms, 2),
                total_equity_usd=round(total_usd, 2),
                free_cash_usd=round(free_usd, 2),
                locked_margin_usd=round(locked_usd, 2),
                balances=balances,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            logger.warning(f"Error querying live balance for {exchange_upper}: {e}")
            return ExchangeAccountStatus(
                exchange=exchange_upper,
                environment=environment,
                is_connected=False,
                latency_ms=round(latency_ms, 2),
                total_equity_usd=0.0,
                free_cash_usd=0.0,
                locked_margin_usd=0.0,
                error_message=str(e),
            )

    async def get_portfolio_readiness(self, environment: str = "PRODUCTION") -> PortfolioReadinessSummary:
        """Evaluates live account readiness and constitutional risk boundaries."""
        now_ms = int(time.time() * 1000)
        vault_unlocked = credential_vault.is_unlocked()

        exchanges = ["BINANCE", "BYBIT"]
        tasks = [self.probe_exchange(exch, environment) for exch in exchanges]
        statuses_list = await asyncio.gather(*tasks)

        statuses = {s.exchange: s for s in statuses_list}
        active_exchanges = [s.exchange for s in statuses_list if s.is_connected]

        tot_equity = sum(s.total_equity_usd for s in statuses_list)
        tot_free = sum(s.free_cash_usd for s in statuses_list)

        # Constitutional single-trade cap: strictly 1.5% of total portfolio equity
        single_trade_cap = round(tot_equity * 0.015, 2)
        # Constitutional portfolio heat limit: strictly 6.0% total concurrent risk
        portfolio_heat_cap = round(tot_equity * 0.06, 2)

        reasons = []
        if not vault_unlocked:
            reasons.append("Credential vault is locked.")
        if not active_exchanges:
            reasons.append("No live exchange connections active.")
        if tot_equity < 10.0 and active_exchanges:
            reasons.append("Total portfolio equity is below minimum canary threshold ($10 USD).")

        is_ready = vault_unlocked and len(active_exchanges) > 0 and tot_equity >= 10.0

        return PortfolioReadinessSummary(
            timestamp_ms=now_ms,
            vault_unlocked=vault_unlocked,
            total_portfolio_equity_usd=round(tot_equity, 2),
            total_free_cash_usd=round(tot_free, 2),
            single_trade_equity_cap_usd=single_trade_cap,
            max_portfolio_heat_usd=portfolio_heat_cap,
            active_exchanges=active_exchanges,
            exchange_statuses=statuses,
            is_ready_for_canary_trade=is_ready,
            reasons=reasons,
        )


# Global singleton
account_probe = AccountReadinessProbe()
