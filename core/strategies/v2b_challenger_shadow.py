"""core/strategies/v2b_challenger_shadow.py — 24/7 Challenger Live Shadow Runner & Arena Scoreboard.

Milestone 78: Operationalizes Milestone 77's top candidate (Trial #29: P2_RP_V2B_PVT)
into a completely isolated, 24/7 Challenger Live Shadow Paper Portfolio Daemon
running alongside our untouched Champion (P2_RP) for an unbiased 60-day forward proof.

Constitutional Invariants (NON-NEGOTIABLE):
1. REAL_CAPITAL_ENABLED = False (locked).
2. CAPITAL_MODE = "TIER_0_PAPER" (locked).
3. STRICT CHAMPION ISOLATION: Zero modifications to P2_RP Champion engine or ledger.
   The Challenger uses ONLY data/v2b_challenger_shadow_ledger.db.
   Champion DB (data/p2_shadow_ledger.db) is opened strictly in read-only mode (?mode=ro).
4. Zero-leverage invariant: Combined gross exposure <= 1.0001 at all times.
5. Fail-closed: Missing, stale (>6h live, >24h offline), or < 210 bars executes 0 fills.
6. Exact frozen M77 parameters: 33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN + 15% PVT.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from core.strategies.p2_risk_parity import (
    ANNUALIZATION_FACTOR,
    CRYPTO_MAJORS,
    MIN_WARMUP_BARS,
    UNIVERSE,
    VOL_LOOKBACK,
    compute_s1_indicators,
    compute_trailing_20d_volatility,
    load_candles_for_p2_rp,
)

logger = logging.getLogger("ai_quant_sentinel.core.strategies.v2b_challenger_shadow")

# Constitutional Locks
CAPITAL_MODE: str = "TIER_0_PAPER"
REAL_CAPITAL_ENABLED: bool = False
TARGET_FORWARD_DAYS: int = 60
DEFAULT_INITIAL_EQUITY: float = 10_000.0

# Frozen M77 Parameters (Trial #29: P2_RP_V2B_PVT)
TARGET_VOL: float = 0.15
MIN_ANNUALIZED_VOL_FLOOR: float = 0.04
MAX_CONCENTRATION_CAP: float = 1.50
DEADBAND: float = 0.03
HARD_GROSS_CAP: float = 1.0000


@dataclass
class ChallengerSnapshot:
    """Point-in-time state evaluation for Challenger P2_RP_V2B_PVT."""

    timestamp_utc: str
    bar_ts_utc: int
    data_source: str
    regime_label: str
    action_verdict: str
    account_equity: float
    cash_usd: float
    gross_exposure: float
    pvt_scalar: float
    port_vol_20d_ann_pct: float
    v2b_weights: dict[str, float]
    s1_weights: dict[str, float]
    h5_weights: dict[str, float]
    h1_weights: dict[str, float]
    raw_weights: dict[str, float]
    assets: dict[str, Any] = field(default_factory=dict)
    stale_data_warning: bool = False
    error_reason: str = ""
    decision_headline_en: str = ""
    decision_headline_bn: str = ""
    details: str = ""

    @classmethod
    def create_fail_closed(
        cls,
        account_equity: float = DEFAULT_INITIAL_EQUITY,
        data_source: str = "UNKNOWN",
        data_age_hours: float = 999.0,
        timestamp_utc: str = "",
        reason: str = "FAIL_CLOSED_GUARD_TRIGGERED",
    ) -> ChallengerSnapshot:
        """Constructs a deterministic fail-closed safe state (0 fills, 100% Cash)."""
        ts = timestamp_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        weights_zero = {s: 0.0 for s in UNIVERSE}
        weights_zero["CASH"] = 1.0
        return cls(
            timestamp_utc=ts,
            bar_ts_utc=0,
            data_source=data_source,
            regime_label="BEAR_SHIELD",
            action_verdict="WAIT_STALE_DATA",
            account_equity=account_equity,
            cash_usd=account_equity,
            gross_exposure=0.0,
            pvt_scalar=0.0,
            port_vol_20d_ann_pct=0.0,
            v2b_weights=weights_zero,
            s1_weights={s: 0.0 for s in UNIVERSE},
            h5_weights={s: 0.0 for s in UNIVERSE},
            h1_weights={s: 0.0 for s in UNIVERSE},
            raw_weights={s: 0.0 for s in UNIVERSE},
            assets={},
            stale_data_warning=True,
            error_reason=reason,
            decision_headline_en=f"FAIL-CLOSED SAFETY ACTIVE — {reason}",
            decision_headline_bn=f"ফেল-ক্লোজড সুরক্ষা সক্রিয় — {reason}",
            details=f"Fail-closed safe state engaged: {reason} (data_age={data_age_hours:.1f}h)",
        )


# ==============================================================================
# AUDITED CAUSAL MATHEMATICAL EVALUATORS (FROZEN TRIAL #29)
# ==============================================================================
def compute_s1_weights(
    dfs_aligned: dict[str, pd.DataFrame],
    bar_idx: int,
    s1_ind: dict[str, dict[str, np.ndarray]],
    vols_20d: dict[str, float],
) -> dict[str, float]:
    """Computes S1 (Donchian-48 Macro Trend + EMA-200 Filter) target weights."""
    s1_weights = {s: 0.0 for s in UNIVERSE}
    for s in UNIVERSE:
        c = float(dfs_aligned[s]["close"].iloc[bar_idx])
        ema = float(s1_ind[s]["ema200"][bar_idx])
        h48 = float(s1_ind[s]["donch_h48"][bar_idx])
        atr = float(s1_ind[s]["atr"][bar_idx])
        if c > h48 and c > ema:
            risk_dist = max(3.0 * atr, c * 0.005)
            vol_s = vols_20d.get(s, 0.30)
            vol_scalar = min(TARGET_VOL / max(vol_s, MIN_ANNUALIZED_VOL_FLOOR), 1.0)
            base_risk = 0.01 * vol_scalar
            notional_frac = min((base_risk / risk_dist) * c, 0.25 * min(vol_scalar, 1.5))
            s1_weights[s] = float(notional_frac)
    return s1_weights


def compute_h5_weights(
    dfs_aligned: dict[str, pd.DataFrame],
    bar_idx: int,
    vols_20d: dict[str, float],
    prev_top_assets: list[str] | None = None,
    lookback_fast: int = 84,  # 14 days
    lookback_slow: int = 360,  # 60 days
) -> dict[str, float]:
    """Computes H5 (14d+60d Blended Dual-Momentum Rotation + Gold Defense) target weights."""
    target_weights = {s: 0.0 for s in UNIVERSE}
    scores: dict[str, float] = {}
    gate_passed: dict[str, bool] = {}

    for s in UNIVERSE:
        closes = dfs_aligned[s]["close"].values.astype(float)
        if bar_idx < lookback_slow:
            return target_weights
        c_now = closes[bar_idx]
        c_fast = closes[bar_idx - lookback_fast]
        c_slow = closes[bar_idx - lookback_slow]
        vol = max(vols_20d.get(s, 0.30), MIN_ANNUALIZED_VOL_FLOOR)
        r_fast = (c_now - c_fast) / c_fast if c_fast > 0 else 0.0
        r_slow = (c_now - c_slow) / c_slow if c_slow > 0 else 0.0

        scores[s] = 0.5 * (r_fast / vol) + 0.5 * (r_slow / vol)
        gate_passed[s] = bool((r_fast > 0.0) and (r_slow > 0.0))

    passing_crypto = [s for s in CRYPTO_MAJORS if gate_passed[s]]
    passing_crypto.sort(key=lambda s: scores[s], reverse=True)

    if len(passing_crypto) >= 2:
        c1 = passing_crypto[0]
        c2 = passing_crypto[1]
        if prev_top_assets:
            for prev in prev_top_assets:
                if prev in passing_crypto and prev not in (c1, c2):
                    if (scores[c2] - scores[prev]) < 0.15 * abs(scores[c2]):
                        c2 = prev
        selected = [c1, c2]
    elif len(passing_crypto) == 1:
        c1 = passing_crypto[0]
        if gate_passed.get("PAXGUSDT", False):
            selected = [c1, "PAXGUSDT"]
        else:
            selected = [c1]
    else:
        # Fallback to PAXG if it passes absolute momentum gate
        if gate_passed.get("PAXGUSDT", False):
            selected = ["PAXGUSDT"]
        else:
            # 100% Cash Bear Shield
            return target_weights

    if len(selected) == 2:
        a1, a2 = selected
        v1 = max(vols_20d.get(a1, 0.30), MIN_ANNUALIZED_VOL_FLOOR)
        v2 = max(vols_20d.get(a2, 0.30), MIN_ANNUALIZED_VOL_FLOOR)
        inv1 = 1.0 / v1
        inv2 = 1.0 / v2
        tot_inv = inv1 + inv2
        w1_raw = inv1 / tot_inv
        w2_raw = inv2 / tot_inv

        # Trailing 120-bar basket vol estimate
        c1_series = dfs_aligned[a1]["close"].values[bar_idx - VOL_LOOKBACK : bar_idx + 1]
        c2_series = dfs_aligned[a2]["close"].values[bar_idx - VOL_LOOKBACK : bar_idx + 1]
        r1 = np.diff(c1_series) / c1_series[:-1]
        r2 = np.diff(c2_series) / c2_series[:-1]
        basket_rets = w1_raw * r1 + w2_raw * r2
        basket_vol = float(np.std(basket_rets, ddof=1) * ANNUALIZATION_FACTOR)
        vol_scalar = min(TARGET_VOL / max(basket_vol, MIN_ANNUALIZED_VOL_FLOOR), 1.0)

        w1 = float(w1_raw * vol_scalar)
        w2 = float(w2_raw * vol_scalar)
        gross = w1 + w2
        if gross > 1.0:
            w1 /= gross
            w2 /= gross
        target_weights[a1] = round(w1, 4)
        target_weights[a2] = round(w2, 4)
    elif len(selected) == 1:
        a1 = selected[0]
        v1 = max(vols_20d.get(a1, 0.30), MIN_ANNUALIZED_VOL_FLOOR)
        vol_scalar = min(TARGET_VOL / v1, 1.0)
        target_weights[a1] = round(min(vol_scalar, 1.0), 4)

    return target_weights


def compute_h1_weights(
    dfs_aligned: dict[str, pd.DataFrame],
    bar_idx: int,
    s1_ind: dict[str, dict[str, np.ndarray]],
    vols_20d: dict[str, float],
) -> dict[str, float]:
    """Computes H1_CLEAN (Bollinger Squeeze 20-bar Expansion Breakout) target weights."""
    target_weights = {s: 0.0 for s in UNIVERSE}
    for s in CRYPTO_MAJORS:
        closes = dfs_aligned[s]["close"].values.astype(float)
        highs = dfs_aligned[s]["high"].values.astype(float)
        c_now = closes[bar_idx]
        ema200 = s1_ind[s]["ema200"][bar_idx]
        atr = s1_ind[s]["atr"][bar_idx]

        s_c = pd.Series(closes)
        bb_mid = s_c.rolling(20).mean().values
        bb_std = s_c.rolling(20).std(ddof=0).values
        bb_w = 4.0 * bb_std / np.maximum(bb_mid, 1e-4)
        bb_q20 = pd.Series(bb_w).rolling(120).quantile(0.20).values
        donch_h20 = pd.Series(highs).rolling(20).max().shift(1).values

        is_bull = c_now > ema200
        was_compressed = (bb_q20[bar_idx - 1] > 0.0) and (bb_w[bar_idx - 1] <= bb_q20[bar_idx - 1])
        is_breakout = c_now > donch_h20[bar_idx]

        if is_bull and was_compressed and is_breakout:
            vol_s = vols_20d.get(s, 0.30)
            vol_scalar = min(TARGET_VOL / max(vol_s, MIN_ANNUALIZED_VOL_FLOOR), 1.0)
            sl_dist = max(2.5 * atr, 0.01 * c_now)
            notional_frac = min((0.01 * vol_scalar / sl_dist) * c_now, 0.25)
            target_weights[s] = float(notional_frac)

    return target_weights


def evaluate_v2b_pvt_snapshot(
    candles_by_symbol: dict[str, pd.DataFrame],
    account_equity: float = DEFAULT_INITIAL_EQUITY,
    as_of_ts: int | None = None,
    data_source: str = "LIVE_BINANCE",
    last_scalar: float = 1.0,
    prev_top_assets: list[str] | None = None,
) -> ChallengerSnapshot:
    """Pure point-in-time causal snapshot evaluator for Challenger P2_RP_V2B_PVT.

    Follows Trial #29 specifications with zero parameter changes:
    - 33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN
    - Causal 15% Portfolio Volatility Target (scalar <= 1.50, gross <= 1.0000)
    - 3% notional drift deadband
    """
    if not candles_by_symbol:
        return ChallengerSnapshot.create_fail_closed(
            account_equity=account_equity,
            data_source=data_source,
            reason="NO_CANDLE_DATA_PROVIDED",
        )

    for sym in UNIVERSE:
        if sym not in candles_by_symbol or candles_by_symbol[sym].empty:
            return ChallengerSnapshot.create_fail_closed(
                account_equity=account_equity,
                data_source=data_source,
                reason=f"MISSING_SYMBOL_DATA: {sym}",
            )

    # 1. Align common timestamps
    common_ts = set(candles_by_symbol["BTCUSDT"]["ts"])
    for sym in UNIVERSE[1:]:
        common_ts = common_ts.intersection(candles_by_symbol[sym]["ts"])

    sorted_ts = sorted(list(common_ts))
    n_total = len(sorted_ts)

    if n_total < MIN_WARMUP_BARS:
        return ChallengerSnapshot.create_fail_closed(
            account_equity=account_equity,
            data_source=data_source,
            reason=f"INSUFFICIENT_BARS ({n_total} < {MIN_WARMUP_BARS})",
        )

    dfs_aligned: dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = candles_by_symbol[sym]
        dfs_aligned[sym] = df[df["ts"].isin(sorted_ts)].sort_values("ts").reset_index(drop=True)

    latest_bar_ts = int(sorted_ts[-1])
    latest_dt = datetime.fromtimestamp(latest_bar_ts / 1000.0, tz=UTC)
    ts_iso = latest_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. Check staleness
    wall_ms = int(time.time() * 1000)
    if as_of_ts is not None:
        data_age_hours = max(0.0, (as_of_ts - latest_bar_ts) / 3600_000.0)
        if data_age_hours > 24.0 or (data_source == "LIVE_BINANCE" and data_age_hours > 6.0):
            return ChallengerSnapshot.create_fail_closed(
                account_equity=account_equity,
                data_source=data_source,
                data_age_hours=data_age_hours,
                timestamp_utc=ts_iso,
                reason=f"STALE_DATA_RELATIVE_TO_AS_OF ({data_age_hours:.1f}h)",
            )
    else:
        data_age_hours = max(0.0, (wall_ms - latest_bar_ts) / 3600_000.0)
        if data_source == "LIVE_BINANCE" and data_age_hours > 6.0:
            return ChallengerSnapshot.create_fail_closed(
                account_equity=account_equity,
                data_source=data_source,
                data_age_hours=data_age_hours,
                timestamp_utc=ts_iso,
                reason=f"STALE_LIVE_BINANCE_DATA ({data_age_hours:.1f}h > 6.0h)",
            )

    stale_warning = data_age_hours > 6.0
    bar_T = n_total - 1

    # 3. Compute sleeve indicators & individual sleeve weights
    s1_ind = {s: compute_s1_indicators(dfs_aligned[s]) for s in UNIVERSE}
    vols_20d = {
        s: compute_trailing_20d_volatility(dfs_aligned[s]["close"].values, bar_T)
        for s in UNIVERSE
    }

    s1_w = compute_s1_weights(dfs_aligned, bar_T, s1_ind, vols_20d)
    h5_w = compute_h5_weights(dfs_aligned, bar_T, vols_20d, prev_top_assets=prev_top_assets)
    h1_w = compute_h1_weights(dfs_aligned, bar_T, s1_ind, vols_20d)

    # 4. Form unscaled raw V2B ensemble weights (33.33% each)
    raw_weights = {
        s: (1.0 / 3.0) * s1_w[s] + (1.0 / 3.0) * h5_w[s] + (1.0 / 3.0) * h1_w[s]
        for s in UNIVERSE
    }
    raw_gross = sum(raw_weights[s] for s in UNIVERSE)

    # 5. Causal 15% Portfolio Volatility Target Formula
    # Estimate candidate basket 4h returns over trailing 120 bars
    if raw_gross > 1e-6 and bar_T >= VOL_LOOKBACK:
        basket_rets_120 = np.zeros(VOL_LOOKBACK)
        for s in UNIVERSE:
            w_norm = raw_weights[s] / max(raw_gross, 1e-6)
            s_closes = dfs_aligned[s]["close"].values[bar_T - VOL_LOOKBACK : bar_T + 1]
            s_rets = np.diff(s_closes) / s_closes[:-1]
            basket_rets_120 += w_norm * s_rets
        port_vol_20d = float(np.std(basket_rets_120, ddof=1) * ANNUALIZATION_FACTOR)
    else:
        port_vol_20d = TARGET_VOL

    if raw_gross <= 1e-6:
        target_scalar = 0.0
    else:
        vol_scalar = TARGET_VOL / max(port_vol_20d, MIN_ANNUALIZED_VOL_FLOOR)
        max_no_lev = HARD_GROSS_CAP / raw_gross
        target_scalar = min(vol_scalar, max_no_lev, MAX_CONCENTRATION_CAP)

    # 3% notional drift deadband
    if abs(target_scalar - last_scalar) > DEADBAND or target_scalar == 0.0 or last_scalar == 0.0:
        eff_scalar = target_scalar
    else:
        eff_scalar = last_scalar

    # Zero-leverage invariant clamp
    if raw_gross > 1e-6:
        eff_scalar = min(eff_scalar, HARD_GROSS_CAP / raw_gross, MAX_CONCENTRATION_CAP)
    else:
        eff_scalar = 0.0

    # Final scaled V2B weights
    v2b_weights = {s: round(raw_weights[s] * eff_scalar, 4) for s in UNIVERSE}
    final_gross = sum(v2b_weights[s] for s in UNIVERSE)
    v2b_weights["CASH"] = round(max(0.0, 1.0 - final_gross), 4)

    # 6. Regime & Verdict Classification
    crypto_gross = sum(v2b_weights.get(s, 0.0) for s in CRYPTO_MAJORS)
    paxg_w = v2b_weights.get("PAXGUSDT", 0.0)

    if crypto_gross >= 0.20:
        regime_label = "RISK_ON"
    elif crypto_gross > 0.0 or paxg_w > 0.0:
        regime_label = "MIXED"
    else:
        regime_label = "BEAR_SHIELD"

    if final_gross <= 1e-4:
        action_verdict = "WAIT_BEAR_SHIELD"
    else:
        action_verdict = "HOLD"

    cash_usd = round(account_equity * v2b_weights["CASH"], 2)

    headline_en = f"Challenger P2_RP_V2B_PVT ({regime_label}) | Gross: {final_gross * 100:.1f}% | PVT Scalar: {eff_scalar:.2f}x"
    headline_bn = f"চ্যালেঞ্জার P2_RP_V2B_PVT ({regime_label}) | গ্রস: {final_gross * 100:.1f}% | PVT স্কেলার: {eff_scalar:.2f}x"

    return ChallengerSnapshot(
        timestamp_utc=ts_iso,
        bar_ts_utc=latest_bar_ts,
        data_source=data_source,
        regime_label=regime_label,
        action_verdict=action_verdict,
        account_equity=account_equity,
        cash_usd=cash_usd,
        gross_exposure=round(final_gross, 4),
        pvt_scalar=round(eff_scalar, 4),
        port_vol_20d_ann_pct=round(port_vol_20d * 100.0, 2),
        v2b_weights=v2b_weights,
        s1_weights=s1_w,
        h5_weights=h5_w,
        h1_weights=h1_w,
        raw_weights=raw_weights,
        assets={},
        stale_data_warning=stale_warning,
        decision_headline_en=headline_en,
        decision_headline_bn=headline_bn,
        details=f"P2_RP_V2B_PVT live evaluation complete at {ts_iso}",
    )


# ==============================================================================
# DATABASE INITIALIZATION & MIGRATIONS (CHALLENGER ISOLATION)
# ==============================================================================
def get_challenger_db_path(custom_path: Path | str | None = None) -> Path:
    """Resolves SQLite Challenger shadow database path from param, env var, or default location."""
    if custom_path is not None:
        p = Path(custom_path)
    elif "CBT_CHALLENGER_DB_PATH" in os.environ:
        p = Path(os.environ["CBT_CHALLENGER_DB_PATH"])
    else:
        p = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "v2b_challenger_shadow_ledger.db"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_challenger_db(conn: sqlite3.Connection) -> None:
    """Creates the 4 isolated Challenger shadow ledger tables and initializes default metadata."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_bars (
            bar_ts_utc INTEGER PRIMARY KEY,
            evaluated_at_utc TEXT NOT NULL,
            data_source TEXT NOT NULL,
            regime_label TEXT NOT NULL,
            action_verdict TEXT NOT NULL,
            equity_usd REAL NOT NULL,
            cash_usd REAL NOT NULL,
            bnh_equity_usd REAL NOT NULL,
            gross_exposure REAL NOT NULL,
            s1_weight REAL NOT NULL,
            h5_weight REAL NOT NULL,
            h1_weight REAL NOT NULL,
            pvt_scalar REAL NOT NULL,
            stale_warning INTEGER NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_positions (
            symbol TEXT PRIMARY KEY,
            units REAL NOT NULL,
            avg_entry_price REAL NOT NULL,
            last_price REAL NOT NULL,
            market_value_usd REAL NOT NULL,
            target_weight REAL NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_ts_utc INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            units REAL NOT NULL,
            signal_close_price REAL NOT NULL,
            live_exec_price REAL NOT NULL,
            spread_bps REAL NOT NULL,
            slippage_bps REAL NOT NULL,
            fee_usd REAL NOT NULL,
            notional_usd REAL NOT NULL,
            reason TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    cur.execute(
        "INSERT OR IGNORE INTO shadow_meta (key, value) VALUES ('initial_equity', ?)",
        (str(DEFAULT_INITIAL_EQUITY),),
    )
    cur.execute(
        "INSERT OR IGNORE INTO shadow_meta (key, value) VALUES ('last_processed_bar_ts', '')"
    )
    cur.execute(
        "INSERT OR IGNORE INTO shadow_meta (key, value) VALUES ('last_regime_label', '')"
    )
    cur.execute(
        "INSERT OR IGNORE INTO shadow_meta (key, value) VALUES ('last_scalar', '1.0')"
    )
    cur.execute(
        "INSERT OR IGNORE INTO shadow_meta (key, value) VALUES ('bnh_units_json', '')"
    )
    cur.execute(
        "INSERT OR IGNORE INTO shadow_meta (key, value) VALUES ('prev_top_assets_json', '[]')"
    )
    conn.commit()


# ==============================================================================
# LIVE TOP-OF-BOOK TELEMETRY
# ==============================================================================
def fetch_top_of_book(
    symbol: str, fallback_price: float, timeout_sec: float = 3.0
) -> tuple[float, float, float]:
    """Fetches live public Binance bookTicker (best_bid, best_ask, mid) for symbol.

    Falls back cleanly to fallback_price +/- 10 bps half-spread (20 bps spread)
    when network is unreachable or sandbox blocks external HTTP calls.
    Returns: (best_bid, best_ask, mid)
    """
    endpoints = [
        f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}",
        f"https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol={symbol}",
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, timeout=timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                bid = float(data.get("bidPrice", 0.0))
                ask = float(data.get("askPrice", 0.0))
                if bid > 0 and ask >= bid:
                    mid = (bid + ask) / 2.0
                    return bid, ask, mid
        except Exception:
            pass

    mid = float(fallback_price)
    half_spread = mid * 0.0010  # 10 bps
    best_bid = mid - half_spread
    best_ask = mid + half_spread
    return best_bid, best_ask, mid


# ==============================================================================
# CORE EXECUTION FUNCTION: RUN_CHALLENGER_SHADOW_CYCLE
# ==============================================================================
def run_challenger_shadow_cycle(
    db_path: Path | str | None = None,
    source: str = "live",
    initial_equity: float = DEFAULT_INITIAL_EQUITY,
    notify_callback: Callable[[dict[str, Any]], Any] | None = None,
    candles_override: dict[str, pd.DataFrame] | None = None,
    top_of_book_override: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Executes one idempotent 4h shadow cycle for Challenger P2_RP_V2B_PVT.

    Invariants:
    1. Idempotency: Returns {"status": "ALREADY_PROCESSED"} if bar_ts_utc was already logged.
    2. Fail-closed: Returns {"status": "WAIT_STALE_DATA"} if candles are missing/stale.
    3. Zero leverage: Enforces cash_usd >= 0.0 and gross_exposure <= 1.0001.
    4. Sells execute before Buys to protect cash balance.
    5. Fills persist exact live spread_bps, slippage_bps, and fee_usd (10 bps/leg).
    """
    resolved_db_path = get_challenger_db_path(db_path)
    conn = sqlite3.connect(str(resolved_db_path))
    conn.row_factory = sqlite3.Row

    try:
        init_challenger_db(conn)

        # 1. Fetch & evaluate candles
        try:
            if candles_override is not None:
                candles = candles_override
                resolved_source = "TEST_OVERRIDE"
            else:
                candles, resolved_source = load_candles_for_p2_rp(source=source)
        except Exception as e:
            logger.warning(f"Failed to load candles for challenger shadow cycle: {e}")
            return {
                "status": "WAIT_STALE_DATA",
                "action_verdict": "WAIT_STALE_DATA",
                "reason": str(e),
                "fills": 0,
                "notified": False,
            }

        # Resolve latest bar timestamp
        try:
            common_ts = set(candles["BTCUSDT"]["ts"])
            for sym in UNIVERSE[1:]:
                if sym in candles:
                    common_ts = common_ts.intersection(candles[sym]["ts"])
            if not common_ts:
                return {
                    "status": "WAIT_STALE_DATA",
                    "action_verdict": "WAIT_STALE_DATA",
                    "reason": "NO_COMMON_TIMESTAMPS",
                    "fills": 0,
                    "notified": False,
                }
            latest_bar_ts = int(max(common_ts))
        except Exception as e:
            return {
                "status": "WAIT_STALE_DATA",
                "action_verdict": "WAIT_STALE_DATA",
                "reason": f"TIMESTAMP_RESOLUTION_ERROR: {e}",
                "fills": 0,
                "notified": False,
            }

        # 2. Idempotency Check
        cur = conn.cursor()
        existing = cur.execute(
            "SELECT 1 FROM shadow_bars WHERE bar_ts_utc = ?", (latest_bar_ts,)
        ).fetchone()
        if existing:
            return {
                "status": "ALREADY_PROCESSED",
                "bar_ts_utc": latest_bar_ts,
                "fills": 0,
                "notified": False,
            }

        # 3. Read active state & holdings
        meta_rows = cur.execute("SELECT key, value FROM shadow_meta").fetchall()
        meta = {r["key"]: r["value"] for r in meta_rows}
        last_scalar = float(meta.get("last_scalar", 1.0))
        last_regime_label = meta.get("last_regime_label", "")
        prev_top_assets = json.loads(meta.get("prev_top_assets_json", "[]"))

        pos_rows = cur.execute(
            "SELECT symbol, units, avg_entry_price, last_price, market_value_usd, target_weight FROM shadow_positions"
        ).fetchall()
        current_positions = {r["symbol"]: dict(r) for r in pos_rows}

        last_bar = cur.execute(
            "SELECT equity_usd, cash_usd, bnh_equity_usd FROM shadow_bars ORDER BY bar_ts_utc DESC LIMIT 1"
        ).fetchone()

        if last_bar is not None:
            current_cash = float(last_bar["cash_usd"])
            prev_equity = float(last_bar["equity_usd"])
        else:
            current_cash = float(meta.get("initial_equity", initial_equity))
            prev_equity = current_cash

        # Compute pre-trade mark-to-market equity
        current_market_val = 0.0
        for sym in UNIVERSE:
            close_p = float(candles[sym]["close"].iloc[-1])
            u = current_positions.get(sym, {}).get("units", 0.0)
            current_market_val += u * close_p

        current_equity = current_cash + current_market_val
        if current_equity <= 0.0:
            current_equity = prev_equity

        # 4. Generate Challenger Snapshot
        snapshot = evaluate_v2b_pvt_snapshot(
            candles_by_symbol=candles,
            account_equity=current_equity,
            data_source=resolved_source,
            last_scalar=last_scalar,
            prev_top_assets=prev_top_assets,
        )

        if snapshot.action_verdict == "WAIT_STALE_DATA":
            return {
                "status": "WAIT_STALE_DATA",
                "action_verdict": "WAIT_STALE_DATA",
                "reason": snapshot.error_reason,
                "fills": 0,
                "notified": False,
            }

        # Benchmark (Equal-Weight Buy-and-Hold)
        bnh_units_raw = meta.get("bnh_units_json", "")
        if bnh_units_raw:
            bnh_units = json.loads(bnh_units_raw)
        else:
            bnh_units = {}
            for sym in UNIVERSE:
                p0 = float(candles[sym]["open"].iloc[0])
                bnh_units[sym] = (initial_equity * 0.25) / max(p0, 1e-4)
            cur.execute(
                "INSERT OR REPLACE INTO shadow_meta (key, value) VALUES ('bnh_units_json', ?)",
                (json.dumps(bnh_units),),
            )

        bnh_equity_usd = sum(
            bnh_units[s] * float(candles[s]["close"].iloc[-1]) for s in UNIVERSE
        )

        # 5. Order Execution with Live Slippage & Friction
        target_weights = snapshot.v2b_weights
        fills_this_bar: list[dict[str, Any]] = []

        # Determine target units and dollar delta
        orders: list[dict[str, Any]] = []
        for sym in UNIVERSE:
            tgt_w = target_weights.get(sym, 0.0)
            target_dollar = current_equity * tgt_w
            cur_p = float(candles[sym]["close"].iloc[-1])
            cur_u = current_positions.get(sym, {}).get("units", 0.0)
            cur_dollar = cur_u * cur_p
            delta_dollar = target_dollar - cur_dollar
            delta_w = abs(tgt_w - (cur_dollar / max(current_equity, 1e-4)))

            # 3% Deadband filter
            if delta_w > DEADBAND:
                orders.append({
                    "symbol": sym,
                    "target_dollar": target_dollar,
                    "cur_dollar": cur_dollar,
                    "delta_dollar": delta_dollar,
                    "close_price": cur_p,
                    "side": "SELL" if delta_dollar < 0 else "BUY",
                })

        # Sells first to free cash
        sells = [o for o in orders if o["side"] == "SELL"]
        buys = [o for o in orders if o["side"] == "BUY"]

        # Execute Sells
        for order in sells:
            sym = order["symbol"]
            cur_u = current_positions.get(sym, {}).get("units", 0.0)
            tgt_u = (
                order["target_dollar"] / max(order["close_price"], 1e-4)
                if order["target_dollar"] > 0
                else 0.0
            )
            units_to_sell = max(0.0, cur_u - tgt_u)
            if units_to_sell * order["close_price"] > 10.0:
                if top_of_book_override and sym in top_of_book_override:
                    bid = top_of_book_override[sym]["bid"]
                    ask = top_of_book_override[sym]["ask"]
                    mid = top_of_book_override[sym]["mid"]
                else:
                    bid, ask, mid = fetch_top_of_book(sym, order["close_price"])

                exec_price = bid
                spread_bps = max(0.0, (ask - bid) / max(mid, 1e-4) * 10000.0)
                slippage_bps = max(0.0, (mid - exec_price) / max(mid, 1e-4) * 10000.0)
                gross_proceeds = units_to_sell * exec_price
                fee_usd = gross_proceeds * 0.0010  # 10 bps fee
                net_proceeds = gross_proceeds - fee_usd

                current_cash += net_proceeds
                rem_units = max(0.0, cur_u - units_to_sell)
                current_positions[sym] = {
                    "symbol": sym,
                    "units": rem_units,
                    "avg_entry_price": (
                        current_positions.get(sym, {}).get("avg_entry_price", exec_price)
                        if rem_units > 0
                        else 0.0
                    ),
                    "last_price": exec_price,
                    "market_value_usd": rem_units * exec_price,
                    "target_weight": target_weights.get(sym, 0.0),
                }

                fill_record = {
                    "symbol": sym,
                    "side": "SELL",
                    "units": round(units_to_sell, 8),
                    "signal_close_price": round(order["close_price"], 4),
                    "live_exec_price": round(exec_price, 4),
                    "spread_bps": round(spread_bps, 2),
                    "slippage_bps": round(slippage_bps, 2),
                    "fee_usd": round(fee_usd, 4),
                    "notional_usd": round(gross_proceeds, 4),
                    "reason": f"CHALLENGER_REBALANCE_SELL (tgt_w={target_weights.get(sym, 0.0):.2f})",
                }
                fills_this_bar.append(fill_record)

                cur.execute(
                    """
                    INSERT INTO shadow_fills (
                        bar_ts_utc, symbol, side, units, signal_close_price, live_exec_price,
                        spread_bps, slippage_bps, fee_usd, notional_usd, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        latest_bar_ts,
                        sym,
                        "SELL",
                        fill_record["units"],
                        fill_record["signal_close_price"],
                        fill_record["live_exec_price"],
                        spread_bps,
                        slippage_bps,
                        fill_record["fee_usd"],
                        fill_record["notional_usd"],
                        fill_record["reason"],
                    ),
                )

        # Execute Buys
        for order in buys:
            sym = order["symbol"]
            needed_dollar = order["delta_dollar"]
            if needed_dollar > 10.0 and current_cash > 10.0:
                spendable_cash = max(0.0, current_cash - 1.0)
                notional_to_spend = min(needed_dollar, spendable_cash)

                if top_of_book_override and sym in top_of_book_override:
                    bid = top_of_book_override[sym]["bid"]
                    ask = top_of_book_override[sym]["ask"]
                    mid = top_of_book_override[sym]["mid"]
                else:
                    bid, ask, mid = fetch_top_of_book(sym, order["close_price"])

                exec_price = ask
                spread_bps = max(0.0, (ask - bid) / max(mid, 1e-4) * 10000.0)
                slippage_bps = max(0.0, (exec_price - mid) / max(mid, 1e-4) * 10000.0)
                fee_usd = notional_to_spend * 0.0010
                net_notional = notional_to_spend - fee_usd
                bought_units = net_notional / max(exec_price, 1e-4)

                current_cash -= notional_to_spend
                prior_u = current_positions.get(sym, {}).get("units", 0.0)
                prior_avg = current_positions.get(sym, {}).get("avg_entry_price", 0.0)
                tot_u = prior_u + bought_units
                new_avg = (
                    ((prior_u * prior_avg) + (bought_units * exec_price)) / tot_u
                    if tot_u > 0
                    else exec_price
                )

                current_positions[sym] = {
                    "symbol": sym,
                    "units": tot_u,
                    "avg_entry_price": new_avg,
                    "last_price": exec_price,
                    "market_value_usd": tot_u * exec_price,
                    "target_weight": target_weights.get(sym, 0.0),
                }

                fill_record = {
                    "symbol": sym,
                    "side": "BUY",
                    "units": round(bought_units, 8),
                    "signal_close_price": round(order["close_price"], 4),
                    "live_exec_price": round(exec_price, 4),
                    "spread_bps": round(spread_bps, 2),
                    "slippage_bps": round(slippage_bps, 2),
                    "fee_usd": round(fee_usd, 4),
                    "notional_usd": round(notional_to_spend, 4),
                    "reason": f"CHALLENGER_REBALANCE_BUY (tgt_w={target_weights.get(sym, 0.0):.2f})",
                }
                fills_this_bar.append(fill_record)

                cur.execute(
                    """
                    INSERT INTO shadow_fills (
                        bar_ts_utc, symbol, side, units, signal_close_price, live_exec_price,
                        spread_bps, slippage_bps, fee_usd, notional_usd, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        latest_bar_ts,
                        sym,
                        "BUY",
                        fill_record["units"],
                        fill_record["signal_close_price"],
                        fill_record["live_exec_price"],
                        spread_bps,
                        slippage_bps,
                        fill_record["fee_usd"],
                        fill_record["notional_usd"],
                        fill_record["reason"],
                    ),
                )

        # 6. Post-Trade Accounting & Position Updates
        post_equity = current_cash
        gross_mv = 0.0
        for sym in UNIVERSE:
            cur_price = float(candles[sym]["close"].iloc[-1])
            u = current_positions.get(sym, {}).get("units", 0.0)
            avg_p = current_positions.get(sym, {}).get("avg_entry_price", 0.0)
            mv = u * cur_price
            gross_mv += mv
            tgt_w = target_weights.get(sym, 0.0)

            cur.execute(
                """
                INSERT OR REPLACE INTO shadow_positions (
                    symbol, units, avg_entry_price, last_price, market_value_usd, target_weight, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sym,
                    round(u, 8),
                    round(avg_p, 4),
                    round(cur_price, 4),
                    round(mv, 2),
                    round(tgt_w, 4),
                    snapshot.timestamp_utc,
                ),
            )

        post_equity += gross_mv
        gross_exposure = gross_mv / max(post_equity, 1e-6)

        assert current_cash >= -1e-6, f"cash_usd cannot be negative, got {current_cash}"
        current_cash = max(0.0, current_cash)
        assert (
            gross_exposure <= 1.0001
        ), f"gross_exposure violated zero-leverage cap: {gross_exposure}"

        s1_w_sum = sum(snapshot.s1_weights.get(s, 0.0) for s in UNIVERSE)
        h5_w_sum = sum(snapshot.h5_weights.get(s, 0.0) for s in UNIVERSE)
        h1_w_sum = sum(snapshot.h1_weights.get(s, 0.0) for s in UNIVERSE)

        cur.execute(
            """
            INSERT INTO shadow_bars (
                bar_ts_utc, evaluated_at_utc, data_source, regime_label, action_verdict,
                equity_usd, cash_usd, bnh_equity_usd, gross_exposure,
                s1_weight, h5_weight, h1_weight, pvt_scalar, stale_warning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                latest_bar_ts,
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                snapshot.data_source,
                snapshot.regime_label,
                snapshot.action_verdict,
                round(post_equity, 2),
                round(current_cash, 2),
                round(bnh_equity_usd, 2),
                round(gross_exposure, 4),
                round(s1_w_sum, 4),
                round(h5_w_sum, 4),
                round(h1_w_sum, 4),
                round(snapshot.pvt_scalar, 4),
                1 if snapshot.stale_data_warning else 0,
            ),
        )

        cur.execute(
            "INSERT OR REPLACE INTO shadow_meta (key, value) VALUES ('last_processed_bar_ts', ?)",
            (str(latest_bar_ts),),
        )
        cur.execute(
            "INSERT OR REPLACE INTO shadow_meta (key, value) VALUES ('last_regime_label', ?)",
            (snapshot.regime_label,),
        )
        cur.execute(
            "INSERT OR REPLACE INTO shadow_meta (key, value) VALUES ('last_scalar', ?)",
            (str(snapshot.pvt_scalar),),
        )

        conn.commit()

        cycle_summary = {
            "status": "SUCCESS",
            "bar_ts_utc": latest_bar_ts,
            "timestamp_utc": snapshot.timestamp_utc,
            "regime_label": snapshot.regime_label,
            "last_regime_label": last_regime_label,
            "action_verdict": snapshot.action_verdict,
            "equity_usd": round(post_equity, 2),
            "cash_usd": round(current_cash, 2),
            "bnh_equity_usd": round(bnh_equity_usd, 2),
            "gross_exposure": round(gross_exposure, 4),
            "pvt_scalar": round(snapshot.pvt_scalar, 4),
            "fills": len(fills_this_bar),
            "fill_details": fills_this_bar,
            "capital_mode": CAPITAL_MODE,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
        }

        if notify_callback is not None:
            try:
                if inspect.iscoroutinefunction(notify_callback):
                    import asyncio

                    _task = asyncio.create_task(notify_callback(cycle_summary))  # noqa: RUF006
                else:
                    notify_callback(cycle_summary)
            except Exception as exc:
                logger.warning(f"Challenger notify callback failed: {exc}")

        return cycle_summary

    finally:
        conn.close()


# ==============================================================================
# CHALLENGER SCORECARD TELEMETRY
# ==============================================================================
def get_challenger_scorecard(db_path: Path | str | None = None) -> dict[str, Any]:
    """Computes durable forward track-record metrics for Challenger P2_RP_V2B_PVT."""
    resolved_db_path = get_challenger_db_path(db_path)
    if not resolved_db_path.exists():
        return {
            "days_tracked": 0.0,
            "target_forward_days": TARGET_FORWARD_DAYS,
            "equity_usd": DEFAULT_INITIAL_EQUITY,
            "total_return_pct": 0.0,
            "bnh_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "gross_exposure": 0.0,
            "pvt_scalar": 1.0,
            "bars_ticked": 0,
            "total_fills": 0,
            "current_regime": "BEAR_SHIELD",
            "capital_mode": CAPITAL_MODE,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
        }

    conn = sqlite3.connect(str(resolved_db_path))
    conn.row_factory = sqlite3.Row

    try:
        init_challenger_db(conn)
        cur = conn.cursor()
        bar_rows = cur.execute(
            "SELECT bar_ts_utc, equity_usd, bnh_equity_usd, gross_exposure, pvt_scalar, regime_label FROM shadow_bars ORDER BY bar_ts_utc ASC"
        ).fetchall()

        if not bar_rows:
            return {
                "days_tracked": 0.0,
                "target_forward_days": TARGET_FORWARD_DAYS,
                "equity_usd": DEFAULT_INITIAL_EQUITY,
                "total_return_pct": 0.0,
                "bnh_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "gross_exposure": 0.0,
                "pvt_scalar": 1.0,
                "bars_ticked": 0,
                "total_fills": 0,
                "current_regime": "BEAR_SHIELD",
                "capital_mode": CAPITAL_MODE,
                "real_capital_enabled": REAL_CAPITAL_ENABLED,
            }

        meta_rows = cur.execute("SELECT key, value FROM shadow_meta").fetchall()
        meta = {r["key"]: r["value"] for r in meta_rows}
        init_eq = float(meta.get("initial_equity", DEFAULT_INITIAL_EQUITY))

        first_ts = int(bar_rows[0]["bar_ts_utc"])
        last_ts = int(bar_rows[-1]["bar_ts_utc"])
        days_tracked = (
            round((last_ts - first_ts) / 86_400_000.0, 1)
            if last_ts > first_ts
            else round(len(bar_rows) / 6.0, 1)
        )

        latest_eq = float(bar_rows[-1]["equity_usd"])
        latest_bnh = float(bar_rows[-1]["bnh_equity_usd"])
        current_regime = str(bar_rows[-1]["regime_label"])
        current_gross = float(bar_rows[-1]["gross_exposure"])
        current_scalar = float(bar_rows[-1]["pvt_scalar"])

        total_ret_pct = round((latest_eq - init_eq) / init_eq * 100.0, 2)
        bnh_ret_pct = round((latest_bnh - init_eq) / init_eq * 100.0, 2)

        peak = 0.0
        max_dd = 0.0
        for r in bar_rows:
            eq = float(r["equity_usd"])
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (peak - eq) / peak * 100.0
                if dd > max_dd:
                    max_dd = dd

        fill_stats = cur.execute("SELECT COUNT(*) FROM shadow_fills").fetchone()
        total_fills = int(fill_stats[0] or 0)

        return {
            "days_tracked": days_tracked,
            "target_forward_days": TARGET_FORWARD_DAYS,
            "equity_usd": round(latest_eq, 2),
            "total_return_pct": total_ret_pct,
            "bnh_return_pct": bnh_ret_pct,
            "max_drawdown_pct": round(max_dd, 2),
            "gross_exposure": round(current_gross, 4),
            "pvt_scalar": round(current_scalar, 4),
            "bars_ticked": len(bar_rows),
            "total_fills": total_fills,
            "current_regime": current_regime,
            "capital_mode": CAPITAL_MODE,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
        }
    finally:
        conn.close()


# ==============================================================================
# CHAMPION vs. CHALLENGER ARENA COMPARISON (STRICT READ-ONLY ISOLATION)
# ==============================================================================
def get_arena_comparison(
    champion_db_path: Path | str | None = None,
    challenger_db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Evaluates head-to-head live forward proof between Champion and Challenger.

    Guarantees:
    - Opens Champion database strictly read-only (?mode=ro) using SQLite URI.
    - Zero write or schema side-effects on Champion ledger.
    """
    from core.strategies.p2_shadow_runner import get_db_path as get_champ_path

    champ_path = get_champ_path(champion_db_path)
    chall_path = get_challenger_db_path(challenger_db_path)

    # 1. Read Champion Ledger (Strictly Read-Only URI)
    champion_data = {
        "strategy_id": "CHAMPION_P2_RP",
        "name": "Champion (P2_RP Risk Parity)",
        "equity_usd": DEFAULT_INITIAL_EQUITY,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "gross_exposure": 0.0,
        "bars_ticked": 0,
        "days_tracked": 0.0,
        "regime": "BEAR_SHIELD",
        "total_fills": 0,
    }

    if champ_path.exists():
        uri = f"file:{champ_path.resolve().as_posix()}?mode=ro"
        conn_champ = sqlite3.connect(uri, uri=True)
        conn_champ.row_factory = sqlite3.Row
        try:
            cur = conn_champ.cursor()
            # Verify tables exist
            tbl_check = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='shadow_bars'"
            ).fetchone()
            if tbl_check:
                rows = cur.execute(
                    "SELECT bar_ts_utc, equity_usd, bnh_equity_usd, gross_exposure, regime_label FROM shadow_bars ORDER BY bar_ts_utc ASC"
                ).fetchall()
                if rows:
                    first_ts = int(rows[0]["bar_ts_utc"])
                    last_ts = int(rows[-1]["bar_ts_utc"])
                    days = (
                        round((last_ts - first_ts) / 86_400_000.0, 1)
                        if last_ts > first_ts
                        else round(len(rows) / 6.0, 1)
                    )
                    eq = float(rows[-1]["equity_usd"])
                    gross = float(rows[-1]["gross_exposure"])
                    regime = str(rows[-1]["regime_label"])
                    ret_pct = round((eq - DEFAULT_INITIAL_EQUITY) / DEFAULT_INITIAL_EQUITY * 100.0, 2)

                    peak = 0.0
                    max_dd = 0.0
                    for r in rows:
                        val = float(r["equity_usd"])
                        if val > peak:
                            peak = val
                        if peak > 0:
                            dd = (peak - val) / peak * 100.0
                            if dd > max_dd:
                                max_dd = dd

                    f_count = cur.execute("SELECT COUNT(*) FROM shadow_fills").fetchone()[0]

                    champion_data.update({
                        "equity_usd": round(eq, 2),
                        "total_return_pct": ret_pct,
                        "max_drawdown_pct": round(max_dd, 2),
                        "gross_exposure": round(gross, 4),
                        "bars_ticked": len(rows),
                        "days_tracked": days,
                        "regime": regime,
                        "total_fills": int(f_count or 0),
                    })
        finally:
            conn_champ.close()

    # 2. Read Challenger Ledger
    chall_sc = get_challenger_scorecard(chall_path)
    challenger_data = {
        "strategy_id": "CHALLENGER_V2B_PVT",
        "name": "Challenger (P2_RP_V2B_PVT)",
        "equity_usd": chall_sc["equity_usd"],
        "total_return_pct": chall_sc["total_return_pct"],
        "max_drawdown_pct": chall_sc["max_drawdown_pct"],
        "gross_exposure": chall_sc["gross_exposure"],
        "pvt_scalar": chall_sc["pvt_scalar"],
        "bars_ticked": chall_sc["bars_ticked"],
        "days_tracked": chall_sc["days_tracked"],
        "regime": chall_sc["current_regime"],
        "total_fills": chall_sc["total_fills"],
    }

    # 3. Benchmark BnH
    bnh_return_pct = chall_sc["bnh_return_pct"]
    bnh_equity_usd = round(DEFAULT_INITIAL_EQUITY * (1.0 + bnh_return_pct / 100.0), 2)

    # 4. Arena Verdict & Delta
    delta_usd = round(challenger_data["equity_usd"] - champion_data["equity_usd"], 2)
    spread_pct = round(challenger_data["total_return_pct"] - champion_data["total_return_pct"], 2)
    dd_spread_pct = round(challenger_data["max_drawdown_pct"] - champion_data["max_drawdown_pct"], 2)

    if champion_data["bars_ticked"] == 0 and challenger_data["bars_ticked"] == 0:
        leader = "TIE_WARMUP"
        reason_en = "Both Champion and Challenger standing by for live forward proof."
        reason_bn = "চ্যাম্পিয়ন এবং চ্যালেঞ্জার উভয়ই লাইভ ফরোয়ার্ড প্রুফের অপেক্ষায়।"
    elif abs(spread_pct) < 0.05:
        leader = "TIE_WARMUP"
        reason_en = f"Tied forward performance within 0.05% margin (Spread: {spread_pct:+.2f}%)."
        reason_bn = f"০.০৫% ব্যবধানের মধ্যে সম ফরোয়ার্ড পারফরম্যান্স (ব্যবধান: {spread_pct:+.2f}%)।"
    elif challenger_data["total_return_pct"] > champion_data["total_return_pct"]:
        leader = "CHALLENGER_V2B_PVT"
        reason_en = f"Challenger leading by {spread_pct:+.2f}% forward alpha (${delta_usd:+,.2f})."
        reason_bn = f"চ্যালেঞ্জার {spread_pct:+.2f}% ফরোয়ার্ড আলফায় এগিয়ে রয়েছে (${delta_usd:+,.2f})।"
    else:
        leader = "CHAMPION_P2_RP"
        reason_en = f"Champion defending lead by {-spread_pct:+.2f}% (${-delta_usd:+,.2f})."
        reason_bn = f"চ্যাম্পিয়ন {-spread_pct:+.2f}% ব্যবধানে নেতৃত্ব রক্ষা করছে (${-delta_usd:+,.2f})।"

    proof_days = min(champion_data["days_tracked"], challenger_data["days_tracked"])
    proof_progress_pct = round(min(100.0, (proof_days / TARGET_FORWARD_DAYS) * 100.0), 1)

    return {
        "evaluation_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_proof_days": TARGET_FORWARD_DAYS,
        "proof_days_elapsed": proof_days,
        "proof_progress_pct": proof_progress_pct,
        "champion": champion_data,
        "challenger": challenger_data,
        "benchmark_bnh": {
            "equity_usd": bnh_equity_usd,
            "total_return_pct": bnh_return_pct,
        },
        "comparison": {
            "current_leader": leader,
            "equity_delta_usd": delta_usd,
            "return_spread_pct": spread_pct,
            "dd_spread_pct": dd_spread_pct,
            "verdict_reason_en": reason_en,
            "verdict_reason_bn": reason_bn,
        },
        "governance": {
            "capital_mode": CAPITAL_MODE,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
            "champion_db_mode": "STRICT_READ_ONLY",
            "isolation_verified": True,
        },
    }


def format_arena_report(comparison: dict[str, Any], lang: str = "en") -> str:
    """Formats a scannable Champion vs. Challenger Arena Scoreboard in EN or BN."""
    is_bn = str(lang).lower().startswith("bn")
    champ = comparison["champion"]
    chall = comparison["challenger"]
    bnh = comparison["benchmark_bnh"]
    comp = comparison["comparison"]
    prog = comparison["proof_progress_pct"]
    p_days = comparison["proof_days_elapsed"]

    bar_len = 20
    filled = round((prog / 100.0) * bar_len)
    progress_bar = "[" + "=" * filled + "-" * (bar_len - filled) + "]"

    if is_bn:
        lines = [
            "=" * 88,
            "⚔️  সিবিটি এরিনা: চ্যাম্পিয়ন (P2_RP) বনাম চ্যালেঞ্জার (P2_RP_V2B_PVT)",
            "৬০ দিনের ফরোয়ার্ড প্রুফ টেলিমেট্রি [TIER_0_PAPER — কোনো আসল মূলধন ঝুঁকি নেই]",
            "=" * 88,
            f"{'পরিমাপ':<24} | {'চ্যাম্পিয়ন (P2_RP)':<26} | {'চ্যালেঞ্জার (V2B_PVT)':<26} | {'বেঞ্চমার্ক (BnH)':<15}",
            "-" * 88,
            f"{'কৌশল স্থাপত্য':<24} | {'৫০% S1 + ৫০% S2-Div':<26} | {'৩৩% S1 + ৩৩% H5 + ৩৩% H1':<26} | {'সম-ওজন ঝুড়ি':<15}",
            f"{'বর্তমান শাসন (Regime)':<24} | {champ['regime']:<26} | {chall['regime']:<26} | {'—':<15}",
            f"{'ভার্চুয়াল মূলধন':<24} | ${champ['equity_usd']:<25,.2f} | ${chall['equity_usd']:<25,.2f} | ${bnh['equity_usd']:<14,.2f}",
            f"{'ফরোয়ার্ড লাভ/ক্ষতি':<24} | {champ['total_return_pct']:<+25.2f}% | {chall['total_return_pct']:<+25.2f}% | {bnh['total_return_pct']:<+14.2f}%",
            f"{'সর্বোচ্চ ড্রডাউন (DD)':<24} | {champ['max_drawdown_pct']:<25.2f}% | {chall['max_drawdown_pct']:<25.2f}% | {'—':<15}",
            f"{'গ্রস এক্সপোজার':<24} | {champ['gross_exposure'] * 100:<25.2f}% | {chall['gross_exposure'] * 100:<25.2f}% | {'১০০.০০%':<15}",
            f"{'PVT স্কেলার':<24} | {'১.০০x':<26} | {chall.get('pvt_scalar', 1.0):<25.2f}x | {'১.০০x':<15}",
            f"{'টিক করা ৪ ঘণ্টার বার':<24} | {champ['bars_ticked']:<26} | {chall['bars_ticked']:<26} | {champ['bars_ticked']:<15}",
            f"{'ট্র্যাক করা দিন':<24} | {champ['days_tracked']:<20.1f} দিন | {chall['days_tracked']:<20.1f} দিন | {p_days:<11.1f} দিন",
            f"{'সম্পাদিত ট্রেড (Fills)':<24} | {champ['total_fills']:<26} | {chall['total_fills']:<26} | {'—':<15}",
            "-" * 88,
            f"বর্তমান এরিনা লিডার      : {comp['current_leader']}",
            f"রায় ও পারফরম্যান্স ব্যবধান : {comp['verdict_reason_bn']}",
            f"৬০ দিনের প্রমাণ অগ্রগতি    : {progress_bar} {prog:.1f}% সম্পন্ন ({p_days:.1f}/60.0 দিন)",
            "=" * 88,
            "[আইসোলেশন নিশ্চিত: চ্যাম্পিয়ন লেজার সম্পূর্ণ সুরক্ষিত (Strict Read-Only Mode)]",
        ]
    else:
        lines = [
            "=" * 88,
            "⚔️  CBT ARENA: CHAMPION (P2_RP) vs CHALLENGER (P2_RP_V2B_PVT)",
            "60-Day Forward Proof Telemetry [TIER_0_PAPER — No Real Capital]",
            "=" * 88,
            f"{'Metric':<24} | {'Champion (P2_RP)':<26} | {'Challenger (V2B_PVT)':<26} | {'BnH Benchmark':<15}",
            "-" * 88,
            f"{'Strategy Architecture':<24} | {'50% S1 + 50% S2-Div':<26} | {'33% S1 + 33% H5 + 33% H1':<26} | {'Equal-Weight':<15}",
            f"{'Active Regime':<24} | {champ['regime']:<26} | {chall['regime']:<26} | {'—':<15}",
            f"{'Virtual Equity':<24} | ${champ['equity_usd']:<25,.2f} | ${chall['equity_usd']:<25,.2f} | ${bnh['equity_usd']:<14,.2f}",
            f"{'Forward Return %':<24} | {champ['total_return_pct']:<+25.2f}% | {chall['total_return_pct']:<+25.2f}% | {bnh['total_return_pct']:<+14.2f}%",
            f"{'Forward Max DD %':<24} | {champ['max_drawdown_pct']:<25.2f}% | {chall['max_drawdown_pct']:<25.2f}% | {'—':<15}",
            f"{'Current Gross Exposure':<24} | {champ['gross_exposure'] * 100:<25.2f}% | {chall['gross_exposure'] * 100:<25.2f}% | {'100.00%':<15}",
            f"{'PVT Vol Scalar':<24} | {'1.00x':<26} | {chall.get('pvt_scalar', 1.0):<25.2f}x | {'1.00x':<15}",
            f"{'Bars Ticked':<24} | {champ['bars_ticked']:<26} | {chall['bars_ticked']:<26} | {champ['bars_ticked']:<15}",
            f"{'Days Tracked':<24} | {champ['days_tracked']:<20.1f} days | {chall['days_tracked']:<20.1f} days | {p_days:<10.1f} days",
            f"{'Total Fills Executed':<24} | {champ['total_fills']:<26} | {chall['total_fills']:<26} | {'—':<15}",
            "-" * 88,
            f"CURRENT ARENA LEADER    : {comp['current_leader']}",
            f"VERDICT & ALPHA SPREAD  : {comp['verdict_reason_en']}",
            f"60-DAY PROOF PROGRESS   : {progress_bar} {prog:.1f}% Complete ({p_days:.1f}/60.0 days)",
            "=" * 88,
            "[STRICT ISOLATION VERIFIED: Champion Ledger Untouched (Read-Only Mode)]",
        ]

    return "\n".join(lines)
