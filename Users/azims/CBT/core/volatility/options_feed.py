"""
core/volatility/options_feed.py
===============================
Empirical Deribit Options Market Data Feed & Parser.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from typing import Any

import aiohttp

from core.volatility.black_scholes import compute_greeks
from core.volatility.models import OptionContract, OptionType

logger = logging.getLogger("ai_quant_sentinel.volatility.options_feed")

DERIBIT_BASE_URL = "https://www.deribit.com/api/v2/public"
MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def parse_deribit_expiry(expiry_str: str) -> int:
    """
    Parses Deribit expiry string like '25DEC26' or '17SEP26' into UTC ms timestamp.
    Deribit options expire at 08:00:00 UTC on the expiry date.
    """
    m = re.match(r"^(\d{1,2})([A-Z]{3})(\d{2})$", expiry_str.upper())
    if not m:
        raise ValueError(f"Invalid Deribit expiry format: {expiry_str}")
    day = int(m.group(1))
    month_name = m.group(2)
    year = 2000 + int(m.group(3))
    month = MONTH_MAP.get(month_name)
    if not month:
        raise ValueError(f"Unknown month name: {month_name}")

    dt = datetime.datetime(year, month, day, 8, 0, 0, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def parse_deribit_instrument(name: str) -> tuple[str, int, float, OptionType]:
    """
    Parses 'BTC-25DEC26-104000-C' -> ('BTC', expiry_ms, 104000.0, OptionType.CALL).
    """
    parts = name.split("-")
    if len(parts) != 4:
        raise ValueError(f"Cannot parse instrument name: {name}")

    base = parts[0].upper()
    expiry_ms = parse_deribit_expiry(parts[1])
    strike = float(parts[2])
    opt_type = OptionType.CALL if parts[3].upper() == "C" else OptionType.PUT
    return base, expiry_ms, strike, opt_type


class OptionsDataFeed:
    """
    Deribit live options feed and parser.
    """

    def __init__(self):
        self._cached_contracts: dict[str, list[OptionContract]] = {}
        self._cached_timestamps: dict[str, int] = {}
        self._cache_ttl_sec: float = 30.0
        self._lock = asyncio.Lock()
        self._shared_session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._shared_session is None or self._shared_session.closed:
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            self._shared_session = aiohttp.ClientSession(connector=connector)
        return self._shared_session

    async def fetch_options_chain(
        self,
        symbol: str = "BTC",
        session: aiohttp.ClientSession | None = None,
    ) -> list[OptionContract]:
        """
        Fetches full live options book summary from Deribit public REST API.
        """
        currency = symbol.replace("/", "").replace("USDT", "").replace("USD", "").upper()
        if currency not in ("BTC", "ETH", "SOL"):
            currency = "BTC"

        now_ms = int(time.time() * 1000)

        # Fast path: check memory cache without lock
        cached = self._cached_contracts.get(currency)
        cached_ts = self._cached_timestamps.get(currency, 0)
        if cached and (now_ms - cached_ts) < (self._cache_ttl_sec * 1000):
            return cached

        async with self._lock:
            # Re-check under lock (double-checked locking)
            now_ms = int(time.time() * 1000)
            cached = self._cached_contracts.get(currency)
            cached_ts = self._cached_timestamps.get(currency, 0)
            if cached and (now_ms - cached_ts) < (self._cache_ttl_sec * 1000):
                return cached

            url = f"{DERIBIT_BASE_URL}/get_book_summary_by_currency?currency={currency}&kind=option"
            http_session = session or await self._get_session()

            try:
                async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    if resp.status == 200:
                        payload = await resp.json()
                        items = payload.get("result", [])
                        contracts = self._parse_deribit_items(items, currency, now_ms)
                        if contracts:
                            self._cached_contracts[currency] = contracts
                            self._cached_timestamps[currency] = now_ms
                            logger.info(
                                "Parsed %d live options contracts for %s from Deribit.",
                                len(contracts),
                                currency,
                            )
                            return contracts
            except Exception as exc:
                logger.warning("Deribit live options feed failed for %s: %s", currency, exc)

            # If live fetch failed, return cached if available, else synthetic calibrated fallback
            if cached:
                return cached

            fallback = self._generate_calibrated_baseline_chain(currency, now_ms)
            self._cached_contracts[currency] = fallback
            self._cached_timestamps[currency] = now_ms
            return fallback

    def _parse_deribit_items(
        self,
        items: list[dict[str, Any]],
        currency: str,
        now_ms: int,
    ) -> list[OptionContract]:
        parsed: list[OptionContract] = []
        for item in items:
            name = item.get("instrument_name", "")
            try:
                base, expiry_ms, strike, opt_type = parse_deribit_instrument(name)
            except Exception:
                continue

            ms_to_expiry = expiry_ms - now_ms
            if ms_to_expiry <= 3600000:  # Skip contracts expiring in under 1 hour
                continue

            t_years = ms_to_expiry / (365.25 * 86400 * 1000)
            underlying = float(item.get("underlying_price") or item.get("estimated_delivery_price") or 0.0)
            if underlying <= 0.0:
                continue

            mark_iv = float(item.get("mark_iv") or 0.0) / 100.0
            if mark_iv <= 0.0:
                continue

            # Deribit quotes prices in base currency (BTC or ETH), multiply by underlying to get USD
            mark_price_crypto = float(item.get("mark_price") or 0.0)
            mark_price_usd = mark_price_crypto * underlying

            bid_crypto = item.get("bid_price")
            ask_crypto = item.get("ask_price")
            bid_usd = float(bid_crypto) * underlying if bid_crypto is not None else None
            ask_usd = float(ask_crypto) * underlying if ask_crypto is not None else None

            greeks = compute_greeks(
                option_type="CALL" if opt_type == OptionType.CALL else "PUT",
                s=underlying,
                k=strike,
                t=t_years,
                sigma=mark_iv,
                r=0.0,
            )

            contract = OptionContract(
                instrument_name=name,
                base_currency=base,
                strike=strike,
                expiry_timestamp_ms=expiry_ms,
                option_type=opt_type,
                time_to_expiry_years=t_years,
                underlying_price=underlying,
                mark_price_usd=round(mark_price_usd, 2),
                mark_iv=round(mark_iv, 4),
                bid_price_usd=round(bid_usd, 2) if bid_usd else None,
                ask_price_usd=round(ask_usd, 2) if ask_usd else None,
                open_interest=float(item.get("open_interest") or 0.0),
                volume_24h_usd=float(item.get("volume_usd") or 0.0),
                delta=round(greeks["delta"], 4),
                gamma=round(greeks["gamma"], 8),
                vega=round(greeks["vega"], 4),
                evidence_grade="EMPIRICAL",
            )
            parsed.append(contract)

        return parsed

    def _generate_calibrated_baseline_chain(
        self,
        currency: str,
        now_ms: int,
    ) -> list[OptionContract]:
        """
        Calibrated synthetic fallback using historical crypto options skew parameters.
        Used only when Deribit endpoint is unreachable or during unit tests.
        """
        underlying = 77000.0 if currency == "BTC" else 2480.0
        tenors_days = [7, 14, 30, 60, 90, 180]
        strike_multipliers = [0.70, 0.80, 0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20, 1.30]

        contracts: list[OptionContract] = []
        for days in tenors_days:
            expiry_ms = now_ms + (days * 86400 * 1000)
            t_years = days / 365.25

            # Base ATM IV: contango term structure (45% at 7d to 56% at 180d)
            base_atm_iv = 0.45 + (0.11 * (days / 180.0))

            for sm in strike_multipliers:
                strike = round(underlying * sm, -2 if currency == "BTC" else -1)
                moneyness = sm

                # Volatility smile: parabolic smile + structural put skew
                # Puts have higher IV (left skew)
                smile_adjustment = 0.50 * (moneyness - 1.0) ** 2
                skew_adjustment = -0.10 * (moneyness - 1.0)  # Downside puts higher IV
                iv = max(0.20, base_atm_iv + smile_adjustment + skew_adjustment)

                for opt_type in (OptionType.CALL, OptionType.PUT):
                    kind_char = "C" if opt_type == OptionType.CALL else "P"
                    name = f"{currency}-EXP{days}D-{int(strike)}-{kind_char}"
                    greeks = compute_greeks(
                        option_type="CALL" if opt_type == OptionType.CALL else "PUT",
                        s=underlying,
                        k=strike,
                        t=t_years,
                        sigma=iv,
                        r=0.0,
                    )
                    c = OptionContract(
                        instrument_name=name,
                        base_currency=currency,
                        strike=strike,
                        expiry_timestamp_ms=expiry_ms,
                        option_type=opt_type,
                        time_to_expiry_years=t_years,
                        underlying_price=underlying,
                        mark_price_usd=100.0,
                        mark_iv=round(iv, 4),
                        open_interest=50.0,
                        volume_24h_usd=15000.0,
                        delta=round(greeks["delta"], 4),
                        gamma=round(greeks["gamma"], 8),
                        vega=round(greeks["vega"], 4),
                        evidence_grade="STOCHASTIC_SAMPLE",
                    )
                    contracts.append(c)

        return contracts


options_feed = OptionsDataFeed()
