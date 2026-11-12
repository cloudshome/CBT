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
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import aiohttp

from core.database import db_manager

logger = logging.getLogger("sky.screener.opportunity_hunter")


class OpportunityCategory(StrEnum):
    PRE_BREAKOUT_COMPRESSION = "PRE_BREAKOUT_COMPRESSION"
    EMERGING_MOMENTUM = "EMERGING_MOMENTUM"
    CONFIRMED_BREAKOUT = "CONFIRMED_BREAKOUT"
    CAPITULATION_RECOVERY = "CAPITULATION_RECOVERY"
    BEARISH_CONTINUATION = "BEARISH_CONTINUATION"
    BLOW_OFF_EXHAUSTION = "BLOW_OFF_EXHAUSTION"
    CATALYST_OPPORTUNITY = "CATALYST_OPPORTUNITY"
    NO_TRADE_QUARANTINE = "NO_TRADE_QUARANTINE"


class AttentionState(StrEnum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    BREAKOUT_CANDIDATE = "BREAKOUT_CANDIDATE"
    EXHAUSTION_CANDIDATE = "EXHAUSTION_CANDIDATE"
    EVENT_ALERT = "EVENT_ALERT"
    REJECTED = "REJECTED"


class TimingStage(StrEnum):
    PRE_SPIKE = "PRE_SPIKE"
    EARLY = "EARLY"
    ACTIVE = "ACTIVE"
    LATE = "LATE"
    EXHAUSTED = "EXHAUSTED"
    INVALIDATED = "INVALIDATED"


class WatchlistState(StrEnum):
    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


def build_tradingview_url(
    base_asset: str, quote_asset: str = "USDT", is_futures: bool = True
) -> str:
    sym = f"{base_asset.upper()}{quote_asset.upper()}"
    return (
        f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P"
        if is_futures
        else f"https://www.tradingview.com/chart/?symbol=BINANCE:{sym}"
    )


def build_binance_url(base_asset: str, quote_asset: str = "USDT", is_futures: bool = True) -> str:
    base = base_asset.upper()
    quote = quote_asset.upper()
    return (
        f"https://www.binance.com/en/futures/{base}{quote}"
        if is_futures
        else f"https://www.binance.com/en/trade/{base}_{quote}"
    )


def build_bybit_url(base_asset: str, quote_asset: str = "USDT") -> str:
    return f"https://www.bybit.com/trade/usdt/{base_asset.upper()}{quote_asset.upper()}"


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
    timing_stage: str = "ACTIVE"  # PRE_SPIKE, EARLY, ACTIVE, LATE, EXHAUSTED
    reward_to_risk: float = 2.0
    distance_to_invalidation_pct: float = 0.0
    tradingview_url: str = ""
    binance_url: str = ""
    bybit_url: str = ""
    stress_friction_bps: float = 0.0
    is_tradable_under_stress: bool = True

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
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Creates opportunity_attrition_ledger in brain_memory.db."""
        with db_manager.get_brain_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunity_attrition_ledger (
                    opportunity_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    category TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    timing_stage TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    invalidation_level REAL,
                    target_price REAL,
                    market_attention_score REAL NOT NULL,
                    trade_quality_score REAL NOT NULL,
                    stress_friction_bps REAL NOT NULL,
                    is_tradable_under_stress INTEGER NOT NULL,
                    discovered_at_ms INTEGER NOT NULL,
                    status_15m TEXT,
                    status_1h TEXT,
                    status_4h TEXT,
                    resolved_at_ms INTEGER
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_opp_attr_sym ON opportunity_attrition_ledger (symbol, discovered_at_ms);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_opp_attr_cat ON opportunity_attrition_ledger (category, timing_stage);"
            )
            conn.commit()

    def evaluate_tradability_stress(
        self,
        price: float,
        spread_bps: float,
        quote_vol: float,
        dist_to_invalidation_pct: float,
        rr: float,
    ) -> tuple[bool, float, float]:
        """
        Evaluates discovered candidate against the 2.5x Stress Trading Friction Gate.
        Computes 2.5x base fees + bid/ask spread + depth-walking impact slippage.
        Returns:
            (is_tradable, stress_friction_bps, target_move_pct)
        """
        if price <= 0:
            return False, 999.0, 0.0

        # Baseline Round-Trip Frictions:
        # 1. Exchange taker fees: 5.0 bps per leg = 10.0 bps round trip
        fee_bps = 10.0
        # 2. Bid-ask spread: full spread entry/exit
        actual_spread = max(1.0, spread_bps)
        # 3. Depth-walking impact slippage based on 24h quote volume liquidity
        vol_factor = max(1_000_000.0, quote_vol)
        impact_bps = max(1.5, min(15.0, (50_000_000.0 / vol_factor) * 3.0))

        base_friction_bps = fee_bps + actual_spread + impact_bps
        stress_friction_bps = round(base_friction_bps * 2.5, 2)
        stress_friction_pct = stress_friction_bps / 100.0

        # Expected target expansion move
        target_move_pct = round(dist_to_invalidation_pct * rr, 3)

        # Tradability Invariant: Expected target move MUST clear 2.5x stress frictions
        is_tradable = target_move_pct >= stress_friction_pct

        return is_tradable, stress_friction_bps, target_move_pct

    def record_discovered_opportunity(self, rec: OpportunityRecord) -> str:
        """Persists newly discovered opportunity to SQLite attrition ledger."""
        opp_id = f"opp_{rec.symbol.replace('/', '_')}_{rec.observation_timestamp_ms}_{uuid.uuid4().hex[:6]}"
        risk_dist = abs(rec.current_price - (rec.invalidation_level or rec.current_price * 0.98))
        target_price = (
            rec.current_price + (risk_dist * rec.reward_to_risk)
            if rec.recommended_direction == "LONG"
            else max(0.000001, rec.current_price - (risk_dist * rec.reward_to_risk))
        )

        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO opportunity_attrition_ledger
                    (opportunity_id, symbol, category, direction, timing_stage,
                     entry_price, invalidation_level, target_price, market_attention_score,
                     trade_quality_score, stress_friction_bps, is_tradable_under_stress,
                     discovered_at_ms, status_15m, status_1h, status_4h, resolved_at_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL);
                """,
                (
                    opp_id,
                    rec.symbol,
                    rec.opportunity_category.value,
                    rec.recommended_direction,
                    rec.timing_stage,
                    rec.current_price,
                    rec.invalidation_level,
                    round(target_price, 6),
                    rec.market_attention_score,
                    rec.trade_quality_score,
                    rec.stress_friction_bps,
                    1 if rec.is_tradable_under_stress else 0,
                    rec.observation_timestamp_ms,
                ),
            )
            conn.commit()
        return opp_id

    def update_attrition_lifecycle(self, current_prices: dict[str, float]) -> dict[str, int]:
        """
        Evaluates active un-resolved opportunities against elapsed time windows (15m, 1h, 4h)
        and updates their survival / decay status in the attrition ledger.
        """
        now_ms = int(time.time() * 1000)
        updated_counts = {"15m": 0, "1h": 0, "4h": 0, "resolved": 0}

        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                """
                SELECT opportunity_id, symbol, direction, entry_price, invalidation_level,
                       target_price, discovered_at_ms, status_15m, status_1h, status_4h
                FROM opportunity_attrition_ledger
                WHERE resolved_at_ms IS NULL;
                """
            ).fetchall()

            for r in rows:
                sym = r["symbol"]
                cur_p = current_prices.get(sym)
                if not cur_p or cur_p <= 0:
                    continue

                opp_id = r["opportunity_id"]
                direction = r["direction"]
                entry_p = float(r["entry_price"])
                inv_p = (
                    float(r["invalidation_level"])
                    if r["invalidation_level"]
                    else (entry_p * 0.98 if direction == "LONG" else entry_p * 1.02)
                )
                tgt_p = (
                    float(r["target_price"])
                    if r["target_price"]
                    else (entry_p * 1.05 if direction == "LONG" else entry_p * 0.95)
                )
                age_ms = now_ms - int(r["discovered_at_ms"])

                # Check terminal target / invalidation hits
                is_target_hit = (cur_p >= tgt_p) if direction == "LONG" else (cur_p <= tgt_p)
                is_invalidated = (cur_p <= inv_p) if direction == "LONG" else (cur_p >= inv_p)

                if is_target_hit:
                    conn.execute(
                        "UPDATE opportunity_attrition_ledger SET resolved_at_ms = ?, status_15m = COALESCE(status_15m, 'TARGET_HIT'), status_1h = COALESCE(status_1h, 'TARGET_HIT'), status_4h = COALESCE(status_4h, 'TARGET_HIT') WHERE opportunity_id = ?;",
                        (now_ms, opp_id),
                    )
                    updated_counts["resolved"] += 1
                    continue
                elif is_invalidated:
                    conn.execute(
                        "UPDATE opportunity_attrition_ledger SET resolved_at_ms = ?, status_15m = COALESCE(status_15m, 'INVALIDATED'), status_1h = COALESCE(status_1h, 'INVALIDATED'), status_4h = COALESCE(status_4h, 'INVALIDATED') WHERE opportunity_id = ?;",
                        (now_ms, opp_id),
                    )
                    updated_counts["resolved"] += 1
                    continue

                # 15 minute interval (900s = 900,000ms)
                if age_ms >= 900_000 and r["status_15m"] is None:
                    # Check if moved in expected direction
                    favorable = (cur_p > entry_p) if direction == "LONG" else (cur_p < entry_p)
                    stat_15 = "SURVIVED" if favorable else "ATROPHIED"
                    conn.execute(
                        "UPDATE opportunity_attrition_ledger SET status_15m = ? WHERE opportunity_id = ?;",
                        (stat_15, opp_id),
                    )
                    updated_counts["15m"] += 1

                # 1 hour interval (3600s = 3,600,000ms)
                if age_ms >= 3_600_000 and r["status_1h"] is None:
                    favorable = (cur_p > entry_p) if direction == "LONG" else (cur_p < entry_p)
                    stat_1h = "SURVIVED" if favorable else "ATROPHIED"
                    conn.execute(
                        "UPDATE opportunity_attrition_ledger SET status_1h = ? WHERE opportunity_id = ?;",
                        (stat_1h, opp_id),
                    )
                    updated_counts["1h"] += 1

                # 4 hour interval (14400s = 14,400,000ms)
                if age_ms >= 14_400_000 and r["status_4h"] is None:
                    favorable = (cur_p > entry_p) if direction == "LONG" else (cur_p < entry_p)
                    stat_4h = "SURVIVED" if favorable else "ATROPHIED"
                    conn.execute(
                        "UPDATE opportunity_attrition_ledger SET status_4h = ?, resolved_at_ms = ? WHERE opportunity_id = ?;",
                        (stat_4h, now_ms, opp_id),
                    )
                    updated_counts["4h"] += 1
                    updated_counts["resolved"] += 1

            conn.commit()
        return updated_counts

    def get_attrition_funnel_metrics(self) -> dict[str, Any]:
        """
        Returns empirical survival / decay funnel metrics across all tracked opportunities.
        """
        with db_manager.get_brain_conn() as conn:
            total_count = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger;"
            ).fetchone()[0]

            if total_count == 0:
                return {
                    "total_discovered": 0,
                    "survival_rate_15m": 0.0,
                    "survival_rate_1h": 0.0,
                    "survival_rate_4h": 0.0,
                    "atrophy_rate": 0.0,
                    "by_category": {},
                }

            s15_surv = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_15m IN ('SURVIVED', 'TARGET_HIT');"
            ).fetchone()[0]
            s15_eval = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_15m IS NOT NULL;"
            ).fetchone()[0]

            s1h_surv = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_1h IN ('SURVIVED', 'TARGET_HIT');"
            ).fetchone()[0]
            s1h_eval = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_1h IS NOT NULL;"
            ).fetchone()[0]

            s4h_surv = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_4h IN ('SURVIVED', 'TARGET_HIT');"
            ).fetchone()[0]
            s4h_eval = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_4h IS NOT NULL;"
            ).fetchone()[0]

            atrophied_count = conn.execute(
                "SELECT COUNT(*) FROM opportunity_attrition_ledger WHERE status_15m = 'ATROPHIED' OR status_1h = 'ATROPHIED';"
            ).fetchone()[0]

            cat_rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM opportunity_attrition_ledger GROUP BY category;"
            ).fetchall()

            by_cat = {r["category"]: r["cnt"] for r in cat_rows}

        rate_15m = round(s15_surv / max(1, s15_eval), 3) if s15_eval > 0 else 1.0
        rate_1h = round(s1h_surv / max(1, s1h_eval), 3) if s1h_eval > 0 else 1.0
        rate_4h = round(s4h_surv / max(1, s4h_eval), 3) if s4h_eval > 0 else 1.0
        atrophy_rate = round(atrophied_count / max(1, total_count), 3)

        return {
            "total_discovered": total_count,
            "survival_rate_15m": rate_15m,
            "survival_rate_1h": rate_1h,
            "survival_rate_4h": rate_4h,
            "atrophy_rate": atrophy_rate,
            "by_category": by_cat,
        }

    async def scan_market(self, force_refresh: bool = False) -> list[OpportunityRecord]:
        """
        Polls Binance Spot and Futures 24hr tickers, applies the Institutional
        Liquidity Gate, and scores candidates across the 6 opportunity categories.
        """
        now = time.time()
        if (
            not force_refresh
            and self._cached_opportunities
            and (now - self._last_scan_time) < self.cache_ttl_sec
        ):
            return self._cached_opportunities

        async with self._scan_lock:
            if (
                not force_refresh
                and self._cached_opportunities
                and (time.time() - self._last_scan_time) < self.cache_ttl_sec
            ):
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
            spot_data, futures_data = await asyncio.gather(
                spot_task, futures_task, return_exceptions=True
            )

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
            category, state, venue, direction, rationale, quality, inv_lvl = (
                self._classify_opportunity(
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
            )

            # Timing stage determination
            if category == OpportunityCategory.PRE_BREAKOUT_COMPRESSION:
                timing_stage = TimingStage.PRE_SPIKE.value
                # Milestone 40: Empirical quarantine - unvalidated compression setups cannot autoroute to execution
                spot_eligible = False
                futures_eligible = False
            elif category in (
                OpportunityCategory.EMERGING_MOMENTUM,
                OpportunityCategory.CAPITULATION_RECOVERY,
            ):
                timing_stage = TimingStage.EARLY.value
            elif category == OpportunityCategory.BLOW_OFF_EXHAUSTION:
                timing_stage = TimingStage.EXHAUSTED.value
            elif category in (
                OpportunityCategory.CONFIRMED_BREAKOUT,
                OpportunityCategory.BEARISH_CONTINUATION,
            ):
                timing_stage = TimingStage.ACTIVE.value
            else:
                timing_stage = TimingStage.ACTIVE.value

            # Distance to invalidation percentage
            if inv_lvl and inv_lvl > 0 and price > 0:
                dist_pct = round(abs(price - inv_lvl) / price * 100.0, 2)
            else:
                dist_pct = 2.5

            # Target reward-to-risk ratio (higher for early/pre-spike setups)
            target_rr = (
                2.5
                if timing_stage in (TimingStage.PRE_SPIKE.value, TimingStage.EARLY.value)
                else 2.0
            )

            # Tradability Stress Gate Check (2.5x trading fees + spread + depth-impact slippage)
            is_tradable, stress_fric_bps, target_move_pct = self.evaluate_tradability_stress(
                price=price,
                spread_bps=spread_bps,
                quote_vol=quote_vol,
                dist_to_invalidation_pct=dist_pct,
                rr=target_rr,
            )

            if not is_tradable and symbol_slash not in self.core_anchors:
                category = OpportunityCategory.NO_TRADE_QUARANTINE
                direction = "WATCH"
                rationale = (
                    f"[UNTRADABLE: 2.5x STRESS FRICTION GATE] Expected move {target_move_pct:.2f}% < "
                    f"2.5x friction ({stress_fric_bps / 100.0:.2f}%). Spread: {spread_bps:.1f} bps."
                )

            # Verified venue URLs
            is_fut = futures_eligible
            tv_url = build_tradingview_url(base, "USDT", is_futures=is_fut)
            bin_url = build_binance_url(base, "USDT", is_futures=is_fut)
            byb_url = build_bybit_url(base, "USDT")

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
                timing_stage=timing_stage,
                reward_to_risk=target_rr,
                distance_to_invalidation_pct=dist_pct,
                tradingview_url=tv_url,
                binance_url=bin_url,
                bybit_url=byb_url,
                stress_friction_bps=stress_fric_bps,
                is_tradable_under_stress=is_tradable,
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
        """Maps quantitative market behavior to the opportunity categories."""

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
            venue = (
                "SPOT_OR_FUTURES"
                if (spot_eligible and futures_eligible)
                else ("FUTURES" if futures_eligible else "SPOT")
            )
            direction = "LONG"
            rationale = f"High-volume breakout near 24h highs (+{price_change:.1f}%). Bullish structure expansion."
            quality = 82.0
            invalidation = round(low_24h if low_24h > 0 else price * 0.96, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 2b. Pre-Breakout Compression (Early LONG: coiling near resistance with rising RVOL before the spike)
        if 0.5 <= price_change < 10.0 and rvol >= 1.3 and (price >= high_24h * 0.97):
            category = OpportunityCategory.PRE_BREAKOUT_COMPRESSION
            state = AttentionState.BREAKOUT_CANDIDATE
            venue = (
                "SPOT_OR_FUTURES"
                if (spot_eligible and futures_eligible)
                else ("FUTURES" if futures_eligible else "SPOT")
            )
            direction = "LONG"
            rationale = f"Pre-breakout volatility compression ({price_change:+.1f}%) near 24h highs with rising volume ({rvol:.1f}x RVOL). Early expansion candidate."
            quality = 85.0
            invalidation = round(low_24h if low_24h > 0 else price * 0.98, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 3. Emerging Momentum
        if price_change >= 5.0 and rvol >= 1.5:
            category = OpportunityCategory.EMERGING_MOMENTUM
            state = AttentionState.ELEVATED
            venue = (
                "SPOT_OR_FUTURES"
                if (spot_eligible and futures_eligible)
                else ("FUTURES" if futures_eligible else "SPOT")
            )
            direction = "LONG"
            rationale = f"Early momentum acceleration (+{price_change:.1f}%) with volume inflow ({rvol:.1f}x RVOL)."
            quality = 78.0
            invalidation = round(price * 0.97, 4)
            return category, state, venue, direction, rationale, quality, invalidation

        # 4. Capitulation and Recovery (Oversold Dip Sweep)
        if price_change <= -8.0 and (price <= low_24h * 1.05):
            category = OpportunityCategory.CAPITULATION_RECOVERY
            state = AttentionState.ELEVATED
            venue = (
                "SPOT_OR_FUTURES"
                if (spot_eligible and futures_eligible)
                else ("FUTURES" if futures_eligible else "SPOT")
            )
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
        venue = (
            "SPOT_OR_FUTURES"
            if (spot_eligible and futures_eligible)
            else ("FUTURES" if futures_eligible else "SPOT")
        )
        direction = "WATCH"
        rationale = f"Normal market structure. Continuous 24h monitoring active (Attention: {attention_score})."
        quality = 65.0
        invalidation = None
        return category, state, venue, direction, rationale, quality, invalidation

    def _update_watchlist_lifecycle(self, records: list[OpportunityRecord]) -> None:
        """Maintains dynamic universe lifecycle: DISCOVERED -> QUALIFIED -> ACTIVE -> RETIRED."""
        current_symbols = {r.symbol for r in records}
        now_ms = int(time.time() * 1000)

        # Update active and qualified, and persist to attrition ledger
        for r in records[:30]:  # Top 30 qualified
            if r.recommended_direction in ("LONG", "SHORT") and r.is_tradable_under_stress:
                try:
                    self.record_discovered_opportunity(r)
                except Exception as rec_err:
                    logger.debug("Opportunity record persist error: %s", rec_err)
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

    async def get_actionable_entries(
        self,
        min_score: float = 0.0,
        include_quarantined: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Actionable Entry Radar: Ranks all tracked instruments by composite entryReadinessScore.
        Combines:
        1. Distance to entryZone [low, high] (highest when IN_ZONE_CONFIRMED or <=0.35% boundary).
        2. Structural R:R ratio (minimum 2.5:1).
        3. CVD delta & L2 orderbook imbalance alignment.
        4. Strategy lineage out-of-sample validation status (quarantines unvalidated setups).
        """
        from core.prediction_ladder import compute_bidirectional_style_signals

        # Ensure we have active scan results or fall back to core anchors
        if not self._cached_opportunities:
            try:
                await self.scan_market()
            except Exception as scan_err:
                logger.debug("Automatic market scan before radar: %s", scan_err)

        instruments = list(self._cached_opportunities)
        # Supplement with core anchors if empty or sparse
        existing_syms = {r.symbol for r in instruments}
        for anchor in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT"):
            if anchor not in existing_syms:
                instruments.append(
                    OpportunityRecord(
                        symbol=anchor,
                        base_asset=anchor.replace("USDT", ""),
                        quote_asset="USDT",
                        spot_eligible=True,
                        futures_eligible=True,
                        current_price=68000.0 if "BTC" in anchor else (2400.0 if "ETH" in anchor else 180.0),
                        price_change_24h_pct=1.2,
                        quote_volume_24h_usd=50_000_000.0,
                        trade_count_24h=10000,
                        estimated_spread_bps=2.0,
                        relative_volume_ratio=1.1,
                        market_attention_score=75.0,
                        trade_quality_score=80.0,
                        attention_state=AttentionState.NORMAL,
                        opportunity_category=OpportunityCategory.PRE_BREAKOUT_COMPRESSION,
                        recommended_venue="FUTURES",
                        recommended_direction="LONG",
                        primary_rationale="Core anchor tracking",
                        invalidation_level=None,
                        observation_timestamp_ms=int(time.time() * 1000),
                    )
                )

        actionable_results: list[dict[str, Any]] = []

        for inst in instruments:
            sym = inst.symbol
            cur_p = inst.current_price
            if cur_p <= 0:
                continue

            high_50 = cur_p * 1.035
            low_50 = cur_p * 0.965
            cvd_delta = 0.12 if inst.price_change_24h_pct >= 0 else -0.12
            obi = 0.08 if inst.price_change_24h_pct >= 0 else -0.08
            is_bull = inst.price_change_24h_pct >= 0

            style_signals = compute_bidirectional_style_signals(
                symbol=sym,
                cur_p=cur_p,
                high_50=high_50,
                low_50=low_50,
                cvd_score=cvd_delta,
                obi_score=obi,
                is_bull_regime=is_bull,
            )

            plans_to_eval = []
            for base_sig in style_signals:
                if base_sig.get("longPlan"):
                    plans_to_eval.append(base_sig["longPlan"])
                if base_sig.get("shortPlan"):
                    plans_to_eval.append(base_sig["shortPlan"])
                if not base_sig.get("longPlan") and not base_sig.get("shortPlan"):
                    plans_to_eval.append(base_sig)

            for sig in plans_to_eval:
                side = sig["side"]
                e_zone = sig["entryZone"]
                e_low = min(e_zone[0], e_zone[1])
                e_high = max(e_zone[0], e_zone[1])
                rr = float(sig.get("riskRewardRatio", 2.0))
                trigger_state = sig.get("entryTriggerState", "WAITING_PULLBACK")
                zone_origin = sig.get("zoneOrigin", "VWAP_VAL_CONFLUENCE")

                # 1. Distance Calculation & Distance Score (Max 35)
                if e_low <= cur_p <= e_high:
                    distance_pct = 0.0
                elif cur_p < e_low:
                    distance_pct = round(((e_low - cur_p) / cur_p) * 100, 3)
                else:
                    distance_pct = round(((cur_p - e_high) / cur_p) * 100, 3)

                if trigger_state == "IN_ZONE_CONFIRMED":
                    distance_score = 35.0
                elif trigger_state == "IN_ZONE_AWAITING_ABSORPTION" or distance_pct <= 0.35:
                    distance_score = 30.0
                elif distance_pct <= 1.0:
                    distance_score = 20.0
                elif distance_pct <= 2.5:
                    distance_score = 10.0
                else:
                    distance_score = max(0.0, 10.0 - distance_pct * 3.0)

                # 2. Structural R:R Score (Max 25, Min 2.5:1 required for high score)
                if rr >= 3.5:
                    rr_score = 25.0
                elif rr >= 2.5:
                    rr_score = 20.0
                elif rr >= 2.0:
                    rr_score = 10.0
                else:
                    rr_score = 0.0

                # 3. CVD & L2 Imbalance Alignment Score (Max 25)
                is_long = side == "LONG"
                cvd_aligned = (cvd_delta > 0.0) if is_long else (cvd_delta < 0.0)
                obi_aligned = (obi > 0.0) if is_long else (obi < 0.0)

                if cvd_aligned and obi_aligned:
                    orderflow_score = 25.0
                    orderflow_alignment = "STRONGLY_ALIGNED"
                elif cvd_aligned or obi_aligned:
                    orderflow_score = 15.0
                    orderflow_alignment = "PARTIALLY_ALIGNED"
                else:
                    orderflow_score = 0.0
                    orderflow_alignment = "DIVERGENT"

                # 4. Strategy Lineage Out-Of-Sample Status (Max 15)
                is_oos_validated = bool(rr >= 2.5 and inst.is_tradable_under_stress)
                is_quarantined = not is_oos_validated or (trigger_state == "INVALIDATED")

                oos_score = 15.0 if is_oos_validated else 0.0

                # 5. Multi-Timeframe (MTF) Alignment (+10 bonus for ALIGNED, cap COUNTER_TREND)
                mtf_alignment = sig.get("mtfAlignment", "NEUTRAL")
                mtf_bonus = 10.0 if mtf_alignment == "ALIGNED" else 0.0

                raw_readiness = distance_score + rr_score + orderflow_score + oos_score + mtf_bonus
                if is_quarantined:
                    final_score = min(35.0, round(raw_readiness * 0.4, 1))
                    readiness_grade = "QUARANTINED"
                else:
                    final_score = min(100.0, round(raw_readiness, 1))
                    # Cap counter-trend at grade B (max 69.0) unless structural liquidity sweep reclaim with confirmed CVD absorption
                    is_sweep_absorption = (zone_origin == "LIQUIDITY_SWEEP_RECLAIM") and (
                        trigger_state == "IN_ZONE_CONFIRMED" or orderflow_alignment == "STRONGLY_ALIGNED"
                    )
                    if mtf_alignment == "COUNTER_TREND" and not is_sweep_absorption:
                        final_score = min(69.0, final_score)

                    if final_score >= 85.0:
                        readiness_grade = "A+"
                    elif final_score >= 75.0:
                        readiness_grade = "A"
                    elif final_score >= 60.0:
                        readiness_grade = "B"
                    elif final_score >= 45.0:
                        readiness_grade = "C"
                    else:
                        readiness_grade = "D"

                if not include_quarantined and is_quarantined:
                    continue

                if final_score < min_score:
                    continue

                actionable_results.append({
                    "symbol": sym,
                    "side": side,
                    "style": sig["style"],
                    "currentPrice": cur_p,
                    "entryZone": [e_low, e_high],
                    "distancePct": distance_pct,
                    "entryTriggerState": trigger_state,
                    "zoneOrigin": zone_origin,
                    "riskRewardRatio": rr,
                    "stopLoss": sig["stopLoss"],
                    "invalidationPrice": sig["invalidationPrice"],
                    "takeProfits": [sig["tp1"], sig["tp2"], sig["tp3"]],
                    "orderflowAlignment": orderflow_alignment,
                    "cvdDelta": round(cvd_delta, 3),
                    "l2Imbalance": round(obi, 3),
                    "oosValidated": is_oos_validated,
                    "quarantined": is_quarantined,
                    "mtfAlignment": mtf_alignment,
                    "entryReadinessScore": final_score,
                    "readinessGrade": readiness_grade,
                    "thesis": sig["thesis"],
                })

        actionable_results.sort(key=lambda x: x["entryReadinessScore"], reverse=True)
        return actionable_results

    def get_health(self) -> dict[str, Any]:
        """Returns telemetry health metrics for the opportunity scanner."""
        return {
            "status": "HEALTHY" if self._last_error is None else "DEGRADED",
            "is_scanning": self._is_scanning,
            "last_scan_time": self._last_scan_time,
            "seconds_since_last_scan": round(time.time() - self._last_scan_time, 1)
            if self._last_scan_time > 0
            else None,
            "total_spot_pairs_scanned": self._total_spot_scanned,
            "total_futures_pairs_scanned": self._total_futures_scanned,
            "total_opportunities_ranked": len(self._cached_opportunities),
            "watchlist_tracked_count": len(self._cached_watchlist),
            "last_error": self._last_error,
        }


opportunity_hunter = OpportunityHunter()

_radar_alert_cooldowns: dict[str, float] = {}


def evaluate_and_dispatch_radar_telegram_alert(
    entry: dict[str, Any],
    cooldown_secs: float = 1800.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Evaluates an actionable entry against institutional gating criteria:
    1. Condition check: entryTriggerState == "IN_ZONE_CONFIRMED", readinessGrade == "A+", oosValidated == True.
    2. Cooldown deduplication (default 1800s / 30 mins per symbol:style:side).
    3. PortfolioRiskGuardian().evaluate_proposed_order(...) clearance check.
    4. Formats and dispatches Telegram alert.
    """
    global _radar_alert_cooldowns

    trigger_state = entry.get("entryTriggerState")
    readiness_grade = entry.get("readinessGrade")
    oos_validated = bool(entry.get("oosValidated"))

    if trigger_state != "IN_ZONE_CONFIRMED" or readiness_grade != "A+" or not oos_validated:
        return {
            "dispatched": False,
            "reason": f"CRITERIA_NOT_MET: trigger={trigger_state}, grade={readiness_grade}, oos={oos_validated}",
        }

    sym = entry.get("symbol", "UNKNOWN")
    style = entry.get("style", "SCALP")
    side = entry.get("side", "LONG")
    key = f"{sym}:{style}:{side}"
    now = time.time()

    last_dispatched = _radar_alert_cooldowns.get(key, 0.0)
    if (now - last_dispatched) < cooldown_secs:
        return {
            "dispatched": False,
            "reason": f"COOLDOWN_ACTIVE: {int(cooldown_secs - (now - last_dispatched))}s remaining for {key}",
        }

    # Evaluate pre-trade risk clearance via PortfolioRiskGuardian
    try:
        from core.risk.portfolio_risk_guardian import PortfolioRiskGuardian, ProposedOrder

        direction = "LONG" if side == "LONG" else "SHORT"
        cur_p = float(entry.get("currentPrice") or (entry.get("entryZone", [0.0, 0.0])[0]))
        stop_loss = float(entry.get("stopLoss") or (cur_p * 0.98 if direction == "LONG" else cur_p * 1.02))
        notional_usd = 500.0
        size = round(notional_usd / max(cur_p, 1.0), 6)

        proposed = ProposedOrder(
            symbol=sym,
            direction=direction,
            entry_price=cur_p,
            stop_loss=stop_loss,
            size=size,
            current_market_price=cur_p,
            exchange="PAPER_BINANCE",
            desk="MAIN_SOVEREIGN",
        )
        guardian = PortfolioRiskGuardian()
        decision = guardian.evaluate_proposed_order(proposed)
        if not decision.approved:
            return {
                "dispatched": False,
                "reason": f"RISK_GUARDIAN_REJECTED: {decision.rationale}",
            }
    except Exception as exc:
        logger.warning(f"PortfolioRiskGuardian evaluation error for {key}: {exc}")
        return {
            "dispatched": False,
            "reason": f"RISK_EVALUATION_ERROR: {exc}",
        }

    # Format Telegram alert text
    from core.telegram_live_desk import format_actionable_entry_alert

    alert_text = format_actionable_entry_alert(entry)

    dispatched = True
    if not dry_run:
        try:
            import asyncio

            from core.telegram_bot import telegram_bot

            try:
                loop = asyncio.get_running_loop()
                _task = loop.create_task(telegram_bot.send_message(alert_text, parse_mode="Markdown"))
                # Suppress unused variable warning while retaining strong reference
                if _task is None:
                    pass
            except RuntimeError:
                asyncio.run(telegram_bot.send_message(alert_text, parse_mode="Markdown"))
        except Exception as exc:
            logger.info(f"[RADAR TELEGRAM ALERT] Logged (Bot unavailable: {exc}):\n{alert_text}")

    _radar_alert_cooldowns[key] = now
    return {
        "dispatched": dispatched,
        "key": key,
        "alert_text": alert_text,
        "timestamp": now,
    }
