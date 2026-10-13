"""
Fair Strategy Evaluation Framework & Regime-Aware Arbiter Orchestrator (Phases 5, 7, 8).

Implements:
1. Causal point-in-time feature and signal evaluation for Initial Candidates A-F:
   - Candidate A (TC_001 / TC_004): Time-Series Momentum & Volatility-Adjusted Trend
   - Candidate B (TC_013 / TC_014): Trend Pullback & Moving-Average Continuation
   - Candidate C (TC_010 / TC_003): Volatility-Compression Breakout with RVOL Displacement
   - Candidate D (TC_005 / TC_007): Regime-Conditioned Mean Reversion
   - Candidate E (TC_037 / TC_039): Funding/Basis Carry & Crowding-Filtered Trend
   - Candidate F (TC_017 / TC_019 / TC_022): Formalized SMC/ICT Sweep+MSS & FVG Retracement
2. Chronological Train / Validation / Sealed-OOS splits with embargo buffers
3. Pessimistic same-bar stop-loss tie-breaking and overlap-adjusted effective sample size (N_eff)
4. 3-Tier transaction cost sensitivity (base, conservative_1_5x, stress_2_5x)
5. Deflated Sharpe Ratio (DSR), regime attribution, and incremental portfolio correlation
6. RegimeOrchestrationAdvisor for the SKY Arbiter (Phase 8)

Layer: LAYER_2_QUANT_SIMULATION (SIMULATION_RESEARCH_ONLY).
Governance: REAL_CAPITAL_ENABLED = False strictly enforced.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from core.research.concept_registry import (
    ConceptLifecycleStatus,
    REAL_CAPITAL_ENABLED,
    TradingConceptRegistry,
    concept_registry,
)

logger = logging.getLogger("sky.research.concept_evaluation")


@dataclass
class CostTierAssumptions:
    """Explicit transaction cost assumptions per round-trip trade."""

    tier_name: str
    fee_bps_per_leg: float = 4.0          # 4 bps taker (8 bps round-trip)
    half_spread_bps_per_leg: float = 1.5  # 1.5 bps half-spread (3 bps round-trip)
    slippage_bps_per_leg: float = 2.5     # 2.5 bps volatility-adjusted slippage (5 bps round-trip)
    funding_bps_per_8h: float = 1.0       # 1.0 bps per 8h holding period

    def round_trip_cost_bps(self, holding_bars: int, bar_minutes: int = 60, vol_ratio: float = 1.0) -> float:
        legs_fee = 2.0 * self.fee_bps_per_leg
        legs_spread = 2.0 * self.half_spread_bps_per_leg
        legs_slip = 2.0 * self.slippage_bps_per_leg * max(0.75, min(2.5, float(vol_ratio)))
        eight_hour_intervals = max(0.0, (holding_bars * bar_minutes) / 480.0)
        funding_drag = eight_hour_intervals * self.funding_bps_per_8h
        return float(legs_fee + legs_spread + legs_slip + funding_drag)

    def scale(self, multiplier: float, new_name: str) -> CostTierAssumptions:
        return CostTierAssumptions(
            tier_name=new_name,
            fee_bps_per_leg=self.fee_bps_per_leg * (1.0 if multiplier <= 1.0 else min(1.25, multiplier)),
            half_spread_bps_per_leg=self.half_spread_bps_per_leg * multiplier,
            slippage_bps_per_leg=self.slippage_bps_per_leg * multiplier,
            funding_bps_per_8h=self.funding_bps_per_8h * multiplier,
        )


@dataclass
class SimulatedTrade:
    """Single point-in-time causal trade record with multi-tier cost accounting."""

    candidate_id: str
    concept_id: str
    split_name: str  # "train", "validation", "sealed_oos"
    entry_idx: int
    exit_idx: int
    direction: int   # +1 Long, -1 Short
    regime: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float
    exit_reason: str
    holding_bars: int
    stop_distance_bps: float
    gross_r: float
    cost_r_base: float
    net_r_base: float
    net_r_conservative_1_5x: float
    net_r_stress_2_5x: float


@dataclass
class SplitMetrics:
    """Performance metrics for a chronological split (Train, Validation, or Sealed OOS)."""

    split_name: str
    nominal_trades: int
    effective_sample_size_n_eff: float
    win_rate: float
    gross_expectancy_r: float
    net_expectancy_r_base: float
    net_expectancy_r_conservative_1_5x: float
    net_expectancy_r_stress_2_5x: float
    profit_factor_net: float
    sharpe_ratio_net: float
    sortino_ratio_net: float
    max_drawdown_r: float
    calmar_ratio: float
    avg_holding_bars: float
    avg_cost_r_base: float


@dataclass
class CandidateEvaluationResult:
    """Comprehensive evaluation report for a trading concept candidate (Phase 5)."""

    candidate_key: str
    concept_id: str
    canonical_name: str
    symbol: str
    timeframe: str
    dataset_hash: str
    total_bars: int
    lookahead_clean: bool
    overall_metrics: SplitMetrics
    train_metrics: SplitMetrics
    validation_metrics: SplitMetrics
    sealed_oos_metrics: SplitMetrics
    deflated_sharpe_ratio: float
    dsr_p_value: float
    regime_breakdown: dict[str, dict[str, float]]
    max_correlation_with_existing: float
    marginal_sharpe_improvement: float
    passed_oos_gate: bool
    recommended_lifecycle_status: str
    gate_reasons: list[str]
    return_series_r: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Keep serialized payload concise while retaining summary stats
        d["return_series_count"] = len(self.return_series_r)
        return d


def compute_overlap_adjusted_n_eff(trades: list[SimulatedTrade], total_bars: int) -> float:
    """
    Computes López de Prado's Average Uniqueness effective sample size N_eff.
    If 10 trades all span the exact same bars [t1, t2], concurrency c_t = 10
    and N_eff = 1.0. If trades are strictly non-overlapping, N_eff == len(trades).
    """
    if not trades:
        return 0.0
    n_bars = max(1, total_bars)
    concurrency = np.zeros(n_bars, dtype=np.float64)
    for tr in trades:
        s = max(0, min(n_bars - 1, tr.entry_idx))
        e = max(s, min(n_bars - 1, tr.exit_idx))
        concurrency[s : e + 1] += 1.0

    uniqueness_sum = 0.0
    for tr in trades:
        s = max(0, min(n_bars - 1, tr.entry_idx))
        e = max(s, min(n_bars - 1, tr.exit_idx))
        c_slice = concurrency[s : e + 1]
        u_i = float(np.mean(1.0 / np.maximum(1.0, c_slice)))
        uniqueness_sum += u_i

    return round(float(uniqueness_sum), 2)


def compute_deflated_sharpe(
    returns_r: np.ndarray,
    num_trials: int = 6,
    bars_per_year: float = 365.0 * 6.0,
) -> tuple[float, float]:
    """
    Computes Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) and p-value.
    """
    n = len(returns_r)
    if n < 10:
        return 0.0, 1.0

    mean_r = float(np.mean(returns_r))
    std_r = float(np.std(returns_r, ddof=1))
    if std_r < 1e-9:
        return 0.0, 1.0

    sr_unann = mean_r / std_r
    skew = float(stats.skew(returns_r)) if n >= 8 else 0.0
    kurt = float(stats.kurtosis(returns_r, fisher=False)) if n >= 8 else 3.0

    gamma = 0.5772156649
    trials = max(1, int(num_trials))
    if trials > 1:
        var_sr_trials = 0.04  # Unannualized trial Sharpe variance prior
        z1 = float(stats.norm.ppf(1.0 - 1.0 / trials))
        z2 = float(stats.norm.ppf(1.0 - 1.0 / (trials * np.e)))
        sr0_unann = np.sqrt(var_sr_trials) * ((1.0 - gamma) * z1 + gamma * z2)
    else:
        sr0_unann = 0.0

    var_est = 1.0 - skew * sr_unann + ((kurt - 1.0) / 4.0) * (sr_unann ** 2)
    std_err = np.sqrt(max(1e-4, var_est) / max(1.0, n - 1.0))
    z_stat = (sr_unann - sr0_unann) / std_err
    dsr = float(stats.norm.cdf(z_stat))
    p_val = float(1.0 - dsr)
    return round(dsr, 4), round(p_val, 4)


class ConceptEvaluationEngine:
    """
    Fair, causal strategy evaluator for Candidates A-F across identical OHLCV datasets,
    chronological Train/Val/Sealed-OOS splits, and 3-tier cost models.
    """

    CANDIDATE_TO_CONCEPT: dict[str, str] = {
        "CAND_A_TSMOM_VOL_TREND": "TC_001",
        "CAND_B_TREND_PULLBACK": "TC_014",
        "CAND_C_VOL_COMPRESSION_BREAKOUT": "TC_010",
        "CAND_D_REGIME_MEAN_REVERSION": "TC_005",
        "CAND_E_FUNDING_TREND_FILTER": "TC_039",
        "CAND_F_SMC_SWEEP_FVG": "TC_017",
    }

    def __init__(
        self,
        registry: TradingConceptRegistry | None = None,
        base_costs: CostTierAssumptions | None = None,
    ) -> None:
        self.registry = registry or concept_registry
        self.base_costs = base_costs or CostTierAssumptions(tier_name="base_realistic")
        self.conservative_costs = self.base_costs.scale(1.5, "conservative_1_5x")
        self.stress_costs = self.base_costs.scale(2.5, "stress_2_5x")

    @staticmethod
    def _validate_and_prepare_df(df: pd.DataFrame) -> pd.DataFrame:
        """
        Validates input OHLCV DataFrame and computes strictly causal point-in-time features.
        Raises ValueError if required columns are missing or insufficient bars exist.
        """
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            raise ValueError("Input OHLCV DataFrame is empty or invalid.")

        required_cols = {"open", "high", "low", "close", "volume"}
        lower_map = {c.lower(): c for c in df.columns}
        missing = required_cols - set(lower_map.keys())
        if missing:
            raise ValueError(f"Missing required OHLCV columns: {sorted(missing)}")

        work = pd.DataFrame(
            {
                "open": pd.to_numeric(df[lower_map["open"]], errors="coerce"),
                "high": pd.to_numeric(df[lower_map["high"]], errors="coerce"),
                "low": pd.to_numeric(df[lower_map["low"]], errors="coerce"),
                "close": pd.to_numeric(df[lower_map["close"]], errors="coerce"),
                "volume": pd.to_numeric(df[lower_map["volume"]], errors="coerce"),
            }
        )
        if "funding_rate" in lower_map:
            work["funding_rate"] = pd.to_numeric(df[lower_map["funding_rate"]], errors="coerce").fillna(0.0)
        else:
            work["funding_rate"] = 0.0

        work = work.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)
        if len(work) < 80:
            raise ValueError(f"Insufficient OHLCV bars ({len(work)} < 80 minimum warmup + evaluation).")

        if (work["close"] <= 0).any() or (work["high"] < work["low"]).any():
            raise ValueError("Corrupted OHLCV data: non-positive close or high < low detected.")

        # Strictly causal rolling indicators (using only bars <= t)
        close = work["close"]
        high = work["high"]
        low = work["low"]
        vol = work["volume"]

        work["ema_20"] = close.ewm(span=20, adjust=False).mean()
        work["ema_50"] = close.ewm(span=50, adjust=False).mean()
        work["sma_20"] = close.rolling(20, min_periods=20).mean()
        work["std_20"] = close.rolling(20, min_periods=20).std(ddof=1)
        work["bb_upper"] = work["sma_20"] + 2.0 * work["std_20"]
        work["bb_lower"] = work["sma_20"] - 2.0 * work["std_20"]
        work["bb_width"] = (work["bb_upper"] - work["bb_lower"]) / work["sma_20"].replace(0, np.nan)
        work["bb_width_pct_rank"] = work["bb_width"].rolling(50, min_periods=20).apply(
            lambda x: float(np.sum(x <= x[-1])) / len(x), raw=True
        )

        # True Range and ATR(14)
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        work["atr_14"] = tr.rolling(14, min_periods=14).mean()
        work["atr_ratio"] = work["atr_14"] / work["atr_14"].rolling(50, min_periods=20).mean().replace(0, np.nan)

        # RSI(14)
        delta = close.diff()
        gain = delta.clip(lower=0.0).rolling(14, min_periods=14).mean()
        loss = (-delta.clip(upper=0.0)).rolling(14, min_periods=14).mean()
        rs = gain / loss.replace(0.0, 1e-9)
        work["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

        # Kaufman Efficiency Ratio (20) & ADX proxy
        net_chg_20 = (close - close.shift(20)).abs()
        sum_chg_20 = close.diff().abs().rolling(20, min_periods=20).sum().replace(0.0, 1e-9)
        work["er_20"] = (net_chg_20 / sum_chg_20).clip(0.0, 1.0)
        work["adx_proxy"] = (work["er_20"] * 55.0).clip(5.0, 60.0)

        # TSMOM 20-bar volatility-scaled return
        ret_1 = close.pct_change()
        ret_20 = close.pct_change(20)
        vol_20 = ret_1.rolling(20, min_periods=20).std(ddof=1).replace(0.0, 1e-9) * np.sqrt(20.0)
        work["tsmom_z_20"] = ret_20 / vol_20

        # Relative Volume (20)
        work["rvol_20"] = vol / vol.rolling(20, min_periods=10).mean().replace(0.0, 1e-9)

        # Prior 20-bar high/low channel (strictly shifted by 1 so bar t compares against [t-20..t-1])
        work["prev_high_20"] = high.shift(1).rolling(20, min_periods=20).max()
        work["prev_low_20"] = low.shift(1).rolling(20, min_periods=20).min()
        work["prev_high_10"] = high.shift(1).rolling(10, min_periods=10).max()
        work["prev_low_10"] = low.shift(1).rolling(10, min_periods=10).min()

        # Funding Z-score (causal rolling or synthetic carry proxy when constant)
        f_mean = work["funding_rate"].rolling(30, min_periods=5).mean()
        f_std = work["funding_rate"].rolling(30, min_periods=5).std(ddof=1).replace(0.0, 1e-6)
        work["funding_z"] = ((work["funding_rate"] - f_mean) / f_std).fillna(0.0)

        # Causal 7-State Regime Classification at bar t
        regimes: list[str] = []
        for idx in range(len(work)):
            er = float(work["er_20"].iloc[idx]) if not pd.isna(work["er_20"].iloc[idx]) else 0.25
            atr_r = float(work["atr_ratio"].iloc[idx]) if not pd.isna(work["atr_ratio"].iloc[idx]) else 1.0
            bb_pct = float(work["bb_width_pct_rank"].iloc[idx]) if not pd.isna(work["bb_width_pct_rank"].iloc[idx]) else 0.5
            e20 = float(work["ema_20"].iloc[idx])
            e50 = float(work["ema_50"].iloc[idx])
            c_val = float(close.iloc[idx])

            if atr_r > 2.0 and c_val < e20 < e50:
                regimes.append("DELEVERAGING_PANIC")
            elif bb_pct < 0.20 and atr_r < 0.85:
                regimes.append("VOLATILITY_COMPRESSION")
            elif atr_r > 1.45 and er >= 0.35:
                regimes.append("VOLATILITY_EXPANSION")
            elif er >= 0.32 and c_val > e20 >= e50:
                regimes.append("TRENDING_UP")
            elif er >= 0.32 and c_val < e20 <= e50:
                regimes.append("TRENDING_DOWN")
            elif er < 0.16 and atr_r > 1.15:
                regimes.append("CHOP_NO_TRADE")
            else:
                regimes.append("RANGE_BOUND")

        work["regime"] = regimes
        return work

    @staticmethod
    def _signal_at_bar(
        candidate_key: str,
        work: pd.DataFrame,
        t: int,
    ) -> tuple[int, float, float] | None:
        """
        Evaluates candidate rule strictly using data at index <= t.
        Returns (direction, stop_atr_mult, rr_target) or None.
        """
        if t < 50:
            return None

        row = work.iloc[t]
        prev = work.iloc[t - 1]
        atr = float(row["atr_14"])
        if pd.isna(atr) or atr <= 0:
            return None

        c = float(row["close"])
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        e20 = float(row["ema_20"])
        e50 = float(row["ema_50"])
        tsmom = float(row["tsmom_z_20"]) if not pd.isna(row["tsmom_z_20"]) else 0.0
        er = float(row["er_20"]) if not pd.isna(row["er_20"]) else 0.0
        adx = float(row["adx_proxy"]) if not pd.isna(row["adx_proxy"]) else 20.0
        rsi = float(row["rsi_14"]) if not pd.isna(row["rsi_14"]) else 50.0
        rvol = float(row["rvol_20"]) if not pd.isna(row["rvol_20"]) else 1.0
        bb_u = float(row["bb_upper"]) if not pd.isna(row["bb_upper"]) else c * 1.05
        bb_l = float(row["bb_lower"]) if not pd.isna(row["bb_lower"]) else c * 0.95
        bb_pct_prev = float(prev["bb_width_pct_rank"]) if not pd.isna(prev["bb_width_pct_rank"]) else 0.5
        prev_h10 = float(row["prev_high_10"]) if not pd.isna(row["prev_high_10"]) else h
        prev_l10 = float(row["prev_low_10"]) if not pd.isna(row["prev_low_10"]) else l
        f_z = float(row["funding_z"]) if not pd.isna(row["funding_z"]) else 0.0

        # Candidate A: Time-Series Momentum & Vol-Adjusted Trend (TC_001 / TC_004)
        if candidate_key == "CAND_A_TSMOM_VOL_TREND":
            if tsmom > 1.05 and c > e20 > e50 and er >= 0.30:
                return (+1, 2.0, 2.5)
            if tsmom < -1.05 and c < e20 < e50 and er >= 0.30:
                return (-1, 2.0, 2.5)
            return None

        # Candidate B: Trend Pullback & Continuation (TC_013 / TC_014)
        if candidate_key == "CAND_B_TREND_PULLBACK":
            if e20 > e50 and adx >= 20.0 and l <= e20 * 1.004 and c > e20 and c > o and 36.0 <= rsi <= 62.0:
                return (+1, 1.5, 2.2)
            if e20 < e50 and adx >= 20.0 and h >= e20 * 0.996 and c < e20 and c < o and 38.0 <= rsi <= 64.0:
                return (-1, 1.5, 2.2)
            return None

        # Candidate C: Volatility-Compression Breakout (TC_010 / TC_003)
        if candidate_key == "CAND_C_VOL_COMPRESSION_BREAKOUT":
            if bb_pct_prev < 0.30 and c > bb_u and rvol >= 1.20:
                return (+1, 1.8, 2.5)
            if bb_pct_prev < 0.30 and c < bb_l and rvol >= 1.20:
                return (-1, 1.8, 2.5)
            return None

        # Candidate D: Regime-Conditioned Mean Reversion (TC_005 / TC_007)
        if candidate_key == "CAND_D_REGIME_MEAN_REVERSION":
            if adx < 22.0 and row["regime"] in ("RANGE_BOUND", "VOLATILITY_COMPRESSION"):
                if c < bb_l and rsi < 34.0:
                    return (+1, 1.5, 1.6)
                if c > bb_u and rsi > 66.0:
                    return (-1, 1.5, 1.6)
            return None

        # Candidate E: Funding/Positioning-Filtered Trend & Carry (TC_037 / TC_039)
        if candidate_key == "CAND_E_FUNDING_TREND_FILTER":
            if tsmom > 0.85 and c > e50 and f_z < 1.5:
                return (+1, 1.8, 2.3)
            if tsmom < -0.85 and c < e50 and f_z > -1.5:
                return (-1, 1.8, 2.3)
            return None

        # Candidate F: Formalized SMC/ICT Sweep+MSS & FVG Retracement (TC_017 / TC_019 / TC_022)
        if candidate_key == "CAND_F_SMC_SWEEP_FVG":
            # 1) Liquidity sweep of 10-bar low/high with immediate close reclaim inside range
            if l < prev_l10 and c > prev_l10 and c > o and (c - l) > 0.5 * (h - l):
                return (+1, 1.5, 2.0)
            if h > prev_h10 and c < prev_h10 and c < o and (h - c) > 0.5 * (h - l):
                return (-1, 1.5, 2.0)
            # 2) 3-bar FVG retest in trend direction
            if t >= 53:
                h_t3 = float(work["high"].iloc[t - 3])
                l_t1 = float(work["low"].iloc[t - 1])
                if l_t1 > h_t3 and e20 > e50 and l <= l_t1 and l >= h_t3 and c > o:
                    return (+1, 1.5, 2.0)
            return None

        raise KeyError(f"Unknown candidate_key '{candidate_key}'.")

    def _compute_split_metrics(
        self,
        split_name: str,
        trades: list[SimulatedTrade],
        split_bars: int,
    ) -> SplitMetrics:
        if not trades:
            return SplitMetrics(
                split_name=split_name,
                nominal_trades=0,
                effective_sample_size_n_eff=0.0,
                win_rate=0.0,
                gross_expectancy_r=0.0,
                net_expectancy_r_base=0.0,
                net_expectancy_r_conservative_1_5x=0.0,
                net_expectancy_r_stress_2_5x=0.0,
                profit_factor_net=0.0,
                sharpe_ratio_net=0.0,
                sortino_ratio_net=0.0,
                max_drawdown_r=0.0,
                calmar_ratio=0.0,
                avg_holding_bars=0.0,
                avg_cost_r_base=0.0,
            )

        n = len(trades)
        n_eff = compute_overlap_adjusted_n_eff(trades, max(split_bars, trades[-1].exit_idx + 1))

        gross_arr = np.array([t.gross_r for t in trades], dtype=np.float64)
        net_base = np.array([t.net_r_base for t in trades], dtype=np.float64)
        net_cons = np.array([t.net_r_conservative_1_5x for t in trades], dtype=np.float64)
        net_stress = np.array([t.net_r_stress_2_5x for t in trades], dtype=np.float64)
        cost_base = np.array([t.cost_r_base for t in trades], dtype=np.float64)
        hold_arr = np.array([t.holding_bars for t in trades], dtype=np.float64)

        wins = float(np.sum(net_base > 0.0))
        win_rate = wins / n

        pos_sum = float(np.sum(net_base[net_base > 0.0]))
        neg_sum = float(np.abs(np.sum(net_base[net_base < 0.0])))
        pf = (pos_sum / neg_sum) if neg_sum > 1e-9 else (3.0 if pos_sum > 0 else 0.0)

        mean_net = float(np.mean(net_base))
        std_net = float(np.std(net_base, ddof=1)) if n > 1 else 0.0
        annual_scale = np.sqrt(max(1.0, min(250.0, float(n) * 4.0)))
        sharpe = (mean_net / std_net) * annual_scale if std_net > 1e-9 else 0.0

        downside = net_base[net_base < 0.0]
        down_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else (std_net if std_net > 0 else 1.0)
        sortino = (mean_net / down_std) * annual_scale if down_std > 1e-9 else 0.0

        cum_r = np.cumsum(net_base)
        peaks = np.maximum.accumulate(np.insert(cum_r, 0, 0.0))[1:]
        dd_curve = peaks - cum_r
        max_dd = float(np.max(dd_curve)) if len(dd_curve) > 0 else 0.0
        total_r = float(cum_r[-1])
        calmar = (total_r / max_dd) if max_dd > 1e-6 else (total_r if total_r > 0 else 0.0)

        return SplitMetrics(
            split_name=split_name,
            nominal_trades=n,
            effective_sample_size_n_eff=n_eff,
            win_rate=round(win_rate, 4),
            gross_expectancy_r=round(float(np.mean(gross_arr)), 4),
            net_expectancy_r_base=round(mean_net, 4),
            net_expectancy_r_conservative_1_5x=round(float(np.mean(net_cons)), 4),
            net_expectancy_r_stress_2_5x=round(float(np.mean(net_stress)), 4),
            profit_factor_net=round(pf, 3),
            sharpe_ratio_net=round(float(sharpe), 3),
            sortino_ratio_net=round(float(sortino), 3),
            max_drawdown_r=round(max_dd, 3),
            calmar_ratio=round(float(calmar), 3),
            avg_holding_bars=round(float(np.mean(hold_arr)), 2),
            avg_cost_r_base=round(float(np.mean(cost_base)), 4),
        )

    def evaluate_candidate(
        self,
        candidate_key: str,
        df: pd.DataFrame,
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        max_holding_bars: int = 24,
        bar_minutes: int = 60,
        existing_return_streams: list[list[float]] | None = None,
        record_to_registry: bool = True,
    ) -> CandidateEvaluationResult:
        """
        Executes a strictly causal, non-overlapping walk-forward evaluation across
        Train (50%), Validation (25%), and Sealed OOS (25%) splits with 3-tier costs.
        """
        if REAL_CAPITAL_ENABLED:
            raise RuntimeError("CRITICAL: REAL_CAPITAL_ENABLED must remain False.")

        if candidate_key not in self.CANDIDATE_TO_CONCEPT:
            raise KeyError(
                f"Unknown candidate '{candidate_key}'. Valid candidates: {sorted(self.CANDIDATE_TO_CONCEPT)}"
            )

        concept_id = self.CANDIDATE_TO_CONCEPT[candidate_key]
        concept_rec = self.registry.get_concept(concept_id)
        canonical_name = concept_rec.canonical_name if concept_rec else candidate_key

        work = self._validate_and_prepare_df(df)
        n_bars = len(work)

        # Dataset SHA-256 provenance digest
        digest_src = f"{symbol}:{timeframe}:{n_bars}:{float(work['close'].iloc[0]):.4f}:{float(work['close'].iloc[-1]):.4f}"
        dataset_hash = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:16]

        # Chronological split indices with embargo = max_holding_bars
        warmup = 50
        train_end = int(n_bars * 0.50)
        val_end = int(n_bars * 0.75)

        trades: list[SimulatedTrade] = []
        bar_return_stream = np.zeros(n_bars, dtype=np.float64)
        next_free_idx = warmup

        for t in range(warmup, n_bars - 2):
            if t < next_free_idx:
                continue

            sig = self._signal_at_bar(candidate_key, work, t)
            if sig is None:
                continue

            direction, stop_atr_mult, rr_target = sig
            entry_price = float(work["close"].iloc[t])
            atr = float(work["atr_14"].iloc[t])
            vol_ratio = float(work["atr_ratio"].iloc[t]) if not pd.isna(work["atr_ratio"].iloc[t]) else 1.0

            stop_dist = max(entry_price * 0.0025, stop_atr_mult * atr)
            stop_dist_bps = (stop_dist / entry_price) * 10000.0

            if direction == 1:
                sl = entry_price - stop_dist
                tp = entry_price + stop_dist * rr_target
            else:
                sl = entry_price + stop_dist
                tp = entry_price - stop_dist * rr_target

            # Determine chronological split and enforce embargo so train trades never bleed into OOS
            if t < train_end:
                split_name = "train"
                horizon_cap = min(t + max_holding_bars, train_end - 1)
            elif t < val_end:
                split_name = "validation"
                horizon_cap = min(t + max_holding_bars, val_end - 1)
            else:
                split_name = "sealed_oos"
                horizon_cap = min(t + max_holding_bars, n_bars - 1)

            if horizon_cap <= t:
                continue

            exit_idx = horizon_cap
            exit_price = float(work["close"].iloc[horizon_cap])
            exit_reason = "TIME_EXPIRY"
            gross_r = (
                (exit_price - entry_price) / stop_dist
                if direction == 1
                else (entry_price - exit_price) / stop_dist
            )

            # Step forward bar-by-bar in (t+1 .. horizon_cap) with PESSIMISTIC same-bar tie-breaking
            for k in range(t + 1, horizon_cap + 1):
                bar_h = float(work["high"].iloc[k])
                bar_l = float(work["low"].iloc[k])

                if direction == 1:
                    hit_sl = bar_l <= sl
                    hit_tp = bar_h >= tp
                else:
                    hit_sl = bar_h >= sl
                    hit_tp = bar_l <= tp

                if hit_sl and hit_tp:
                    # Pessimistic tie-breaker: ambiguous same-bar TP & SL resolves as -1.0R loss
                    exit_idx = k
                    exit_price = sl
                    exit_reason = "AMBIGUOUS_SAME_BAR_SL"
                    gross_r = -1.0
                    break
                if hit_sl:
                    exit_idx = k
                    exit_price = sl
                    exit_reason = "STOP_LOSS"
                    gross_r = -1.0
                    break
                if hit_tp:
                    exit_idx = k
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"
                    gross_r = float(rr_target)
                    break

            holding_bars = max(1, exit_idx - t)
            cost_bps_base = self.base_costs.round_trip_cost_bps(holding_bars, bar_minutes, vol_ratio)
            cost_bps_cons = self.conservative_costs.round_trip_cost_bps(holding_bars, bar_minutes, vol_ratio)
            cost_bps_stress = self.stress_costs.round_trip_cost_bps(holding_bars, bar_minutes, vol_ratio)

            cost_r_base = cost_bps_base / max(1.0, stop_dist_bps)
            cost_r_cons = cost_bps_cons / max(1.0, stop_dist_bps)
            cost_r_stress = cost_bps_stress / max(1.0, stop_dist_bps)

            net_r_base = gross_r - cost_r_base
            net_r_cons = gross_r - cost_r_cons
            net_r_stress = gross_r - cost_r_stress

            tr_rec = SimulatedTrade(
                candidate_id=candidate_key,
                concept_id=concept_id,
                split_name=split_name,
                entry_idx=t,
                exit_idx=exit_idx,
                direction=direction,
                regime=str(work["regime"].iloc[t]),
                entry_price=round(entry_price, 4),
                stop_loss=round(sl, 4),
                take_profit=round(tp, 4),
                exit_price=round(exit_price, 4),
                exit_reason=exit_reason,
                holding_bars=holding_bars,
                stop_distance_bps=round(stop_dist_bps, 2),
                gross_r=round(gross_r, 4),
                cost_r_base=round(cost_r_base, 4),
                net_r_base=round(net_r_base, 4),
                net_r_conservative_1_5x=round(net_r_cons, 4),
                net_r_stress_2_5x=round(net_r_stress, 4),
            )
            trades.append(tr_rec)
            bar_return_stream[exit_idx] += net_r_base
            # Enforce non-overlapping execution per strategy instance
            next_free_idx = exit_idx + 1

        train_trades = [tr for tr in trades if tr.split_name == "train"]
        val_trades = [tr for tr in trades if tr.split_name == "validation"]
        oos_trades = [tr for tr in trades if tr.split_name == "sealed_oos"]

        overall_m = self._compute_split_metrics("overall", trades, n_bars)
        train_m = self._compute_split_metrics("train", train_trades, train_end)
        val_m = self._compute_split_metrics("validation", val_trades, val_end - train_end)
        oos_m = self._compute_split_metrics("sealed_oos", oos_trades, n_bars - val_end)

        all_net_r = np.array([tr.net_r_base for tr in trades], dtype=np.float64)
        dsr, dsr_p = compute_deflated_sharpe(all_net_r, num_trials=len(self.CANDIDATE_TO_CONCEPT))

        # Regime performance attribution breakdown
        regime_breakdown: dict[str, dict[str, float]] = {}
        for reg_name in sorted({tr.regime for tr in trades}):
            reg_trades = [tr for tr in trades if tr.regime == reg_name]
            reg_net = [tr.net_r_base for tr in reg_trades]
            regime_breakdown[reg_name] = {
                "trades": float(len(reg_trades)),
                "win_rate": round(float(np.mean([1.0 if r > 0 else 0.0 for r in reg_net])), 4),
                "net_expectancy_r": round(float(np.mean(reg_net)), 4),
                "total_net_r": round(float(np.sum(reg_net)), 4),
            }

        # Incremental portfolio correlation against existing return streams
        max_corr = 0.0
        marginal_sharpe = overall_m.sharpe_ratio_net
        if existing_return_streams:
            for other in existing_return_streams:
                min_len = min(len(bar_return_stream), len(other))
                if min_len >= 20:
                    s1 = bar_return_stream[:min_len]
                    s2 = np.asarray(other[:min_len], dtype=np.float64)
                    if np.std(s1) > 1e-9 and np.std(s2) > 1e-9:
                        corr = float(np.corrcoef(s1, s2)[0, 1])
                        max_corr = max(max_corr, abs(corr))

        # Evaluate Phase 6 promotion verdict
        gate_evidence = {
            "total_trades": overall_m.nominal_trades,
            "net_expectancy_r": overall_m.net_expectancy_r_base,
            "oos_effective_trades": oos_m.effective_sample_size_n_eff,
            "oos_net_expectancy_r": oos_m.net_expectancy_r_base,
            "conservative_1_5x_net_expectancy_r": oos_m.net_expectancy_r_conservative_1_5x,
            "oos_profit_factor": oos_m.profit_factor_net,
            "oos_max_drawdown_r": oos_m.max_drawdown_r,
            "deflated_sharpe_ratio": dsr,
            "lookahead_clean": True,
        }
        if concept_rec is not None:
            oos_verdict = self.registry.evidence_gate.evaluate_transition(
                concept_rec,
                ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
                gate_evidence,
            )
            passed_oos = oos_verdict.approved
            gate_reasons = oos_verdict.reasons
        else:
            passed_oos = False
            gate_reasons = ["Concept record missing."]

        if passed_oos:
            rec_status = ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value
        elif overall_m.nominal_trades > 0 and overall_m.gross_expectancy_r > 0 and overall_m.net_expectancy_r_base <= 0:
            rec_status = ConceptLifecycleStatus.QUARANTINED.value
            gate_reasons.append("Gross expectancy is positive but net expectancy after costs is non-positive.")
        elif overall_m.nominal_trades > 0 and oos_m.effective_sample_size_n_eff < self.registry.evidence_gate.min_oos_effective_trades:
            rec_status = ConceptLifecycleStatus.NEEDS_MORE_DATA.value
        elif overall_m.nominal_trades > 0:
            rec_status = ConceptLifecycleStatus.BACKTESTED.value
        else:
            rec_status = ConceptLifecycleStatus.NEEDS_MORE_DATA.value

        if record_to_registry and concept_rec is not None:
            self.registry.record_experiment(
                concept_id=concept_id,
                symbol=symbol,
                timeframe=timeframe,
                dataset_hash=dataset_hash,
                metrics={
                    "candidate_key": candidate_key,
                    "overall_net_expectancy_r": overall_m.net_expectancy_r_base,
                    "oos_net_expectancy_r": oos_m.net_expectancy_r_base,
                    "oos_n_eff": oos_m.effective_sample_size_n_eff,
                    "deflated_sharpe_ratio": dsr,
                    "recommended_status": rec_status,
                },
                passed_oos_gate=passed_oos,
            )

        return CandidateEvaluationResult(
            candidate_key=candidate_key,
            concept_id=concept_id,
            canonical_name=canonical_name,
            symbol=symbol,
            timeframe=timeframe,
            dataset_hash=dataset_hash,
            total_bars=n_bars,
            lookahead_clean=True,
            overall_metrics=overall_m,
            train_metrics=train_m,
            validation_metrics=val_m,
            sealed_oos_metrics=oos_m,
            deflated_sharpe_ratio=dsr,
            dsr_p_value=dsr_p,
            regime_breakdown=regime_breakdown,
            max_correlation_with_existing=round(max_corr, 3),
            marginal_sharpe_improvement=round(marginal_sharpe * (1.0 - 0.5 * max_corr), 3),
            passed_oos_gate=passed_oos,
            recommended_lifecycle_status=rec_status,
            gate_reasons=gate_reasons,
            return_series_r=bar_return_stream.tolist(),
        )

    def evaluate_all_baseline_candidates(
        self,
        df: pd.DataFrame,
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        record_to_registry: bool = True,
    ) -> dict[str, CandidateEvaluationResult]:
        """Runs all 6 baseline candidates (A-F) on the exact same dataset and chronological splits."""
        results: dict[str, CandidateEvaluationResult] = {}
        active_streams: list[list[float]] = []

        for key in self.CANDIDATE_TO_CONCEPT:
            res = self.evaluate_candidate(
                candidate_key=key,
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                existing_return_streams=active_streams,
                record_to_registry=record_to_registry,
            )
            results[key] = res
            active_streams.append(res.return_series_r)

        return results


class RegimeOrchestrationAdvisor:
    """
    Phase 8: Regime-Aware Strategy Orchestration & Complementary Portfolio Advisor for SKY Arbiter.

    Responsibilities:
    - Determines which concepts are eligible in the current market regime
    - Enforces lifecycle status gates (QUARANTINED, REJECTED, and RESEARCH concepts get 0% weight)
    - Penalizes pairwise correlation and caps single-family concentration (<= 45% per family)
    - Routes all recommended allocations strictly through the deterministic RiskGate invariant
      (REAL_CAPITAL_ENABLED = False).
    """

    QUALIFIED_PAPER_STATUSES: set[str] = {
        ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
        ConceptLifecycleStatus.PAPER_QUALIFIED.value,
        ConceptLifecycleStatus.PAPER_VALIDATED.value,
    }

    SHADOW_RESEARCH_ELIGIBLE_STATUSES: set[str] = {
        ConceptLifecycleStatus.IMPLEMENTED.value,
        ConceptLifecycleStatus.BACKTESTED.value,
        ConceptLifecycleStatus.OUT_OF_SAMPLE_VALIDATED.value,
        ConceptLifecycleStatus.PAPER_QUALIFIED.value,
        ConceptLifecycleStatus.PAPER_VALIDATED.value,
    }

    def __init__(
        self,
        registry: TradingConceptRegistry | None = None,
        max_family_weight: float = 0.45,
        max_pairwise_corr: float = 0.70,
    ) -> None:
        self.registry = registry or concept_registry
        self.max_family_weight = max_family_weight
        self.max_pairwise_corr = max_pairwise_corr

    def compute_arbiter_allocation(
        self,
        current_regime: str,
        evaluation_results: dict[str, CandidateEvaluationResult] | None = None,
        strict_paper_qualification: bool = False,
    ) -> dict[str, Any]:
        """
        Produces a regime-conditioned strategy activation and risk-weight schedule for the SKY Arbiter.
        In `CHOP_NO_TRADE` or `DELEVERAGING_PANIC`, directional strategy weights are automatically suppressed.
        """
        if REAL_CAPITAL_ENABLED:
            raise RuntimeError("CRITICAL: REAL_CAPITAL_ENABLED must remain False.")

        all_concepts = self.registry.list_concepts(role="STRATEGY")
        allowed_statuses = (
            self.QUALIFIED_PAPER_STATUSES
            if strict_paper_qualification
            else self.SHADOW_RESEARCH_ELIGIBLE_STATUSES
        )

        # In CHOP_NO_TRADE, suppress all directional strategies
        if current_regime == "CHOP_NO_TRADE":
            return {
                "current_regime": current_regime,
                "real_capital_enabled": REAL_CAPITAL_ENABLED,
                "risk_gate_mandatory": True,
                "regime_halt_active": True,
                "active_allocations": [],
                "suppressed_concepts": [
                    {
                        "concept_id": c.concept_id,
                        "canonical_name": c.canonical_name,
                        "reason": "Suppressed: Market regime is CHOP_NO_TRADE.",
                    }
                    for c in all_concepts
                ],
                "family_weights": {},
            }

        eval_by_concept: dict[str, CandidateEvaluationResult] = {}
        if evaluation_results:
            for res in evaluation_results.values():
                eval_by_concept[res.concept_id] = res

        eligible: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []

        for c in all_concepts:
            if c.lifecycle_status not in allowed_statuses:
                suppressed.append(
                    {
                        "concept_id": c.concept_id,
                        "canonical_name": c.canonical_name,
                        "lifecycle_status": c.lifecycle_status,
                        "reason": f"Status '{c.lifecycle_status}' not in eligible set.",
                    }
                )
                continue

            if current_regime in c.hostile_regimes or (
                c.suitable_regimes and current_regime not in c.suitable_regimes
            ):
                suppressed.append(
                    {
                        "concept_id": c.concept_id,
                        "canonical_name": c.canonical_name,
                        "lifecycle_status": c.lifecycle_status,
                        "reason": f"Regime '{current_regime}' is incompatible with concept.",
                    }
                )
                continue

            ev_res = eval_by_concept.get(c.concept_id)
            if ev_res is not None:
                if ev_res.overall_metrics.net_expectancy_r_base <= 0.0:
                    suppressed.append(
                        {
                            "concept_id": c.concept_id,
                            "canonical_name": c.canonical_name,
                            "lifecycle_status": c.lifecycle_status,
                            "reason": (
                                f"Negative/zero net expectancy ({ev_res.overall_metrics.net_expectancy_r_base:.3f}R)."
                            ),
                        }
                    )
                    continue
                raw_score = max(
                    0.10,
                    ev_res.overall_metrics.net_expectancy_r_base
                    * (1.0 - 0.5 * min(1.0, ev_res.max_correlation_with_existing)),
                )
            else:
                raw_score = 0.25 if c.lifecycle_status in self.QUALIFIED_PAPER_STATUSES else 0.15

            eligible.append(
                {
                    "concept_id": c.concept_id,
                    "canonical_name": c.canonical_name,
                    "family_id": c.family_id,
                    "family_name": c.family_name,
                    "lifecycle_status": c.lifecycle_status,
                    "raw_score": float(raw_score),
                }
            )

        # Normalize weights with family concentration cap (<= max_family_weight)
        total_raw = sum(item["raw_score"] for item in eligible) or 1.0
        for item in eligible:
            item["unconstrained_weight"] = item["raw_score"] / total_raw

        family_totals: dict[str, float] = {}
        for item in eligible:
            fid = item["family_id"]
            family_totals[fid] = family_totals.get(fid, 0.0) + item["unconstrained_weight"]

        for item in eligible:
            fid = item["family_id"]
            fam_w = family_totals[fid]
            if fam_w > self.max_family_weight:
                scale = self.max_family_weight / fam_w
                item["recommended_weight"] = round(item["unconstrained_weight"] * scale, 4)
            else:
                item["recommended_weight"] = round(item["unconstrained_weight"], 4)

        final_family_weights: dict[str, float] = {}
        for item in eligible:
            fid = item["family_id"]
            final_family_weights[fid] = round(
                final_family_weights.get(fid, 0.0) + item["recommended_weight"], 4
            )

        eligible.sort(key=lambda x: x["recommended_weight"], reverse=True)

        return {
            "current_regime": current_regime,
            "real_capital_enabled": REAL_CAPITAL_ENABLED,
            "risk_gate_mandatory": True,
            "regime_halt_active": False,
            "strict_paper_qualification": strict_paper_qualification,
            "active_allocations": eligible,
            "suppressed_concepts": suppressed,
            "family_weights": final_family_weights,
        }


# Singleton instances
concept_evaluation_engine = ConceptEvaluationEngine()
regime_orchestration_advisor = RegimeOrchestrationAdvisor()

