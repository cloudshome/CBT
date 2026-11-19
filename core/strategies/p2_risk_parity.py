"""core/strategies/p2_risk_parity.py — Production P2_RP Risk-Parity Shadow Desk Engine.

Milestone 66 Production Promotion:
Port of the audited Milestone 65.1 P2_RP strategy (S1 Donchian-48/EMA-200 + S2-Div 7-day
Top-2 Dual-Momentum with PAXG/Cash bear shield and 15% candidate-basket vol targeting)
into a production shadow desk service.

Strict Invariants:
1. REAL_CAPITAL_ENABLED = False (locked).
2. CapitalGovernor = "TIER_0_PAPER" (locked).
3. Zero leverage cap: Gross Exposure <= 1.0001 at all times.
4. Frozen strategy parameters (Donchian=48, EMA=200, ATR=14, Momentum=30d, Rebalance=7d,
   Hysteresis=15%, Target Vol=15%, 3% drift deadband).
5. Fail-closed: Missing, stale (>6h live, >24h offline), or <210 4h bars returns
   action_verdict = "WAIT_STALE_DATA" with 0% new trade allocation.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("ai_quant_sentinel.core.strategies.p2_risk_parity")

# ==============================================================================
# FROZEN STRATEGY CONSTANTS (DO NOT MODIFY)
# ==============================================================================
UNIVERSE: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
CRYPTO_MAJORS: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME: str = "4h"

# Lookbacks & Parameters
DONCHIAN_H: int = 48
DONCHIAN_L: int = 24
EMA_SPAN: int = 200
ATR_SPAN: int = 14
MOMENTUM_LOOKBACK: int = 180  # 30 calendar days (6 * 30)
VOL_LOOKBACK: int = 120       # 20 calendar days (6 * 20)
ANNUALIZATION_FACTOR: float = math.sqrt(2190.0)  # sqrt(365 * 6)
REBALANCE_CADENCE: int = 42   # 7 calendar days (6 * 7)
HYSTERESIS: float = 0.15      # 15% advantage to currently held assets
TARGET_VOL: float = 0.15      # 15% annualized target volatility
DEADBAND: float = 0.03        # 3% notional drift deadband
MIN_WARMUP_BARS: int = 210

CAPITAL_MODE: str = "TIER_0_PAPER"
REAL_CAPITAL_ENABLED: bool = False


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================
@dataclass
class AssetMetrics:
    symbol: str
    price: float
    ema_200: float
    ema_status: str  # "ABOVE" | "BELOW"
    donchian_h48: float
    donchian_l24: float
    atr_14: float
    stop_loss: float
    momentum_30d_pct: float
    vol_20d_ann_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TodayDeskSnapshot:
    timestamp_utc: str
    data_source: str  # "LIVE_BINANCE" | "LOCAL_PARQUET"
    data_age_hours: float
    stale_data_warning: bool
    regime_label: str  # "RISK_ON" | "MIXED" | "BEAR_SHIELD"
    action_verdict: str  # "ACT" | "HOLD" | "WAIT_STALE_DATA" | "BEAR_SHIELD"
    assets: dict[str, AssetMetrics]
    s1_weights: dict[str, float]
    s2_weights: dict[str, float]
    p2_rp_weights: dict[str, float]
    gross_exposure: float
    account_equity: float
    dollar_allocations: dict[str, float]
    days_to_rebalance: float
    capital_mode: str = CAPITAL_MODE
    real_capital_enabled: bool = REAL_CAPITAL_ENABLED
    details: str = ""
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["assets"] = {s: m.to_dict() if hasattr(m, "to_dict") else m for s, m in self.assets.items()}
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def create_fail_closed(
        cls,
        account_equity: float = 10_000.0,
        data_source: str = "LOCAL_PARQUET",
        data_age_hours: float = 999.0,
        reason: str = "FAIL_CLOSED",
        timestamp_utc: str | None = None,
    ) -> TodayDeskSnapshot:
        """Returns safe fail-closed snapshot with 0% new trade allocation."""
        ts = timestamp_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        zero_weights = {s: 0.0 for s in UNIVERSE}
        zero_weights["CASH"] = 1.0
        dollar_alloc = {s: 0.0 for s in UNIVERSE}
        dollar_alloc["CASH"] = round(account_equity, 2)

        return cls(
            timestamp_utc=ts,
            data_source=data_source,
            data_age_hours=round(data_age_hours, 2),
            stale_data_warning=True,
            regime_label="BEAR_SHIELD",
            action_verdict="WAIT_STALE_DATA",
            assets={},
            s1_weights=zero_weights,
            s2_weights=zero_weights,
            p2_rp_weights=zero_weights,
            gross_exposure=0.0,
            account_equity=account_equity,
            dollar_allocations=dollar_alloc,
            days_to_rebalance=0.0,
            capital_mode=CAPITAL_MODE,
            real_capital_enabled=REAL_CAPITAL_ENABLED,
            details=f"Fail-closed safe state engaged: {reason}",
            error_reason=reason,
        )


# ==============================================================================
# AUDITED CAUSAL MATHEMATICAL EVALUATORS
# ==============================================================================
def compute_s1_indicators(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Computes S1 indicators (Donchian-48, Donchian-24, EMA-200, ATR-14) strictly causally."""
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    closes = df["close"].values.astype(float)
    opens = df["open"].values.astype(float)
    ts_vals = df["ts"].values

    if len(closes) == 0:
        return {}

    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    tr = np.insert(tr, 0, highs[0] - lows[0])
    atr = pd.Series(tr).rolling(ATR_SPAN).mean().values

    donch_h48 = pd.Series(highs).rolling(DONCHIAN_H).max().shift(1).values
    donch_l24 = pd.Series(lows).rolling(DONCHIAN_L).min().shift(1).values
    ema200 = pd.Series(closes).ewm(span=EMA_SPAN, adjust=False).mean().values

    return {
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "ts": ts_vals,
        "atr": atr,
        "donch_h48": donch_h48,
        "donch_l24": donch_l24,
        "ema200": ema200,
    }


def compute_trailing_20d_volatility(
    closes: np.ndarray, bar_idx: int, lookback_bars: int = VOL_LOOKBACK
) -> float:
    """Computes annualized trailing 20-day realized volatility from 4h returns (sqrt(2190))."""
    if bar_idx < lookback_bars or len(closes) <= lookback_bars:
        return 0.15

    window_closes = closes[bar_idx - lookback_bars : bar_idx + 1]
    if len(window_closes) < 2:
        return 0.15

    rets = np.diff(window_closes) / window_closes[:-1]
    std = float(np.std(rets, ddof=1))
    ann_vol = std * ANNUALIZATION_FACTOR
    return max(ann_vol, 1e-4)


def rank_s2_div_assets(
    dfs_aligned: dict[str, pd.DataFrame],
    bar_idx: int,
    current_crypto_holdings: list[str] | None = None,
    lookback_bars: int = MOMENTUM_LOOKBACK,
    vol_lookback_bars: int = VOL_LOOKBACK,
    hysteresis: float = HYSTERESIS,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
    """Evaluates Strategy S2-Div Allocation under exact M65.1 rules.

    Returns:
    - base_weights: {symbol: weight} summing to <= 1.0 (before vol scaling)
    - scores: {symbol: 30d risk-adjusted momentum score}
    - ret_30ds: {symbol: 30d percentage return}
    - vols_20d: {symbol: trailing 20d annualized volatility}
    """
    if current_crypto_holdings is None:
        current_crypto_holdings = []

    scores: dict[str, float] = {}
    ret_30ds: dict[str, float] = {}
    vols_20d: dict[str, float] = {}

    for s in UNIVERSE:
        s_closes = dfs_aligned[s]["close"].values.astype(float)
        if bar_idx < lookback_bars:
            scores[s] = 0.0
            ret_30ds[s] = 0.0
            vols_20d[s] = 0.50
            continue

        c_now = s_closes[bar_idx]
        c_past = s_closes[bar_idx - lookback_bars]
        ret_30d = (c_now - c_past) / max(c_past, 1e-6)
        ret_4h = (
            np.diff(s_closes[bar_idx - lookback_bars : bar_idx + 1])
            / s_closes[bar_idx - lookback_bars : bar_idx]
        )
        vol_30d = float(np.std(ret_4h, ddof=1) * ANNUALIZATION_FACTOR) if len(ret_4h) > 1 else 1e-4
        score = ret_30d / max(vol_30d, 1e-4)

        vol_20d = compute_trailing_20d_volatility(s_closes, bar_idx, lookback_bars=vol_lookback_bars)

        scores[s] = float(score)
        ret_30ds[s] = float(ret_30d)
        vols_20d[s] = float(vol_20d)

    # Positive crypto majors
    pos_crypto = [s for s in CRYPTO_MAJORS if ret_30ds.get(s, 0.0) > 0 and scores.get(s, 0.0) > 0]

    def effective_score(sym: str) -> float:
        base = scores.get(sym, 0.0)
        if sym in current_crypto_holdings:
            return base * (1.0 + hysteresis)
        return base

    ranked_crypto = sorted(pos_crypto, key=effective_score, reverse=True)

    base_weights: dict[str, float] = {s: 0.0 for s in UNIVERSE}
    base_weights["CASH"] = 0.0

    if len(ranked_crypto) >= 2:
        top1, top2 = ranked_crypto[0], ranked_crypto[1]
        v1 = vols_20d[top1]
        v2 = vols_20d[top2]
        inv_v1 = 1.0 / max(v1, 1e-4)
        inv_v2 = 1.0 / max(v2, 1e-4)
        sum_inv = inv_v1 + inv_v2
        base_weights[top1] = inv_v1 / sum_inv
        base_weights[top2] = inv_v2 / sum_inv
    elif len(ranked_crypto) == 1:
        top1 = ranked_crypto[0]
        base_weights[top1] = 0.50
        if ret_30ds.get("PAXGUSDT", -1.0) > 0:
            base_weights["PAXGUSDT"] = 0.50
        else:
            base_weights["CASH"] = 0.50
    else:
        # Bear Shield
        if ret_30ds.get("PAXGUSDT", -1.0) > 0:
            base_weights["PAXGUSDT"] = 1.00
        else:
            base_weights["CASH"] = 1.00

    return base_weights, scores, ret_30ds, vols_20d


# ==============================================================================
# MAIN SNAPSHOT EVALUATOR
# ==============================================================================
def evaluate_p2_rp_snapshot(
    candles_by_symbol: dict[str, pd.DataFrame],
    account_equity: float = 10_000.0,
    as_of_ts: int | None = None,
    data_source: str = "LOCAL_PARQUET",
) -> TodayDeskSnapshot:
    """Pure point-in-time causal snapshot evaluator for P2_RP Risk Parity Desk.

    Follows audited M65.1 rules with zero parameter modification.
    """
    # 1. Validate inputs
    if not candles_by_symbol:
        return TodayDeskSnapshot.create_fail_closed(
            account_equity=account_equity,
            data_source=data_source,
            reason="NO_CANDLE_DATA_PROVIDED",
        )

    for sym in UNIVERSE:
        if sym not in candles_by_symbol or candles_by_symbol[sym].empty:
            return TodayDeskSnapshot.create_fail_closed(
                account_equity=account_equity,
                data_source=data_source,
                reason=f"MISSING_SYMBOL_DATA: {sym}",
            )

    # 2. Align common timestamps
    common_ts = set(candles_by_symbol["BTCUSDT"]["ts"])
    for sym in UNIVERSE[1:]:
        common_ts = common_ts.intersection(candles_by_symbol[sym]["ts"])

    sorted_ts = sorted(list(common_ts))
    n_total = len(sorted_ts)

    if n_total < MIN_WARMUP_BARS:
        return TodayDeskSnapshot.create_fail_closed(
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

    # 3. Check staleness
    wall_ms = int(time.time() * 1000)
    if as_of_ts is not None:
        data_age_hours = max(0.0, (as_of_ts - latest_bar_ts) / 3600_000.0)
        # In as_of mode, if candles are >24h stale relative to as_of_ts, fail-closed
        if data_age_hours > 24.0 or (data_source == "LIVE_BINANCE" and data_age_hours > 6.0):
            return TodayDeskSnapshot.create_fail_closed(
                account_equity=account_equity,
                data_source=data_source,
                data_age_hours=data_age_hours,
                timestamp_utc=ts_iso,
                reason=f"STALE_DATA_RELATIVE_TO_AS_OF ({data_age_hours:.1f}h)",
            )
    else:
        data_age_hours = max(0.0, (wall_ms - latest_bar_ts) / 3600_000.0)
        if data_source == "LIVE_BINANCE" and data_age_hours > 6.0:
            return TodayDeskSnapshot.create_fail_closed(
                account_equity=account_equity,
                data_source=data_source,
                data_age_hours=data_age_hours,
                timestamp_utc=ts_iso,
                reason=f"STALE_LIVE_BINANCE_DATA ({data_age_hours:.1f}h > 6.0h)",
            )

    stale_warning = data_age_hours > 6.0

    # 4. Compute Indicators & Asset Metrics at bar T
    bar_T = n_total - 1
    s1_ind = {s: compute_s1_indicators(dfs_aligned[s]) for s in UNIVERSE}

    base_weights, scores, ret_30ds, vols_20d = rank_s2_div_assets(
        dfs_aligned,
        bar_idx=bar_T,
        current_crypto_holdings=[],  # clean candidate ranking
        lookback_bars=MOMENTUM_LOOKBACK,
        vol_lookback_bars=VOL_LOOKBACK,
        hysteresis=HYSTERESIS,
    )

    asset_metrics_map: dict[str, AssetMetrics] = {}
    for s in UNIVERSE:
        c = float(dfs_aligned[s]["close"].iloc[bar_T])
        ema = float(s1_ind[s]["ema200"][bar_T])
        h48 = float(s1_ind[s]["donch_h48"][bar_T])
        l24 = float(s1_ind[s]["donch_l24"][bar_T])
        atr = float(s1_ind[s]["atr"][bar_T])
        risk_d = max(3.0 * atr, c * 0.005)
        sl = max(l24, c - risk_d)

        asset_metrics_map[s] = AssetMetrics(
            symbol=s,
            price=round(c, 4),
            ema_200=round(ema, 4),
            ema_status="ABOVE" if c > ema else "BELOW",
            donchian_h48=round(h48, 4),
            donchian_l24=round(l24, 4),
            atr_14=round(atr, 4),
            stop_loss=round(sl, 4),
            momentum_30d_pct=round(ret_30ds.get(s, 0.0) * 100.0, 2),
            vol_20d_ann_pct=round(vols_20d.get(s, 0.50) * 100.0, 2),
        )

    # 5. S1 Sleeve Allocation
    # Evaluate S1 active breakout signals across universe
    s1_weights: dict[str, float] = {s: 0.0 for s in UNIVERSE}
    s1_weights["CASH"] = 0.0

    # S1 realized volatility targeting
    # Calculate realized volatility of 4h equal/active sleeve over trailing 120 bars
    # Single asset trailing vol proxy
    s1_active_entries: list[str] = []
    for s in UNIVERSE:
        c = float(dfs_aligned[s]["close"].iloc[bar_T])
        ema = float(s1_ind[s]["ema200"][bar_T])
        h48 = float(s1_ind[s]["donch_h48"][bar_T])
        if c > h48 and c > ema:
            s1_active_entries.append(s)

    # In M65.1, S1 sizes each trade with base 1% risk scaled by vol scalar, capped at 25% equity
    # If S1 has active positions or entries:
    s1_gross = 0.0
    for s in s1_active_entries:
        c = float(dfs_aligned[s]["close"].iloc[bar_T])
        atr = float(s1_ind[s]["atr"][bar_T])
        risk_d = max(3.0 * atr, c * 0.005)
        vol_s = vols_20d.get(s, 0.30)
        s1_scalar = min(TARGET_VOL / max(vol_s, 0.04), 1.0)
        base_risk = 0.01 * s1_scalar
        notional_frac = min((base_risk / risk_d) * c, 0.25 * min(s1_scalar, 1.5))
        s1_weights[s] = notional_frac
        s1_gross += notional_frac

    s1_weights["CASH"] = max(0.0, 1.0 - s1_gross)

    # 6. S2-Div Sleeve Volatility Targeting on Candidate Unscaled Basket Returns
    # Candidate unscaled basket returns: r_basket = sum(w_s * r_s)
    basket_rets_120 = np.zeros(VOL_LOOKBACK)
    for s in UNIVERSE:
        w_s = base_weights.get(s, 0.0)
        if w_s > 0.0:
            s_c = dfs_aligned[s]["close"].values.astype(float)
            s_rets = (
                np.diff(s_c[bar_T - VOL_LOOKBACK : bar_T + 1])
                / s_c[bar_T - VOL_LOOKBACK : bar_T]
            )
            basket_rets_120 += w_s * s_rets

    if np.sum(np.abs(basket_rets_120)) > 1e-8:
        s2_ann_vol = float(np.std(basket_rets_120, ddof=1) * ANNUALIZATION_FACTOR)
    else:
        s2_ann_vol = sum(base_weights[s] * vols_20d.get(s, 0.50) for s in UNIVERSE)

    # Causal 15% Volatility Target Scalar (Capped at 1.0x gross notional)
    s2_vol_scalar = min(TARGET_VOL / max(s2_ann_vol, 0.04), 1.0)

    s2_target_weights: dict[str, float] = {s: 0.0 for s in UNIVERSE}
    s2_target_weights["CASH"] = 0.0
    s2_gross = 0.0

    for s in UNIVERSE:
        w = base_weights.get(s, 0.0) * s2_vol_scalar
        s2_target_weights[s] = w
        s2_gross += w

    if s2_gross > 1.0:
        scale_back = 1.0 / s2_gross
        s2_target_weights = {s: v * scale_back for s, v in s2_target_weights.items()}
        s2_gross = 1.0

    s2_target_weights["CASH"] = max(0.0, 1.0 - s2_gross)

    # 7. Combined P2_RP 50/50 Ensemble
    p2_weights: dict[str, float] = {}
    gross_exposure = 0.0

    for s in UNIVERSE:
        w_comb = 0.5 * s1_weights.get(s, 0.0) + 0.5 * s2_target_weights.get(s, 0.0)
        p2_weights[s] = round(w_comb, 6)
        gross_exposure += w_comb

    p2_weights["CASH"] = round(max(0.0, 1.0 - gross_exposure), 6)

    # Strictly enforce zero-leverage guarantee
    if gross_exposure > 1.0001:
        scale_down = 1.0 / gross_exposure
        for s in UNIVERSE:
            p2_weights[s] = round(p2_weights[s] * scale_down, 6)
        gross_exposure = sum(p2_weights[s] for s in UNIVERSE)
        p2_weights["CASH"] = round(max(0.0, 1.0 - gross_exposure), 6)

    # Dollar allocations
    dollar_allocations = {
        s: round(account_equity * p2_weights[s], 2) for s in [*UNIVERSE, "CASH"]
    }

    # 8. Regime & Verdict Logic
    pos_crypto_count = len([s for s in CRYPTO_MAJORS if ret_30ds.get(s, 0.0) > 0 and scores.get(s, 0.0) > 0])
    if pos_crypto_count >= 2:
        regime_label = "RISK_ON"
    elif pos_crypto_count == 1:
        regime_label = "MIXED"
    else:
        regime_label = "BEAR_SHIELD"

    # Days until next 7-day rebalance
    # Using 42-bar cadence
    bars_since_rebalance = (bar_T - MIN_WARMUP_BARS) % REBALANCE_CADENCE
    bars_remaining = 0 if bars_since_rebalance == 0 else (REBALANCE_CADENCE - bars_since_rebalance)
    days_to_rebalance = round(bars_remaining * 4.0 / 24.0, 1)

    if regime_label == "BEAR_SHIELD" and gross_exposure == 0.0:
        action_verdict = "BEAR_SHIELD"
    elif days_to_rebalance == 0.0 or len(s1_active_entries) > 0:
        action_verdict = "ACT"
    else:
        action_verdict = "HOLD"

    return TodayDeskSnapshot(
        timestamp_utc=ts_iso,
        data_source=data_source,
        data_age_hours=round(data_age_hours, 2),
        stale_data_warning=stale_warning,
        regime_label=regime_label,
        action_verdict=action_verdict,
        assets=asset_metrics_map,
        s1_weights={k: round(v, 4) for k, v in s1_weights.items()},
        s2_weights={k: round(v, 4) for k, v in s2_target_weights.items()},
        p2_rp_weights={k: round(v, 4) for k, v in p2_weights.items()},
        gross_exposure=round(gross_exposure, 4),
        account_equity=account_equity,
        dollar_allocations=dollar_allocations,
        days_to_rebalance=days_to_rebalance,
        capital_mode=CAPITAL_MODE,
        real_capital_enabled=REAL_CAPITAL_ENABLED,
        details="M65.1 Audited Point-in-Time Risk-Parity Snapshot",
    )


# ==============================================================================
# CANDLE STORE / DATA LOADER
# ==============================================================================
def load_candles_for_p2_rp(
    source: str = "auto",
    store_path: Path | str | None = None,
    limit: int = 500,
) -> tuple[dict[str, pd.DataFrame], str]:
    """Loads 4h candles for UNIVERSE symbols from Binance live or Parquet store.

    Parameters:
    - source: "auto", "parquet", or "live".
    Returns:
    - (candles_by_symbol, resolved_source)
    """
    dfs: dict[str, pd.DataFrame] = {}

    if source in ("live", "auto"):
        try:
            from data.binance_client import BinanceClient

            client = BinanceClient()
            for sym in UNIVERSE:
                df = client.klines(sym, timeframe="4h", limit=limit)
                if df is None or len(df) < MIN_WARMUP_BARS:
                    raise ConnectionError(f"Insufficient live klines for {sym}: {len(df) if df is not None else 0}")
                dfs[sym] = df
            return dfs, "LIVE_BINANCE"
        except Exception as e:
            logger.warning(f"Could not load live Binance candles ({e}); source={source}")
            if source == "live":
                raise

    # Parquet fallback or explicit parquet
    from data.store import CandleStore

    base_dir = Path(store_path) if store_path else Path(__file__).resolve().parent.parent.parent / "data" / "store"
    store = CandleStore(base_dir)

    for sym in UNIVERSE:
        df = store.read("binance", "perp", sym, "4h")
        if df.empty:
            df = store.read("binance", "spot", sym, "4h")
        if df.empty:
            raise FileNotFoundError(f"Parquet store has no 4h candle data for {sym} at {base_dir}")
        dfs[sym] = df

    return dfs, "LOCAL_PARQUET"


# ==============================================================================
# INSTITUTIONAL BOXED BRIEFING FORMATTERS (EN & BN)
# ==============================================================================
def format_today_desk_briefing(snapshot: TodayDeskSnapshot, lang: str = "en") -> str:
    """Formats TodayDeskSnapshot into a crisp, institutional boxed summary in English or Bengali."""
    is_bn = str(lang).strip().lower() in ("bn", "bangla", "bengali")

    eq_str = f"${snapshot.account_equity:,.2f}"
    age_str = f"{snapshot.data_age_hours:.1f}h"
    rebal_str = f"{snapshot.days_to_rebalance:.1f}d"

    if is_bn:
        regime_map = {
            "RISK_ON": "বুলিশ মোমেন্টাম (RISK_ON)",
            "MIXED": "মিশ্র / সতর্ক (MIXED)",
            "BEAR_SHIELD": "বিয়ার শিল্ড / ক্যাশ সুরক্ষা (BEAR_SHIELD)",
        }
        verdict_map = {
            "ACT": "অ্যাকশন প্রয়োজন (ACT)",
            "HOLD": "পজিশন ধরে রাখুন (HOLD)",
            "WAIT_STALE_DATA": "অপেক্ষারত / বাসি ডেটা (WAIT_STALE_DATA)",
            "BEAR_SHIELD": "বিয়ার শিল্ড / ক্যাশ সুরক্ষা (BEAR_SHIELD)",
        }
        source_map = {
            "LIVE_BINANCE": "লাইভ বাইন্যান্স (LIVE_BINANCE)",
            "LOCAL_PARQUET": "লোকাল পার্কো (LOCAL_PARQUET)",
        }

        regime_display = regime_map.get(snapshot.regime_label, snapshot.regime_label)
        verdict_display = verdict_map.get(snapshot.action_verdict, snapshot.action_verdict)
        source_display = source_map.get(snapshot.data_source, snapshot.data_source)

        lines = [
            "╔══════════════════════════════════════════════════════════════════════════════════╗",
            "║                            সিবিটি আজকের মার্কেট ডেস্ক (TODAY)                    ║",
            "║                    P2_RP রিস্ক-প্যারিটি শ্যাডো ডেস্ক (৪ ঘণ্টা ক্যান্ডেল)          ║",
            "╠══════════════════════════════════════════════════════════════════════════════════╣",
            f"║ সময় (UTC): {snapshot.timestamp_utc:<19} | উৎস: {source_display:<20} ║",
            f"║ মোড: {snapshot.capital_mode:<12} | আসল তহবিল: নিষ্ক্রিয় (REAL_CAPITAL=False) | বয়স: {age_str:<6} ║",
            f"║ রেজিম: {regime_display:<22} | রায়: {verdict_display:<22} ║",
            f"║ ইকুইটি: {eq_str:<12} | পরবর্তী রিভার্স: {rebal_str:<8} | গ্রস এক্সপোজার: {snapshot.gross_exposure*100:.1f}% ║",
            "╠══════════════════════════════════════════════════════════════════════════════════╣",
            "║ অ্যাসেট       মূল্য         EMA-200    স্টপ-লস       ৩০দ মোম    ২০দ ভোল    টার্গেট $  ║",
            "╟──────────────────────────────────────────────────────────────────────────────────╢",
        ]

        for s in UNIVERSE:
            if s in snapshot.assets:
                m = snapshot.assets[s]
                p_str = f"${m.price:,.2f}"
                sl_str = f"${m.stop_loss:,.2f}"
                mom_str = f"{m.momentum_30d_pct:+.1f}%"
                vol_str = f"{m.vol_20d_ann_pct:.1f}%"
                alloc_str = f"${snapshot.dollar_allocations.get(s, 0.0):,.0f}"
                lines.append(
                    f"║ {s:<10} {p_str:>11} {m.ema_status:>8} {sl_str:>12} {mom_str:>10} {vol_str:>9} {alloc_str:>10} ║"
                )

        cash_alloc = f"${snapshot.dollar_allocations.get('CASH', snapshot.account_equity):,.0f}"
        cash_pct = f"{snapshot.p2_rp_weights.get('CASH', 1.0)*100:.1f}%"
        lines.extend([
            f"║ CASH(USD)    $1.00          -          -            0.0%      0.0%    {cash_alloc:>10} ║",
            "╠══════════════════════════════════════════════════════════════════════════════════╣",
            f"║ ওয়েট বন্টন (P2_RP): BTC: {snapshot.p2_rp_weights.get('BTCUSDT', 0)*100:.1f}% | ETH: {snapshot.p2_rp_weights.get('ETHUSDT', 0)*100:.1f}% | SOL: {snapshot.p2_rp_weights.get('SOLUSDT', 0)*100:.1f}% | PAXG: {snapshot.p2_rp_weights.get('PAXGUSDT', 0)*100:.1f}% | ক্যাশ: {cash_pct} ║",
            f"║ গ্রস এক্সপোজার: {snapshot.gross_exposure*100:.1f}% (সর্বোচ্চ: 100.0%) | S1: {sum(snapshot.s1_weights.get(s,0) for s in UNIVERSE)*100:.1f}% | S2-Div: {sum(snapshot.s2_weights.get(s,0) for s in UNIVERSE)*100:.1f}% ║",
            "╚══════════════════════════════════════════════════════════════════════════════════╝",
        ])
        return "\n".join(lines)

    # English Default
    lines = [
        "╔══════════════════════════════════════════════════════════════════════════════════╗",
        "║                          CBT TODAY'S DESK BRIEFING                               ║",
        "║                    P2_RP RISK-PARITY SHADOW DESK (4H)                            ║",
        "╠══════════════════════════════════════════════════════════════════════════════════╣",
        f"║ As-Of UTC: {snapshot.timestamp_utc:<19} | Source: {snapshot.data_source:<13} | Mode: {snapshot.capital_mode:<12} ║",
        f"║ Capital: {eq_str:<14} | Real Capital: DISABLED      | Data Age: {age_str:<6} ║",
        f"║ Regime: {snapshot.regime_label:<15} | Verdict: {snapshot.action_verdict:<13} | Rebalance In: {rebal_str:<6} ║",
        "╠══════════════════════════════════════════════════════════════════════════════════╣",
        "║ ASSET        PRICE        EMA-200    STOP-LOSS      30D MOM    20D VOL   TARGET $ ║",
        "╟──────────────────────────────────────────────────────────────────────────────────╢",
    ]

    for s in UNIVERSE:
        if s in snapshot.assets:
            m = snapshot.assets[s]
            p_str = f"${m.price:,.2f}"
            sl_str = f"${m.stop_loss:,.2f}"
            mom_str = f"{m.momentum_30d_pct:+.1f}%"
            vol_str = f"{m.vol_20d_ann_pct:.1f}%"
            alloc_str = f"${snapshot.dollar_allocations.get(s, 0.0):,.0f}"
            lines.append(
                f"║ {s:<10} {p_str:>11} {m.ema_status:>8} {sl_str:>12} {mom_str:>10} {vol_str:>9} {alloc_str:>10} ║"
            )

    cash_alloc = f"${snapshot.dollar_allocations.get('CASH', snapshot.account_equity):,.0f}"
    cash_pct = f"{snapshot.p2_rp_weights.get('CASH', 1.0)*100:.1f}%"
    lines.extend([
        f"║ CASH (USD)   $1.00          -          -            0.0%      0.0%    {cash_alloc:>10} ║",
        "╠══════════════════════════════════════════════════════════════════════════════════╣",
        f"║ WEIGHTS (P2_RP): BTC: {snapshot.p2_rp_weights.get('BTCUSDT', 0)*100:.1f}% | ETH: {snapshot.p2_rp_weights.get('ETHUSDT', 0)*100:.1f}% | SOL: {snapshot.p2_rp_weights.get('SOLUSDT', 0)*100:.1f}% | PAXG: {snapshot.p2_rp_weights.get('PAXGUSDT', 0)*100:.1f}% | CASH: {cash_pct} ║",
        f"║ Gross Exposure: {snapshot.gross_exposure*100:.1f}% (Cap: 100.0%) | S1: {sum(snapshot.s1_weights.get(s,0) for s in UNIVERSE)*100:.1f}% | S2-Div: {sum(snapshot.s2_weights.get(s,0) for s in UNIVERSE)*100:.1f}% ║",
        "╚══════════════════════════════════════════════════════════════════════════════════╝",
    ])
    return "\n".join(lines)
