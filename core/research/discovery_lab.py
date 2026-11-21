"""core/research/discovery_lab.py — Unified Historical Strategy Discovery Lab.

Milestone 75 Institutional Research & Falsification Engine:
1. Reusable hypothesis abstractions: HypothesisSpec and BaseHypothesis.
2. FailureMemory pre-check gate enforcing Invariant 7 (rejects duplicate previously falsified families).
3. 3-Regime institutional execution & cost stress testing:
   - Regime 1: Baseline Causal (20 bps roundtrip fee + actual 8h funding, open[t+1] fill).
   - Regime 2: 2x Friction Stress (40 bps roundtrip fee + actual 8h funding, open[t+1] fill).
   - Regime 3: 1-Bar Execution Delay Stress (20 bps roundtrip fee + actual 8h funding, open[t+2] fill).
4. Append-only trial ledger (research/discovery_trial_ledger.json) tracking cumulative multiple-testing trials (M_cum).
5. Dynamic CP-2 6-hurdle evaluation and honest epistemic verdicts.
6. Permanent governance invariants: REAL_CAPITAL_ENABLED = False, CAPITAL_MODE = "TIER_0_PAPER".
"""

from __future__ import annotations

import json
import logging
import math
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.autonomous_research.failure_memory import FailureMemoryEngine  # noqa: E402
from core.quantitative_validation.metrics import calculate_deflated_sharpe_ratio  # noqa: E402
from data.store import CandleStore  # noqa: E402
from scripts.research.run_m65_risk_parity_and_stress_test import (  # noqa: E402
    calculate_continuous_mtm_metrics,
    run_cpcv_analysis,
)

logger = logging.getLogger("cbt.research.discovery_lab")

# Non-negotiable Institutional Governance Invariants
REAL_CAPITAL_ENABLED: bool = False
CAPITAL_MODE: str = "TIER_0_PAPER"
LEDGER_PATH = ROOT_DIR / "research" / "discovery_trial_ledger.json"
BASELINE_M_CUM = 18  # Prior M63 (4) + M64 (4) + M65 (4) + M67 (4) + M72 (2) = 18


class DuplicateFalsifiedHypothesisError(Exception):
    """Raised when a candidate hypothesis duplicates a previously falsified family."""


class NumpyJSONEncoder(json.JSONEncoder):
    """Encodes numpy/pandas types cleanly for JSON serialization."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp, datetime)):
            return obj.isoformat()
        return super().default(obj)


@dataclass
class HypothesisSpec:
    """Immutable metadata and configuration of a research hypothesis."""

    hypothesis_id: str
    name: str
    family: str
    direction_mode: str  # "LONG_ONLY" | "SHORT_ONLY" | "MARKET_NEUTRAL_RV"
    universe: list[str]
    timeframe: str
    parameters: dict[str, Any]
    economic_rationale: str
    distinct_novelty_rationale: str = ""


class BaseHypothesis(ABC):
    """Abstract interface for all causal research hypotheses."""

    @abstractmethod
    def spec(self) -> HypothesisSpec:
        """Returns the immutable specification of this hypothesis."""

    def generate_target_weights(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> dict[str, float]:
        """Generates target portfolio weights strictly using information <= bar_idx."""
        return {}

    def evaluate_trade_intents(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generates discrete trade intents (entries/exits) strictly using information <= bar_idx."""
        return []

    def check_intrabar_exit(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        position: dict[str, Any],
    ) -> tuple[bool, float, str]:
        """Checks intrabar SL/TP hits. Enforces worst-case SL-first tie breaker."""
        return False, 0.0, ""


class TrialLedgerManager:
    """Manages the append-only research trial ledger and cumulative trial tracking."""

    def __init__(self, ledger_path: Path = LEDGER_PATH):
        self.ledger_path = ledger_path

    def load_ledger(self) -> dict[str, Any]:
        """Loads or initializes the append-only discovery trial ledger."""
        if not self.ledger_path.exists():
            initial_ledger = {
                "ledger_version": "1.0.0",
                "baseline_trials": BASELINE_M_CUM,
                "cumulative_trials_count": BASELINE_M_CUM,
                "last_updated_utc": datetime.now(UTC).isoformat(),
                "trials": [],
            }
            self.save_ledger(initial_ledger)
            return initial_ledger

        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read trial ledger at {self.ledger_path}: {e}")
            raise

    def save_ledger(self, ledger_data: dict[str, Any]) -> None:
        """Persists the updated ledger to disk atomically."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.ledger_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(ledger_data, f, indent=2, cls=NumpyJSONEncoder)
        temp_path.replace(self.ledger_path)

    def get_current_m_cum(self) -> int:
        """Returns current M_cum including all recorded trials."""
        ledger = self.load_ledger()
        trials_count = len(ledger.get("trials", []))
        return int(ledger.get("baseline_trials", BASELINE_M_CUM) + trials_count)

    def record_trial(self, trial_entry: dict[str, Any]) -> int:
        """Appends a new trial record to the ledger and increments cumulative trials count."""
        ledger = self.load_ledger()
        current_m_cum = self.get_current_m_cum()
        next_m_cum = current_m_cum + 1

        trial_entry["m_cum"] = next_m_cum
        trial_entry["trial_number"] = next_m_cum
        trial_entry["recorded_at_utc"] = datetime.now(UTC).isoformat()

        ledger.setdefault("trials", []).append(trial_entry)
        ledger["cumulative_trials_count"] = next_m_cum
        ledger["last_updated_utc"] = datetime.now(UTC).isoformat()

        self.save_ledger(ledger)
        logger.info(f"Recorded discovery trial {trial_entry.get('hypothesis_id')} at M_cum = {next_m_cum}")
        return next_m_cum


def load_discovery_data(root_dir: Path = ROOT_DIR) -> dict[str, Any]:
    """Loads 4h perpetual candle universe and causally aligned 1h derivatives metrics."""
    store = CandleStore(root_dir / "data" / "store")
    all_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"]
    crypto_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # 1. Load 4h candles
    dfs: dict[str, pd.DataFrame] = {}
    for s in all_symbols:
        df = store.read("binance", "perp", s, "4h")
        if df.empty:
            df = store.read("binance", "spot", s, "4h")
        if df.empty:
            raise FileNotFoundError(f"Missing 4h candle data for {s}")
        dfs[s] = df

    # Find common timestamps
    common_ts = set(dfs["BTCUSDT"]["ts"])
    for s in all_symbols[1:]:
        common_ts = common_ts.intersection(dfs[s]["ts"])
    sorted_ts = np.array(sorted(list(common_ts)), dtype=np.int64)

    dfs_aligned = {
        s: dfs[s][dfs[s]["ts"].isin(sorted_ts)].sort_values("ts").reset_index(drop=True)
        for s in all_symbols
    }

    # 2. Ingest derivatives expanded dataset (1h)
    deriv_path = root_dir / "data" / "research" / "datasets" / "derivatives_expanded_2022_2026.parquet"
    if not deriv_path.exists():
        raise FileNotFoundError(f"Missing derivatives dataset at {deriv_path}")

    df_deriv = pd.read_parquet(deriv_path)
    deriv_by_symbol: dict[str, dict[str, np.ndarray]] = {}

    for sym in crypto_symbols:
        sub = df_deriv[df_deriv["symbol"] == sym].sort_values("ts").reset_index(drop=True)
        sub["bar_4h_ts"] = (sub["ts"] // (4 * 3600 * 1000)) * (4 * 3600 * 1000)

        agg = (
            sub.groupby("bar_4h_ts")
            .agg({
                "funding_rate": "last",
                "oi_pct_chg_24h": "last",
                "open_interest": "last",
            })
            .reset_index()
        )

        df_aligned = pd.DataFrame({"bar_4h_ts": sorted_ts})
        df_merged = pd.merge(df_aligned, agg, on="bar_4h_ts", how="left")
        df_merged["funding_rate"] = df_merged["funding_rate"].ffill(limit=2).fillna(0.0)
        df_merged["oi_pct_chg_24h"] = df_merged["oi_pct_chg_24h"].ffill(limit=2).fillna(0.0)

        f_rate = df_merged["funding_rate"].values
        oi_chg = df_merged["oi_pct_chg_24h"].values
        f_7d_mean = pd.Series(f_rate).rolling(42).mean().shift(1).fillna(0.0).values

        deriv_by_symbol[sym] = {
            "funding_rate": f_rate,
            "oi_pct_chg_24h": oi_chg,
            "f_7d_mean": f_7d_mean,
        }

    return {
        "all_symbols": all_symbols,
        "crypto_symbols": crypto_symbols,
        "sorted_ts": sorted_ts,
        "dfs_aligned": dfs_aligned,
        "deriv_by_symbol": deriv_by_symbol,
    }


def compute_standard_indicators(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Computes standard point-in-time indicators (EMA200, ATR14, Bollinger Bandwidth, RSI14)."""
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    opens = df["open"].values
    ts_vals = df["ts"].values

    # True Range & ATR-14
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])),
    )
    tr = np.insert(tr, 0, highs[0] - lows[0])
    atr = pd.Series(tr).rolling(14).mean().values

    # EMAs: 200, 50, 20
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values
    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values
    ema20 = pd.Series(closes).ewm(span=20, adjust=False).mean().values

    # Bollinger Bands (20-bar, 2-std) and Bandwidth
    sma20 = pd.Series(closes).rolling(20).mean().values
    std20 = pd.Series(closes).rolling(20).std(ddof=1).values
    bb_upper = sma20 + 2.0 * std20
    bb_lower = sma20 - 2.0 * std20
    bb_width = np.where(sma20 > 1e-6, (bb_upper - bb_lower) / sma20, 0.0)
    # 20th percentile of bb_width over past 120 bars, shifted by 1 (strictly prior to bar t)
    bb_width_q20_120 = pd.Series(bb_width).rolling(120).quantile(0.20).shift(1).fillna(0.0).values

    # 20-bar high breakout channel (strictly past data)
    donch_h20 = pd.Series(highs).rolling(20).max().shift(1).values
    # 12-bar low trailing stop channel (strictly past data)
    donch_l12 = pd.Series(lows).rolling(12).min().shift(1).values

    # RSI-14
    diff = np.diff(closes)
    diff = np.insert(diff, 0, 0.0)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    avg_gain = pd.Series(gains).rolling(14).mean().values
    avg_loss = pd.Series(losses).rolling(14).mean().values
    rs = np.where(avg_loss > 1e-9, avg_gain / avg_loss, 10.0)
    rsi14 = 100.0 - (100.0 / (1.0 + rs))

    # 20-day annualized realized volatility (120 4h bars)
    log_rets = np.diff(np.log(np.maximum(closes, 1e-6)))
    log_rets = np.insert(log_rets, 0, 0.0)
    vol_20d = pd.Series(log_rets).rolling(120).std(ddof=1).values * math.sqrt(2190.0)
    vol_20d = np.nan_to_num(vol_20d, nan=0.50)

    return {
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "ts": ts_vals,
        "atr": atr,
        "ema200": ema200,
        "ema50": ema50,
        "ema20": ema20,
        "bb_width": bb_width,
        "bb_width_q20_120": bb_width_q20_120,
        "donch_h20": donch_h20,
        "donch_l12": donch_l12,
        "rsi14": rsi14,
        "vol_20d": vol_20d,
    }


def compute_stress_resistance_verdict(
    stress_matrix: dict[str, Any] | None = None,
    *,
    friction_sharpe: float | None = None,
    friction_return: float | None = None,
    delay_sharpe: float | None = None,
    delay_return: float | None = None,
    max_gross_exposure: float = 1.0,
) -> str:
    """Computes strict institutional stress resistance verdict.

    SURVIVES STRESS requires:
    1. oos_return_pct > 0.0 AND oos_sharpe > 0.0 for Regime 2 (2x Friction Stress).
    2. oos_return_pct > 0.0 AND oos_sharpe > 0.0 for Regime 3 (1-Bar Delay Stress).
    3. max_gross_exposure <= 1.0001.
    Any non-positive return (e.g. -54.49%), non-positive Sharpe, or leverage breach returns 'FAILS STRESS'.
    """
    f_sh = friction_sharpe
    f_ret = friction_return
    d_sh = delay_sharpe
    d_ret = delay_return

    if stress_matrix is not None:
        r2_oos = stress_matrix.get("regime_2_friction_stress", {}).get("sealed_oos", {})
        r3_oos = stress_matrix.get("regime_3_delay_stress", {}).get("sealed_oos", {})
        if f_sh is None:
            f_sh = float(r2_oos.get("daily_mtm_sharpe", 0.0))
        if f_ret is None:
            f_ret = float(r2_oos.get("total_return_pct", 0.0))
        if d_sh is None:
            d_sh = float(r3_oos.get("daily_mtm_sharpe", 0.0))
        if d_ret is None:
            d_ret = float(r3_oos.get("total_return_pct", 0.0))

    f_sh = 0.0 if f_sh is None else f_sh
    f_ret = 0.0 if f_ret is None else f_ret
    d_sh = 0.0 if d_sh is None else d_sh
    d_ret = 0.0 if d_ret is None else d_ret

    survives = (
        (f_sh > 0.0)
        and (f_ret > 0.0)
        and (d_sh > 0.0)
        and (d_ret > 0.0)
        and (max_gross_exposure <= 1.0001)
    )
    return "SURVIVES STRESS" if survives else "FAILS STRESS"


class CausalDiscoveryEngine:
    """Institutional Causal Strategy Discovery Engine with 3-regime stress simulation."""

    def __init__(self, data_bundle: dict[str, Any] | None = None, ledger_manager: TrialLedgerManager | None = None):
        self.data_bundle = data_bundle or load_discovery_data()
        self.ledger_manager = ledger_manager or TrialLedgerManager()
        self.failure_engine = FailureMemoryEngine()

        # Precalculate standard indicators for all symbols
        self.indicators = {
            s: compute_standard_indicators(self.data_bundle["dfs_aligned"][s])
            for s in self.data_bundle["all_symbols"]
        }
        self.data_bundle["indicators"] = self.indicators

    def check_failure_memory_pre_gate(self, spec: HypothesisSpec) -> None:
        """Pre-Gate 1: Checks failure archive and rejects duplicate failed families."""
        is_dup, fail_rec, reason = self.failure_engine.check_prior_failures(
            hypothesis_text=f"{spec.name} {spec.family} {spec.economic_rationale}",
            target_symbol=",".join(spec.universe),
            timeframe=spec.timeframe,
            parameters=spec.parameters,
        )
        if is_dup and not spec.distinct_novelty_rationale:
            fail_id = fail_rec.failure_id if fail_rec else "UNKNOWN"
            msg = (
                f"[PRE-GATE 1 REJECTED] Hypothesis '{spec.hypothesis_id}' duplicates previously falsified "
                f"research family ({fail_id}): {reason}"
            )
            logger.warning(msg)
            raise DuplicateFalsifiedHypothesisError(msg)

    def run_single_regime_simulation(
        self,
        hypothesis: BaseHypothesis,
        friction_bps: float = 20.0,
        exec_delay_bars: int = 1,
    ) -> dict[str, Any]:
        """
        Executes causal point-in-time simulation under specific execution and friction regime.
        - friction_bps: total roundtrip fee in bps (e.g. 20 bps = 10 bps per fill).
        - exec_delay_bars: 1 for next bar open[t+1], 2 for 1-bar delay open[t+2].
        """
        sorted_ts = self.data_bundle["sorted_ts"]
        n_bars = len(sorted_ts)
        init_capital = 10000.0

        cash = init_capital
        # Active positions: symbol -> dict(units, entry_price, entry_bar, entry_ts, sl, tp, max_hold, is_short)
        positions: dict[str, dict[str, Any]] = {}
        pending_orders: dict[int, list[dict[str, Any]]] = {}

        equity_series = np.zeros(n_bars)
        gross_exposure_series = np.zeros(n_bars)
        trades_closed: list[dict[str, Any]] = []

        half_fee_rate = (friction_bps / 10000.0) / 2.0
        start_bar = 200  # Warmup for 200 EMA & 120 vol

        state: dict[str, Any] = {
            "cash": cash,
            "positions": positions,
            "current_equity": init_capital,
            "prev_weights": {},
        }

        for i in range(start_bar, n_bars):
            cur_ts = int(sorted_ts[i])
            is_funding_bar = (cur_ts % (8 * 3600 * 1000)) == 0

            # 1. Process Pending Fills at open[i]
            if i in pending_orders:
                orders = pending_orders.pop(i)
                rebal_orders = [o for o in orders if o.get("action") == "REBALANCE"]
                exit_orders = [o for o in orders if o.get("action") == "EXIT"]
                entry_orders = [o for o in orders if o.get("action") == "ENTRY"]

                # A. Handle REBALANCE orders (Phase 1: Exits/reductions, Phase 2: Entries/increases)
                for order in rebal_orders:
                    target_weights = order.get("target_weights", {})
                    # Normalize target weights if sum of abs weights > 1.0
                    sum_abs_w = sum(abs(w) for w in target_weights.values())
                    if sum_abs_w > 1.0:
                        target_weights = {k: v / sum_abs_w for k, v in target_weights.items()}

                    cur_open_px = {s: float(self.indicators[s]["opens"][i]) for s in self.data_bundle["all_symbols"]}
                    cur_nav = max(
                        cash + sum(
                            (p["units"] * cur_open_px[s] if not p["is_short"]
                             else (p["entry_price"] - cur_open_px[s]) * p["units"])
                            for s, p in positions.items()
                        ),
                        10.0,
                    )

                    target_plans = {}
                    for s in self.data_bundle["all_symbols"]:
                        t_w = target_weights.get(s, 0.0)
                        target_plans[s] = {
                            "notional": abs(t_w) * cur_nav,
                            "is_short": t_w < 0.0,
                        }

                    # Phase 1: EXITS and REDUCTIONS executed FIRST to free gross exposure
                    for s in list(positions.keys()):
                        pos = positions[s]
                        op_s = cur_open_px[s]
                        plan = target_plans.get(s, {"notional": 0.0, "is_short": False})
                        curr_notional = pos["units"] * op_s

                        if plan["notional"] < 10.0 or pos["is_short"] != plan["is_short"]:
                            del positions[s]
                            fee = curr_notional * half_fee_rate
                            if not pos["is_short"]:
                                cash += (curr_notional - fee)
                                pnl = (op_s - pos["entry_price"]) * pos["units"] - (fee + pos["units"] * pos["entry_price"] * half_fee_rate)
                            else:
                                pnl = (pos["entry_price"] - op_s) * pos["units"] - (fee + pos["units"] * pos["entry_price"] * half_fee_rate)
                                cash += pnl
                            trades_closed.append({
                                "symbol": s,
                                "entry_bar": pos["entry_bar"],
                                "exit_bar": i,
                                "entry_price": pos["entry_price"],
                                "exit_price": op_s,
                                "pnl": pnl,
                                "r_mult": 0.0,
                                "reason": "REBALANCE_EXIT",
                                "is_short": pos["is_short"],
                            })
                        elif curr_notional > plan["notional"] + 10.0:
                            reduce_notional = curr_notional - plan["notional"]
                            reduce_units = reduce_notional / op_s
                            fee = reduce_notional * half_fee_rate
                            if not pos["is_short"]:
                                cash += (reduce_notional - fee)
                                pnl = (op_s - pos["entry_price"]) * reduce_units - (fee + reduce_units * pos["entry_price"] * half_fee_rate)
                            else:
                                pnl = (pos["entry_price"] - op_s) * reduce_units - (fee + reduce_units * pos["entry_price"] * half_fee_rate)
                                cash += pnl
                            pos["units"] -= reduce_units

                    # Phase 2: ENTRIES and INCREASES executed AFTER exits
                    for s, plan in target_plans.items():
                        if plan["notional"] < 10.0:
                            continue
                        op_s = cur_open_px[s]
                        cur_gross = sum(p["units"] * cur_open_px[k] for k, p in positions.items())
                        cur_eq = max(
                            cash + sum(
                                (p["units"] * cur_open_px[k] if not p["is_short"]
                                 else (p["entry_price"] - cur_open_px[k]) * p["units"])
                                for k, p in positions.items()
                            ),
                            10.0,
                        )
                        avail_gross = max(0.0, 1.0 - (cur_gross / cur_eq)) * cur_eq

                        if s not in positions:
                            eff_notional = min(plan["notional"], avail_gross)
                            if not plan["is_short"]:
                                eff_notional = min(eff_notional, cash)
                            if eff_notional >= 10.0:
                                fee = eff_notional * half_fee_rate
                                units = (eff_notional - fee) / op_s
                                if not plan["is_short"]:
                                    cash -= eff_notional
                                else:
                                    cash -= fee
                                positions[s] = {
                                    "units": units,
                                    "entry_price": op_s,
                                    "entry_bar": i,
                                    "entry_ts": cur_ts,
                                    "initial_sl": 0.0,
                                    "current_sl": 0.0,
                                    "tp": 0.0,
                                    "max_hold_bars": 0,
                                    "is_short": plan["is_short"],
                                    "risk_dist": op_s * 0.02,
                                }
                        else:
                            curr_notional = positions[s]["units"] * op_s
                            if plan["notional"] > curr_notional + 10.0:
                                add_notional = min(plan["notional"] - curr_notional, avail_gross)
                                if not plan["is_short"]:
                                    add_notional = min(add_notional, cash)
                                if add_notional >= 10.0:
                                    fee = add_notional * half_fee_rate
                                    add_units = (add_notional - fee) / op_s
                                    if not plan["is_short"]:
                                        cash -= add_notional
                                    else:
                                        cash -= fee
                                    total_units = positions[s]["units"] + add_units
                                    positions[s]["entry_price"] = (
                                        (positions[s]["entry_price"] * positions[s]["units"] + op_s * add_units)
                                        / total_units
                                    )
                                    positions[s]["units"] = total_units

                # B. Handle discrete trade-based EXIT orders FIRST
                for order in exit_orders:
                    sym = order["symbol"]
                    if sym in positions:
                        pos = positions.pop(sym)
                        op = float(self.indicators[sym]["opens"][i])
                        is_short = pos["is_short"]
                        notional = pos["units"] * op
                        fee = notional * half_fee_rate
                        if not is_short:
                            cash += (notional - fee)
                            pnl = (op - pos["entry_price"]) * pos["units"] - (fee + pos["units"] * pos["entry_price"] * half_fee_rate)
                        else:
                            pnl = (pos["entry_price"] - op) * pos["units"] - (fee + pos["units"] * pos["entry_price"] * half_fee_rate)
                            cash += pnl

                        risk_unit = pos.get("risk_dist", max(pos["entry_price"] * 0.01, 1e-4))
                        r_mult = pnl / (pos["units"] * risk_unit) if risk_unit > 0 else 0.0
                        trades_closed.append({
                            "symbol": sym,
                            "entry_bar": pos["entry_bar"],
                            "exit_bar": i,
                            "entry_price": pos["entry_price"],
                            "exit_price": op,
                            "pnl": pnl,
                            "r_mult": r_mult,
                            "reason": order.get("reason", "SIGNAL_EXIT"),
                            "is_short": is_short,
                        })

                # C. Handle discrete trade-based ENTRY orders with Hard Zero-Leverage Clamp
                for order in entry_orders:
                    sym = order["symbol"]
                    if sym in positions:
                        continue
                    op = float(self.indicators[sym]["opens"][i])
                    is_short = bool(order.get("is_short", False))

                    cur_open_px = {s: float(self.indicators[s]["opens"][i]) for s in self.data_bundle["all_symbols"]}
                    cur_gross_notional = sum(p["units"] * cur_open_px[s] for s, p in positions.items())
                    cur_equity = max(
                        cash + sum(
                            (p["units"] * cur_open_px[s] if not p["is_short"]
                             else (p["entry_price"] - cur_open_px[s]) * p["units"])
                            for s, p in positions.items()
                        ),
                        10.0,
                    )
                    cur_gross_exp = cur_gross_notional / cur_equity if cur_equity > 0 else 0.0

                    if cur_gross_exp >= 1.0:
                        continue

                    remaining_capacity = max(0.0, 1.0 - cur_gross_exp) * cur_equity
                    requested_notional = order["target_notional"]
                    capped_notional = min(requested_notional, remaining_capacity)
                    if not is_short:
                        capped_notional = min(capped_notional, cash)

                    if capped_notional > 10.0:
                        fee = capped_notional * half_fee_rate
                        units = (capped_notional - fee) / op
                        if not is_short:
                            cash -= capped_notional
                        else:
                            cash -= fee
                        positions[sym] = {
                            "units": units,
                            "entry_price": op,
                            "entry_bar": i,
                            "entry_ts": cur_ts,
                            "initial_sl": order.get("initial_sl", 0.0),
                            "current_sl": order.get("initial_sl", 0.0),
                            "tp": order.get("tp", 0.0),
                            "max_hold_bars": order.get("max_hold_bars", 0),
                            "is_short": is_short,
                            "risk_dist": order.get("risk_dist", max(op * 0.01, 1e-4)),
                        }

            # 2. Check Intrabar SL / TP / Time-stops during bar i
            for sym in list(positions.keys()):
                pos = positions[sym]
                hi = float(self.indicators[sym]["highs"][i])
                lo = float(self.indicators[sym]["lows"][i])
                cl = float(self.indicators[sym]["closes"][i])
                is_short = pos["is_short"]

                # Delegate to hypothesis custom intrabar exit check if defined
                exited, exit_px, reason = hypothesis.check_intrabar_exit(self.data_bundle, i, pos)

                # Default intrabar check if hypothesis did not trigger
                if not exited:
                    if not is_short:
                        # Long Stop Loss hit
                        sl_hit = (pos["current_sl"] > 0.0) and (lo <= pos["current_sl"])
                        # Long Take Profit hit
                        tp_hit = (pos["tp"] > 0.0) and (hi >= pos["tp"])

                        # Conservative tie-breaker: SL hit first
                        if sl_hit:
                            exited = True
                            exit_px = min(pos["current_sl"], float(self.indicators[sym]["opens"][i]))
                            reason = "STOP_LOSS"
                        elif tp_hit:
                            exited = True
                            exit_px = pos["tp"]
                            reason = "TAKE_PROFIT"
                        elif pos["max_hold_bars"] > 0 and (i - pos["entry_bar"] >= pos["max_hold_bars"]):
                            exited = True
                            exit_px = cl
                            reason = "TIME_STOP"
                    else:
                        # Short Stop Loss hit
                        sl_hit = (pos["current_sl"] > 0.0) and (hi >= pos["current_sl"])
                        tp_hit = (pos["tp"] > 0.0) and (lo <= pos["tp"])

                        if sl_hit:
                            exited = True
                            exit_px = max(pos["current_sl"], float(self.indicators[sym]["opens"][i]))
                            reason = "STOP_LOSS"
                        elif tp_hit:
                            exited = True
                            exit_px = pos["tp"]
                            reason = "TAKE_PROFIT"
                        elif pos["max_hold_bars"] > 0 and (i - pos["entry_bar"] >= pos["max_hold_bars"]):
                            exited = True
                            exit_px = cl
                            reason = "TIME_STOP"

                if exited:
                    pos = positions.pop(sym)
                    notional = pos["units"] * exit_px
                    fee = notional * half_fee_rate
                    if not is_short:
                        cash += (notional - fee)
                        pnl = (exit_px - pos["entry_price"]) * pos["units"] - (fee + pos["units"] * pos["entry_price"] * half_fee_rate)
                    else:
                        pnl = (pos["entry_price"] - exit_px) * pos["units"] - (fee + pos["units"] * pos["entry_price"] * half_fee_rate)
                        cash += pnl

                    risk_unit = pos.get("risk_dist", max(pos["entry_price"] * 0.01, 1e-4))
                    r_mult = pnl / (pos["units"] * risk_unit) if risk_unit > 0 else 0.0
                    trades_closed.append({
                        "symbol": sym,
                        "entry_bar": pos["entry_bar"],
                        "exit_bar": i,
                        "entry_price": pos["entry_price"],
                        "exit_price": exit_px,
                        "pnl": pnl,
                        "r_mult": r_mult,
                        "reason": reason,
                        "is_short": is_short,
                    })

            # 3. Apply Real 8h Funding Settlement
            if is_funding_bar:
                for sym, pos in positions.items():
                    if sym in self.data_bundle["crypto_symbols"]:
                        fr = float(self.data_bundle["deriv_by_symbol"][sym]["funding_rate"][i])
                        cl_px = float(self.indicators[sym]["closes"][i])
                        notional = pos["units"] * cl_px
                        funding_cash_flow = -notional * fr if not pos["is_short"] else notional * fr
                        cash += funding_cash_flow
                        # Unleveraged zero-borrowing constraint: settle negative cash by trimming position units
                        if not pos["is_short"] and cash < 0.0:
                            shortfall = -cash
                            trim_units = min(shortfall / cl_px, pos["units"])
                            pos["units"] -= trim_units
                            cash += trim_units * cl_px

            # 4. Mark-to-Market Portfolio Valuation at bar close
            gross_notional = sum(p["units"] * float(self.indicators[s]["closes"][i]) for s, p in positions.items())
            cur_equity = max(
                cash + sum(
                    (p["units"] * float(self.indicators[s]["closes"][i]) if not p["is_short"]
                     else (p["entry_price"] - float(self.indicators[s]["closes"][i])) * p["units"])
                    for s, p in positions.items()
                ),
                10.0,
            )

            equity_series[i] = cur_equity
            gross_exposure_series[i] = gross_notional / cur_equity if cur_equity > 0 else 0.0

            # 5. Evaluate Point-in-Time Signals at bar close i strictly <= i
            state["cash"] = cash
            state["positions"] = positions
            state["current_equity"] = cur_equity
            exec_bar = i + exec_delay_bars

            # Check target weight generation (for portfolio / pair strategies)
            weights = hypothesis.generate_target_weights(self.data_bundle, i, state)
            if weights:
                # Enforce zero leverage invariant
                gross_w = sum(abs(w) for w in weights.values())
                if gross_w > 1.0001:
                    scale = 1.0 / gross_w
                    weights = {k: v * scale for k, v in weights.items()}
                pending_orders[exec_bar] = [{
                    "symbol": "PORTFOLIO",
                    "action": "REBALANCE",
                    "target_weights": weights,
                }]

            # Check discrete trade intents (for long/short breakout/rebound strategies)
            intents = hypothesis.evaluate_trade_intents(self.data_bundle, i, state)
            for intent in intents:
                sym = intent["symbol"]
                action = intent["action"]
                if action == "ENTRY" and sym not in positions:
                    pending_orders.setdefault(exec_bar, []).append(intent)
                elif action == "EXIT" and sym in positions:
                    pending_orders.setdefault(exec_bar, []).append(intent)

        # ----------------------------------------------------------------------
        # Build Calendar-Day Mark-to-Market Time Series
        # ----------------------------------------------------------------------
        date_to_last_bar: dict[Any, int] = {}
        for idx in range(start_bar, n_bars):
            dt = datetime.fromtimestamp(sorted_ts[idx] / 1000.0, tz=UTC).date()
            date_to_last_bar[dt] = idx

        sorted_dates = sorted(date_to_last_bar.keys())
        daily_eq = np.array([equity_series[date_to_last_bar[d]] for d in sorted_dates])
        daily_ret = np.diff(daily_eq) / daily_eq[:-1]
        daily_ret = np.insert(daily_ret, 0, 0.0)
        daily_exp = np.array([gross_exposure_series[date_to_last_bar[d]] for d in sorted_dates])

        # Benchmark: Equal-weight Buy and Hold across BTC, ETH, SOL
        bnh_eq = np.zeros(len(sorted_dates))
        bnh_eq[0] = init_capital
        bnh_rets = np.zeros(len(sorted_dates))
        crypto_syms = self.data_bundle["crypto_symbols"]

        for d_idx in range(1, len(sorted_dates)):
            bar_curr = date_to_last_bar[sorted_dates[d_idx]]
            bar_prev = date_to_last_bar[sorted_dates[d_idx - 1]]
            r_bnh = np.mean([
                (float(self.indicators[s]["closes"][bar_curr]) - float(self.indicators[s]["closes"][bar_prev]))
                / float(self.indicators[s]["closes"][bar_prev])
                for s in crypto_syms
            ])
            bnh_rets[d_idx] = r_bnh
            bnh_eq[d_idx] = bnh_eq[d_idx - 1] * (1.0 + r_bnh)

        df_daily = pd.DataFrame(
            {
                "date": pd.to_datetime(sorted_dates),
                "equity": daily_eq,
                "daily_ret": daily_ret,
                "gross_exposure": daily_exp,
                "bnh_equity": bnh_eq,
                "bnh_ret": bnh_rets,
            }
        ).set_index("date")

        return {
            "df_daily": df_daily,
            "trades": trades_closed,
            "max_gross_exposure": float(np.max(daily_exp)),
            "final_equity": float(daily_eq[-1]),
        }

    def evaluate_hypothesis(self, hypothesis: BaseHypothesis) -> dict[str, Any]:
        """
        Full Institutional Discovery Evaluation for a candidate hypothesis:
        1. Pre-Gate 1: Failure memory duplication check.
        2. Simulates across 3 stress regimes.
        3. Computes Train, Val, Sealed OOS metrics and CPCV.
        4. Evaluates all 6 CP-2 boolean hurdles.
        5. Computes DSR under current M_cum.
        6. Appends trial to ledger and returns structured audit results.
        """
        spec = hypothesis.spec()
        logger.info(f"=== EVALUATING HYPOTHESIS: {spec.hypothesis_id} ({spec.name}) ===")

        # 1. Failure Memory Pre-Gate
        self.check_failure_memory_pre_gate(spec)

        # 2. Simulate 3 Regimes
        logger.info("Running Regime 1: Baseline Causal (20 bps roundtrip + 8h funding, open[t+1])...")
        res_baseline = self.run_single_regime_simulation(hypothesis, friction_bps=20.0, exec_delay_bars=1)

        logger.info("Running Regime 2: 2x Friction Stress (40 bps roundtrip + 8h funding, open[t+1])...")
        res_friction = self.run_single_regime_simulation(hypothesis, friction_bps=40.0, exec_delay_bars=1)

        logger.info("Running Regime 3: 1-Bar Delay Stress (20 bps roundtrip + 8h funding, open[t+2])...")
        res_delay = self.run_single_regime_simulation(hypothesis, friction_bps=20.0, exec_delay_bars=2)

        df_daily = res_baseline["df_daily"]
        n_days = len(df_daily)
        d_train_end = int(n_days * 0.50)
        d_val_end = int(n_days * 0.75)

        splits_data = {
            "train": df_daily.iloc[:d_train_end],
            "val": df_daily.iloc[d_train_end:d_val_end],
            "sealed_oos": df_daily.iloc[d_val_end:],
            "combined_walk_forward": df_daily.iloc[d_train_end:],
            "full_period": df_daily,
        }

        splits_scorecard = {}
        for sp_name, sp_df in splits_data.items():
            splits_scorecard[sp_name] = {
                "days": len(sp_df),
                "strategy": calculate_continuous_mtm_metrics(sp_df["daily_ret"].values, sp_df["equity"].values),
                "bnh": calculate_continuous_mtm_metrics(sp_df["bnh_ret"].values, sp_df["bnh_equity"].values),
            }

        # Year-by-Year Breakdown (2022-2026)
        years = [y for y in sorted(list(set(df_daily.index.year))) if y >= 2022]
        yearly_benchmark: dict[int, dict[str, Any]] = {}
        for yr in years:
            yr_df = df_daily[df_daily.index.year == yr]
            if len(yr_df) > 5:
                yearly_benchmark[yr] = {
                    "days": len(yr_df),
                    "strategy": calculate_continuous_mtm_metrics(yr_df["daily_ret"].values, yr_df["equity"].values),
                    "bnh": calculate_continuous_mtm_metrics(yr_df["bnh_ret"].values, yr_df["bnh_equity"].values),
                }

        # Trade metrics
        trades = res_baseline["trades"]
        n_trades = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        pf = (gross_profit / gross_loss) if gross_loss > 1e-4 else (999.0 if wins else 0.0)
        r_mults = [t.get("r_mult", 0.0) for t in trades]
        net_expectancy_r = float(np.mean(r_mults)) if r_mults else 0.0

        # Trade list splits
        val_start_date = splits_data["sealed_oos"].index[0]
        oos_trades = [
            t for t in trades
            if datetime.fromtimestamp(self.data_bundle["sorted_ts"][t["entry_bar"]] / 1000.0, tz=UTC).date()
            >= val_start_date.date()
        ]
        oos_r_mults = [t.get("r_mult", 0.0) for t in oos_trades]
        oos_net_expectancy_r = float(np.mean(oos_r_mults)) if oos_r_mults else 0.0

        # Stress Matrix Comparison
        stress_matrix = {
            "regime_1_baseline": {
                "description": "Baseline Causal (20 bps roundtrip + 8h funding, open[t+1])",
                "sealed_oos": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"].iloc[d_val_end:]["daily_ret"].values,
                    res_baseline["df_daily"].iloc[d_val_end:]["equity"].values,
                ),
                "full_period": calculate_continuous_mtm_metrics(
                    res_baseline["df_daily"]["daily_ret"].values,
                    res_baseline["df_daily"]["equity"].values,
                ),
            },
            "regime_2_friction_stress": {
                "description": "2x Friction Stress (40 bps roundtrip + 8h funding, open[t+1])",
                "sealed_oos": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"].iloc[d_val_end:]["daily_ret"].values,
                    res_friction["df_daily"].iloc[d_val_end:]["equity"].values,
                ),
                "full_period": calculate_continuous_mtm_metrics(
                    res_friction["df_daily"]["daily_ret"].values,
                    res_friction["df_daily"]["equity"].values,
                ),
            },
            "regime_3_delay_stress": {
                "description": "1-Bar Delay Stress (20 bps roundtrip + 8h funding, open[t+2])",
                "sealed_oos": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"].iloc[d_val_end:]["daily_ret"].values,
                    res_delay["df_daily"].iloc[d_val_end:]["equity"].values,
                ),
                "full_period": calculate_continuous_mtm_metrics(
                    res_delay["df_daily"]["daily_ret"].values,
                    res_delay["df_daily"]["equity"].values,
                ),
            },
        }

        # 3. Multiple Testing & CPCV Rigor
        current_m_cum = self.ledger_manager.get_current_m_cum() + 1  # Trial index
        oos_rets = splits_data["sealed_oos"]["daily_ret"].values.tolist()
        _, dsr_oos, pval_oos = calculate_deflated_sharpe_ratio(
            oos_rets,
            estimated_trials=current_m_cum,
            benchmark_sharpe=0.0,
        )

        comb_rets = splits_data["combined_walk_forward"]["daily_ret"].values.tolist()
        _, dsr_comb, pval_comb = calculate_deflated_sharpe_ratio(
            comb_rets,
            estimated_trials=current_m_cum,
            benchmark_sharpe=0.0,
        )

        cpcv_res = run_cpcv_analysis(df_daily["daily_ret"], n_partitions=6, k_test_groups=2)
        cpcv_median_sharpe = float(cpcv_res.get("median_sharpe", 0.0))

        # 4. Dynamic CP-2 6-Hurdles Evaluation
        strat_oos = splits_scorecard["sealed_oos"]["strategy"]
        bnh_oos = splits_scorecard["sealed_oos"]["bnh"]

        # Hurdle 1: Alpha & Expectancy
        h1_passed = bool(
            (strat_oos["total_return_pct"] > bnh_oos["total_return_pct"])
            and (oos_net_expectancy_r > 0 or strat_oos["total_return_pct"] > 0)
        )
        # Hurdle 2: Daily MtM Sharpe >= 1.00 on OOS
        h2_passed = bool(strat_oos["daily_mtm_sharpe"] >= 1.00)
        # Hurdle 3: Cumulative DSR >= 0.95 under M_cum
        h3_passed = bool(dsr_oos >= 0.95 or dsr_comb >= 0.95)
        # Hurdle 4: 2022 Bear Market Survival (Max DD < Half of BnH DD)
        bnh_2022_dd = yearly_benchmark.get(2022, {}).get("bnh", {}).get("max_drawdown_pct", 65.0)
        strat_2022_dd = yearly_benchmark.get(2022, {}).get("strategy", {}).get("max_drawdown_pct", 100.0)
        half_bnh_dd = round(bnh_2022_dd / 2.0, 2)
        h4_passed = bool(strat_2022_dd < half_bnh_dd)
        # Hurdle 5: Sample Size Integrity (>= 100 trades or rebalance steps AND >= 500 OOS days)
        # If market neutral rebalance, count active allocation days
        sample_count = n_trades if n_trades > 0 else int(np.sum(res_baseline["df_daily"]["gross_exposure"] > 0.05))
        h5_passed = bool(sample_count >= 100 and splits_scorecard["sealed_oos"]["days"] >= 500)
        # Hurdle 6: Zero Leverage Invariant (Gross exposure <= 1.0001)
        h6_passed = bool(res_baseline["max_gross_exposure"] <= 1.0001)

        hurdles = {
            "hurdle_1_alpha_and_expectancy": {
                "name": "Alpha & Positive Expectancy",
                "requirement": "OOS Return > BnH Return AND Positive Expectancy",
                "passed": h1_passed,
                "details": f"OOS Ret: {strat_oos['total_return_pct']:+.2f}% vs BnH: {bnh_oos['total_return_pct']:+.2f}%, Net E[R]: {oos_net_expectancy_r:+.4f}R",
            },
            "hurdle_2_daily_mtm_sharpe_ge_1_0": {
                "name": "Daily MtM Sharpe >= 1.00 on OOS",
                "requirement": "Sealed OOS Sharpe >= 1.00",
                "passed": h2_passed,
                "details": f"Sealed OOS Sharpe: {strat_oos['daily_mtm_sharpe']:.4f} (req >= 1.00)",
            },
            "hurdle_3_cumulative_dsr_ge_0_95": {
                "name": f"Cumulative DSR >= 0.95 (M_cum = {current_m_cum})",
                "requirement": f"DSR(M_cum={current_m_cum}) >= 0.95",
                "passed": h3_passed,
                "details": f"OOS DSR: {dsr_oos:.4f} (p={pval_oos:.4f}), Combined DSR: {dsr_comb:.4f} (p={pval_comb:.4f})",
            },
            "hurdle_4_bear_market_survival": {
                "name": "2022 Bear Market Survival (< Half BnH DD)",
                "requirement": f"2022 Max DD < {half_bnh_dd:.2f}% (Half of BnH {bnh_2022_dd:.2f}%)",
                "passed": h4_passed,
                "details": f"2022 Max DD: Strategy = {strat_2022_dd:.2f}% vs Threshold {half_bnh_dd:.2f}%",
            },
            "hurdle_5_sample_size_integrity": {
                "name": "Sample Size Integrity",
                "requirement": "Total Trades / Allocation Bars >= 100 AND OOS Days >= 500",
                "passed": h5_passed,
                "details": f"Sample Count: {sample_count} (req >= 100), OOS Days: {splits_scorecard['sealed_oos']['days']} (req >= 500)",
            },
            "hurdle_6_zero_leverage_invariant": {
                "name": "Zero Leverage Invariant",
                "requirement": "Gross Exposure <= 1.0001 at all times",
                "passed": h6_passed,
                "details": f"Max Gross Exposure: {res_baseline['max_gross_exposure']:.4f} (req <= 1.0001)",
            },
        }

        passed_count = sum(1 for h in hurdles.values() if h["passed"])
        failed_count = len(hurdles) - passed_count

        # 5. Epistemic Verdict & Strict Stress Resistance Verification
        stress_verdict = compute_stress_resistance_verdict(
            stress_matrix=stress_matrix,
            max_gross_exposure=res_baseline["max_gross_exposure"],
        )
        stress_matrix["stress_resistance_verdict"] = stress_verdict

        friction_oos_sh = stress_matrix["regime_2_friction_stress"]["sealed_oos"]["daily_mtm_sharpe"]
        friction_oos_ret = stress_matrix["regime_2_friction_stress"]["sealed_oos"]["total_return_pct"]
        delay_oos_sh = stress_matrix["regime_3_delay_stress"]["sealed_oos"]["daily_mtm_sharpe"]
        delay_oos_ret = stress_matrix["regime_3_delay_stress"]["sealed_oos"]["total_return_pct"]

        if passed_count == 6 and stress_verdict == "SURVIVES STRESS":
            verdict = "CANDIDATE_QUALIFIED_FOR_SHADOW_PROMOTION"
            verdict_rationale = (
                f"Qualified all 6 CP-2 institutional hurdles with OOS Sharpe {strat_oos['daily_mtm_sharpe']:.2f}, "
                f"surviving 2x friction (Sharpe {friction_oos_sh:.2f}) and 1-bar delay (Sharpe {delay_oos_sh:.2f})."
            )
        else:
            verdict = "FALSIFIED"
            reasons = []
            if passed_count < 6:
                reasons.append(f"Failed {failed_count}/6 CP-2 hurdles")
            if friction_oos_sh <= 0 or friction_oos_ret <= 0:
                reasons.append(f"Fails 2x friction stress (Sharpe: {friction_oos_sh:.2f}, Ret: {friction_oos_ret:+.2f}%)")
            if delay_oos_sh <= 0 or delay_oos_ret <= 0:
                reasons.append(f"Fails 1-bar delay stress (Sharpe: {delay_oos_sh:.2f}, Ret: {delay_oos_ret:+.2f}%)")
            if res_baseline["max_gross_exposure"] > 1.0001:
                reasons.append(f"Gross exposure breach ({res_baseline['max_gross_exposure']:.4f} > 1.0001)")
            verdict_rationale = "; ".join(reasons)

        result_payload = {
            "hypothesis_id": spec.hypothesis_id,
            "name": spec.name,
            "family": spec.family,
            "direction_mode": spec.direction_mode,
            "universe": spec.universe,
            "parameters": spec.parameters,
            "evaluation_timestamp_utc": datetime.now(UTC).isoformat(),
            "m_cum": current_m_cum,
            "splits_scorecard": splits_scorecard,
            "yearly_benchmark": yearly_benchmark,
            "stress_matrix": stress_matrix,
            "trade_metrics": {
                "total_trades": n_trades,
                "win_rate_pct": round(win_rate, 2),
                "profit_factor": round(pf, 4),
                "expectancy_net_r": round(net_expectancy_r, 4),
                "oos_trades": len(oos_trades),
                "oos_expectancy_net_r": round(oos_net_expectancy_r, 4),
            },
            "statistical_rigor": {
                "m_cum": current_m_cum,
                "dsr_oos": round(dsr_oos, 4),
                "pval_oos": round(pval_oos, 4),
                "dsr_comb": round(dsr_comb, 4),
                "pval_comb": round(pval_comb, 4),
                "cpcv_median_sharpe": round(cpcv_median_sharpe, 4),
            },
            "cp2_hurdles": hurdles,
            "hurdle_summary": {
                "passed_count": passed_count,
                "failed_count": failed_count,
                "summary_text": f"{passed_count}/6 PASS | {failed_count}/6 FAIL",
            },
            "epistemic_verdict": verdict,
            "verdict_rationale": verdict_rationale,
        }

        # 6. Append to Trial Ledger
        ledger_entry = {
            "hypothesis_id": spec.hypothesis_id,
            "name": spec.name,
            "family": spec.family,
            "direction_mode": spec.direction_mode,
            "train_sharpe": splits_scorecard["train"]["strategy"]["daily_mtm_sharpe"],
            "val_sharpe": splits_scorecard["val"]["strategy"]["daily_mtm_sharpe"],
            "oos_sharpe": strat_oos["daily_mtm_sharpe"],
            "oos_return_pct": strat_oos["total_return_pct"],
            "oos_max_dd_pct": strat_oos["max_drawdown_pct"],
            "cpcv_median_sharpe": round(cpcv_median_sharpe, 4),
            "dsr_oos": round(dsr_oos, 4),
            "dsr_pval": round(pval_oos, 4),
            "hurdles_passed": passed_count,
            "hurdles_total": 6,
            "stress_regimes": {
                "baseline_oos_sharpe": strat_oos["daily_mtm_sharpe"],
                "baseline_oos_return_pct": strat_oos["total_return_pct"],
                "friction_2x_oos_sharpe": friction_oos_sh,
                "friction_2x_oos_return_pct": friction_oos_ret,
                "delay_1bar_oos_sharpe": delay_oos_sh,
                "delay_1bar_oos_return_pct": delay_oos_ret,
                "stress_resistance_verdict": stress_verdict,
            },
            "verdict": verdict,
            "verdict_rationale": verdict_rationale,
        }
        self.ledger_manager.record_trial(ledger_entry)

        return result_payload


# ==============================================================================
# 3 PRE-REGISTERED ORTHOGONAL CANDIDATE HYPOTHESES (H1, H2, H3)
# ==============================================================================
class H1_VolSqueezeExpansionLong(BaseHypothesis):
    """
    Hypothesis 1: Volatility Compression -> Expansion Breakout (Long-Only).
    Entry: close[t] > EMA200[t] AND bb_width[t-1] <= q20(bb_width_120)[t-1] AND close[t] > max(high[t-20:t]).
    Sizing: 15% vol-targeted (0.01 * equity * min(0.15/vol_20d, 1.0)), max 25% notional per asset, gross <= 1.0.
    Exit: 2.5 * ATR trailing stop OR close[k] < min(low[k-12:k]) at open[k+1].
    """

    def spec(self) -> HypothesisSpec:
        return HypothesisSpec(
            hypothesis_id="H1_VOL_SQUEEZE_EXPANSION_LONG",
            name="Volatility Compression Expansion Breakout Long",
            family="Volatility Breakout & Squeeze Expansion",
            direction_mode="LONG_ONLY",
            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            timeframe="4h",
            parameters={
                "ema_trend_filter": 200,
                "bollinger_window": 20,
                "bollinger_std": 2.0,
                "compression_quantile_window": 120,
                "compression_quantile": 0.20,
                "breakout_window": 20,
                "trailing_stop_atr": 2.5,
                "donchian_exit_window": 12,
                "target_vol": 0.15,
                "max_notional_per_asset": 0.25,
                "risk_per_trade_cap": 0.01,
            },
            economic_rationale=(
                "Asset volatility regime clustering implies prolonged volatility contraction precedes large "
                "directional expansion; entering breakouts in the direction of the macro trend (EMA-200) "
                "captures convex upside while 2.5 ATR trailing stops truncate chop bleed."
            ),
            distinct_novelty_rationale=(
                "Orthogonal long-only volatility compression expansion breakout distinct from M72 shorting engine."
            ),
        )

    def evaluate_trade_intents(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        intents = []
        indicators = data_bundle["indicators"]
        universe = self.spec().universe
        cur_equity = state["current_equity"]
        cash = state["cash"]
        positions = state["positions"]

        active_notional = sum(
            p["units"] * float(indicators[s]["closes"][bar_idx]) for s, p in positions.items()
        )

        for sym in universe:
            c_now = float(indicators[sym]["closes"][bar_idx])
            ema200_now = float(indicators[sym]["ema200"][bar_idx])
            bb_w_prev = float(indicators[sym]["bb_width"][bar_idx - 1])
            bb_q20_prev = float(indicators[sym]["bb_width_q20_120"][bar_idx - 1])
            donch_h20_now = float(indicators[sym]["donch_h20"][bar_idx])
            donch_l12_now = float(indicators[sym]["donch_l12"][bar_idx])
            atr_now = float(indicators[sym]["atr"][bar_idx])
            vol_20d = float(indicators[sym]["vol_20d"][bar_idx])

            if sym in positions:
                # Update trailing stop on open position
                pos = positions[sym]
                new_sl = max(pos["current_sl"], c_now - 2.5 * atr_now)
                pos["current_sl"] = new_sl

                # Check Donchian-12 low exit at bar close
                if c_now < donch_l12_now:
                    intents.append({
                        "symbol": sym,
                        "action": "EXIT",
                        "reason": "DONCHIAN_L12_EXIT",
                    })
            else:
                # Check Entry Signal:
                # 1. Macro trend gate: close > EMA200
                # 2. Vol compression at t-1: bb_width[t-1] <= q20[t-1]
                # 3. 20-bar high breakout at t: close[t] > donch_h20[t]
                is_bull_regime = c_now > ema200_now
                was_compressed = (bb_q20_prev > 0.0) and (bb_w_prev <= bb_q20_prev)
                is_breakout = c_now > donch_h20_now

                if is_bull_regime and was_compressed and is_breakout:
                    vol_scalar = min(0.15 / max(vol_20d, 0.04), 1.0)
                    base_risk_usd = 0.01 * cur_equity * vol_scalar
                    sl_dist = max(2.5 * atr_now, 0.01 * c_now)
                    calc_notional = (base_risk_usd / sl_dist) * c_now
                    max_asset_notional = 0.25 * cur_equity
                    avail_equity = max(cur_equity - active_notional, 0.0)
                    target_notional = min(calc_notional, max_asset_notional, avail_equity, cash)

                    if target_notional > 10.0:
                        intents.append({
                            "symbol": sym,
                            "action": "ENTRY",
                            "target_notional": target_notional,
                            "initial_sl": c_now - sl_dist,
                            "risk_dist": sl_dist,
                            "is_short": False,
                        })

        return intents


class H2_CrossAssetRvPair(BaseHypothesis):
    """
    Hypothesis 2: Market-Neutral Cross-Asset Relative-Value Momentum Pair.
    Universe: BTCUSDT, ETHUSDT, SOLUSDT. Evaluated every 7 days (42 bars).
    Score: 30-day vol-adjusted momentum (ret_30d / max(vol_20d, 0.04)).
    Dispersion Gate: Active only when (max_score - min_score) >= 0.75.
    Allocation: Long top-ranked asset (+w_long), Short bottom-ranked asset (-w_short),
    inverse-vol balanced, scaled to 15% target vol, with strict gross exposure <= 1.0 (zero leverage).
    """

    def __init__(self):
        self.prev_top: str | None = None
        self.prev_bot: str | None = None

    def spec(self) -> HypothesisSpec:
        return HypothesisSpec(
            hypothesis_id="H2_CROSS_ASSET_RV_PAIR",
            name="Market-Neutral Cross-Asset Relative-Value Momentum Pair",
            family="Cross-Asset Cross-Sectional Relative Value",
            direction_mode="MARKET_NEUTRAL_RV",
            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            timeframe="4h",
            parameters={
                "rebalance_cadence_bars": 42,
                "momentum_lookback_bars": 180,
                "vol_lookback_bars": 120,
                "dispersion_threshold": 0.75,
                "target_vol": 0.15,
                "hysteresis": 0.15,
                "gross_exposure_cap": 1.0001,
            },
            economic_rationale=(
                "Cryptocurrency market beta dominates gross variance; isolating relative cross-sectional momentum "
                "via dollar-neutral pairs exploits capital rotation between leaders and laggards while neutralizing "
                "systemic market drawdowns, provided momentum dispersion is statistically wide."
            ),
            distinct_novelty_rationale=(
                "Market-neutral cross-asset relative-value momentum pair distinct from single-asset trend/shorting."
            ),
        )

    def generate_target_weights(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> dict[str, float]:
        # Evaluated on a 7-day (42 4h bars) cadence
        if (bar_idx - 200) % 42 != 0:
            return {}

        universe = self.spec().universe
        indicators = data_bundle["indicators"]

        # Compute 30-day vol-adjusted momentum scores
        scores: dict[str, float] = {}
        vols: dict[str, float] = {}
        for s in universe:
            c_now = float(indicators[s]["closes"][bar_idx])
            c_past = float(indicators[s]["closes"][bar_idx - 180])
            ret_30d = (c_now - c_past) / c_past if c_past > 0 else 0.0
            vol_20d = float(indicators[s]["vol_20d"][bar_idx])
            vols[s] = max(vol_20d, 0.04)
            scores[s] = ret_30d / vols[s]

        max_s = max(scores.values())
        min_s = min(scores.values())
        dispersion = max_s - min_s

        # Dispersion Gate: Stay flat (100% cash) if dispersion < 0.75
        if dispersion < 0.75:
            self.prev_top = None
            self.prev_bot = None
            return {s: 0.0 for s in data_bundle["all_symbols"]}

        sorted_assets = sorted(universe, key=lambda sym: scores[sym], reverse=True)
        top_cand = sorted_assets[0]
        bot_cand = sorted_assets[-1]

        # 15% Hysteresis deadband on rank flips
        if self.prev_top in universe and self.prev_top != top_cand:
            if (scores[top_cand] - scores[self.prev_top]) < 0.15 * dispersion:
                top_cand = self.prev_top
        if self.prev_bot in universe and self.prev_bot != bot_cand:
            if (scores[self.prev_bot] - scores[bot_cand]) < 0.15 * dispersion:
                bot_cand = self.prev_bot

        self.prev_top = top_cand
        self.prev_bot = bot_cand

        # Inverse-volatility pair balancing
        inv_top = 1.0 / vols[top_cand]
        inv_bot = 1.0 / vols[bot_cand]
        tot_inv = inv_top + inv_bot
        w_top_raw = inv_top / tot_inv
        w_bot_raw = inv_bot / tot_inv

        # Realized pair volatility estimate over trailing 120 bars
        c_top = indicators[top_cand]["closes"][bar_idx - 120 : bar_idx + 1]
        c_bot = indicators[bot_cand]["closes"][bar_idx - 120 : bar_idx + 1]
        rets_top = np.diff(c_top) / c_top[:-1]
        rets_bot = np.diff(c_bot) / c_bot[:-1]
        pair_rets = w_top_raw * rets_top - w_bot_raw * rets_bot
        pair_vol = float(np.std(pair_rets, ddof=1) * math.sqrt(2190.0))
        vol_scalar = min(0.15 / max(pair_vol, 0.04), 1.0)

        # Target weights: Long top asset, Short bottom asset (strictly gross <= 1.0001)
        w_long = float(w_top_raw * vol_scalar)
        w_short = float(-w_bot_raw * vol_scalar)

        gross = abs(w_long) + abs(w_short)
        if gross > 1.0001:
            scale = 1.0 / gross
            w_long *= scale
            w_short *= scale

        target_weights = {s: 0.0 for s in data_bundle["all_symbols"]}
        target_weights[top_cand] = round(w_long, 4)
        target_weights[bot_cand] = round(w_short, 4)
        return target_weights


class H3_PostCrashLiqRebound(BaseHypothesis):
    """
    Hypothesis 3: Capitulation Flush & Leverage-Exhaustion Rebound (Long-Only).
    Entry: 48h ret <= -0.10 AND 24h OI chg <= -0.05 AND close[t] > open[t] (green reversal) AND RSI14 <= 35.
    Sizing: 1.0% equity risk cap scaled by min(0.15/vol_20d, 1.0), max 25% notional per asset.
    Exit: Initial SL = entry - max(2.0*ATR, 0.01*entry), TP = entry + 2.0*R, or 72h (18 bars) time-stop.
    Worst-case intrabar SL-first tie-breaker.
    """

    def spec(self) -> HypothesisSpec:
        return HypothesisSpec(
            hypothesis_id="H3_POST_CRASH_LIQ_REBOUND",
            name="Capitulation Flush & Leverage-Exhaustion Rebound Long",
            family="Derivatives Liquidation Exhaustion & Mean Reversion",
            direction_mode="LONG_ONLY",
            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            timeframe="4h",
            parameters={
                "flush_ret_48h_threshold": -0.10,
                "oi_pct_chg_24h_threshold": -0.05,
                "rsi_threshold": 35.0,
                "target_vol": 0.15,
                "sl_atr_mult": 2.0,
                "tp_r_mult": 2.0,
                "max_hold_bars": 18,
                "max_notional_per_asset": 0.25,
                "risk_per_trade_cap": 0.01,
            },
            economic_rationale=(
                "Cascading liquidations trigger temporary supply-demand dislocations pushing prices below fundamental "
                "fair value; once open interest contracts sharply (flushing overleveraged longs) and the first 4h "
                "green stabilization candle appears in oversold RSI territory, structural mean-reversion offers "
                "convex 2:1 payoff asymmetry."
            ),
            distinct_novelty_rationale=(
                "Long-only post-crash capitulation flush and liquidation rebound with RSI reversal distinct from M63 crowding fades."
            ),
        )

    def evaluate_trade_intents(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        intents = []
        indicators = data_bundle["indicators"]
        deriv_data = data_bundle["deriv_by_symbol"]
        universe = self.spec().universe
        cur_equity = state["current_equity"]
        cash = state["cash"]
        positions = state["positions"]

        active_notional = sum(
            p["units"] * float(indicators[s]["closes"][bar_idx]) for s, p in positions.items()
        )

        for sym in universe:
            if sym in positions:
                continue

            c_now = float(indicators[sym]["closes"][bar_idx])
            op_now = float(indicators[sym]["opens"][bar_idx])
            c_48h_ago = float(indicators[sym]["closes"][bar_idx - 12])
            ret_48h = (c_now - c_48h_ago) / c_48h_ago if c_48h_ago > 0 else 0.0
            oi_chg_24h = float(deriv_data[sym]["oi_pct_chg_24h"][bar_idx])
            rsi_now = float(indicators[sym]["rsi14"][bar_idx])
            atr_now = float(indicators[sym]["atr"][bar_idx])
            vol_20d = float(indicators[sym]["vol_20d"][bar_idx])

            # Entry condition:
            # 1. 48h return <= -10% (sharp capitulation flush)
            # 2. 24h OI change <= -5% (leveraged long flush)
            # 3. Green reversal bar: close > open
            # 4. RSI <= 35
            cond_flush = ret_48h <= -0.10
            cond_oi = oi_chg_24h <= -0.05
            cond_green = c_now > op_now
            cond_rsi = rsi_now <= 35.0

            if cond_flush and cond_oi and cond_green and cond_rsi:
                vol_scalar = min(0.15 / max(vol_20d, 0.04), 1.0)
                base_risk_usd = 0.01 * cur_equity * vol_scalar
                sl_dist = max(2.0 * atr_now, 0.01 * c_now)
                tp_dist = 2.0 * sl_dist
                calc_notional = (base_risk_usd / sl_dist) * c_now
                max_asset_notional = 0.25 * cur_equity
                avail_equity = max(cur_equity - active_notional, 0.0)
                target_notional = min(calc_notional, max_asset_notional, avail_equity, cash)

                if target_notional > 10.0:
                    intents.append({
                        "symbol": sym,
                        "action": "ENTRY",
                        "target_notional": target_notional,
                        "initial_sl": c_now - sl_dist,
                        "tp": c_now + tp_dist,
                        "max_hold_bars": 18,  # 72 hours
                        "risk_dist": sl_dist,
                        "is_short": False,
                    })

        return intents


# ==============================================================================
# MILESTONE 75.1 CLEAN DISCOVERY BATCH #2 CANDIDATE HYPOTHESES (H1_CLEAN, H4, H5)
# ==============================================================================
class H1_CleanVolSqueezeExpansionLong(BaseHypothesis):
    """
    Hypothesis 1 (Clean Re-test): Volatility Compression -> Expansion Breakout (Long-Only).
    Evaluated under the hardened zero-leverage clamp (gross <= 1.0000).
    Entry: close[t] > EMA200[t] AND bb_width[t-1] <= q20(bb_width_120)[t-1] AND close[t] > max(high[t-20:t]).
    Sizing: 15% vol-targeted, max 25% notional per asset, hard gross <= 1.0.
    Exit: 2.5 * ATR trailing stop OR close[k] < min(low[k-12:k]) at open[k+1].
    """

    def spec(self) -> HypothesisSpec:
        return HypothesisSpec(
            hypothesis_id="H1_CLEAN_VOL_SQUEEZE_LONG",
            name="Clean Volatility Compression Expansion Breakout Long",
            family="Volatility Breakout & Squeeze Expansion",
            direction_mode="LONG_ONLY",
            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            timeframe="4h",
            parameters={
                "ema_trend_filter": 200,
                "bollinger_window": 20,
                "bollinger_std": 2.0,
                "compression_quantile_window": 120,
                "compression_quantile": 0.20,
                "breakout_window": 20,
                "trailing_stop_atr": 2.5,
                "donchian_exit_window": 12,
                "target_vol": 0.15,
                "max_notional_per_asset": 0.25,
                "risk_per_trade_cap": 0.01,
                "hard_gross_clamp": 1.0,
            },
            economic_rationale=(
                "Asset volatility regime clustering implies prolonged volatility contraction precedes large "
                "directional expansion; entering breakouts in the direction of the macro trend (EMA-200) "
                "captures convex upside under strict zero-leverage portfolio clamp."
            ),
            distinct_novelty_rationale=(
                "Clean evaluation of H1 volatility breakout under hardened zero-leverage simulator clamp to measure true unlevered performance."
            ),
        )

    def evaluate_trade_intents(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        intents = []
        indicators = data_bundle["indicators"]
        universe = self.spec().universe
        cur_equity = state["current_equity"]
        cash = state["cash"]
        positions = state["positions"]

        active_notional = sum(
            p["units"] * float(indicators[s]["closes"][bar_idx]) for s, p in positions.items()
        )
        allocated_in_intents = 0.0

        for sym in universe:
            c_now = float(indicators[sym]["closes"][bar_idx])
            ema200_now = float(indicators[sym]["ema200"][bar_idx])
            bb_w_prev = float(indicators[sym]["bb_width"][bar_idx - 1])
            bb_q20_prev = float(indicators[sym]["bb_width_q20_120"][bar_idx - 1])
            donch_h20_now = float(indicators[sym]["donch_h20"][bar_idx])
            donch_l12_now = float(indicators[sym]["donch_l12"][bar_idx])
            atr_now = float(indicators[sym]["atr"][bar_idx])
            vol_20d = float(indicators[sym]["vol_20d"][bar_idx])

            if sym in positions:
                # Update trailing stop on open position
                pos = positions[sym]
                new_sl = max(pos["current_sl"], c_now - 2.5 * atr_now)
                pos["current_sl"] = new_sl

                # Check Donchian-12 low exit at bar close
                if c_now < donch_l12_now:
                    intents.append({
                        "symbol": sym,
                        "action": "EXIT",
                        "reason": "DONCHIAN_L12_EXIT",
                    })
            else:
                is_bull_regime = c_now > ema200_now
                was_compressed = (bb_q20_prev > 0.0) and (bb_w_prev <= bb_q20_prev)
                is_breakout = c_now > donch_h20_now

                if is_bull_regime and was_compressed and is_breakout:
                    vol_scalar = min(0.15 / max(vol_20d, 0.04), 1.0)
                    base_risk_usd = 0.01 * cur_equity * vol_scalar
                    sl_dist = max(2.5 * atr_now, 0.01 * c_now)
                    calc_notional = (base_risk_usd / sl_dist) * c_now
                    max_asset_notional = 0.25 * cur_equity
                    avail_equity = max(cur_equity - active_notional - allocated_in_intents, 0.0)
                    target_notional = min(calc_notional, max_asset_notional, avail_equity, cash)

                    if target_notional > 10.0:
                        allocated_in_intents += target_notional
                        intents.append({
                            "symbol": sym,
                            "action": "ENTRY",
                            "target_notional": target_notional,
                            "initial_sl": c_now - sl_dist,
                            "risk_dist": sl_dist,
                            "is_short": False,
                        })

        return intents


class H4_TrendPullbackVolTarget(BaseHypothesis):
    """
    Hypothesis 4: Orthogonal Trend-Pullback Long with Volatility Targeting.
    Universe: BTCUSDT, ETHUSDT, SOLUSDT.
    Macro Trend Filter at bar close t: close[t] > EMA_200[t] AND EMA_50[t] > EMA_200[t].
    Pullback Reclaim Trigger at bar close t (fill at open[t+1]):
        low[t] <= EMA_20[t] AND close[t] > EMA_20[t] AND close[t] > open[t].
    Sizing: 1.0% equity risk scaled by min(0.15 / max(vol_20d, 0.04), 1.0),
        per-asset notional <= 25%, hard portfolio gross <= 1.0x.
    Exit: 2.5 * ATR_14 trailing stop OR close[k] < EMA_50[k] at open[k+1].
    Conservative SL-first intrabar tie-breaker.
    """

    def spec(self) -> HypothesisSpec:
        return HypothesisSpec(
            hypothesis_id="H4_TREND_PULLBACK_VOL_TARGET",
            name="Orthogonal Trend-Pullback Long with Volatility Targeting",
            family="Trend Following & Moving Average Pullback",
            direction_mode="LONG_ONLY",
            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            timeframe="4h",
            parameters={
                "ema_trend_filter": 200,
                "ema_fast_trend": 50,
                "ema_pullback": 20,
                "trailing_stop_atr": 2.5,
                "target_vol": 0.15,
                "max_notional_per_asset": 0.25,
                "risk_per_trade_cap": 0.01,
                "hard_gross_clamp": 1.0,
            },
            economic_rationale=(
                "In established bull trends (close > EMA200, EMA50 > EMA200), pullbacks to the intermediate 20-EMA "
                "represent temporary liquidity absorptions rather than trend reversals; buying the bullish reclaim "
                "rejection of the 20-EMA offers superior risk-reward than chasing breakouts at highs."
            ),
            distinct_novelty_rationale=(
                "Orthogonal trend pullback entry on 20-EMA reclaim in confirmed dual-EMA bull regime distinct from breakout or reversal strategies."
            ),
        )

    def evaluate_trade_intents(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        intents = []
        indicators = data_bundle["indicators"]
        universe = self.spec().universe
        cur_equity = state["current_equity"]
        cash = state["cash"]
        positions = state["positions"]

        active_notional = sum(
            p["units"] * float(indicators[s]["closes"][bar_idx]) for s, p in positions.items()
        )
        allocated_in_intents = 0.0

        for sym in universe:
            c_now = float(indicators[sym]["closes"][bar_idx])
            op_now = float(indicators[sym]["opens"][bar_idx])
            lo_now = float(indicators[sym]["lows"][bar_idx])
            ema200_now = float(indicators[sym]["ema200"][bar_idx])
            ema50_now = float(indicators[sym]["ema50"][bar_idx])
            ema20_now = float(indicators[sym]["ema20"][bar_idx])
            atr_now = float(indicators[sym]["atr"][bar_idx])
            vol_20d = float(indicators[sym]["vol_20d"][bar_idx])

            if sym in positions:
                # Update trailing stop on open position
                pos = positions[sym]
                new_sl = max(pos["current_sl"], c_now - 2.5 * atr_now)
                pos["current_sl"] = new_sl

                # Check EMA-50 breakdown exit at bar close
                if c_now < ema50_now:
                    intents.append({
                        "symbol": sym,
                        "action": "EXIT",
                        "reason": "EMA50_BREAKDOWN_EXIT",
                    })
            else:
                # Macro trend: close > EMA200 AND EMA50 > EMA200
                is_macro_bull = (c_now > ema200_now) and (ema50_now > ema200_now)
                # Pullback reclaim: low <= EMA20 AND close > EMA20 AND close > open
                is_reclaim = (lo_now <= ema20_now) and (c_now > ema20_now) and (c_now > op_now)

                if is_macro_bull and is_reclaim:
                    vol_scalar = min(0.15 / max(vol_20d, 0.04), 1.0)
                    base_risk_usd = 0.01 * cur_equity * vol_scalar
                    sl_dist = max(2.5 * atr_now, 0.01 * c_now)
                    calc_notional = (base_risk_usd / sl_dist) * c_now
                    max_asset_notional = 0.25 * cur_equity
                    avail_equity = max(cur_equity - active_notional - allocated_in_intents, 0.0)
                    target_notional = min(calc_notional, max_asset_notional, avail_equity, cash)

                    if target_notional > 10.0:
                        allocated_in_intents += target_notional
                        intents.append({
                            "symbol": sym,
                            "action": "ENTRY",
                            "target_notional": target_notional,
                            "initial_sl": c_now - sl_dist,
                            "risk_dist": sl_dist,
                            "is_short": False,
                        })

        return intents


class H5_DualHorizonRotationGold(BaseHypothesis):
    """
    Hypothesis 5: 14d + 60d Blended Dual-Momentum Rotation with Gold Defensive Fallback.
    Universe: BTCUSDT, ETHUSDT, SOLUSDT, PAXGUSDT.
    Cadence: Evaluated every 7 days (42 4h bars).
    Score: 0.5 * (ret_14d / max(vol_20d, 0.04)) + 0.5 * (ret_60d / max(vol_20d, 0.04)).
    Absolute Momentum Gate: Asset eligible ONLY if ret_14d > 0 AND ret_60d > 0.
    Selection: Top-2 inverse-vol weighted, 15% hysteresis deadband, 15% basket vol-targeting.
    Defensive: PAXG fallback if crypto majors fail gate, 100% Cash if all fail gate.
    Hard gross <= 1.0x (zero leverage).
    """

    def __init__(self):
        self.prev_top_assets: list[str] = []

    def spec(self) -> HypothesisSpec:
        return HypothesisSpec(
            hypothesis_id="H5_DUAL_HORIZON_ROTATION_GOLD",
            name="14d + 60d Blended Dual-Momentum Rotation with Gold Defensive Fallback",
            family="Cross-Asset Dual-Momentum Rotation",
            direction_mode="LONG_ONLY",
            universe=["BTCUSDT", "ETHUSDT", "SOLUSDT", "PAXGUSDT"],
            timeframe="4h",
            parameters={
                "rebalance_cadence_bars": 42,
                "lookback_fast_bars": 84,  # 14 days
                "lookback_slow_bars": 360,  # 60 days
                "vol_lookback_bars": 120,
                "target_vol": 0.15,
                "hysteresis": 0.15,
                "gross_exposure_cap": 1.0000,
            },
            economic_rationale=(
                "Cross-asset dual momentum blends medium-term (14d) responsiveness with secular (60d) trend stability "
                "to allocate capital to crypto leaders in bull runs, while falling back to gold (PAXG) during crypto bear "
                "markets and moving to 100% cash during generalized liquidity shocks."
            ),
            distinct_novelty_rationale=(
                "Blended 14d+60d dual-horizon momentum rotation with gold defensive fallback and cash capital preservation, distinct from single-asset trend and pair trading."
            ),
        )

    def generate_target_weights(
        self,
        data_bundle: dict[str, Any],
        bar_idx: int,
        state: dict[str, Any],
    ) -> dict[str, float]:
        if (bar_idx - 200) % 42 != 0:
            return {}

        all_symbols = data_bundle["all_symbols"]
        indicators = data_bundle["indicators"]
        crypto_majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

        target_weights = {s: 0.0 for s in all_symbols}

        scores: dict[str, float] = {}
        vols: dict[str, float] = {}
        gate_passed: dict[str, bool] = {}

        for s in all_symbols:
            c_now = float(indicators[s]["closes"][bar_idx])
            c_14d = float(indicators[s]["closes"][bar_idx - 84])
            c_60d = float(indicators[s]["closes"][bar_idx - 360])
            vol = max(float(indicators[s]["vol_20d"][bar_idx]), 0.04)
            vols[s] = vol

            ret_14d = (c_now - c_14d) / c_14d if c_14d > 0 else 0.0
            ret_60d = (c_now - c_60d) / c_60d if c_60d > 0 else 0.0

            scores[s] = 0.5 * (ret_14d / vol) + 0.5 * (ret_60d / vol)
            gate_passed[s] = (ret_14d > 0.0) and (ret_60d > 0.0)

        # Check crypto majors passing absolute momentum gate
        passing_crypto = [s for s in crypto_majors if gate_passed[s]]
        passing_crypto.sort(key=lambda s: scores[s], reverse=True)

        selected_assets: list[str] = []

        if len(passing_crypto) >= 2:
            # Top-2 crypto majors
            c1 = passing_crypto[0]
            c2 = passing_crypto[1]

            # 15% hysteresis deadband on rank flips if previous top assets are still passing
            if self.prev_top_assets:
                for prev in self.prev_top_assets:
                    if prev in passing_crypto and prev not in (c1, c2):
                        if (scores[c2] - scores[prev]) < 0.15 * abs(scores[c2]):
                            c2 = prev
            selected_assets = [c1, c2]

        elif len(passing_crypto) == 1:
            c1 = passing_crypto[0]
            if gate_passed.get("PAXGUSDT", False):
                selected_assets = [c1, "PAXGUSDT"]
            else:
                selected_assets = [c1]

        else:
            # 0 crypto majors pass gate -> fallback to PAXG if it passes gate
            if gate_passed.get("PAXGUSDT", False):
                selected_assets = ["PAXGUSDT"]
            else:
                # 100% Cash
                self.prev_top_assets = []
                return target_weights

        self.prev_top_assets = selected_assets

        if len(selected_assets) == 2:
            a1, a2 = selected_assets
            inv1 = 1.0 / vols[a1]
            inv2 = 1.0 / vols[a2]
            tot_inv = inv1 + inv2
            w1_raw = inv1 / tot_inv
            w2_raw = inv2 / tot_inv

            # Trailing 120-bar basket vol estimate
            c1_series = indicators[a1]["closes"][bar_idx - 120 : bar_idx + 1]
            c2_series = indicators[a2]["closes"][bar_idx - 120 : bar_idx + 1]
            r1 = np.diff(c1_series) / c1_series[:-1]
            r2 = np.diff(c2_series) / c2_series[:-1]
            basket_rets = w1_raw * r1 + w2_raw * r2
            basket_vol = float(np.std(basket_rets, ddof=1) * math.sqrt(2190.0))
            vol_scalar = min(0.15 / max(basket_vol, 0.04), 1.0)

            w1 = float(w1_raw * vol_scalar)
            w2 = float(w2_raw * vol_scalar)
            gross = w1 + w2
            if gross > 1.0:
                w1 /= gross
                w2 /= gross

            target_weights[a1] = round(w1, 4)
            target_weights[a2] = round(w2, 4)

        elif len(selected_assets) == 1:
            a1 = selected_assets[0]
            vol_scalar = min(0.15 / vols[a1], 1.0)
            target_weights[a1] = round(min(vol_scalar, 1.0), 4)

        return target_weights

