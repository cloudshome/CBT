"""core/ops/market_radar.py — Milestone 73: 24/7 Proactive Market Radar & Trader Copilot.

Actively monitors the 4h market (BTCUSDT, ETHUSDT, SOLUSDT, PAXGUSDT) on behalf of the trader,
detects approaching setups and regime shifts BEFORE a trade triggers, and delivers concise,
zero-spam bilingual (EN + BN) proactive surveillance updates.

Key Invariants:
1. FORECAST != SIGNAL: Market Radar is pre-trade surveillance only.
   It NEVER executes orders, fills trades, or modifies p2_shadow_ledger.db.
2. TIER_0_PAPER: REAL_CAPITAL_ENABLED = False permanently locked.
3. FAIL-CLOSED: If candle data is stale (stale_data_warning == True) or missing,
   radar_status = "STALE_DATA" with zero alerts fired.
4. ZERO-SPAM: Alert cooldown (default 4h) persisted in SQLite data/market_radar_state.db.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.risk.execution_isolation import REAL_CAPITAL_ENABLED
from core.strategies.p2_risk_parity import (
    CAPITAL_MODE,
    UNIVERSE,
    TodayDeskSnapshot,
    evaluate_p2_rp_snapshot,
    load_candles_for_p2_rp,
)

logger = logging.getLogger("cbt.market_radar")

RADAR_COOLDOWN_HOURS = 4.0
PROXIMITY_THRESHOLD_PCT = 3.0
VOLATILITY_SPIKE_THRESHOLD_PCT = 80.0


@dataclass
class RadarAlert:
    """Pre-trade surveillance alert emitted by Market Radar."""

    alert_key: str
    symbol: str
    alert_type: str  # "NEAR_S1_BREAKOUT" | "APPROACHING_EMA200" | "MOMENTUM_FLIP_WATCH" | "VOLATILITY_SPIKE" | "REGIME_SHIFT"
    priority: str  # "HIGH" | "MEDIUM" | "INFO" | "CAUTION"
    headline_en: str
    headline_bn: str
    details_en: str = ""
    details_bn: str = ""
    timestamp_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetProximity:
    """Proximity metrics for an asset relative to its next actionable trigger."""

    symbol: str
    price: float
    ema_status: str
    distance_to_ema200_pct: float
    distance_to_breakout_pct: float
    momentum_30d_pct: float
    vol_20d_ann_pct: float
    s1_status: str
    s2_status: str
    closest_trigger_type: str  # "ACTIVE_LONG" | "S1_BREAKOUT" | "EMA200_RECLAIM"
    proximity_pct: float
    rank: int = 1
    summary_en: str = ""
    summary_bn: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketRadarReport:
    """Full operational market radar report."""

    radar_status: str  # "ACTIVE_WATCH" | "ALERT_ACTIVE" | "STALE_DATA" | "NOT_INITIALIZED"
    checked_at_utc: str
    data_source: str
    data_age_hours: float
    stale_data_warning: bool
    current_regime: str
    last_regime: str | None
    action_verdict: str
    closest_setup: AssetProximity | None
    ranked_assets: list[AssetProximity] = field(default_factory=list)
    active_alerts: list[RadarAlert] = field(default_factory=list)
    new_alerts_fired: list[RadarAlert] = field(default_factory=list)
    headline_en: str = ""
    headline_bn: str = ""
    action_guidance_en: str = ""
    action_guidance_bn: str = ""
    capital_mode: str = CAPITAL_MODE
    real_capital_enabled: bool = REAL_CAPITAL_ENABLED

    def to_dict(self) -> dict[str, Any]:
        return {
            "radar_status": self.radar_status,
            "checked_at_utc": self.checked_at_utc,
            "data_source": self.data_source,
            "data_age_hours": self.data_age_hours,
            "stale_data_warning": self.stale_data_warning,
            "current_regime": self.current_regime,
            "last_regime": self.last_regime,
            "action_verdict": self.action_verdict,
            "closest_setup": self.closest_setup.to_dict() if self.closest_setup else None,
            "ranked_assets": [a.to_dict() for a in self.ranked_assets],
            "active_alerts": [a.to_dict() for a in self.active_alerts],
            "new_alerts_fired": [a.to_dict() for a in self.new_alerts_fired],
            "headline_en": self.headline_en,
            "headline_bn": self.headline_bn,
            "action_guidance_en": self.action_guidance_en,
            "action_guidance_bn": self.action_guidance_bn,
            "capital_mode": self.capital_mode,
            "real_capital_enabled": self.real_capital_enabled,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


def get_default_radar_db_path() -> Path:
    """Returns the default SQLite path for Market Radar state & cooldown tracking."""
    return Path(__file__).resolve().parent.parent.parent / "data" / "market_radar_state.db"


def init_radar_db(db_path: Path | str) -> sqlite3.Connection:
    """Initializes dedicated SQLite database for Market Radar state and anti-spam cooldowns."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radar_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radar_alerts (
            alert_key TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            priority TEXT NOT NULL,
            headline_en TEXT NOT NULL,
            headline_bn TEXT NOT NULL,
            last_fired_ts REAL NOT NULL,
            fire_count INTEGER DEFAULT 1
        )
        """
    )
    conn.commit()
    return conn


def get_radar_state(conn: sqlite3.Connection, key: str) -> str | None:
    """Retrieves state string from radar_state table."""
    row = conn.execute("SELECT value FROM radar_state WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def set_radar_state(conn: sqlite3.Connection, key: str, value: str, now_utc_iso: str) -> None:
    """Stores key-value pair in radar_state table."""
    conn.execute(
        """
        INSERT INTO radar_state (key, value, updated_at_utc)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at_utc=excluded.updated_at_utc
        """,
        (key, value, now_utc_iso),
    )
    conn.commit()


def is_alert_in_cooldown(
    conn: sqlite3.Connection,
    alert_key: str,
    now_ts: float,
    cooldown_hours: float = RADAR_COOLDOWN_HOURS,
) -> bool:
    """Determines whether an alert key is currently throttled by the 4h cooldown."""
    row = conn.execute("SELECT last_fired_ts FROM radar_alerts WHERE alert_key = ?", (alert_key,)).fetchone()
    if not row:
        return False
    last_fired_ts = float(row[0])
    return (now_ts - last_fired_ts) < (cooldown_hours * 3600.0)


def record_alert_fired(conn: sqlite3.Connection, alert: RadarAlert, now_ts: float) -> None:
    """Records an alert firing in SQLite to enforce cooldown on future runs."""
    conn.execute(
        """
        INSERT INTO radar_alerts (alert_key, symbol, alert_type, priority, headline_en, headline_bn, last_fired_ts, fire_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(alert_key) DO UPDATE SET
            headline_en=excluded.headline_en,
            headline_bn=excluded.headline_bn,
            last_fired_ts=excluded.last_fired_ts,
            fire_count=fire_count + 1
        """,
        (
            alert.alert_key,
            alert.symbol,
            alert.alert_type,
            alert.priority,
            alert.headline_en,
            alert.headline_bn,
            now_ts,
        ),
    )
    conn.commit()


def run_market_radar(
    db_path: Path | str | None = None,
    notify_callback: Callable[[MarketRadarReport], Any] | None = None,
    cooldown_hours: float = RADAR_COOLDOWN_HOURS,
    force_brief: bool = False,
    offline_only: bool = False,
    now_utc: datetime | None = None,
    snapshot_override: TodayDeskSnapshot | None = None,
) -> MarketRadarReport:
    """Executes 24/7 proactive market surveillance across the 4h universe.

    Steps:
    1. Evaluates TodayDeskSnapshot (live Binance or local Parquet).
    2. Fail-closed: If data is stale or corrupted, returns STALE_DATA with zero alerts.
    3. Scans all 4 assets for proximity to actionable triggers (NEAR_S1_BREAKOUT, APPROACHING_EMA200, MOMENTUM_FLIP_WATCH, VOLATILITY_SPIKE).
    4. Detects macro regime transitions against SQLite-persisted history.
    5. Ranks opportunities by proximity distance and highlights #1 Closest Setup.
    6. Filters alerts through strict 4h anti-spam cooldown.
    7. Delivers proactive notification if new HIGH/MEDIUM alerts fired or force_brief=True.
    """
    resolved_db = Path(db_path) if db_path is not None else get_default_radar_db_path()
    conn = init_radar_db(resolved_db)

    now = now_utc if now_utc is not None else datetime.now(UTC)
    now_iso = now.isoformat()
    now_ts = now.timestamp()

    # 1. Obtain Snapshot
    if snapshot_override is not None:
        snapshot = snapshot_override
    else:
        source_req = "parquet" if offline_only else "auto"
        try:
            candles, data_source = load_candles_for_p2_rp(source=source_req)
            snapshot = evaluate_p2_rp_snapshot(
                candles_by_symbol=candles,
                account_equity=10_000.0,
                data_source=data_source,
            )
        except Exception as e:
            logger.warning(f"Market radar could not load candles ({e}); entering fail-closed mode.")
            snapshot = TodayDeskSnapshot.create_fail_closed(
                account_equity=10_000.0,
                data_source="ERROR",
                reason=str(e),
            )

    # 2. Fail-Closed Check on Stale or Erroneous Data
    if snapshot.stale_data_warning or not snapshot.assets:
        conn.close()
        return MarketRadarReport(
            radar_status="STALE_DATA",
            checked_at_utc=now_iso,
            data_source=snapshot.data_source,
            data_age_hours=snapshot.data_age_hours,
            stale_data_warning=True,
            current_regime=snapshot.regime_label or "UNKNOWN",
            last_regime=None,
            action_verdict=snapshot.action_verdict or "FAIL_CLOSED",
            closest_setup=None,
            ranked_assets=[],
            active_alerts=[],
            new_alerts_fired=[],
            headline_en="Market Radar: STALE DATA / FEED UNAVAILABLE",
            headline_bn="মার্কেট রাডার: ডাটা পুরানো / ফিড অপ্রাপ্য",
            action_guidance_en="Market data is stale or disconnected. Stand aside — fail-closed active.",
            action_guidance_bn="মার্কেট ডাটা পুরানো বা সংযোগ বিচ্ছিন্ন। দূরে থাকুন — ফেইল-ক্লোজড সক্রিয়।",
        )

    # 3. Regime Shift Detection
    last_regime = get_radar_state(conn, "last_regime_label")
    current_regime = snapshot.regime_label
    regime_alerts: list[RadarAlert] = []

    if last_regime is not None and last_regime != current_regime:
        regime_alerts.append(
            RadarAlert(
                alert_key=f"REGIME_SHIFT_{last_regime}_TO_{current_regime}",
                symbol="PORTFOLIO",
                alert_type="REGIME_SHIFT",
                priority="HIGH",
                headline_en=f"Regime Shift Detected: {last_regime} -> {current_regime}",
                headline_bn=f"মার্কেট রেজিম পরিবর্তন সনাক্ত: {last_regime} -> {current_regime}",
                details_en=f"P2_RP macro regime transitioned from {last_regime} to {current_regime}.",
                details_bn=f"P2_RP ম্যাক্রো রেজিম {last_regime} থেকে পরিবর্তিত হয়ে {current_regime}-এ স্থানান্তরিত হয়েছে।",
                timestamp_utc=now_iso,
            )
        )

    # 4. Pre-Trigger Proximity Scanner & Opportunity Ranking
    active_alerts: list[RadarAlert] = list(regime_alerts)
    proximities: list[AssetProximity] = []

    for sym in UNIVERSE:
        asset = snapshot.assets.get(sym)
        if not asset:
            continue

        # Proximity measurement
        # If ACTIVE_LONG: distance is 0.0%
        # If ABOVE EMA200: distance is distance_to_breakout_pct
        # If BELOW EMA200: distance is abs(distance_to_ema200_pct)
        if asset.s1_status == "ACTIVE_LONG":
            proximity_pct = 0.0
            trigger_type = "ACTIVE_LONG"
        elif asset.ema_status == "ABOVE":
            proximity_pct = max(0.0, float(asset.distance_to_breakout_pct))
            trigger_type = "S1_BREAKOUT"
        else:
            proximity_pct = float(abs(asset.distance_to_ema200_pct))
            trigger_type = "EMA200_RECLAIM"

        summary_en = (
            f"{sym}: {proximity_pct:.1f}% to {trigger_type} "
            f"[Price: ${asset.price:,.2f} | EMA200: {asset.ema_status} | Mom30d: {asset.momentum_30d_pct:+.1f}%]"
        )
        summary_bn = (
            f"{sym}: {trigger_type} থেকে {proximity_pct:.1f}% দূরে "
            f"[মূল্য: ${asset.price:,.2f} | ইএমএ-২০০: {asset.ema_status} | ৩০ দিনের মোমেন্টাম: {asset.momentum_30d_pct:+.1f}%]"
        )

        prox_obj = AssetProximity(
            symbol=sym,
            price=asset.price,
            ema_status=asset.ema_status,
            distance_to_ema200_pct=asset.distance_to_ema200_pct,
            distance_to_breakout_pct=asset.distance_to_breakout_pct,
            momentum_30d_pct=asset.momentum_30d_pct,
            vol_20d_ann_pct=asset.vol_20d_ann_pct,
            s1_status=asset.s1_status,
            s2_status=asset.s2_status,
            closest_trigger_type=trigger_type,
            proximity_pct=proximity_pct,
            summary_en=summary_en,
            summary_bn=summary_bn,
        )
        proximities.append(prox_obj)

        # Alert Check 1: NEAR_S1_BREAKOUT (HIGH priority)
        # Condition: Above EMA 200 and within 3.0% of Donchian-48 High (or ACTIVE_LONG)
        if asset.s1_status == "ACTIVE_LONG":
            active_alerts.append(
                RadarAlert(
                    alert_key=f"{sym}_ACTIVE_S1_LONG",
                    symbol=sym,
                    alert_type="NEAR_S1_BREAKOUT",
                    priority="HIGH",
                    headline_en=f"{sym} Active Donchian-48 Breakout! Long trigger active.",
                    headline_bn=f"{sym} ডোঙ্কিয়ান-৪৮ ব্রেকআউট সক্রিয়! লং ট্রিগার একটিভ।",
                    details_en=f"Price ${asset.price:,.2f} has broken out above Donchian-48 high (${asset.donchian48_high:,.2f}).",
                    details_bn=f"মূল্য ${asset.price:,.2f} ডোঙ্কিয়ান-৪৮ হাই (${asset.donchian48_high:,.2f})-এর উপরে অবস্থান করছে।",
                    timestamp_utc=now_iso,
                )
            )
        elif asset.ema_status == "ABOVE" and 0.0 < asset.distance_to_breakout_pct <= PROXIMITY_THRESHOLD_PCT:
            active_alerts.append(
                RadarAlert(
                    alert_key=f"{sym}_NEAR_S1_BREAKOUT",
                    symbol=sym,
                    alert_type="NEAR_S1_BREAKOUT",
                    priority="HIGH",
                    headline_en=f"{sym} Near S1 Breakout ({asset.distance_to_breakout_pct:.1f}% to Donchian-48 High)",
                    headline_bn=f"{sym} এস১ ব্রেকআউটের কাছাকাছি (ডোঙ্কিয়ান-৪৮ হাই থেকে {asset.distance_to_breakout_pct:.1f}% দূরে)",
                    details_en=f"Price ${asset.price:,.2f} is within {asset.distance_to_breakout_pct:.1f}% of Donchian-48 high (${asset.donchian48_high:,.2f}).",
                    details_bn=f"মূল্য ${asset.price:,.2f} ডোঙ্কিয়ান-৪৮ হাই (${asset.donchian48_high:,.2f}) থেকে মাত্র {asset.distance_to_breakout_pct:.1f}% দূরে।",
                    timestamp_utc=now_iso,
                )
            )

        # Alert Check 2: APPROACHING_EMA200 (MEDIUM priority)
        # Condition: Below EMA 200 but within 3.0% of reclaiming it (-3.0 <= distance_to_ema200_pct < 0)
        if asset.ema_status == "BELOW" and -PROXIMITY_THRESHOLD_PCT <= asset.distance_to_ema200_pct < 0.0:
            dist_val = abs(asset.distance_to_ema200_pct)
            active_alerts.append(
                RadarAlert(
                    alert_key=f"{sym}_APPROACHING_EMA200",
                    symbol=sym,
                    alert_type="APPROACHING_EMA200",
                    priority="MEDIUM",
                    headline_en=f"{sym} Approaching EMA-200 ({dist_val:.1f}% below recovery line)",
                    headline_bn=f"{sym} ইএমএ-২০০ রিকভারির কাছাকাছি ({dist_val:.1f}% নিচে)",
                    details_en=f"Price ${asset.price:,.2f} is {dist_val:.1f}% below 200 EMA (${asset.ema200_price:,.2f}).",
                    details_bn=f"মূল্য ${asset.price:,.2f} ২০০ ইএমএ (${asset.ema200_price:,.2f}) থেকে {dist_val:.1f}% নিচে অবস্থান করছে।",
                    timestamp_utc=now_iso,
                )
            )

        # Alert Check 3: MOMENTUM_FLIP_WATCH (MEDIUM priority)
        # Condition: 30-day momentum near zero crossing (-3.0 <= momentum_30d_pct <= 3.0)
        if -PROXIMITY_THRESHOLD_PCT <= asset.momentum_30d_pct <= PROXIMITY_THRESHOLD_PCT:
            active_alerts.append(
                RadarAlert(
                    alert_key=f"{sym}_MOMENTUM_FLIP_WATCH",
                    symbol=sym,
                    alert_type="MOMENTUM_FLIP_WATCH",
                    priority="MEDIUM",
                    headline_en=f"{sym} Momentum Flip Watch (30d momentum {asset.momentum_30d_pct:+.1f}% near zero-line)",
                    headline_bn=f"{sym} মোমেন্টাম ফ্লিপ ওয়াচ (৩০ দিনের মোমেন্টাম {asset.momentum_30d_pct:+.1f}% শূন্য রেখার সন্নিকটে)",
                    details_en=f"30-day momentum is {asset.momentum_30d_pct:+.1f}%, near zero-crossing for S2-Div ranking.",
                    details_bn=f"৩০ দিনের মোমেন্টাম {asset.momentum_30d_pct:+.1f}%, এস২-ডিভ র‍্যাংকিংয়ে শূন্য রেখা অতিক্রম করার সন্নিকটে।",
                    timestamp_utc=now_iso,
                )
            )

        # Alert Check 4: VOLATILITY_SPIKE (INFO/CAUTION priority)
        # Condition: vol_20d_ann_pct >= 80.0
        if asset.vol_20d_ann_pct >= VOLATILITY_SPIKE_THRESHOLD_PCT:
            active_alerts.append(
                RadarAlert(
                    alert_key=f"{sym}_VOLATILITY_SPIKE",
                    symbol=sym,
                    alert_type="VOLATILITY_SPIKE",
                    priority="INFO",
                    headline_en=f"{sym} High Volatility Spike ({asset.vol_20d_ann_pct:.1f}% ann; sizing compressed)",
                    headline_bn=f"{sym} উচ্চ অস্থিরতা স্পাইক ({asset.vol_20d_ann_pct:.1f}% বার্ষিক; সাইজিং সংকুচিত)",
                    details_en=f"20-day annualized volatility reached {asset.vol_20d_ann_pct:.1f}%. Volatility targeting is compressing risk-parity weights.",
                    details_bn=f"২০ দিনের বার্ষিক অস্থিরতা {asset.vol_20d_ann_pct:.1f}%-এ পৌঁছেছে। ভোলাটিলিটি টার্গেটিং ঝুঁকি-সমতা বরাদ্দ সংকুচিত করছে।",
                    timestamp_utc=now_iso,
                )
            )

    # Sort proximities to establish opportunity ranking
    proximities.sort(key=lambda p: p.proximity_pct)
    for idx, p in enumerate(proximities, start=1):
        p.rank = idx

    closest_setup = proximities[0] if proximities else None

    # Determine Headline & Action Guidance
    if closest_setup:
        if closest_setup.closest_trigger_type == "ACTIVE_LONG":
            headline_en = f"#1 Closest Setup: {closest_setup.symbol} ACTIVE LONG (Trigger confirmed)"
            headline_bn = f"#১ নিকটতম সেটআপ: {closest_setup.symbol} একটিভ লং (ট্রিগার নিশ্চিত)"
            action_guidance_en = (
                f"{closest_setup.symbol} has confirmed Donchian-48 breakout above EMA-200. "
                "P2_RP maintains risk-parity exposure."
            )
            action_guidance_bn = (
                f"{closest_setup.symbol} ডোঙ্কিয়ান-৪৮ ব্রেকআউট নিশ্চিত করেছে। "
                "P2_RP ঝুঁকি-সমতা বরাদ্দ বজায় রেখেছে।"
            )
        elif closest_setup.closest_trigger_type == "S1_BREAKOUT":
            headline_en = (
                f"#1 Closest Setup: {closest_setup.symbol} near S1 Breakout "
                f"({closest_setup.proximity_pct:.1f}% to Donchian-48 High)"
            )
            headline_bn = (
                f"#১ নিকটতম সেটআপ: {closest_setup.symbol} এস১ ব্রেকআউটের কাছে "
                f"(ডোঙ্কিয়ান-৪৮ হাই থেকে {closest_setup.proximity_pct:.1f}% দূরে)"
            )
            c_asset = snapshot.assets.get(closest_setup.symbol)
            h_price = c_asset.donchian48_high if c_asset else 0.0
            action_guidance_en = (
                f"Surveillance active. Prepare for long entry when 4h close confirms breakout above ${h_price:,.2f}."
            )
            action_guidance_bn = (
                f"সার্ভিল্যান্স সক্রিয়। ৪ ঘণ্টার ক্যান্ডেল ক্লোজে ${h_price:,.2f}-এর উপরে ব্রেকআউট নিশ্চিত হলে লং এন্ট্রি প্রস্তুত হবে।"
            )
        else:  # EMA200_RECLAIM
            headline_en = (
                f"#1 Closest Setup: {closest_setup.symbol} approaching EMA-200 "
                f"({closest_setup.proximity_pct:.1f}% below recovery line)"
            )
            headline_bn = (
                f"#১ নিকটতম সেটআপ: {closest_setup.symbol} ইএমএ-২০০ রিকভারির কাছাকাছি "
                f"({closest_setup.proximity_pct:.1f}% নিচে)"
            )
            c_asset = snapshot.assets.get(closest_setup.symbol)
            e_price = c_asset.ema200_price if c_asset else 0.0
            action_guidance_en = (
                f"Bear Shield active. Watching for structural reclaim above 200 EMA (${e_price:,.2f}) before breakout tracking."
            )
            action_guidance_bn = (
                f"বেয়ার শিল্ড সক্রিয়। ব্রেকআউট ট্র্যাক করার আগে ২০০ ইএমএ (${e_price:,.2f})-এর উপরে মার্কেট রিকভারি পর্যবেক্ষণ করা হচ্ছে।"
            )
    else:
        headline_en = "No setups within 3% trigger zone — Bear Shield active."
        headline_bn = "৩% ট্রিগার জোনের মধ্যে কোনো সেটআপ নেই — বেয়ার শিল্ড সক্রিয়।"
        action_guidance_en = "All assets below EMA-200 or out of range. 100% Cash / PAXG defensive shield active."
        action_guidance_bn = "সমস্ত অ্যাসেট ২০০ ইএমএ-এর নিচে বা সীমার বাইরে। ১০০% ক্যাশ / PAXG রক্ষণাত্মক শিল্ড সক্রিয়।"

    # 5. Cooldown Filtering and SQLite State Persistence
    new_alerts_fired: list[RadarAlert] = []
    for alert in active_alerts:
        in_cooldown = is_alert_in_cooldown(conn, alert.alert_key, now_ts, cooldown_hours=cooldown_hours)
        if not in_cooldown:
            new_alerts_fired.append(alert)
            record_alert_fired(conn, alert, now_ts)

    # Persist updated regime and action verdict in radar_state
    set_radar_state(conn, "last_regime_label", current_regime, now_iso)
    set_radar_state(conn, "last_action_verdict", snapshot.action_verdict, now_iso)
    set_radar_state(conn, "last_checked_at_utc", now_iso, now_iso)
    conn.close()

    # Determine radar_status
    if any(a.priority in ("HIGH", "MEDIUM") for a in active_alerts):
        radar_status = "ALERT_ACTIVE"
    else:
        radar_status = "ACTIVE_WATCH"

    report = MarketRadarReport(
        radar_status=radar_status,
        checked_at_utc=now_iso,
        data_source=snapshot.data_source,
        data_age_hours=snapshot.data_age_hours,
        stale_data_warning=False,
        current_regime=current_regime,
        last_regime=last_regime,
        action_verdict=snapshot.action_verdict,
        closest_setup=closest_setup,
        ranked_assets=proximities,
        active_alerts=active_alerts,
        new_alerts_fired=new_alerts_fired,
        headline_en=headline_en,
        headline_bn=headline_bn,
        action_guidance_en=action_guidance_en,
        action_guidance_bn=action_guidance_bn,
    )

    # 6. Optional Notification Dispatch
    if notify_callback is not None:
        has_actionable_new_alert = any(a.priority in ("HIGH", "MEDIUM") for a in new_alerts_fired)
        if has_actionable_new_alert or force_brief:
            try:
                notify_callback(report)
            except Exception as n_err:
                logger.error(f"Error executing market radar notify_callback: {n_err}")

    return report


def format_radar_report(report: MarketRadarReport, lang: str = "en") -> str:
    """Formats MarketRadarReport into institutional, scannable CLI/Telegram text in English or Bengali."""
    is_bn = str(lang).lower() in ("bn", "bangla", "bengali")

    if report.radar_status == "STALE_DATA" or report.stale_data_warning:
        if is_bn:
            return (
                "================================================================\n"
                "সিবিটি সার্বক্ষণিক মার্কেট রাডার ও ট্রেডার কোপাইলট\n"
                "================================================================\n"
                f"স্ট্যাটাস     : {report.radar_status} (ফেইল-ক্লোজড)\n"
                f"যাচাইয়ের সময় : {report.checked_at_utc}\n"
                f"ডাটার বয়স    : {report.data_age_hours:.1f} ঘণ্টা\n"
                "----------------------------------------------------------------\n"
                f"{report.headline_bn}\n"
                f"দিকনির্দেশনা : {report.action_guidance_bn}\n"
                "================================================================\n"
                "[TIER_0_PAPER — রিয়েল ক্যাপিটাল সম্পূর্ণ নিষ্ক্রিয়]"
            )
        return (
            "================================================================\n"
            "CBT PROACTIVE MARKET RADAR & TRADER COPILOT\n"
            "================================================================\n"
            f"Radar Status : {report.radar_status} (FAIL-CLOSED)\n"
            f"Checked At   : {report.checked_at_utc}\n"
            f"Data Age     : {report.data_age_hours:.1f}h\n"
            "----------------------------------------------------------------\n"
            f"{report.headline_en}\n"
            f"Guidance     : {report.action_guidance_en}\n"
            "================================================================\n"
            "[TIER_0_PAPER — REAL CAPITAL DISABLED]"
        )

    if is_bn:
        lines = [
            "================================================================",
            "সিবিটি সার্বক্ষণিক মার্কেট রাডার ও ট্রেডার কোপাইলট",
            "================================================================",
            f"যাচাইয়ের সময়  : {report.checked_at_utc} (ডাটার বয়স: {report.data_age_hours:.1f}h)",
            f"রাডার স্ট্যাটাস: {report.radar_status} | রেজিম: {report.current_regime}",
            f"সিদ্ধান্ত       : {report.action_verdict}",
            "----------------------------------------------------------------",
            "শীর্ষ সুযোগ (#১ নিকটতম সেটআপ):",
            f"  • {report.headline_bn}",
            f"    দিকনির্দেশনা: {report.action_guidance_bn}",
            "----------------------------------------------------------------",
            "অ্যাসেট প্রক্সিমিটি র‍্যাংকিং (ট্রিগার নৈকট্য):",
        ]
        for p in report.ranked_assets:
            lines.append(f"  {p.rank}. {p.summary_bn}")

        lines.append("----------------------------------------------------------------")
        lines.append(f"সক্রিয় রাডার অ্যালার্ট ({len(report.active_alerts)}):")
        if not report.active_alerts:
            lines.append("  • ৩% ট্রিগার জোনের মধ্যে কোনো সেটআপ নেই — বেয়ার শিল্ড সক্রিয়।")
        else:
            for a in report.active_alerts:
                lines.append(f"  [{a.priority}] {a.alert_key}: {a.headline_bn}")

        lines.extend([
            "================================================================",
            "[TIER_0_PAPER — রিয়েল ক্যাপিটাল সম্পূর্ণ নিষ্ক্রিয়]",
        ])
        return "\n".join(lines)

    # English default
    lines = [
        "================================================================",
        "CBT PROACTIVE MARKET RADAR & TRADER COPILOT",
        "================================================================",
        f"Checked At   : {report.checked_at_utc} (Data Age: {report.data_age_hours:.1f}h)",
        f"Radar Status : {report.radar_status} | Regime: {report.current_regime}",
        f"Verdict      : {report.action_verdict}",
        "----------------------------------------------------------------",
        "TOP OPPORTUNITY (#1 CLOSEST SETUP):",
        f"  • {report.headline_en}",
        f"    Guidance: {report.action_guidance_en}",
        "----------------------------------------------------------------",
        "ASSET PROXIMITY LADDER (NEXT ACTIONABLE TRIGGER):",
    ]
    for p in report.ranked_assets:
        lines.append(f"  {p.rank}. {p.summary_en}")

    lines.append("----------------------------------------------------------------")
    lines.append(f"ACTIVE RADAR ALERTS ({len(report.active_alerts)}):")
    if not report.active_alerts:
        lines.append("  • No setups within 3% trigger zone — Bear Shield active.")
    else:
        for a in report.active_alerts:
            lines.append(f"  [{a.priority}] {a.alert_key}: {a.headline_en}")

    lines.extend([
        "================================================================",
        "[TIER_0_PAPER — REAL CAPITAL DISABLED]",
    ])
    return "\n".join(lines)
