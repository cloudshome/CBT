"""engine/smt_regime.py
====================
Point-in-time Cross-Asset ETH/BTC Relative-Strength (RS) & Smart Money Technique (SMT)
Regime Filter for Milestone 56.

Strictly causal: at any timestamp `ts`, only benchmark bars with `btc_ts <= ts`
are inspected via binary search (`np.searchsorted(..., side='right') - 1`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class EthBtcRegimeSnapshot:
    ts: int
    eth_close: float
    btc_close: float
    eth_btc_ratio: float = 0.0
    rs_ema20: float = 0.0
    rs_ema50: float = 0.0
    rs_ema200: float = 0.0
    rs_roc24_pct: float = 0.0
    rs_zscore48: float = 0.0
    regime: str = "ETH_NEUTRAL"  # "ETH_OUTPERFORMING" | "ETH_UNDERPERFORMING" | "ETH_NEUTRAL"
    smt_signal: str | None = None  # "BULLISH_SMT_ETH_STRONG" | "BEARISH_SMT_ETH_WEAK" | None
    allow_long: bool = True
    allow_short: bool = True
    min_confidence_required: int = 65
    min_rr_required: float = 2.5
    rationale: str = ""
    btc_ts: int = 0

    def __init__(self, **kwargs: Any) -> None:
        ts = kwargs.get("ts", kwargs.get("eth_ts", 0))
        self.ts = int(ts)
        self.btc_ts = int(kwargs.get("btc_ts", ts))
        self.eth_close = float(kwargs.get("eth_close", 0.0))
        self.btc_close = float(kwargs.get("btc_close", 0.0))
        self.eth_btc_ratio = float(kwargs.get("eth_btc_ratio", kwargs.get("ratio", 0.0)))
        self.rs_ema20 = float(kwargs.get("rs_ema20", kwargs.get("ema20", 0.0)))
        self.rs_ema50 = float(kwargs.get("rs_ema50", kwargs.get("ema50", 0.0)))
        self.rs_ema200 = float(kwargs.get("rs_ema200", kwargs.get("ema200", 0.0)))
        self.rs_roc24_pct = float(kwargs.get("rs_roc24_pct", kwargs.get("roc_24", 0.0)))
        self.rs_zscore48 = float(kwargs.get("rs_zscore48", kwargs.get("z_score_48", 0.0)))
        self.regime = str(kwargs.get("regime", "ETH_NEUTRAL"))

        smt_sig = kwargs.get("smt_signal")
        if smt_sig is None:
            if kwargs.get("bullish_smt"):
                smt_sig = "BULLISH_SMT_ETH_STRONG"
            elif kwargs.get("bearish_smt"):
                smt_sig = "BEARISH_SMT_ETH_WEAK"
        self.smt_signal = smt_sig

        if "allow_long" in kwargs:
            self.allow_long = bool(kwargs["allow_long"])
        else:
            self.allow_long = (
                False if (self.regime == "ETH_UNDERPERFORMING" and not self.bullish_smt) else True
            )

        if "allow_short" in kwargs:
            self.allow_short = bool(kwargs["allow_short"])
        else:
            self.allow_short = (
                False if (self.regime == "ETH_OUTPERFORMING" and not self.bearish_smt) else True
            )

        self.min_confidence_required = int(kwargs.get("min_confidence_required", 65))
        self.min_rr_required = float(kwargs.get("min_rr_required", 2.5))
        self.rationale = str(kwargs.get("rationale", ""))

    @property
    def eth_ts(self) -> int:
        return self.ts

    @property
    def ratio(self) -> float:
        return self.eth_btc_ratio

    @property
    def ema20(self) -> float:
        return self.rs_ema20

    @property
    def ema50(self) -> float:
        return self.rs_ema50

    @property
    def ema200(self) -> float:
        return self.rs_ema200

    @property
    def roc_24(self) -> float:
        return self.rs_roc24_pct

    @property
    def z_score_48(self) -> float:
        return self.rs_zscore48

    @property
    def bullish_smt(self) -> bool:
        return self.smt_signal == "BULLISH_SMT_ETH_STRONG"

    @property
    def bearish_smt(self) -> bool:
        return self.smt_signal == "BEARISH_SMT_ETH_WEAK"

    @property
    def smt_divergence(self) -> str | None:
        return self.smt_signal

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "btc_ts": self.btc_ts,
            "eth_close": round(self.eth_close, 4),
            "btc_close": round(self.btc_close, 4),
            "eth_btc_ratio": round(self.eth_btc_ratio, 6),
            "rs_ema20": round(self.rs_ema20, 6),
            "rs_ema50": round(self.rs_ema50, 6),
            "rs_ema200": round(self.rs_ema200, 6),
            "rs_roc24_pct": round(self.rs_roc24_pct, 4),
            "rs_zscore48": round(self.rs_zscore48, 4),
            "regime": self.regime,
            "smt_signal": self.smt_signal,
            "allow_long": self.allow_long,
            "allow_short": self.allow_short,
            "min_confidence_required": self.min_confidence_required,
            "min_rr_required": self.min_rr_required,
            "rationale": self.rationale,
        }


def precompute_eth_btc_regime_table(
    eth_df: pd.DataFrame,
    btc_df: pd.DataFrame,
    smt_lookback: int = 20,
    smt_recent: int = 5,
    timeframe: str = "1h",
) -> dict[int, EthBtcRegimeSnapshot]:
    """Precomputes point-in-time ETH/BTC relative-strength metrics and SMT signals.

    Strictly causal: For each bar in eth_df at time t_i, only btc_df bars with
    timestamp <= t_i are evaluated. Returns a dict mapping eth bar timestamp -> EthBtcRegimeSnapshot.
    """
    if eth_df.empty or btc_df.empty or len(eth_df) < 30 or len(btc_df) < 30:
        return {}

    tf_str = str(eth_df.attrs.get("timeframe") or timeframe).lower()

    # Copy and ensure ascending sort by ts
    e_df = eth_df.sort_values("ts").reset_index(drop=True).copy()
    b_df = btc_df.sort_values("ts").reset_index(drop=True).copy()

    # Normalize microseconds to milliseconds if needed
    if e_df["ts"].iloc[0] >= 10**14:
        e_df["ts"] = e_df["ts"] // 1000
    if b_df["ts"].iloc[0] >= 10**14:
        b_df["ts"] = b_df["ts"] // 1000

    e_ts = e_df["ts"].to_numpy(dtype=np.int64)
    e_closes = e_df["close"].to_numpy(dtype=np.float64)
    e_highs = e_df["high"].to_numpy(dtype=np.float64)
    e_lows = e_df["low"].to_numpy(dtype=np.float64)

    b_ts = b_df["ts"].to_numpy(dtype=np.int64)
    b_closes = b_df["close"].to_numpy(dtype=np.float64)
    b_highs = b_df["high"].to_numpy(dtype=np.float64)
    b_lows = b_df["low"].to_numpy(dtype=np.float64)

    n_eth = len(e_df)

    # Causal matching: for each eth bar i, find index j in btc_df with b_ts[j] <= e_ts[i]
    matched_indices = np.searchsorted(b_ts, e_ts, side="right") - 1

    # Ratio series R_i = ETH_close / BTC_close (NaN if stale or unmatched)
    ratios = np.full(n_eth, np.nan, dtype=np.float64)
    valid_mask = np.zeros(n_eth, dtype=bool)

    # Timeframe-aware staleness threshold
    tf_ms = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}.get(
        tf_str, 3_600_000
    )
    max_stale_ms = max(4 * 3600 * 1000, 3 * tf_ms)

    for i in range(n_eth):
        j = matched_indices[i]
        if j >= 0:
            diff_ms = abs(e_ts[i] - b_ts[j])
            if diff_ms <= max_stale_ms and b_closes[j] > 0.0:
                ratios[i] = e_closes[i] / b_closes[j]
                valid_mask[i] = True

    if not np.any(valid_mask):
        raise ValueError(
            f"Reference BTC candle is stale (> {max_stale_ms // 3600000}h) or unmatched across series."
        )

    # Timeframe-aware EMA & ROC / Z-score window scaling
    if tf_str == "15m" and n_eth >= 250:
        span_fast = 80
        span_mid = 200
        span_slow = 800
        roc_window = 96  # 24 hours of 15m bars
        z_window = 192  # 48 hours of 15m bars
    elif tf_str == "4h" and n_eth >= 150:
        span_fast = 14
        span_mid = 35
        span_slow = 120
        roc_window = 12  # 48 hours of 4h bars
        z_window = 30  # 5 days of 4h bars
    else:
        span_fast = 20
        span_mid = 50
        span_slow = 200
        roc_window = 24
        z_window = 48

    # Compute causal EMAs and rolling metrics over R
    s_r = pd.Series(ratios).ffill().bfill()
    ema20 = s_r.ewm(span=span_fast, adjust=False).mean().to_numpy()
    ema50 = s_r.ewm(span=span_mid, adjust=False).mean().to_numpy()
    ema200 = s_r.ewm(span=span_slow, adjust=False).mean().to_numpy()

    # ROC on ratio
    roc_series = np.zeros(n_eth, dtype=np.float64)
    if n_eth >= roc_window:
        prev = s_r.shift(roc_window).to_numpy()
        curr = s_r.to_numpy()
        roc_series = np.where(prev > 0, ((curr - prev) / prev) * 100.0, 0.0)

    # Rolling Z-score
    roll_mean = s_r.rolling(window=z_window, min_periods=5).mean().to_numpy()
    roll_std = s_r.rolling(window=z_window, min_periods=5).std().fillna(0.0).to_numpy()
    zscore = np.where(
        roll_std > 1e-8,
        (s_r.to_numpy() - roll_mean) / np.maximum(roll_std, 1e-8),
        0.0,
    )

    # Precompute rolling lookback windows for point-in-time SMT divergence (O(N) vectorization)
    e_lows_s = pd.Series(e_lows)
    e_highs_s = pd.Series(e_highs)
    b_lows_s = pd.Series(b_lows)
    b_highs_s = pd.Series(b_highs)

    eth_prev_l_arr = e_lows_s.rolling(15).min().shift(5).to_numpy()
    eth_rec_l_arr = e_lows_s.rolling(5).min().to_numpy()
    eth_prev_h_arr = e_highs_s.rolling(15).max().shift(5).to_numpy()
    eth_rec_h_arr = e_highs_s.rolling(5).max().to_numpy()

    btc_prev_l_arr = b_lows_s.rolling(15).min().shift(5).to_numpy()
    btc_rec_l_arr = b_lows_s.rolling(5).min().to_numpy()
    btc_prev_h_arr = b_highs_s.rolling(15).max().shift(5).to_numpy()
    btc_rec_h_arr = b_highs_s.rolling(5).max().to_numpy()

    out_table: dict[int, EthBtcRegimeSnapshot] = {}

    for i in range(n_eth):
        if not valid_mask[i]:
            continue

        ts_i = int(e_ts[i])
        eth_c = float(e_closes[i])
        j = matched_indices[i]
        btc_c = float(b_closes[j])
        r_val = float(ratios[i])
        e20 = float(ema20[i])
        e50 = float(ema50[i])
        e200 = float(ema200[i])
        roc = float(roc_series[i])
        z48 = float(zscore[i])

        # Point-in-Time SMT Divergence
        smt_sig = None
        if i >= 19 and j >= 19:
            # Lookback = 20 bars: prior 15 bars [k-19 : k-4] vs recent 5 bars [k-4 : k+1]
            eth_prev_l = eth_prev_l_arr[i]
            eth_rec_l = eth_rec_l_arr[i]
            eth_prev_h = eth_prev_h_arr[i]
            eth_rec_h = eth_rec_h_arr[i]

            btc_prev_l = btc_prev_l_arr[j]
            btc_rec_l = btc_rec_l_arr[j]
            btc_prev_h = btc_prev_h_arr[j]
            btc_rec_h = btc_rec_h_arr[j]

            is_bull_smt = (btc_rec_l < btc_prev_l and eth_rec_l >= eth_prev_l * 1.0002) or (
                eth_rec_h > eth_prev_h * 1.0005 and btc_rec_h <= btc_prev_h and roc > 0.25
            )

            is_bear_smt = (btc_rec_h > btc_prev_h and eth_rec_h <= eth_prev_h * 0.9998) or (
                eth_rec_l < eth_prev_l and btc_rec_l >= btc_prev_l * 1.0002
            )

            if is_bull_smt and not is_bear_smt:
                smt_sig = "BULLISH_SMT_ETH_STRONG"
            elif is_bear_smt and not is_bull_smt:
                smt_sig = "BEARISH_SMT_ETH_WEAK"

        # Regime classification
        is_outperforming = (r_val > e50 and e20 >= e50 and roc >= -0.15) or (
            r_val > e20 and roc >= 0.60 and smt_sig == "BULLISH_SMT_ETH_STRONG"
        )
        is_underperforming = (
            (r_val < e50 and e20 <= e50 and roc <= 0.15)
            or (r_val < e20 and roc <= -0.60)
            or (r_val < e200 and roc < 0.0)
        )

        if is_outperforming and not is_underperforming:
            regime = "ETH_OUTPERFORMING"
        elif is_underperforming:
            regime = "ETH_UNDERPERFORMING"
        else:
            regime = "ETH_NEUTRAL"

        # Directional gating rules
        if regime == "ETH_OUTPERFORMING":
            allow_l = bool(
                smt_sig == "BULLISH_SMT_ETH_STRONG"
                or (smt_sig != "BEARISH_SMT_ETH_WEAK" and z48 <= 0.60)
            )
            allow_s = bool(smt_sig == "BEARISH_SMT_ETH_WEAK" and z48 > 1.25)
            min_conf = 65
            min_rr = 2.5
            rationale = (
                "ETH outperforming BTC on RS ratio; longs favored unless overextended (zscore > 0.6) "
                "or Bearish SMT blowoff."
            )
        elif regime == "ETH_UNDERPERFORMING":
            allow_l = bool(smt_sig == "BULLISH_SMT_ETH_STRONG" and z48 <= 0.0)
            allow_s = bool(smt_sig != "BULLISH_SMT_ETH_STRONG")
            min_conf = 65
            min_rr = 2.5
            rationale = "ETH underperforming BTC on RS ratio; oversold bounce longs permitted only with confirmed Bullish SMT at discount."
        else:  # ETH_NEUTRAL
            allow_l = bool(
                smt_sig == "BULLISH_SMT_ETH_STRONG"
                or (smt_sig != "BEARISH_SMT_ETH_WEAK" and z48 <= 0.0)
            )
            allow_s = bool(smt_sig != "BULLISH_SMT_ETH_STRONG")
            min_conf = 65
            min_rr = 2.5
            rationale = "ETH/BTC relative strength is neutral; trades require balanced risk and no adverse SMT."

        out_table[ts_i] = EthBtcRegimeSnapshot(
            ts=ts_i,
            btc_ts=int(b_ts[j]),
            eth_close=eth_c,
            btc_close=btc_c,
            eth_btc_ratio=r_val,
            rs_ema20=e20,
            rs_ema50=e50,
            rs_ema200=e200,
            rs_roc24_pct=roc,
            rs_zscore48=z48,
            regime=regime,
            smt_signal=smt_sig,
            allow_long=allow_l,
            allow_short=allow_s,
            min_confidence_required=min_conf,
            min_rr_required=min_rr,
            rationale=rationale,
        )

    return out_table


def evaluate_eth_plan_under_smt_regime(
    plan: dict,
    local_regime: str,
    smt_snap: EthBtcRegimeSnapshot | None,
    strict_a_plus_only: bool = True,
) -> tuple[bool, str]:
    """Evaluates an ETH plan against point-in-time cross-asset relative-strength and SMT divergence.

    Returns (True, "ALLOWED") or (False, reason).
    """
    if smt_snap is None:
        return True, "NO_REFERENCE_SERIES"

    if not strict_a_plus_only:
        return True, "STRICT_A_PLUS_DISABLED"

    plan_type = str(plan.get("type", ""))
    side = str(plan.get("action", "")).upper()
    confidence = int(plan.get("confidence", 0) or 0)
    rr_val = float(plan.get("riskRewardRatio") or plan.get("rr") or plan.get("risk_reward") or 0.0)

    # 1. Reject immediate market taker entries on ETH under strict A+
    if plan_type in ("Immediate Buy", "Immediate Sell"):
        return False, "VETO_ETH_IMMEDIATE_TAKER_ENTRY"

    # 2. Reject chop/compression regimes unless directly confirmed by strong SMT or high confidence
    local_reg_upper = str(local_regime or "").upper()
    is_chop_regime = any(
        k in local_reg_upper for k in ("LIQUIDITY_TRAP_CHOP", "VOLATILITY_COMPRESSION")
    )
    if is_chop_regime:
        has_smt_confirm = (side == "BUY" and smt_snap.smt_signal == "BULLISH_SMT_ETH_STRONG") or (
            side == "SELL" and smt_snap.smt_signal == "BEARISH_SMT_ETH_WEAK"
        )
        if not (has_smt_confirm or confidence >= 70):
            return False, f"VETO_ETH_CHOP_REGIME_{local_regime}"

    # 3. Directional regime veto
    if side == "BUY":
        if smt_snap.regime == "ETH_OUTPERFORMING":
            if smt_snap.rs_zscore48 > 0.60 and not smt_snap.bullish_smt:
                return False, "VETO_ETH_OUTPERFORMING_OVEREXTENDED_LONG"

        elif smt_snap.regime == "ETH_UNDERPERFORMING":
            if not (smt_snap.bullish_smt and smt_snap.rs_zscore48 <= 0.0):
                return False, "ETH_UNDERPERFORMING_LONG_VETO"

        elif smt_snap.regime == "ETH_NEUTRAL":
            if not smt_snap.bullish_smt and smt_snap.rs_zscore48 > 0.0:
                return False, "VETO_ETH_NEUTRAL_PREMIUM_LONG_WITHOUT_SMT"

        if smt_snap.rs_roc24_pct < -2.0 and not smt_snap.bullish_smt:
            return False, "VETO_ETH_MOMENTUM_BREAKDOWN_LONG"

        if not smt_snap.allow_long and not smt_snap.bullish_smt:
            return False, f"VETO_ETH_LONG_IN_{smt_snap.regime}"

    if side == "SELL" and not smt_snap.allow_short:
        return False, f"VETO_ETH_SHORT_IN_{smt_snap.regime}"

    # 4. Confluence hurdle
    if confidence < smt_snap.min_confidence_required:
        return (
            False,
            f"VETO_ETH_CONFIDENCE_{confidence}_BELOW_REQUIRED_{smt_snap.min_confidence_required}",
        )

    # 5. Risk:Reward hurdle
    if rr_val > 0.0 and rr_val < smt_snap.min_rr_required:
        return (
            False,
            f"VETO_ETH_RR_{rr_val:.2f}_BELOW_REQUIRED_{smt_snap.min_rr_required}",
        )

    return True, None
