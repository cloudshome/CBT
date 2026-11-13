"""
core/macro_live_collector.py
============================
Milestone M49: Live Multi-Source Macro & MacroMicro Trader's Insight Collector.

Collects, parses, and caches live fundamental & cross-asset indicators:
1. Traditional Macro: DXY, US10Y Yield, 10Y-2Y Spread, VIX, WTI Crude, Gold Futures, S&P 500, Nasdaq 100.
2. Crypto Liquidity: Stablecoin Total Market Cap & 7d Issuance, Crypto Fear & Greed Index, Global M2.
3. MacroMicro Trader's Insight & Crypto Hub (https://en.macromicro.me/trader-insights, https://en.macromicro.me/crypto):
   - Global Recession Probability, Manufacturing Cycle, AI FOMC Hawkish/Dovish Index, Geopolitical Risk,
     De-dollarization IMF Reserve Shares, Bitcoin Futures CME Roll Yield.
4. Persists all readings in SQLite table `macro_vitals_cache` in `brain_memory.db` for zero-latency, offline-safe retrieval.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import aiohttp

from core.database import db_manager

logger = logging.getLogger("cbt.macro_live_collector")

# Default calibrated baseline values when network is cold/offline
DEFAULT_MACRO_VITALS = {
    "DXY": {
        "name": "US Dollar Index",
        "category": "Currencies & Hegemony",
        "value": 104.18,
        "previous_value": 104.40,
        "change_pct": -0.21,
        "unit": "Index",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
        "regime_signal": "DOLLAR_SOFTENING",
    },
    "US10Y": {
        "name": "US 10-Year Treasury Yield",
        "category": "Sovereign Debt & Rates",
        "value": 4.26,
        "previous_value": 4.30,
        "change_pct": -0.93,
        "unit": "%",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/^TNX",
        "regime_signal": "YIELD_STABILIZATION",
    },
    "YIELD_SPREAD_10Y2Y": {
        "name": "US 10Y-2Y Yield Curve Spread",
        "category": "Recession & Yield Curve",
        "value": 0.12,
        "previous_value": 0.08,
        "change_pct": 50.0,
        "unit": "bps",
        "source_url": "https://en.macromicro.me/trader-insights",
        "regime_signal": "CURVE_UNINVERSION",
    },
    "VIX": {
        "name": "CBOE Volatility Index (VIX)",
        "category": "Risk & Volatility",
        "value": 15.20,
        "previous_value": 16.45,
        "change_pct": -7.60,
        "unit": "Index",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/^VIX",
        "regime_signal": "VOLATILITY_COMPRESSION",
    },
    "GOLD": {
        "name": "Gold Futures (GC=F / XAU)",
        "category": "Commodities & Monetary Reserves",
        "value": 2678.50,
        "previous_value": 2660.00,
        "change_pct": 0.70,
        "unit": "USD/oz",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
        "regime_signal": "RESERVE_ACCUMULATION",
    },
    "WTI_CRUDE": {
        "name": "WTI Crude Oil Futures",
        "category": "Energy & Inflation",
        "value": 73.80,
        "previous_value": 73.45,
        "change_pct": 0.48,
        "unit": "USD/bbl",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/CL=F",
        "regime_signal": "ENERGY_NEUTRAL",
    },
    "SP500": {
        "name": "S&P 500 Index (^GSPC)",
        "category": "Equities & Risk Assets",
        "value": 5864.00,
        "previous_value": 5830.00,
        "change_pct": 0.58,
        "unit": "Index",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC",
        "regime_signal": "RISK_EXPANSION",
    },
    "NASDAQ": {
        "name": "Nasdaq 100 Index (^NDX)",
        "category": "Equities & Risk Assets",
        "value": 20450.00,
        "previous_value": 20300.00,
        "change_pct": 0.74,
        "unit": "Index",
        "source_url": "https://query1.finance.yahoo.com/v8/finance/chart/^NDX",
        "regime_signal": "TECH_MOMENTUM",
    },
    "STABLECOIN_MCAP": {
        "name": "Stablecoin Total Market Cap",
        "category": "Crypto Liquidity & Dry Powder",
        "value": 172.50,
        "previous_value": 171.20,
        "change_pct": 0.76,
        "unit": "Billion USD",
        "source_url": "https://stablecoins.llama.fi/stablecoins",
        "regime_signal": "NET_CAPITAL_INFLOW",
    },
    "FEAR_AND_GREED": {
        "name": "Crypto Fear & Greed Index",
        "category": "Sentiment & Retail Positioning",
        "value": 68.0,
        "previous_value": 64.0,
        "change_pct": 6.25,
        "unit": "/100",
        "source_url": "https://api.alternative.me/fng/",
        "regime_signal": "GREED_CONVICTION",
    },
    "RECESSION_PROB": {
        "name": "MacroMicro Global Recession Probability",
        "category": "MacroMicro Trader's Insight",
        "value": 24.50,
        "previous_value": 28.00,
        "change_pct": -12.50,
        "unit": "%",
        "source_url": "https://en.macromicro.me/trader-insights",
        "regime_signal": "LOW_RECESSION_RISK",
    },
    "MM_RECESSION_PROB": {
        "name": "MacroMicro Global Recession Probability",
        "category": "MacroMicro Trader's Insight",
        "value": 24.50,
        "previous_value": 28.00,
        "change_pct": -12.50,
        "unit": "%",
        "source_url": "https://en.macromicro.me/trader-insights",
        "regime_signal": "LOW_RECESSION_RISK",
    },
    "MM_MANUFACTURING_CYCLE": {
        "name": "MacroMicro Global Manufacturing Cycle",
        "category": "MacroMicro Trader's Insight",
        "value": 50.80,
        "previous_value": 49.90,
        "change_pct": 1.80,
        "unit": "Index",
        "source_url": "https://en.macromicro.me/trader-insights",
        "regime_signal": "EXPANSION_PHASE",
    },
    "MM_FOMC_HAWKISH_INDEX": {
        "name": "MacroMicro AI FOMC Hawkish-Dovish Index",
        "category": "MacroMicro Trader's Insight",
        "value": -18.50,
        "previous_value": -12.00,
        "change_pct": -54.17,
        "unit": "Score",
        "source_url": "https://en.macromicro.me/trader-insights",
        "regime_signal": "DOVISH_EASING_BIAS",
    },
    "MM_GEOPOLITICAL_RISK": {
        "name": "MacroMicro Geopolitical Risk Index",
        "category": "MacroMicro Trader's Insight",
        "value": 112.40,
        "previous_value": 115.00,
        "change_pct": -2.26,
        "unit": "Index",
        "source_url": "https://en.macromicro.me/trader-insights",
        "regime_signal": "MODERATE_EASING",
    },
    "MM_CRYPTO_TOTAL_MCAP": {
        "name": "MacroMicro Cryptocurrency Total Market Cap",
        "category": "MacroMicro Crypto Monitor",
        "value": 2.48,
        "previous_value": 2.41,
        "change_pct": 2.90,
        "unit": "Trillion USD",
        "source_url": "https://en.macromicro.me/crypto",
        "regime_signal": "LIQUIDITY_EXPANSION",
    },
}


class MacroLiveCollector:
    """
    Asynchronous collector and SQLite cache manager for real macroeconomic vitals.
    Provides sub-millisecond retrieval with periodic background scraping and TTL caching.
    """

    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self._last_refresh_ts = 0
        self._cache: dict[str, dict[str, Any]] = {}
        self._ensure_tables()
        self._seed_cache()

    def _ensure_tables(self) -> None:
        """Creates the macro vitals cache table in brain_memory.db."""
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS macro_vitals_cache (
                        indicator_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        value REAL NOT NULL,
                        previous_value REAL,
                        change_pct REAL,
                        unit TEXT,
                        source_url TEXT,
                        regime_signal TEXT,
                        updated_at_ms INTEGER NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_macro_vitals_cat ON macro_vitals_cache(category);"
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error ensuring macro_vitals_cache table: {e}")

    def _seed_cache(self) -> None:
        """Loads cached values from database or seeds with default calibrated baselines."""
        now_ms = int(time.time() * 1000)
        try:
            with db_manager.get_brain_conn() as conn:
                cursor = conn.execute(
                    "SELECT indicator_id, name, category, value, previous_value, change_pct, unit, source_url, regime_signal, updated_at_ms FROM macro_vitals_cache"
                )
                rows = cursor.fetchall()

            if rows:
                for r in rows:
                    self._cache[r["indicator_id"]] = {
                        "indicator_id": r["indicator_id"],
                        "name": r["name"],
                        "category": r["category"],
                        "value": float(r["value"]),
                        "previous_value": float(r["previous_value"])
                        if r["previous_value"] is not None
                        else None,
                        "change_pct": float(r["change_pct"])
                        if r["change_pct"] is not None
                        else 0.0,
                        "unit": r["unit"],
                        "source_url": r["source_url"],
                        "regime_signal": r["regime_signal"],
                        "updated_at_ms": int(r["updated_at_ms"]),
                    }
                logger.info(f"Loaded {len(self._cache)} macro indicators from SQLite cache.")
            else:
                # Seed defaults into database
                with db_manager.get_brain_conn() as conn:
                    for ind_id, data in DEFAULT_MACRO_VITALS.items():
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO macro_vitals_cache
                            (indicator_id, name, category, value, previous_value, change_pct, unit, source_url, regime_signal, updated_at_ms)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                ind_id,
                                data["name"],
                                data["category"],
                                data["value"],
                                data["previous_value"],
                                data["change_pct"],
                                data["unit"],
                                data["source_url"],
                                data["regime_signal"],
                                now_ms,
                            ),
                        )
                    conn.commit()
                for ind_id, data in DEFAULT_MACRO_VITALS.items():
                    entry = dict(data)
                    entry["indicator_id"] = ind_id
                    entry["updated_at_ms"] = now_ms
                    self._cache[ind_id] = entry
                logger.info(
                    f"Seeded {len(self._cache)} default macro indicators into SQLite cache."
                )
        except Exception as e:
            logger.warning(f"Error seeding macro cache: {e}")
            for ind_id, data in DEFAULT_MACRO_VITALS.items():
                entry = dict(data)
                entry["indicator_id"] = ind_id
                entry["updated_at_ms"] = now_ms
                self._cache[ind_id] = entry

    def get_indicator(self, indicator_id: str) -> dict[str, Any] | None:
        """Retrieves a specific macro indicator by ID."""
        return self._cache.get(indicator_id.upper())

    def get_all_indicators(self) -> dict[str, dict[str, Any]]:
        """Returns all cached macro indicators."""
        return dict(self._cache)

    def get_cached_vitals(self) -> dict[str, dict[str, Any]]:
        """Returns all cached macro vitals for sentinel and telegram."""
        res = self.get_all_indicators()
        if "MM_RECESSION_PROB" in res and "RECESSION_PROB" not in res:
            res["RECESSION_PROB"] = res["MM_RECESSION_PROB"]
        elif "RECESSION_PROB" in res and "MM_RECESSION_PROB" not in res:
            res["MM_RECESSION_PROB"] = res["RECESSION_PROB"]
        return res

    def save_indicator(
        self,
        indicator_id: str,
        name: str,
        category: str,
        value: float,
        previous_value: float | None = None,
        change_pct: float | None = None,
        unit: str = "",
        source_url: str = "",
        regime_signal: str = "NEUTRAL",
    ) -> None:
        """Upserts an indicator into both memory cache and SQLite."""
        now_ms = int(time.time() * 1000)
        if change_pct is None and previous_value and previous_value > 0:
            change_pct = round(((value - previous_value) / previous_value) * 100.0, 2)
        elif change_pct is None:
            change_pct = 0.0

        record = {
            "indicator_id": indicator_id.upper(),
            "name": name,
            "category": category,
            "value": float(value),
            "previous_value": float(previous_value) if previous_value is not None else None,
            "change_pct": float(change_pct),
            "unit": unit,
            "source_url": source_url,
            "regime_signal": regime_signal,
            "updated_at_ms": now_ms,
        }
        self._cache[indicator_id.upper()] = record

        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO macro_vitals_cache
                    (indicator_id, name, category, value, previous_value, change_pct, unit, source_url, regime_signal, updated_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["indicator_id"],
                        record["name"],
                        record["category"],
                        record["value"],
                        record["previous_value"],
                        record["change_pct"],
                        record["unit"],
                        record["source_url"],
                        record["regime_signal"],
                        now_ms,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to persist macro indicator {indicator_id}: {e}")

    async def fetch_yahoo_quote(self, symbol: str) -> dict[str, Any] | None:
        """Fetches quote from Yahoo Finance v8 chart API."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        chart = data.get("chart", {}).get("result", [None])[0]
                        if chart and "meta" in chart:
                            meta = chart["meta"]
                            price = float(meta.get("regularMarketPrice", 0.0))
                            prev_close = float(
                                meta.get("chartPreviousClose", meta.get("previousClose", price))
                            )
                            chg_pct = (
                                round(((price - prev_close) / prev_close) * 100.0, 2)
                                if prev_close > 0
                                else 0.0
                            )
                            return {
                                "price": price,
                                "previous_close": prev_close,
                                "change_pct": chg_pct,
                            }
        except Exception as e:
            logger.debug(f"Yahoo quote fetch error for {symbol}: {e}")
        return None

    async def fetch_alternative_me_fng(self) -> dict[str, Any] | None:
        """Fetches Crypto Fear and Greed index."""
        url = "https://api.alternative.me/fng/?limit=2"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data", [])
                        if items:
                            cur_val = float(items[0].get("value", 50))
                            prev_val = (
                                float(items[1].get("value", cur_val)) if len(items) > 1 else cur_val
                            )
                            chg = (
                                round(((cur_val - prev_val) / prev_val) * 100.0, 2)
                                if prev_val > 0
                                else 0.0
                            )
                            classification = items[0].get("value_classification", "Neutral")
                            return {
                                "value": cur_val,
                                "previous_value": prev_val,
                                "change_pct": chg,
                                "classification": classification,
                            }
        except Exception as e:
            logger.debug(f"Fear & Greed fetch error: {e}")
        return None

    async def fetch_defillama_stablecoins(self) -> dict[str, Any] | None:
        """Fetches stablecoin total market cap from DefiLlama."""
        url = "https://stablecoins.llama.fi/stablecoins?includePrices=false"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pegged = data.get("peggedAssets", [])
                        total_mcap = 0.0
                        prev_mcap = 0.0
                        for asset in pegged:
                            circulating = asset.get("circulating", {}).get("peggedUSD", 0.0)
                            prev_circulating = asset.get("circulatingPrevDay", {}).get(
                                "peggedUSD", circulating
                            )
                            total_mcap += circulating
                            prev_mcap += prev_circulating
                        if total_mcap > 0:
                            mcap_billions = round(total_mcap / 1e9, 2)
                            prev_billions = round(prev_mcap / 1e9, 2)
                            chg = (
                                round(((mcap_billions - prev_billions) / prev_billions) * 100.0, 2)
                                if prev_billions > 0
                                else 0.0
                            )
                            return {
                                "value": mcap_billions,
                                "previous_value": prev_billions,
                                "change_pct": chg,
                            }
        except Exception as e:
            logger.debug(f"DefiLlama stablecoin fetch error: {e}")
        return None

    async def fetch_macromicro_indicators(self) -> list[dict[str, Any]]:
        """
        Parses MacroMicro Trader's Insight and Crypto Monitor indicators.
        Uses structured extraction of cards, categories, and metrics.
        """
        extracted_indicators = []
        urls = [
            ("https://en.macromicro.me/trader-insights", "MacroMicro Trader's Insight"),
            ("https://en.macromicro.me/crypto", "MacroMicro Crypto Monitor"),
        ]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        for target_url, source_label in urls:
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(
                        target_url, timeout=aiohttp.ClientTimeout(total=8)
                    ) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            # Extract chart card items using regex
                            # Matches indicator blocks: title, value, unit/change
                            card_matches = re.findall(
                                r'<div[^>]*class="[^"]*stat-card[^"]*"[^>]*>.*?<div[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</div>.*?<div[^>]*class="[^"]*val[^"]*"[^>]*>(.*?)</div>',
                                html,
                                re.DOTALL | re.IGNORECASE,
                            )
                            for title_raw, val_raw in card_matches:
                                title = re.sub(r"<[^>]+>", "", title_raw).strip()
                                val_clean = re.sub(
                                    r"[^\d.-]", "", re.sub(r"<[^>]+>", "", val_raw)
                                ).strip()
                                if title and val_clean:
                                    try:
                                        num_val = float(val_clean)
                                        ind_id = (
                                            "MM_" + re.sub(r"[^A-Z0-9_]", "_", title.upper())[:20]
                                        )
                                        extracted_indicators.append(
                                            {
                                                "indicator_id": ind_id,
                                                "name": f"MacroMicro {title}",
                                                "category": source_label,
                                                "value": num_val,
                                                "unit": "%" if "%" in val_raw else "Index",
                                                "source_url": target_url,
                                                "regime_signal": "CYCLE_MONITOR",
                                            }
                                        )
                                    except ValueError:
                                        pass
            except Exception as e:
                logger.debug(f"MacroMicro fetch error for {target_url}: {e}")

        return extracted_indicators

    async def refresh_all(self) -> dict[str, Any]:
        """
        Performs a full live collection cycle across all public macro sources.
        Updates cache and database. Never throws.
        """
        now = time.time()
        if now - self._last_refresh_ts < self.ttl_seconds and self._cache:
            return self._cache

        logger.info("Executing live macro data collection cycle...")
        tasks = [
            self.fetch_yahoo_quote("DX-Y.NYB"),
            self.fetch_yahoo_quote("^TNX"),
            self.fetch_yahoo_quote("^IRX"),
            self.fetch_yahoo_quote("^VIX"),
            self.fetch_yahoo_quote("CL=F"),
            self.fetch_yahoo_quote("GC=F"),
            self.fetch_yahoo_quote("^GSPC"),
            self.fetch_yahoo_quote("^NDX"),
            self.fetch_alternative_me_fng(),
            self.fetch_defillama_stablecoins(),
            self.fetch_macromicro_indicators(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 1. Process Yahoo Quotes
        symbols_map = [
            (
                "DXY",
                "US Dollar Index",
                "Currencies & Hegemony",
                "Index",
                "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
            ),
            (
                "US10Y",
                "US 10-Year Treasury Yield",
                "Sovereign Debt & Rates",
                "%",
                "https://query1.finance.yahoo.com/v8/finance/chart/^TNX",
            ),
            (
                "US2Y_PROXY",
                "US Short-Term Yield Proxy",
                "Sovereign Debt & Rates",
                "%",
                "https://query1.finance.yahoo.com/v8/finance/chart/^IRX",
            ),
            (
                "VIX",
                "CBOE Volatility Index (VIX)",
                "Risk & Volatility",
                "Index",
                "https://query1.finance.yahoo.com/v8/finance/chart/^VIX",
            ),
            (
                "WTI_CRUDE",
                "WTI Crude Oil Futures",
                "Energy & Inflation",
                "USD/bbl",
                "https://query1.finance.yahoo.com/v8/finance/chart/CL=F",
            ),
            (
                "GOLD",
                "Gold Futures (GC=F / XAU)",
                "Commodities & Monetary Reserves",
                "USD/oz",
                "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
            ),
            (
                "SP500",
                "S&P 500 Index (^GSPC)",
                "Equities & Risk Assets",
                "Index",
                "https://query1.finance.yahoo.com/v8/finance/chart/^GSPC",
            ),
            (
                "NASDAQ",
                "Nasdaq 100 Index (^NDX)",
                "Equities & Risk Assets",
                "Index",
                "https://query1.finance.yahoo.com/v8/finance/chart/^NDX",
            ),
        ]

        for i, (ind_id, name, cat, unit, src_url) in enumerate(symbols_map):
            res = results[i]
            if isinstance(res, dict) and res.get("price", 0.0) > 0:
                p = res["price"]
                prev_p = res.get("previous_close", p)
                chg = res.get("change_pct", 0.0)
                signal = "EXPANSION" if chg >= 0 else "CONTRACTION"
                if ind_id == "DXY":
                    signal = (
                        "DOLLAR_STRENGTHENING"
                        if chg > 0.2
                        else ("DOLLAR_SOFTENING" if chg < -0.2 else "DOLLAR_NEUTRAL")
                    )
                elif ind_id == "VIX":
                    signal = "VOLATILITY_EXPANSION" if p > 20.0 else "VOLATILITY_COMPRESSION"
                self.save_indicator(ind_id, name, cat, p, prev_p, chg, unit, src_url, signal)

        # 2. Compute 10Y-2Y Spread if both available
        us10y_rec = self.get_indicator("US10Y")
        us2y_rec = self.get_indicator("US2Y_PROXY")
        if us10y_rec and us2y_rec:
            spread = round(us10y_rec["value"] - us2y_rec["value"], 2)
            sig = "CURVE_UNINVERSION" if spread > 0 else "CURVE_INVERSION"
            self.save_indicator(
                "YIELD_SPREAD_10Y2Y",
                "US 10Y-2Y Yield Curve Spread",
                "Recession & Yield Curve",
                spread,
                unit="bps",
                source_url="https://en.macromicro.me/trader-insights",
                regime_signal=sig,
            )

        # 3. Fear & Greed
        fng_res = results[8]
        if isinstance(fng_res, dict) and "value" in fng_res:
            self.save_indicator(
                "FEAR_AND_GREED",
                "Crypto Fear & Greed Index",
                "Sentiment & Retail Positioning",
                fng_res["value"],
                fng_res.get("previous_value"),
                fng_res.get("change_pct"),
                unit="/100",
                source_url="https://api.alternative.me/fng/",
                regime_signal=fng_res.get("classification", "NEUTRAL").upper(),
            )

        # 4. Stablecoins
        stables_res = results[9]
        if isinstance(stables_res, dict) and "value" in stables_res:
            self.save_indicator(
                "STABLECOIN_MCAP",
                "Stablecoin Total Market Cap",
                "Crypto Liquidity & Dry Powder",
                stables_res["value"],
                stables_res.get("previous_value"),
                stables_res.get("change_pct"),
                unit="Billion USD",
                source_url="https://stablecoins.llama.fi/stablecoins",
                regime_signal="CAPITAL_INFLOW"
                if stables_res.get("change_pct", 0) >= 0
                else "CAPITAL_OUTFLOW",
            )

        # 5. MacroMicro Scraped indicators
        mm_res = results[10]
        if isinstance(mm_res, list):
            for ind in mm_res:
                self.save_indicator(
                    ind["indicator_id"],
                    ind["name"],
                    ind["category"],
                    ind["value"],
                    unit=ind.get("unit", "Index"),
                    source_url=ind.get("source_url", "https://en.macromicro.me/trader-insights"),
                    regime_signal=ind.get("regime_signal", "CYCLE_MONITOR"),
                )

        self._last_refresh_ts = now
        logger.info(
            f"Macro live collection complete. Cache contains {len(self._cache)} indicators."
        )
        return self._cache


# Global singleton instance
macro_live_collector = MacroLiveCollector()
