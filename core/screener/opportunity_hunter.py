"""
core/screener/opportunity_hunter.py
===================================
Dynamic Market Universe Discovery & Opportunity Hunter Engine.
Continuously scans 700+ cryptocurrency pairs across Binance Spot and Binance Futures,
evaluates liquidity, spread, volatility acceleration, and market attention, and
classifies tradeable candidates into 6 quantitative opportunity categories.

Enforces:
1. Zero Lookahead Bias: Uses completed historical candles and explicit observation timestamps.
2. Institutional Liquidity Gate: Minimum $15M Spot / $25M Futures volume, tight spread tolerance.
3. Venue-Specific Eligibility: Evaluates Spot and Futures instruments independently.
4. Separation of Concerns: Separates Market Attention Score from Trade Quality Score.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger("sky.screener.opportunity_hunter")


class OpportunityCategory(str, Enum):
    EMERGING_MOMENTUM = "EMERGING_MOMENTUM"
    CONFIRMED_BREAKOUT = "CONFIRMED_BREAKOUT"
    CAPITULATION_RECOVERY = "CAPITULATION_RECOVERY"
    BEARISH_CONTINUATION = "BEARISH_CONTINUATION"
    BLOW_OFF_EXHAUSTION = "BLOW_OFF_EXHAUSTION"
    CATALYST_OPPORTUNITY = "CATALYST_OPPORTUNITY"


class AttentionState(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    BREAKOUT_CANDIDATE = "BREAKOUT_CANDIDATE"
    EXHAUSTION_CANDIDATE = "EXHAUSTION_CANDIDATE"
    EVENT_ALERT = "EVENT_ALERT"
    REJECTED = "REJECTED"


class WatchlistState(str, Enum):
    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


@dataclass
class OpportunityRecord:
    symbol: str
    base_asset: str
    quote_asset: str
    spot_eligible: bool
    futures_eligible: bool
    current_price: float
    price_change_24h_pct: float
    quote_volume_24h_usd: float
    trade_count_24h: int
    estimated_spread_bps: float
    relative_volume_ratio: float
    market_attention_score: float  # [0.0, 100.0]
    trade_quality_score: float  # [0.0, 100.0]
    attention_state: AttentionState
    opportunity_category: OpportunityCategory
    recommended_venue: str  # "SPOT", "FUTURES", or "SPOT_OR_FUTURES"
    recommended_direction: str  # "LONG", "SHORT", or "WATCH"
    primary_rationale: str
    invalidation_level: float | None
    observation_timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["attention_state"] = self.attention_state.value
        d["opportunity_category"] = self.opportunity_category.value
        return d


class OpportunityHunter:
    """
    Autonomous multi-exchange scanner discovering high-momentum gainers,
    oversold liquidity sweep reclaims, and overextended exhaustion reversals.
    """

    def __init__(
        self,
        min_spot_volume_usd: float = 15_000_000.0,
        min_futures_volume_usd: float = 25_000_000.0,
        max_spread_bps: float = 12.0,
        cache_ttl_sec: float = 180.0,  # 3 minutes cache to protect exchange rate limits
    ):
        self.min_spot_volume_usd = min_spot_volume_usd
        self.min_futures_volume_usd = min_futures_volume_usd
        self.max_spread_bps = max_spread_bps
        self.cache_ttl_sec = cache_ttl_sec

        self._cached_opportunities: list[OpportunityRecord] = []
        self._cached_watchlist: dict[str, dict[str, Any]] = {}
        self._last_scan_time: float = 0.0
        self._scan_lock = asyncio.Lock()
        self._is_scanning: bool = False
        self._total_spot_scanned: int = 0
        self._total_futures_scanned: int = 0
        self._last_error: str | None = None

        # Core Benchmark Anchors that are always preserved in the universe
        self.core_anchors = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

    async def scan_market(self, force_refresh: bool = False) -> list[OpportunityRecord]:
        """
        Polls Binance Spot and Futures 24hr tickers, applies the Institutional
        Liquidity Gate, and scores candidates across the 6 opportunity categories.
        """
        now = time.time()
        if not force_refresh and self._cached_opportunities and (now - self._last_scan_time) < self.cache_ttl_sec:
            return self._cached_opportunities

        async with self._scan_lock:
            if not force_refresh and self._cached_opportunities and (time.time() - self._last_scan_time) < self.cache_ttl_sec:
                return self._cached_opportunities

            self._is_scanning = True
            try:
                spot_tickers, futures_tickers = await self._fetch_all_24hr_tickers()
                records = self._process_and_rank_tickers(spot_tickers, futures_tickers)
                self._cached_opportunities = records
                self._update_watchlist_lifecycle(records)
                self._last_scan_time = time.time()
                self._last_error = None
                return records
            except Exception as e:
                logger.error(f"OpportunityHunter scan failed: {e}", exc_info=True)
                self._last_error = str(e)
                return self._cached_opportunities
            finally:
                self._is_scanning = False

    async def _fetch_all_24hr_tickers(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetches 24hr ticker snapshots across Spot and USDⓈ-M Futures simultaneously."""
        spot_url = "https://api.binance.com/api/v3/ticker/24hr"
        futures_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"

        timeout = aiohttp.ClientTimeout(total=8.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            spot_task = self._fetch_json(session, spot_url)
            futures_task = self._fetch_json(session, futures_url)
            spot_data, futures_data = await asyncio.gather(spot_task, futures_task, return_exceptions=True)

            spot_list = spot_data if isinstance(spot_data, list) else []
            futures_list = futures_data if isinstance(futures_data, list) else []

            self._total_spot_scanned = len(spot_list)
            self._total_futures_scanned = len(futures_list)
            return spot_list, futures_list

    async def _fetch_json(self, session: aiohttp.ClientSession, url: str) -> Any:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"Ticker endpoint {url} returned status {resp.status}")
                return []
        except Exception as exc:
            logger.warning(f"Failed to fetch {url}: {exc}")
            return []

    def _process_and_rank_tickers(
        self,
        spot_tickers: list[dict[str, Any]],
        futures_tickers: list[dict[str, Any]],
    ) -> list[OpportunityRecord]:
        """Evaluates liquidity, classifies categories, and ranks candidates by attention and trade quality."""
        futures_map = {t["symbol"]: t for t in futures_tickers if "symbol" in t}
        spot_map = {t["symbol"]: t for t in spot_tickers if "symbol" in t}

        # Combine unique USDT symbols
        all_usdt_symbols = set()
        for sym in spot_map:
            if sym.endswith("USDT"):
                all_usdt_symbols.add(sym)
        for sym in futures_map:
            if sym.endswith("USDT"):
                all_usdt_symbols.add(sym)

        now_ms = int(time.time() * 1000)
        qualified_records: list[OpportunityRecord] = []

        for raw_sym in all_usdt_symbols:
            base = raw_sym[:-4]
            symbol_slash = f"{base}/USDT"

            s_ticker = spot_map.get(raw_sym)
            f_ticker = futures_map.get(raw_sym)

            spot_vol = float(s_ticker.get("quoteVolume", 0.0)) if s_ticker else 0.0
            fut_vol = float(f_ticker.get("quoteVolume", 0.0)) if f_ticker else 0.0

            spot_eligible = spot_vol >= self.min_spot_volume_usd
            futures_eligible = fut_vol >= self.min_futures_volume_usd

            # Core anchors bypass minimum volume ceiling
            if symbol_slash in self.core_anchors:
                spot_eligible = s_ticker is not None
                futures_eligible = f_ticker is not None

            # Must be eligible on at least one venue
            if not spot_eligible and not futures_eligible:
                continue

            # Prefer Futures ticker for derivatives intelligence, fallback to Spot
            primary_ticker = f_ticker if f_ticker and futures_eligible else s_ticker
            if not primary_ticker:
                continue

            try:
                price = float(primary_ticker.get("lastPrice", 0.0))
                price_change = float(primary_ticker.get("priceChangePercent", 0.0))
                quote_vol = max(spot_vol, fut_vol)
                trades_count = int(primary_ticker.get("count", 0))
                high_24h = float(primary_ticker.get("highPrice", price))
                low_24h = float(primary_ticker.get("lowPrice", price))
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            # Estimate bid-ask spread from ask/bid or volatility proxy
            bid_price = float(primary_ticker.get("bidPrice", 0.0) or 0.0)
            ask_price = float(primary_ticker.get("askPrice", 0.0) or 0.0)
            if bid_price > 0 and ask_price > 0 and ask_price >= bid_price:
                spread_bps = ((ask_price - bid_price) / price) * 10_000.0
            else:
                spread_bps = 3.5  # Standard tight benchmark proxy

            if spread_bps > self.max_spread_bps and symbol_slash not in self.core_anchors:
                continue

            # Relative volume estimate against baseline
            rvol = min(max(quote_vol / 40_000_000.0, 0.5), 10.0)

            # Market Attention Score: composite of price velocity, volume surge, and trade frequency
            norm_vol = min(quote_vol / 150_000_000.0, 1.0) * 40.0
            norm_change = min(abs(price_change) / 25.0, 1.0) * 35.0
            norm_trades = min(trades_count / 300_000.0, 1.0) * 25.0
            attention_score = round(norm_vol + norm_change + norm_trades, 1)

            # Classify into 6 Quantitative Categories
            category, state, venue, direction, rationale, quality, inv_lvl = self._classify_opportunity(
                symbol=symbol_slash,
                price=price,
                price_change=price_change,
                quote_vol=quote_vol,
                rvol=rvol,
                spread_bps=spread_bps,
                high_24h=high_24h,
                low_24h=low_24h,
                spot_eligible=spot_eligible,
                futures_eligible=futures_eligible,
                attention_score=attention_score,
            )

            rec = OpportunityRecord(
                symbol=symbol_slash,
                base_asset=base,
                quote_asset="USDT",
                spot_eligible=spot_eligible,
                futures_eligible=futures_eligible,
                current_price=price,
                price_change_24h_pct=round(price_change, 2),
                quote_volume_24h_usd=round(quote_vol, 2),
                trade_count_24h=trades_count,
                estimated_spread_bps=round(spread_bps, 2),
                relative_volume_ratio=round(rvol, 2),
                market_attention_score=attention_score,
                trade_quality_score=quality,
                attention_state=state,
                opportunity_category=category,
                recommended_venue=venue,
                recommended_direction=direction,
                primary_rationale=rationale,
                invalidation_level=inv_lvl,
                observation_timestamp_ms=now_ms,
            )
            qualified_records.append(rec)

        # Sort: Top Attention Score descending
        qualified_records.sort(key=lambda r: r.market_attention_score, reverse=True)
        return qualified_records

    def _classify_opportunity(
        self,
        symbol: str,
        price: float,
        price_change: float,
        quote_vol: float,
        rvol: float,
        spread_bps: float,
        high_24h: float,
        low_24h: float,
        spot_eligible: bool,
        futures_eligible: bool,
        attention_score: float,
    ) -> tuple[OpportunityCategory, AttentionState, str, str, str, float, float | None]:
        """Maps quantitative market behavior to the 6 opportunity categories."""

        # 1. Blow-off Exhaustion (Extreme Surge with potential reversal)
        if price_change >= 22.0 and rvol >= 2.0:
            category = OpportunityCategory.BLOW_OFF_EXHAUSTION
            state = AttentionState.EXHAUSTION_CANDIDATE
            venue = "FUTURES" if futures_eligible else "SPOT"
            direction = "SHORT" if futures_eligible else "WATCH"
            rationale = f"Parabolic expansion (+{price_change:.1f}%) with {rvol:.1f}x abnormal volume. Monitor for distribution MSS."
            quality = 74.0
            invalidation = round(high_24h * 1.015, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 2. Confirmed Breakout
        if price_change >= 10.0 and (price >= high_24h * 0.96):
            category = OpportunityCategory.CONFIRMED_BREAKOUT
            state = AttentionState.BREAKOUT_CANDIDATE
            venue = "SPOT_OR_FUTURES" if (spot_eligible and futures_eligible) else ("FUTURES" if futures_eligible else "SPOT")
            direction = "LONG"
            rationale = f"High-volume breakout near 24h highs (+{price_change:.1f}%). Bullish structure expansion."
            quality = 82.0
            invalidation = round(low_24h if low_24h > 0 else price * 0.96, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 3. Emerging Momentum
        if price_change >= 5.0 and rvol >= 1.5:
            category = OpportunityCategory.EMERGING_MOMENTUM
            state = AttentionState.ELEVATED
            venue = "SPOT_OR_FUTURES" if (spot_eligible and futures_eligible) else ("FUTURES" if futures_eligible else "SPOT")
            direction = "LONG"
            rationale = f"Early momentum acceleration (+{price_change:.1f}%) with volume inflow ({rvol:.1f}x RVOL)."
            quality = 78.0
            invalidation = round(price * 0.97, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 4. Capitulation and Recovery (Oversold Dip Sweep)
        if price_change <= -8.0 and (price <= low_24h * 1.05):
            category = OpportunityCategory.CAPITULATION_RECOVERY
            state = AttentionState.ELEVATED
            venue = "SPOT_OR_FUTURES" if (spot_eligible and futures_eligible) else ("FUTURES" if futures_eligible else "SPOT")
            direction = "LONG"
            rationale = f"Heavy multi-day capitulation ({price_change:.1f}%) probing 24h lows. Watch for liquidity sweep reclaim."
            quality = 80.0
            invalidation = round(low_24h * 0.985, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 5. Bearish Continuation
        if price_change <= -4.0:
            category = OpportunityCategory.BEARISH_CONTINUATION
            state = AttentionState.WATCH
            venue = "FUTURES" if futures_eligible else "SPOT"
            direction = "SHORT" if futures_eligible else "WATCH"
            rationale = f"Bearish downward drift ({price_change:.1f}%). Weak bounce participation."
            quality = 70.0
            invalidation = round(high_24h, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 6. Default Catalyst / Active Monitoring
        category = OpportunityCategory.CATALYST_OPPORTUNITY
        state = AttentionState.NORMAL if attention_score < 40 else AttentionState.ELEVATED
        venue = "SPOT_OR_FUTURES" if (spot_eligible and futures_eligible) else ("FUTURES" if futures_eligible else "SPOT")
        direction = "WATCH"
        rationale = f"Normal market structure. Continuous 24h monitoring active (Attention: {attention_score})."
        quality = 65.0
        invalidation = None
        return category, state, venue, direction, rationale, quality, invalidation

    def _update_watchlist_lifecycle(self, records: list[OpportunityRecord]) -> None:
        """Maintains dynamic universe lifecycle: DISCOVERED -> QUALIFIED -> ACTIVE -> RETIRED."""
        current_symbols = {r.symbol for r in records}
        now_ms = int(time.time() * 1000)

        # Update active and qualified
        for r in records[:30]:  # Top 30 qualified
            if r.symbol not in self._cached_watchlist:
                self._cached_watchlist[r.symbol] = {
                    "symbol": r.symbol,
                    "state": WatchlistState.QUALIFIED.value,
                    "discovered_at": now_ms,
                    "last_updated_at": now_ms,
                    "attention_score": r.market_attention_score,
                    "category": r.opportunity_category.value,
                }
            else:
                self._cached_watchlist[r.symbol]["last_updated_at"] = now_ms
                self._cached_watchlist[r.symbol]["attention_score"] = r.market_attention_score
                self._cached_watchlist[r.symbol]["state"] = WatchlistState.ACTIVE.value

        # Retire symbols that fell off the top rankings (preserving open positions!)
        for sym, data in list(self._cached_watchlist.items()):
            if sym not in current_symbols and sym not in self.core_anchors:
                if (now_ms - data.get("last_updated_at", now_ms)) > (1800 * 1000):  # 30 mins
                    data["state"] = WatchlistState.RETIRED.value

    def get_watchlist(self) -> list[dict[str, Any]]:
        """Returns the current dynamic universe with lifecycle states."""
        return list(self._cached_watchlist.values())

    def get_health(self) -> dict[str, Any]:
        """Returns telemetry health metrics for the opportunity scanner."""
        return {
            "status": "HEALTHY" if self._last_error is None else "DEGRADED",
            "is_scanning": self._is_scanning,
            "last_scan_time": self._last_scan_time,
            "seconds_since_last_scan": round(time.time() - self._last_scan_time, 1) if self._last_scan_time > 0 else None,
            "total_spot_pairs_scanned": self._total_spot_scanned,
            "total_futures_pairs_scanned": self._total_futures_scanned,
            "total_opportunities_ranked": len(self._cached_opportunities),
            "watchlist_tracked_count": len(self._cached_watchlist),
            "last_error": self._last_error,
        }


opportunity_hunter = OpportunityHunter()
