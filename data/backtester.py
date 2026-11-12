"""data/backtester.py

Walk-forward grader for the brain's conditional plans — the learning loop.

For every bar in a historical OHLCV series (from `min_bars` onward) the engine
is re-run on the data *up to that bar only* (no look-ahead), producing its
conditional plans. Each plan is then followed forward over the configured
horizons (default 1h / 4h / 24h) and graded:

  WIN / PARTIAL_WIN / FULL_WIN : price hit TP1 (and TP2) before SL
  LOSS                         : price hit SL before TP1
  OPEN                         : neither level touched within the horizon
  NOT_TRIGGERED                : price never reached the plan's entry level
                                 (a conditional plan that never fired)

Output aggregates win-rate, average R:R and expectancy by plan type, by
confidence bucket and by action, per horizon. Results can be saved into the
signal database (`--save`) so the engine learns which setups actually work.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from config import BACKTEST_HORIZONS, BACKTEST_MIN_BARS, BACKTEST_STEP, EXECUTION_MODEL
from data.binance_client import TIMEFRAME_TO_MS
from data.costs import DEFAULT_HALF_SPREAD, SPREADS, calculate_trade_cost
from data.symbols import normalize_symbol
from engine.execution import adjust_for_slip
from engine.indicators import add_all_indicators
from engine.signal_engine import analyze_frame_at

OUTCOMES = ("FULL_WIN", "PARTIAL_WIN", "LOSS", "OPEN", "NOT_TRIGGERED")
WIN_SET = {"FULL_WIN", "PARTIAL_WIN"}


@dataclass
class GradedPlan:
    ts: int
    plan_type: str
    action: str
    confidence_pct: int
    entry: float | None
    trigger_level: float | None
    horizon_hours: float
    outcome: str = "OPEN"
    rr_achieved: float = 0.0
    # Net R and cost breakdown (P12.6): E_net = E_gross − fees − slip − funding
    rr_net: float | None = None
    fee_r: float = 0.0
    slip_r: float = 0.0
    funding_r: float = 0.0
    cost_r: float = 0.0
    max_favorable: float = 0.0
    max_adverse: float = 0.0
    regime: str = ""  # market regime at signal time (decision B3)
    # Bars from entry to the deciding touch (SL or TP), and the same span in
    # hours. Recorded, not decided: P12.3's scorecard needs to know how long
    # the money was exposed. None while the trade never reached a decision.
    holding_bars: int | None = None
    holding_hours: float | None = None
    #: True when the deciding candle touched BOTH the stop and the target, so
    #: the outcome was resolved by the conservative stop-first rule rather than
    #: observed ordering. In-memory diagnostic only (not persisted): on real
    #: data its rate tells you how much of the book rests on that assumption.
    #: Near-zero on synthetic series; expected to be non-trivial on real wicks.
    ambiguous_bar: bool = False
    # P16 — the sentiment colour reading at signal time (offline mirror of
    # the live strip: engine scores + trend×ADX + signal, renormalised).
    sentiment_bucket: str = ""
    sentiment_score: float = 0.0
    sentiment_intensity: float = 0.0
    sentiment_persistence_min: float = 0.0

    def __post_init__(self):
        if self.rr_net is None:
            if self.rr_achieved is not None:
                self.rr_net = round(float(self.rr_achieved) - float(self.cost_r or 0.0), 3)
            else:
                self.rr_net = None

    def as_row(self) -> dict:
        return {
            "ts": self.ts,
            "plan_type": self.plan_type,
            "action": self.action,
            "confidence_pct": self.confidence_pct,
            "entry": self.entry,
            "trigger_level": self.trigger_level,
            "horizon_hours": self.horizon_hours,
            "outcome": self.outcome,
            "rr_achieved": self.rr_achieved,
            "rr_net": self.rr_net
            if self.rr_net is not None
            else (self.rr_achieved if self.rr_achieved is not None else 0.0),
            "fee_r": self.fee_r,
            "slip_r": self.slip_r,
            "funding_r": self.funding_r,
            "cost_r": self.cost_r,
            "max_favorable": self.max_favorable,
            "max_adverse": self.max_adverse,
            "regime": self.regime,
            "holding_bars": self.holding_bars,
            "holding_hours": self.holding_hours,
            "sentiment_bucket": self.sentiment_bucket,
            "sentiment_score": self.sentiment_score,
            "sentiment_intensity": self.sentiment_intensity,
            "sentiment_persistence_min": self.sentiment_persistence_min,
        }


def _evaluate(
    plan: dict,
    df: pd.DataFrame,
    i: int,
    horizon_bars: int,
    regime: str = "",
    sentiment: dict | None = None,
    ladder_parity: bool = False,
    strict_a_plus_only: bool = False,
    payoff_asymmetry: bool = False,
    maker_reclaim: bool = False,
) -> GradedPlan:
    """Grade one plan produced at bar i over `horizon_bars` future bars."""
    entry = plan.get("entry")
    sl = plan.get("stop_loss")
    tps = plan.get("take_profits") or []
    tp1 = tps[0] if len(tps) > 0 else None
    tp2 = tps[1] if len(tps) > 1 else None
    side = plan.get("action")
    is_buy = side == "BUY"

    sentiment = sentiment or {}
    gp = GradedPlan(
        ts=int(df.iloc[i]["ts"]),
        plan_type=plan.get("type", "?"),
        action=side or "?",
        confidence_pct=plan.get("confidence", 0),
        entry=entry,
        trigger_level=plan.get("trigger_level"),
        horizon_hours=round(
            horizon_bars
            * TIMEFRAME_TO_MS.get(df.attrs.get("timeframe", "15m"), 900_000)
            / 3_600_000,
            2,
        ),
        regime=regime,
        sentiment_bucket=sentiment.get("bucket", ""),
        sentiment_score=float(sentiment.get("score", 0.0) or 0.0),
        sentiment_intensity=float(sentiment.get("intensity", 0.0) or 0.0),
        sentiment_persistence_min=float(sentiment.get("persistence_min", 0.0) or 0.0),
    )
    if entry is None or sl is None or tp1 is None:
        gp.outcome = "NOT_TRIGGERED"
        return gp

    risk = abs(entry - sl)
    if strict_a_plus_only:
        # Grade A+ requires high-conviction institutional confidence (confidence >= 65)
        if gp.confidence_pct < 65:
            gp.outcome = "NOT_TRIGGERED"
            return gp

        mtf_alignment = plan.get("mtfAlignment")
        if mtf_alignment is not None:
            if mtf_alignment != "ALIGNED":
                gp.outcome = "NOT_TRIGGERED"
                return gp
        else:
            # Chronological sentiment & structural regime alignment
            s_score = float(sentiment.get("score", 0.0) or 0.0)
            s_bucket = (sentiment.get("bucket") or "").upper()
            reg_up = (regime or "").upper()
            if "BULL" in reg_up or "BEAR" in reg_up:
                is_aligned = (is_buy and ("BULL" in reg_up or "UP" in reg_up)) or (
                    not is_buy and ("BEAR" in reg_up or "DOWN" in reg_up)
                )
            elif "BULL" in s_bucket or "BEAR" in s_bucket:
                is_aligned = (is_buy and "BULL" in s_bucket) or (not is_buy and "BEAR" in s_bucket)
            else:
                is_aligned = (is_buy and s_score >= 0.0) or (not is_buy and s_score <= 0.0)

            if not is_aligned:
                gp.outcome = "NOT_TRIGGERED"
                return gp

        rr_val = plan.get("riskRewardRatio") or plan.get("rr") or plan.get("risk_reward")
        if rr_val is None:
            best_tp = max(tps) if is_buy and tps else (min(tps) if not is_buy and tps else None)
            target_tp = best_tp if best_tp is not None else tp1
            rr_val = (
                (abs(target_tp - entry) / max(risk, 1e-6))
                if target_tp is not None and risk > 0
                else 0.0
            )
        if float(rr_val or 0.0) < 2.5:
            gp.outcome = "NOT_TRIGGERED"
            return gp

    end = min(len(df), i + 1 + horizon_bars)
    window = df.iloc[i + 1 : end]
    if window.empty:
        gp.outcome = "OPEN"
        return gp

    highs = window["high"].to_numpy()
    lows = window["low"].to_numpy()
    opens = window["open"].to_numpy() if "open" in window.columns else highs
    closes = window["close"].to_numpy() if "close" in window.columns else highs
    cvd_vals = window["cvd"].to_numpy() if "cvd" in window.columns else np.zeros(len(window))

    # Did price ever trade at the entry level? Only conditional (waiting) plans
    # need the trigger — immediate plans execute at the current bar.
    conditional = (
        plan.get("status") == "waiting"
        or plan.get("trigger_level") is not None
        or "entryZone" in plan
        or "entry_zone" in plan
    )
    use_ladder = bool(
        strict_a_plus_only
        or ladder_parity
        or plan.get("ladder_parity")
        or plan.get("use_ladder_parity")
        or "entryZone" in plan
        or "entry_zone" in plan
    )

    # Realized R is always measured from the entry toward the exit price:
    # BUY  → (exit - entry) / risk   (exit above entry = positive R)
    # SELL → (entry - exit) / risk   (exit below entry = positive R)
    # Fix (2026-08-12): sell-side wins were previously signed as (tp - entry)/risk,
    # which is negative for a short, so every sell FULL_WIN/PARTIAL_WIN was
    # recorded as a negative-R trade and destroyed sell-side expectancy/PF.
    def realized_r(exit_price: float) -> float:
        if not risk:
            return 0.0
        return (
            round((exit_price - entry) / risk, 3)
            if is_buy
            else round((entry - exit_price) / risk, 3)
        )

    # Bars held until the deciding touch. Measured off the same first-touch
    # indices the outcome uses, so holding time can never disagree with the
    # grade it belongs to.
    bar_ms = TIMEFRAME_TO_MS.get(df.attrs.get("timeframe", "15m"), 900_000)

    def set_holding(bars_held: int | None) -> None:
        if bars_held is None:
            return
        gp.holding_bars = int(bars_held) + 1  # entry bar → deciding bar
        gp.holding_hours = round(gp.holding_bars * bar_ms / 3_600_000, 3)

    if use_ladder:
        from core.prediction_ladder import evaluate_ladder_tick

        ladder_entry_zone = (
            plan.get("entryZone")
            or plan.get("entry_zone")
            or [round(entry - 0.001 * entry, 2), round(entry + 0.001 * entry, 2)]
        )
        e_low = min(ladder_entry_zone[0], ladder_entry_zone[1])
        e_high = max(ladder_entry_zone[0], ladder_entry_zone[1])

        target_tp1 = (
            tp1
            if tp1 is not None
            else (round(entry + risk * 1.5, 2) if is_buy else round(entry - risk * 1.5, 2))
        )
        target_tp2 = (
            tp2
            if tp2 is not None
            else (round(entry + risk * 3.1, 2) if is_buy else round(entry - risk * 3.1, 2))
        )
        target_tp3 = (tps[2] if len(tps) > 2 else None) or (
            round(entry + risk * 6.2, 2) if is_buy else round(entry - risk * 6.2, 2)
        )

        ladder_plan = {
            "side": "LONG" if is_buy else "SHORT",
            "entryZone": [e_low, e_high],
            "stopLoss": sl,
            "invalidationPrice": plan.get("invalidationPrice")
            or plan.get("invalidation_level")
            or sl,
            "tp1": target_tp1,
            "tp2": target_tp2,
            "tp3": target_tp3,
        }

        is_filled = not conditional
        fill_bar_idx = 0 if not conditional else None

        if not conditional and strict_a_plus_only and len(window) > 0:
            b_o = float(opens[0])
            b_h = float(highs[0])
            b_l = float(lows[0])
            b_c = float(closes[0])
            cvd_v = float(cvd_vals[0])
            tick_eval = evaluate_ladder_tick(ladder_plan, b_o, b_h, b_l, b_c, cvd_score=cvd_v)
            if not (
                tick_eval.fill_allowed
                and (tick_eval.state == "IN_ZONE_CONFIRMED" or tick_eval.rejection_confirmed)
            ):
                is_filled = False
                fill_bar_idx = None

        if conditional:
            for bar_k in range(len(window)):
                b_o = float(opens[bar_k])
                b_h = float(highs[bar_k])
                b_l = float(lows[bar_k])
                b_c = float(closes[bar_k])
                cvd_v = float(cvd_vals[bar_k])

                tick_eval = evaluate_ladder_tick(ladder_plan, b_o, b_h, b_l, b_c, cvd_score=cvd_v)
                if tick_eval.state == "INVALIDATED":
                    # Knife catch avoided: price plunged to stop before confirming entry
                    break
                fill_confirmed = tick_eval.fill_allowed and (
                    not strict_a_plus_only
                    or tick_eval.state == "IN_ZONE_CONFIRMED"
                    or tick_eval.rejection_confirmed
                )
                if fill_confirmed:
                    is_filled = True
                    fill_bar_idx = bar_k
                    break

        if not is_filled or fill_bar_idx is None:
            gp.outcome = "NOT_TRIGGERED"
            return gp

        if maker_reclaim:
            # Gated by realistic intrabar queue fill: limit order must fill within 2 bars
            if fill_bar_idx > 1:
                gp.outcome = "NOT_TRIGGERED"
                return gp
            penetrated = (lows[fill_bar_idx] <= entry) if is_buy else (highs[fill_bar_idx] >= entry)
            if not penetrated:
                gp.outcome = "NOT_TRIGGERED"
                return gp

        current_stop = sl
        breakeven_active = False
        tp1_hit = False
        tp2_hit = False
        tp3_hit = False
        decided_bar = None

        for bar_k in range(fill_bar_idx, len(window)):
            b_h = float(highs[bar_k])
            b_l = float(lows[bar_k])

            sl_touched = (b_l <= current_stop) if is_buy else (b_h >= current_stop)
            tp1_touched = (b_h >= target_tp1) if is_buy else (b_l <= target_tp1)
            tp2_touched = (
                ((b_h >= target_tp2) if is_buy else (b_l <= target_tp2))
                if target_tp2 is not None
                else False
            )

            if sl_touched and tp1_touched and not tp1_hit:
                gp.outcome = "LOSS"
                gp.rr_achieved = -1.0
                gp.ambiguous_bar = True
                set_holding(bar_k)
                return gp

            if payoff_asymmetry and tp2_touched and (tp1_hit or tp1_touched):
                gp.outcome = "FULL_WIN"
                gp.rr_achieved = realized_r(target_tp2)
                set_holding(bar_k)
                decided_bar = bar_k
                break

            if sl_touched:
                if breakeven_active:
                    gp.outcome = "PARTIAL_WIN"
                    gp.rr_achieved = 0.10 if payoff_asymmetry else realized_r(target_tp1)
                else:
                    gp.outcome = "LOSS"
                    gp.rr_achieved = -1.0
                set_holding(bar_k)
                decided_bar = bar_k
                break

            if tp1_touched and not tp1_hit:
                tp1_hit = True
                breakeven_active = True
                current_stop = (
                    ((entry + 0.10 * risk) if is_buy else (entry - 0.10 * risk))
                    if payoff_asymmetry
                    else entry
                )
                decided_bar = bar_k

            if not payoff_asymmetry and target_tp2 is not None:
                if tp2_touched:
                    tp2_hit = True
                    decided_bar = bar_k

            if target_tp3 is not None:
                tp3_touched = (b_h >= target_tp3) if is_buy else (b_l <= target_tp3)
                if tp3_touched:
                    tp3_hit = True
                    decided_bar = bar_k
                    gp.outcome = "FULL_WIN"
                    gp.rr_achieved = realized_r(target_tp3)
                    set_holding(bar_k)
                    break

        if gp.outcome == "OPEN":
            if tp3_hit:
                gp.outcome = "FULL_WIN"
                gp.rr_achieved = realized_r(target_tp3)
                set_holding(decided_bar)
            elif tp2_hit:
                gp.outcome = "PARTIAL_WIN"
                gp.rr_achieved = realized_r(target_tp2)
                set_holding(decided_bar)
            elif tp1_hit:
                gp.outcome = "PARTIAL_WIN"
                gp.rr_achieved = realized_r(target_tp1)
                set_holding(decided_bar)

    else:
        touched_entry = True
        if conditional:
            touched_entry = ((lows <= entry) & (highs >= entry)).any()
        if not touched_entry:
            gp.outcome = "NOT_TRIGGERED"
            return gp

        # Order of SL vs TP1 touches
        sl_mask = (lows <= sl) if is_buy else (highs >= sl)
        tp1_mask = (highs >= tp1) if is_buy else (lows <= tp1)

        def first(idx_arr) -> int | None:
            idx = int(idx_arr[0]) if idx_arr.size else None
            return idx if idx is not None and 0 <= idx < len(window) else None

        first_sl = first(np.flatnonzero(sl_mask))
        first_tp1 = first(np.flatnonzero(tp1_mask))

        # Conservative same-bar rule (<=, not <): when the stop and the target are
        # both touched inside ONE candle, bar data cannot tell us which came first,
        # so we grade the STOP.
        if first_sl is not None and (first_tp1 is None or first_sl <= first_tp1):
            gp.outcome = "LOSS"
            gp.rr_achieved = -1.0
            gp.ambiguous_bar = first_tp1 is not None and first_sl == first_tp1
            set_holding(first_sl)
        elif first_tp1 is not None:
            if tp2 is not None:
                if is_buy:
                    tp2_idx = np.flatnonzero(highs[first_tp1:] >= tp2)
                else:
                    tp2_idx = np.flatnonzero(lows[first_tp1:] <= tp2)
                if tp2_idx.size:
                    gp.outcome = "FULL_WIN"
                    gp.rr_achieved = realized_r(tp2)
                    set_holding(first_tp1 + int(tp2_idx[0]))
                else:
                    gp.outcome = "PARTIAL_WIN"
                    gp.rr_achieved = realized_r(tp1)
                    set_holding(first_tp1)
            else:
                gp.outcome = "PARTIAL_WIN"
                gp.rr_achieved = realized_r(tp1)
                set_holding(first_tp1)
        else:
            gp.outcome = "OPEN"

    if is_buy:
        gp.max_favorable = round(float(highs.max() - entry), 2)
        gp.max_adverse = round(float(entry - lows.min()), 2)
    else:
        gp.max_favorable = round(float(entry - lows.min()), 2)
        gp.max_adverse = round(float(highs.max() - entry), 2)

    # ── execution model: slip/impact adjustment (gated by EXECUTION_MODEL) ─
    # Default "none" keeps the backtest honest (no model = raw fill).
    # When set to "slip" or "impact", the graded R is reduced by the predicted
    # market impact of the order size vs. average volume (execution.py).
    raw_gross_r = gp.rr_achieved
    exec_slip_r = 0.0
    if EXECUTION_MODEL != "none":
        try:
            row = df.iloc[i]
            adjust_for_slip(
                gp,
                plan,
                row,
                window,
                df.attrs.get("symbol", "BTCUSDT"),
                EXECUTION_MODEL,
            )
            exec_slip_r = max(0.0, round(raw_gross_r - gp.rr_achieved, 4))
        except Exception:
            pass  # execution model failure must not break the backtest

    # ── P12.6 trade costs & net R (E_net = E_gross − fees − slip − funding) ─
    if gp.outcome in ("LOSS", "FULL_WIN", "PARTIAL_WIN"):
        try:
            is_passive = bool(
                maker_reclaim
                or plan.get("status") == "waiting"
                or plan.get("trigger_level") is not None
            )
            exec_type = None
            if maker_reclaim:
                exec_type = "maker_in_taker_out" if gp.outcome == "LOSS" else "maker"

            cost = calculate_trade_cost(
                entry=entry,
                stop_loss=sl,
                action=side or "BUY",
                gross_r=raw_gross_r,
                holding_hours=gp.holding_hours,
                symbol=df.attrs.get("symbol", "BTCUSDT"),
                ts=gp.ts,
                is_passive_limit=is_passive,
                execution_type=exec_type,
            )
            gp.fee_r = cost.fee_r
            gp.funding_r = cost.funding_r

            # Deduplicate entry spread between adjust_for_slip and calculate_trade_cost:
            # When EXECUTION_MODEL != "none", adjust_for_slip already accounted for entry
            # spread and size/volatility impact (exec_slip_r).
            # We ensure round-trip fees, spread, impact, and funding are deducted exactly
            # once without double-counting entry spread:
            if EXECUTION_MODEL != "none" and exec_slip_r > 0:
                half_spread = SPREADS.get(
                    df.attrs.get("symbol", "BTCUSDT").upper(), DEFAULT_HALF_SPREAD
                )
                entry_spread_r = (
                    round(half_spread / cost.stop_dist_pct, 4)
                    if not is_passive and cost.stop_dist_pct > 0
                    else 0.0
                )
                impact_r = max(0.0, round(exec_slip_r - entry_spread_r, 4))
                gp.slip_r = round(cost.slip_r + impact_r, 4)
            else:
                gp.slip_r = cost.slip_r

            gp.cost_r = round(gp.fee_r + gp.slip_r + gp.funding_r, 4)
            gp.rr_net = round(raw_gross_r - gp.cost_r, 3)
        except Exception:
            gp.rr_net = gp.rr_achieved

    return gp


def _aggregate(graded: list[GradedPlan]) -> dict:
    if not graded:
        return {
            "executed": 0,
            "wins": 0,
            "losses": 0,
            "opens": 0,
            "not_triggered": 0,
            "win_rate": None,
            "avg_rr": 0.0,
            "expectancy": 0.0,
            "expectancy_net": 0.0,
            "win_rate_net": None,
            "avg_rr_net": 0.0,
            "cost_r": 0.0,
            "fee_r": 0.0,
            "slip_r": 0.0,
            "funding_r": 0.0,
        }
    executed = [g for g in graded if g.outcome != "NOT_TRIGGERED"]
    wins = [g for g in executed if g.outcome in WIN_SET]
    losses = [g for g in executed if g.outcome == "LOSS"]
    opens = [g for g in executed if g.outcome == "OPEN"]
    decided = wins + losses
    win_rate = round(len(wins) / len(decided), 3) if decided else None
    rr_vals = [g.rr_achieved for g in decided]
    avg_rr = round(sum(rr_vals) / len(rr_vals), 3) if rr_vals else 0.0
    # expectancy: average R per decided trade (wins positive, losses -1R)
    exp = round(sum(g.rr_achieved for g in decided) / len(decided), 3) if decided else 0.0

    # Net metrics (P12.6)
    rr_net_vals = [getattr(g, "rr_net", g.rr_achieved) for g in decided]
    cost_vals = [getattr(g, "cost_r", 0.0) for g in decided]
    fee_vals = [getattr(g, "fee_r", 0.0) for g in decided]
    slip_vals = [getattr(g, "slip_r", 0.0) for g in decided]
    fund_vals = [getattr(g, "funding_r", 0.0) for g in decided]
    net_wins = [r for r in rr_net_vals if r > 0]
    win_rate_net = round(len(net_wins) / len(decided), 3) if decided else None
    avg_rr_net = round(sum(rr_net_vals) / len(rr_net_vals), 3) if rr_net_vals else 0.0
    exp_net = round(sum(rr_net_vals) / len(decided), 3) if decided else 0.0
    avg_cost = round(sum(cost_vals) / len(cost_vals), 4) if cost_vals else 0.0
    avg_fee = round(sum(fee_vals) / len(fee_vals), 4) if fee_vals else 0.0
    avg_slip = round(sum(slip_vals) / len(slip_vals), 4) if slip_vals else 0.0
    avg_funding = round(sum(fund_vals) / len(fund_vals), 4) if fund_vals else 0.0

    return {
        "executed": len(executed),
        "wins": len(wins),
        "losses": len(losses),
        "opens": len(opens),
        "not_triggered": len(graded) - len(executed),
        "win_rate": win_rate,
        "avg_rr": avg_rr,
        "expectancy": exp,
        "expectancy_net": exp_net,
        "win_rate_net": win_rate_net,
        "avg_rr_net": avg_rr_net,
        "cost_r": avg_cost,
        "fee_r": avg_fee,
        "slip_r": avg_slip,
        "funding_r": avg_funding,
    }


def group_by(graded: list[GradedPlan], key_fn) -> dict:
    out: dict = {}
    for g in graded:
        k = key_fn(g)
        out.setdefault(k, []).append(g)
    return {k: _aggregate(v) for k, v in out.items()}


def run_backtest(
    df: pd.DataFrame,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    horizons: list[float] | None = None,
    min_bars: int = BACKTEST_MIN_BARS,
    step: int = BACKTEST_STEP,
    min_confidence: int = 55,
    ladder_parity: bool = False,
    strict_a_plus_only: bool = False,
    payoff_asymmetry: bool = False,
    maker_reclaim: bool = False,
) -> dict:
    """Walk the engine over history and grade every plan at every horizon."""
    symbol = normalize_symbol(symbol)
    horizons = horizons or BACKTEST_HORIZONS
    tf_ms = TIMEFRAME_TO_MS.get(timeframe, 900_000)
    df = df.reset_index(drop=True).copy()
    df.attrs["timeframe"] = timeframe
    df.attrs["symbol"] = symbol

    if strict_a_plus_only:
        ladder_parity = True
        min_confidence = max(min_confidence, 65)

    # P13.4 — precompute the indicator columns once over the whole series,
    # then walk with windowed per-bar analysis instead of re-running the full
    # indicator suite from bar 0 at every step (was O(N^2), now O(N) +
    # O(lookback) per step).  Behaviour-identical: every detector only ever
    # saw its fixed tail window of the prefix, and the prefix always started
    # at row 0, so the precomputed columns agree bar-for-bar.
    ind = add_all_indicators(df)

    all_graded: list[GradedPlan] = []
    scans_done = 0
    plans_total = 0
    start = time.time()

    # P16 — the sentiment colour clock walks the same chronological path the
    # grader does: one reading per analyzed bar, persistence accrues while the
    # direction holds, neutral/flips reset. Plans are tagged with the colour
    # the desk would have seen at that exact bar.
    from engine.sentiment import SentimentClock, compute_historical

    clock = SentimentClock()

    for i in range(min_bars, len(df), step):
        out = analyze_frame_at(
            ind,
            df,
            i,
            symbol=symbol,
            timeframe=timeframe,
            min_confidence=min_confidence,
        )
        bar_ts = int(df.iloc[i]["ts"])
        sig = out.best_signal or {}
        hist_score = compute_historical(
            bull_score=out.bull_score.score if out.bull_score else 0.0,
            bear_score=out.bear_score.score if out.bear_score else 0.0,
            features=out.features,
            signal_action=sig.get("action", "NO TRADE"),
            signal_confidence=sig.get("confidence", ""),
        )
        sentiment = clock.reading(hist_score, bar_ts)
        plans = out.plans
        if not plans:
            continue
        scans_done += 1
        plans_total += len(plans)
        regime = (out.features or {}).get("regime_name", "")
        for h in horizons:
            horizon_bars = max(1, int(h * 3_600_000 / tf_ms))
            for plan in plans:
                all_graded.append(
                    _evaluate(
                        plan,
                        df,
                        i,
                        horizon_bars,
                        regime=regime,
                        sentiment=sentiment,
                        ladder_parity=ladder_parity,
                        strict_a_plus_only=strict_a_plus_only,
                        payoff_asymmetry=payoff_asymmetry,
                        maker_reclaim=maker_reclaim,
                    )
                )

    report = {
        "meta": {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_total": len(df),
            "bars_analyzed": scans_done,
            "plans_generated": plans_total,
            "horizons_hours": horizons,
            "min_bars": min_bars,
            "step": step,
            "runtime_seconds": round(time.time() - start, 2),
            "engine_min_confidence": min_confidence,
            # P16 — the colour proof runs on the offline mirror of the live
            # composite (engine scores + trend×ADX + signal), never on data
            # the walk couldn't see (funding/news/fear&greed/MTF excluded).
            "sentiment_mode": "historical",
        },
        "summary": _aggregate([g for g in all_graded if g.horizon_hours == horizons[0]]),
        "per_horizon": {
            str(h): _aggregate([g for g in all_graded if g.horizon_hours == h]) for h in horizons
        },
        "by_type": group_by(all_graded, lambda g: g.plan_type),
        "by_action": group_by(all_graded, lambda g: g.action),
        "by_confidence": group_by(
            all_graded,
            lambda g: (
                "HIGH" if g.confidence_pct >= 80 else "MEDIUM" if g.confidence_pct >= 60 else "LOW"
            ),
        ),
        "by_regime": group_by(all_graded, lambda g: g.regime or "UNKNOWN"),
        # P16 — does the colour pay? The same buckets the strip paints.
        "by_sentiment": group_by(all_graded, lambda g: g.sentiment_bucket or "UNKNOWN"),
    }
    return {"report": report, "graded": all_graded}


def save_report(report: dict, path: str = "data_samples/backtest_report.json") -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2, default=str))


def run_backtest_on_store(
    exchange: str = "binance",
    market: str = "perp",
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    bars: int = 300,
    horizons: list[float] | None = None,
    min_bars: int = BACKTEST_MIN_BARS,
    step: int = BACKTEST_STEP,
    min_confidence: int = 55,
) -> dict:
    """P10.11 — backtest that reads from the stored Parquet series.

    The engine no longer depends on a live ``client.klines()`` fetch; it reads
    from ``CandleStore.read()`` (immutable, deduplicated, ordered) and can
    therefore run multi-year backtests offline.  The result feeds ``P10.12``
    feature-store queries.

    If the series does not exist or has fewer bars than ``min_bars``, a clear
    error is returned rather than a corrupt result.
    """
    from data.store import CandleStore

    store = CandleStore()
    df = store.read(exchange, market, symbol, timeframe)
    if df.empty:
        return {
            "ok": False,
            "error": f"No stored candles for {exchange}/{market}/{symbol}/{timeframe}",
            "report": {},
            "graded": [],
        }
    if len(df) < min_bars:
        return {
            "ok": False,
            "error": f"Only {len(df)} bars stored (need >= {min_bars})",
            "stored": len(df),
            "required": min_bars,
            "report": {},
            "graded": [],
        }
    # Respect the `bars` cap for quick backtests; if None or <=0, use full historical dataset.
    if bars is not None and bars > 0:
        df = df.tail(bars).reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)
    result = run_backtest(
        df,
        symbol=symbol,
        timeframe=timeframe,
        horizons=horizons,
        min_bars=min_bars,
        step=step,
        min_confidence=min_confidence,
    )
    # P12.11 — report the provenance of the series that was actually graded,
    # read off the stored frame itself rather than assumed from arguments.
    from data.provenance import provenance_of_frame, source_key

    prov_exchange, prov_market, prov_price_type = provenance_of_frame(
        df, exchange=exchange, market=market
    )
    return {
        "ok": True,
        **result,
        "store_source": True,
        "store_path": store._series_dir(exchange, market, symbol, timeframe).as_posix(),
        "bars_read": len(df),
        "exchange": prov_exchange,
        "market": prov_market,
        "price_type": prov_price_type,
        "source_key": source_key(prov_exchange, prov_market, prov_price_type),
    }


def print_report(report: dict) -> None:
    meta, s = report["meta"], report["summary"]
    print("=" * 66)
    print(
        f"BACKTEST  {meta['symbol']} {meta['timeframe']}  "
        f"bars={meta['bars_total']} analyzed={meta['bars_analyzed']} "
        f"plans={meta['plans_generated']} ({meta['runtime_seconds']}s)"
    )
    print(
        f"primary horizon {meta['horizons_hours'][0]}h — "
        f"executed {s['executed']} | wins {s['wins']} | losses {s['losses']} | "
        f"open {s['opens']} | not-triggered {s['not_triggered']}"
    )
    wr = s["win_rate"]
    print(
        f"win-rate {f'{wr * 100:.1f}%' if wr is not None else 'n/a'}  "
        f"avg R {s['avg_rr']}  expectancy {s['expectancy']}R/trade"
    )
    print("-" * 66)
    for h, agg in report["per_horizon"].items():
        wr = agg["win_rate"]
        print(
            f"  {h}h: win {f'{wr * 100:.1f}%' if wr is not None else 'n/a'}"
            f" ({agg['wins']}/{agg['wins'] + agg['losses']})  avgR {agg['avg_rr']}  "
            f"exp {agg['expectancy']}  exec {agg['executed']}"
        )
    print("-" * 66)
    print("by plan type:")
    for t, agg in sorted(report["by_type"].items(), key=lambda kv: -(kv[1]["executed"] or 0)):
        wr = agg["win_rate"]
        print(
            f"  {t:<24} exec {agg['executed']:>4}  win "
            f"{f'{wr * 100:.1f}%' if wr is not None else 'n/a'}  "
            f"avgR {agg['avg_rr']}  exp {agg['expectancy']}"
        )
    print("by confidence:")
    for c, agg in report["by_confidence"].items():
        wr = agg["win_rate"]
        print(
            f"  {c:<8} exec {agg['executed']:>4}  win "
            f"{f'{wr * 100:.1f}%' if wr is not None else 'n/a'}  "
            f"avgR {agg['avg_rr']}  exp {agg['expectancy']}"
        )
    print("by regime (decision B3 — strategy = setup × regime × asset):")
    for r, agg in sorted(
        report.get("by_regime", {}).items(), key=lambda kv: -(kv[1]["executed"] or 0)
    ):
        wr = agg["win_rate"]
        print(
            f"  {r:<22} exec {agg['executed']:>4}  win "
            f"{f'{wr * 100:.1f}%' if wr is not None else 'n/a'}  "
            f"avgR {agg['avg_rr']}  exp {agg['expectancy']}"
        )
    print("by sentiment colour (P16 — does deep green actually pay?):")
    from engine.sentiment import bucket_label

    for r, agg in sorted(
        report.get("by_sentiment", {}).items(), key=lambda kv: -(kv[1]["executed"] or 0)
    ):
        wr = agg["win_rate"]
        print(
            f"  {bucket_label(r):<12} exec {agg['executed']:>4}  win "
            f"{f'{wr * 100:.1f}%' if wr is not None else 'n/a'}  "
            f"avgR {agg['avg_rr']}  exp {agg['expectancy']}"
        )
