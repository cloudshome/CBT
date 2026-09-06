"""data/scorecard.py — P12.3 & P12.6: the boxed strategy scorecard & net expectancy (E_net).

One command, one block.  This is a **report layer**, not a second grader:
it reads outcomes that already exist (graded plans from `data/backtester.py`,
`backtest_results` and decided `paper_trades` from `data/database.py`) and
prints the numbers a discretionary desk actually needs before it risks money:

  * expectancy R (gross and NET of costs: E_net = E_gross − fees − slip − funding)
  * win rate (gross and net)
  * profit factor (gross and net)
  * total R (gross and net)
  * risk-adjusted: Sharpe / Sortino / Calmar (trade-level, documented below)
  * max drawdown in R (gross and net), longest win/loss streak
  * holding time (hours) — how long the money is exposed
  * cost breakdown: fees in R, spread/slippage in R, funding in R
  * effective sample size N_eff (P12.3.3) — raw walk-forward counts divided
    by the window-overlap factor (horizon_bars / step), with standard errors
    and 95% confidence intervals widened honestly (SE = σ / √N_eff)
  * the same block split by **side** (long/short), **regime**, **session**,
    **setup**, and **market condition** (funding sign, CVD flow, OI trend)

Design rules (deliberate, do not "improve" away):

  * No new math engine and no new dependency — the R values are the ones the
    existing grader produced (BUY R = (exit-entry)/risk,
    SELL R = (entry-exit)/risk).
  * No second grader.  `data/backtester.py` stays the only thing that decides
    WIN / LOSS.  This file never touches raw OHLCV.
  * The pass/fail bar is the existing graduation bar, imported from
    `data.validation` (which imports it from `data.simulator`), enforced **NET**
    of costs (P12.6). It is not loosened here: E_net >= +0.50R, WR_net > 55%, PF_net >= 1.5.
  * Every metric degrades to ``None`` rather than to a guess when the sample
    cannot support it.  Silence is not an edge.

Risk-adjusted metrics are **per decided trade**, not annualised returns:

  Sharpe   = mean(R) / stdev(R)                 (sample stdev, ddof=1)
  Sortino  = mean(R) / sqrt(mean(min(R,0)^2))   (downside deviation about 0)
  Calmar   = total R / max drawdown R           (both in R units)

These are deliberately **not** annualised.  A walk-forward grade steps through
history every few bars, so its "trades" overlap heavily; multiplying by
sqrt(trades per year) would turn a Sharpe of 0.27 into a Sharpe of 36 and that
number would be a lie.  The sample span and trades-per-day are reported as
plain context instead, so the reader can judge frequency themselves.

P12.3.3 closes the same overlap gap for sample *counts*: ``N_eff = N / overlap``
(``overlap = horizon_bars / step``) is reported alongside raw ``N``, and every
standard error / 95% confidence interval uses ``√N_eff`` rather than ``√N`` so
the reported uncertainty does not silently shrink ~30×.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Iterable

from config import BACKTEST_STEP, GOLD_LONDON_WINDOW, GOLD_NY_WINDOW
from data.backtester import WIN_SET
from data.binance_client import TIMEFRAME_TO_MS
from data.costs import (
    CostModel,
    calculate_trade_cost,
)
from data.provenance import normalize as _provenance_normalize
from data.provenance import parse_source_key as _provenance_parse
from data.provenance import source_key as _provenance_key
from data.validation import DEFAULT_MIN_DECIDED, VALIDATION_CRITERIA, meets_bar
from engine.sentiment import BUCKETS

DECIDED_BACKTEST = set(WIN_SET) | {"LOSS"}
DECIDED_PAPER = {"TP_HIT", "STOP_LOSS"}

# Session buckets in UTC hours.  Derived from the gold playbook windows in
# config (GOLD_LONDON_WINDOW=(7,16), GOLD_NY_WINDOW=(12,21)) so the desk reads
# one definition of "London" everywhere.  The London/NY overlap is attributed
# to New York (that is where the volume prints), and everything outside both
# windows is the Asia / off-window bucket.
SESSION_ASIA = "asia"
SESSION_LONDON = "london"
SESSION_NEWYORK = "newyork"
SESSION_NAMES = (SESSION_ASIA, SESSION_LONDON, SESSION_NEWYORK)
SESSION_LABELS = {
    SESSION_ASIA: f"Asia / off-window (outside {GOLD_LONDON_WINDOW[0]:02d}:00–"
    f"{GOLD_NY_WINDOW[1]:02d}:00 UTC)",
    SESSION_LONDON: f"London ({GOLD_LONDON_WINDOW[0]:02d}:00–"
    f"{GOLD_NY_WINDOW[0]:02d}:00 UTC)",
    SESSION_NEWYORK: f"New York ({GOLD_NY_WINDOW[0]:02d}:00–"
    f"{GOLD_NY_WINDOW[1]:02d}:00 UTC)",
}

MS_PER_HOUR = 3_600_000
SIDES = ("BUY", "SELL")


# ──────────────────────────────────────────────────────────────────────────
# Session bucketing
# ──────────────────────────────────────────────────────────────────────────
def session_of_hour(hour: int) -> str:
    """UTC hour → session bucket (overlap counted as New York)."""
    hour = int(hour) % 24
    if GOLD_NY_WINDOW[0] <= hour < GOLD_NY_WINDOW[1]:
        return SESSION_NEWYORK
    if GOLD_LONDON_WINDOW[0] <= hour < GOLD_NY_WINDOW[0]:
        return SESSION_LONDON
    return SESSION_ASIA


def session_of_ts(ts_ms: int | None) -> str | None:
    """Epoch-milliseconds → session bucket; ``None`` when there is no clock."""
    if ts_ms is None:
        return None
    try:
        hour = int((int(ts_ms) // MS_PER_HOUR) % 24)
    except (TypeError, ValueError):
        return None
    return session_of_hour(hour)


# ──────────────────────────────────────────────────────────────────────────
# Row adapters — every source is flattened to one honest row shape
# ──────────────────────────────────────────────────────────────────────────
def _row(
    ts,
    side,
    setup,
    regime,
    r,
    outcome,
    holding_hours,
    symbol="",
    timeframe="",
    source="",
    entry=None,
    stop_loss=None,
    r_net=None,
    fee_r=None,
    slip_r=None,
    funding_r=None,
    cost_r=None,
    funding_rate=None,
    cvd_z=None,
    oi_trend=None,
    horizon_hours: float | None = None,
    step: int | None = None,
    cost_model: CostModel | None = None,
    exchange=None,
    market=None,
    price_type=None,
    sentiment_bucket=None,
    sentiment_score=None,
    sentiment_intensity=None,
) -> dict:
    gross_r = float(r) if r is not None else 0.0
    hold = round(float(holding_hours), 3) if holding_hours is not None else None

    # If net R and costs are not pre-computed, calculate via the cost model
    if r_net is None or fee_r is None:
        cost = calculate_trade_cost(
            entry=entry,
            stop_loss=stop_loss,
            action=side or "BUY",
            gross_r=gross_r,
            holding_hours=hold,
            symbol=symbol or "BTCUSDT",
            ts=ts,
            cost_model=cost_model,
        )
        r_net = cost.net_r
        fee_r = cost.fee_r
        slip_r = cost.slip_r
        funding_r = cost.funding_r
        cost_r = cost.total_cost_r
        if funding_rate is None:
            funding_rate = cost.funding_rate_8h

    # P12.11 — provenance travels with the row so every downstream reader
    # (scorecard splits, calibrator keys, quality score) can tell which price
    # series produced it. Missing fields normalise to the canonical live
    # series, which is what all pre-provenance history actually is.
    prov_exchange, prov_market, prov_price_type = _provenance_normalize(
        exchange, market, price_type
    )

    # P16 — the sentiment colour at signal time. Pre-P16 rows carry NULL and
    # must stay UNKNOWN (never silently re-labelled slate).
    s_bucket = sentiment_bucket or "UNKNOWN"
    s_intensity = (
        float(sentiment_intensity) if sentiment_intensity is not None else None
    )
    if s_bucket in ("bull", "bear", "deep_bull", "deep_bear"):
        s_depth = (
            "DEEP" if (s_intensity is not None and s_intensity >= 0.5) else "FRESH"
        )
    elif s_bucket == "slate":
        s_depth = "SLATE"
    else:
        s_depth = "UNKNOWN"

    return {
        "ts": int(ts) if ts is not None else None,
        "side": (side or "?").upper(),
        "setup": setup or "?",
        "regime": regime or "UNKNOWN",
        "r": gross_r,
        "r_net": float(r_net),
        "fee_r": float(fee_r or 0.0),
        "slip_r": float(slip_r or 0.0),
        "funding_r": float(funding_r or 0.0),
        "cost_r": float(cost_r or 0.0),
        "outcome": outcome or "",
        "holding_hours": hold,
        "symbol": symbol or "",
        "timeframe": timeframe or "",
        "source": source,
        "horizon_hours": horizon_hours,
        "step": step,
        "session": session_of_ts(ts),
        "funding_rate": funding_rate,
        "cvd_z": cvd_z,
        "oi_trend": oi_trend,
        "exchange": prov_exchange,
        "market": prov_market,
        "price_type": prov_price_type,
        "source_key": _provenance_key(prov_exchange, prov_market, prov_price_type),
        "sentiment_bucket": s_bucket,
        "sentiment_score": float(sentiment_score)
        if sentiment_score is not None
        else None,
        "sentiment_intensity": s_intensity,
        "sentiment_depth": s_depth,
    }


def rows_from_graded(
    graded: Iterable,
    symbol: str = "",
    timeframe: str = "",
    horizon_hours: float | None = None,
    cost_model: CostModel | None = None,
    exchange: str | None = None,
    market: str | None = None,
    price_type: str | None = None,
) -> list[dict]:
    """Decided rows from in-memory `GradedPlan` objects (the grader's output).

    ``horizon_hours`` filters to one horizon so a multi-horizon backtest is
    not counted three times.  Defaults to the shortest horizon present.
    """
    graded = list(graded)
    if horizon_hours is None:
        horizons = {g.horizon_hours for g in graded}
        horizon_hours = min(horizons) if horizons else None
    rows = []
    for g in graded:
        if horizon_hours is not None and g.horizon_hours != horizon_hours:
            continue
        if g.outcome not in DECIDED_BACKTEST:
            continue
        rows.append(
            _row(
                ts=g.ts,
                side=g.action,
                setup=g.plan_type,
                regime=g.regime,
                r=g.rr_achieved,
                outcome=g.outcome,
                holding_hours=getattr(g, "holding_hours", None),
                symbol=symbol,
                timeframe=timeframe,
                source="backtest",
                entry=getattr(g, "entry", None),
                r_net=getattr(g, "rr_net", None),
                fee_r=getattr(g, "fee_r", None),
                slip_r=getattr(g, "slip_r", None),
                funding_r=getattr(g, "funding_r", None),
                cost_r=getattr(g, "cost_r", None),
                horizon_hours=getattr(g, "horizon_hours", None),
                cost_model=cost_model,
                exchange=exchange,
                market=market,
                price_type=price_type,
            )
        )
    rows.sort(key=lambda r: (r["ts"] is None, r["ts"]))
    return rows


def _source_sql(cols: set, source_key: str | None, args: list) -> str:
    """P12.11 source filter for the `backtest_results` reader.

    The canonical key ``""`` also matches legacy NULL rows: history written
    before provenance existed *is* the canonical Binance spot series.
    """
    if source_key is None or "source_key" not in cols:
        return ""
    key = _provenance_key(*_provenance_parse(source_key))
    if key == "":
        args.append("")
        return " AND COALESCE(source_key,'')=?"
    args.append(key)
    return " AND source_key=?"


def rows_from_backtest_db(
    db,
    symbol: str | None = None,
    include_sim: bool = True,
    since_ts: int | None = None,
    until_ts: int | None = None,
    cost_model: CostModel | None = None,
    source_key: str | None = None,
) -> list[dict]:
    """Decided rows from the stored `backtest_results` table.

    ``since_ts`` / ``until_ts`` bound the signal bar (inclusive) so one
    book can hold several data eras (e.g. the old synthetic samples vs.
    the P12.3.2 real-market rows) without mixing them.
    """
    # Verify available columns gracefully for backwards compatibility
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(backtest_results)")}
    sel_cols = [
        "ts",
        "symbol",
        "timeframe",
        "plan_type",
        "action",
        "outcome",
        "rr_achieved",
        "regime",
        "holding_hours",
        "horizon_hours",
    ]
    for extra in (
        "entry",
        "trigger_level",
        "rr_net",
        "fee_r",
        "slip_r",
        "funding_r",
        "cost_r",
        "step",
        "exchange",
        "market",
        "price_type",
        "sentiment_bucket",
        "sentiment_score",
        "sentiment_intensity",
    ):
        if extra in cols:
            sel_cols.append(extra)

    q = (
        f"SELECT {', '.join(sel_cols)} "
        "FROM backtest_results WHERE outcome IN "
        f"({','.join('?' * len(DECIDED_BACKTEST))})"
    )
    args: list = sorted(DECIDED_BACKTEST)
    if symbol:
        q += " AND symbol=?"
        args.append(symbol)
    if since_ts is not None:
        q += " AND ts>=?"
        args.append(int(since_ts))
    if until_ts is not None:
        q += " AND ts<=?"
        args.append(int(until_ts))
    if not include_sim and "sim_key" in cols:
        q += " AND sim_key IS NULL"
    # P12.11 — restrict to one price series when asked. `None` = every source.
    q += _source_sql(cols, source_key, args)
    q += " ORDER BY ts ASC"
    out = []
    for r in db.conn.execute(q, args).fetchall():
        d = dict(r)
        out.append(
            _row(
                ts=d.get("ts"),
                side=d.get("action"),
                setup=d.get("plan_type"),
                regime=d.get("regime"),
                r=d.get("rr_achieved") or 0.0,
                outcome=d.get("outcome"),
                holding_hours=d.get("holding_hours"),
                symbol=d.get("symbol"),
                timeframe=d.get("timeframe"),
                source="backtest",
                entry=d.get("entry"),
                r_net=d.get("rr_net"),
                fee_r=d.get("fee_r"),
                slip_r=d.get("slip_r"),
                funding_r=d.get("funding_r"),
                cost_r=d.get("cost_r"),
                cost_model=cost_model,
                horizon_hours=d.get("horizon_hours"),
                step=d.get("step"),
                exchange=d.get("exchange"),
                market=d.get("market"),
                price_type=d.get("price_type"),
                sentiment_bucket=d.get("sentiment_bucket"),
                sentiment_score=d.get("sentiment_score"),
                sentiment_intensity=d.get("sentiment_intensity"),
            )
        )
    return out


def rows_from_paper_db(
    db,
    symbol: str | None = None,
    include_sim: bool = False,
    since_ts: int | None = None,
    cost_model: CostModel | None = None,
    source_key: str | None = None,
) -> list[dict]:
    """Decided rows from the real paper book (TP_HIT / STOP_LOSS).

    Holding time here is measured, not assumed: ``closed_ts - opened_ts``.
    ``since_ts`` bounds ``closed_ts`` (the same era-separation the
    backtest book uses, on the column paper trades actually close on).
    """
    rows = db.decided_paper_rows(
        symbol=symbol,
        exclude_sim=not include_sim,
        since_ts=since_ts,
        source_key=source_key,
    )
    out = []
    for d in rows:
        opened = d.get("opened_ts")
        closed = d.get("closed_ts")
        hold = None
        if opened and closed and closed >= opened:
            hold = (closed - opened) / MS_PER_HOUR
        ts = closed or opened or d.get("created_ts")
        out.append(
            _row(
                ts=ts,
                side=d.get("action"),
                setup=d.get("plan_type"),
                regime=d.get("regime"),
                r=d.get("rr_achieved") or 0.0,
                outcome=d.get("outcome"),
                holding_hours=hold,
                symbol=d.get("symbol"),
                timeframe=d.get("timeframe"),
                source="paper",
                entry=d.get("entry"),
                stop_loss=d.get("stop_loss"),
                r_net=d.get("rr_net"),
                fee_r=d.get("fee_r"),
                slip_r=d.get("slip_r"),
                funding_r=d.get("funding_r"),
                cost_r=d.get("cost_r"),
                cost_model=cost_model,
                exchange=d.get("exchange"),
                market=d.get("market"),
                price_type=d.get("price_type"),
                sentiment_bucket=d.get("sentiment_bucket"),
                sentiment_score=d.get("sentiment_score"),
                sentiment_intensity=d.get("sentiment_intensity"),
            )
        )
    return out


# ──────────────────────────────────────────────────────────────────────────
# Metrics — one block, computed the same way for every split
# ──────────────────────────────────────────────────────────────────────────
def _empty_stats() -> dict:
    return {
        "n": 0,
        "decided": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "expectancy": 0.0,
        "avg_win_r": None,
        "avg_loss_r": None,
        "pf": None,
        "total_r": 0.0,
        "max_drawdown_r": 0.0,
        "sharpe": None,
        "sortino": None,
        "calmar": None,
        "stdev_r": None,
        "best_r": None,
        "worst_r": None,
        "max_win_streak": 0,
        "max_loss_streak": 0,
        # Net metrics (P12.6)
        "wins_net": 0,
        "losses_net": 0,
        "win_rate_net": None,
        "expectancy_net": 0.0,
        "avg_win_r_net": None,
        "avg_loss_r_net": None,
        "pf_net": None,
        "total_r_net": 0.0,
        "max_drawdown_r_net": 0.0,
        "sharpe_net": None,
        "sortino_net": None,
        "calmar_net": None,
        "stdev_r_net": None,
        "best_r_net": None,
        "worst_r_net": None,
        "max_win_streak_net": 0,
        "max_loss_streak_net": 0,
        # Cost breakdown
        "fee_r": 0.0,
        "slip_r": 0.0,
        "funding_r": 0.0,
        "cost_r": 0.0,
        "avg_holding_hours": None,
        "median_holding_hours": None,
        "holding_samples": 0,
        # Effective sample size (P12.3.3) — overlap-corrected, honest counts
        "n_eff": 0.0,
        "overlap": None,
        "expectancy_se": None,
        "expectancy_ci95": None,
        "expectancy_net_se": None,
        "expectancy_net_ci95": None,
    }


def max_drawdown_r(r_values: list[float]) -> float:
    """Peak-to-trough drawdown of the cumulative R curve, in R units."""
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for r in r_values:
        equity += r
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(abs(worst), 3)


def _streaks(r_values: list[float]) -> tuple[int, int]:
    cur_w = cur_l = max_w = max_l = 0
    for r in r_values:
        if r > 0:
            cur_w += 1
            cur_l = 0
            max_w = max(max_w, cur_w)
        elif r <= 0:
            cur_l += 1
            cur_w = 0
            max_l = max(max_l, cur_l)
    return max_w, max_l


# ──────────────────────────────────────────────────────────────────────────
# Effective sample size (P12.3.3)
# ──────────────────────────────────────────────────────────────────────────
def overlap_factor(row: dict, default_step: int = BACKTEST_STEP) -> float:
    """How many walk-forward samples this row's evaluation window overlaps.

    A walk-forward grade steps ``step`` bars and follows each plan over
    ``horizon_bars`` future bars, so consecutive samples share
    ``horizon_bars - step`` bars.  The overlap factor is
    ``horizon_bars / step`` — one independent observation per full window.

    Paper trades are real, non-overlapping positions → factor 1.0.  A
    backtest row with no recorded horizon / timeframe / step is treated as
    independent (1.0) rather than guessed: silence is not an edge, but
    neither is inventing a divisor.
    """
    if (row.get("source") or "") != "backtest":
        return 1.0
    horizon_hours = row.get("horizon_hours")
    timeframe = row.get("timeframe")
    tf_ms = TIMEFRAME_TO_MS.get(timeframe) if timeframe else None
    if not horizon_hours or not tf_ms:
        return 1.0
    step = row.get("step") or default_step
    if step <= 0:
        step = default_step
    horizon_bars = max(1, int(float(horizon_hours) * 3_600_000 / tf_ms))
    return max(1.0, horizon_bars / step)


def effective_sample_size(
    rows: list[dict], default_step: int = BACKTEST_STEP
) -> tuple[float, float | None]:
    """``(n_eff, overlap)`` — honest independent sample size.

    ``n_eff = Σ 1/overlap_i``: each row contributes one independent unit
    divided by its own window-overlap factor.  ``overlap`` is the aggregate
    ``n / n_eff`` (the effective divisor, ≈ horizon_bars/step for a
    homogeneous walk-forward book).
    """
    if not rows:
        return 0.0, None
    n_eff = sum(1.0 / overlap_factor(r, default_step) for r in rows)
    overlap = (len(rows) / n_eff) if n_eff > 0 else None
    return n_eff, (round(overlap, 2) if overlap is not None else None)


def trade_stats(rows: list[dict], step: int = BACKTEST_STEP) -> dict:
    """The scorecard block for one set of decided trades (gross and net)."""
    if not rows:
        return _empty_stats()
    rows = sorted(rows, key=lambda r: (r["ts"] is None, r["ts"]))

    # Ensure every row has r_net and cost fields
    for r in rows:
        if r.get("r_net") is None or r.get("fee_r") is None:
            c = calculate_trade_cost(
                entry=r.get("entry"),
                stop_loss=r.get("stop_loss"),
                action=r.get("side", "BUY"),
                gross_r=r.get("r", 0.0),
                holding_hours=r.get("holding_hours"),
                symbol=r.get("symbol", "BTCUSDT"),
                ts=r.get("ts"),
            )
            r["r_net"] = c.net_r
            r["fee_r"] = c.fee_r
            r["slip_r"] = c.slip_r
            r["funding_r"] = c.funding_r
            r["cost_r"] = c.total_cost_r

    r_values = [float(r["r"]) for r in rows]
    r_net_values = [float(r["r_net"]) for r in rows]
    n = len(r_values)
    n_eff, overlap = effective_sample_size(rows, default_step=step)

    # ── Gross metrics ──────────────────────────────────────────────────────
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (
        round(gross_win / gross_loss, 3)
        if gross_loss > 0
        else (99.0 if gross_win > 0 else None)
    )
    mean_r = sum(r_values) / n
    stdev = statistics.stdev(r_values) if n > 1 else None
    sharpe = round(mean_r / stdev, 3) if stdev else None
    downside = math.sqrt(sum(min(r, 0.0) ** 2 for r in r_values) / n)
    sortino = round(mean_r / downside, 3) if downside > 0 else None
    dd = max_drawdown_r(r_values)
    total_r = round(sum(r_values), 3)
    calmar = round(total_r / dd, 3) if dd > 0 else None
    max_w, max_l = _streaks(r_values)

    # ── Net metrics (P12.6: E_net = E_gross − fees − slip − funding) ────────
    wins_net = [r for r in r_net_values if r > 0]
    losses_net = [r for r in r_net_values if r <= 0]
    net_win_sum = sum(wins_net)
    net_loss_sum = abs(sum(losses_net))
    pf_net = (
        round(net_win_sum / net_loss_sum, 3)
        if net_loss_sum > 0
        else (99.0 if net_win_sum > 0 else None)
    )
    mean_r_net = sum(r_net_values) / n
    stdev_net = statistics.stdev(r_net_values) if n > 1 else None
    sharpe_net = round(mean_r_net / stdev_net, 3) if stdev_net else None
    downside_net = math.sqrt(sum(min(r, 0.0) ** 2 for r in r_net_values) / n)
    sortino_net = round(mean_r_net / downside_net, 3) if downside_net > 0 else None
    dd_net = max_drawdown_r(r_net_values)
    total_r_net = round(sum(r_net_values), 3)
    calmar_net = round(total_r_net / dd_net, 3) if dd_net > 0 else None
    max_w_net, max_l_net = _streaks(r_net_values)

    # ── Cost breakdown averages ─────────────────────────────────────────────
    fee_r_avg = round(sum(float(r.get("fee_r", 0.0)) for r in rows) / n, 4)
    slip_r_avg = round(sum(float(r.get("slip_r", 0.0)) for r in rows) / n, 4)
    funding_r_avg = round(sum(float(r.get("funding_r", 0.0)) for r in rows) / n, 4)
    cost_r_avg = round(sum(float(r.get("cost_r", 0.0)) for r in rows) / n, 4)

    holds = [r["holding_hours"] for r in rows if r.get("holding_hours") is not None]

    # ── Effective sample size: honest standard error & 95% CI (P12.3.3) ────
    # SE = σ / √N_eff.  The raw N would silently narrow every interval by the
    # overlap factor (~30× on a 24h/15m walk-forward); N_eff does not.
    def _ci(mean: float, sd: float | None) -> tuple:
        if not sd or n_eff <= 0:
            return None, None
        se = sd / math.sqrt(n_eff)
        z = 1.96  # 95% two-sided
        return round(se, 4), [round(mean - z * se, 4), round(mean + z * se, 4)]

    expectancy_se, expectancy_ci95 = _ci(mean_r, stdev)
    expectancy_net_se, expectancy_net_ci95 = _ci(mean_r_net, stdev_net)

    return {
        "n": n,
        "decided": n,
        "n_eff": round(n_eff, 2),
        "overlap": overlap,
        "expectancy_se": expectancy_se,
        "expectancy_ci95": expectancy_ci95,
        "expectancy_net_se": expectancy_net_se,
        "expectancy_net_ci95": expectancy_net_ci95,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 3),
        "expectancy": round(mean_r, 3),
        "avg_win_r": round(gross_win / len(wins), 3) if wins else None,
        "avg_loss_r": round(sum(losses) / len(losses), 3) if losses else None,
        "pf": pf,
        "total_r": total_r,
        "max_drawdown_r": dd,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "stdev_r": round(stdev, 3) if stdev is not None else None,
        "best_r": round(max(r_values), 3),
        "worst_r": round(min(r_values), 3),
        "max_win_streak": max_w,
        "max_loss_streak": max_l,
        # Net metrics (P12.6)
        "wins_net": len(wins_net),
        "losses_net": len(losses_net),
        "win_rate_net": round(len(wins_net) / n, 3),
        "expectancy_net": round(mean_r_net, 3),
        "avg_win_r_net": round(net_win_sum / len(wins_net), 3) if wins_net else None,
        "avg_loss_r_net": round(sum(losses_net) / len(losses_net), 3)
        if losses_net
        else None,
        "pf_net": pf_net,
        "total_r_net": total_r_net,
        "max_drawdown_r_net": dd_net,
        "sharpe_net": sharpe_net,
        "sortino_net": sortino_net,
        "calmar_net": calmar_net,
        "stdev_r_net": round(stdev_net, 3) if stdev_net is not None else None,
        "best_r_net": round(max(r_net_values), 3),
        "worst_r_net": round(min(r_net_values), 3),
        "max_win_streak_net": max_w_net,
        "max_loss_streak_net": max_l_net,
        # Cost breakdown
        "fee_r": fee_r_avg,
        "slip_r": slip_r_avg,
        "funding_r": funding_r_avg,
        "cost_r": cost_r_avg,
        "avg_holding_hours": round(sum(holds) / len(holds), 2) if holds else None,
        "median_holding_hours": (round(statistics.median(holds), 2) if holds else None),
        "holding_samples": len(holds),
    }


def _span(rows: list[dict]) -> dict:
    """Sample span and trade frequency — context, not a risk metric."""
    ts = [r["ts"] for r in rows if r.get("ts")]
    if len(ts) < 2:
        return {}
    span_ms = max(ts) - min(ts)
    if span_ms <= 0:
        return {}
    days = span_ms / (24 * MS_PER_HOUR)
    return {
        "span_days": round(days, 1),
        "trades_per_day": round(len(ts) / days, 2) if days else None,
    }


def _split(
    rows: list[dict],
    key: str,
    order: tuple | None = None,
    step: int = BACKTEST_STEP,
    empty_label: str | None = "UNKNOWN",
) -> dict:
    """Group rows by a field and score each bucket.

    ``empty_label=None`` keeps an empty value as its own real bucket instead
    of relabelling it ``UNKNOWN`` — required for the P12.11 source split,
    where ``""`` is not missing data but the *name* of the canonical live
    series.
    """
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        raw = r.get(key)
        if empty_label is None:
            k = "" if raw is None else str(raw)
        else:
            k = str(raw or empty_label)
        buckets.setdefault(k, []).append(r)
    keys = list(order) if order else sorted(buckets, key=lambda k: -len(buckets[k]))
    return {
        k: trade_stats(buckets.get(k, []), step=step)
        for k in keys
        if order or buckets.get(k)
    }


# ──────────────────────────────────────────────────────────────────────────
# Conditioned Expectancy (P12.6)
# ──────────────────────────────────────────────────────────────────────────


def _funding_regime_label(r: dict) -> str:
    f = r.get("funding_rate")
    if f is None:
        return "NEUTRAL"
    if f > 0.00005:
        return "POSITIVE"
    if f < -0.00005:
        return "NEGATIVE"
    return "NEUTRAL"


def _cvd_regime_label(r: dict) -> str:
    z = r.get("cvd_z")
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return "NEUTRAL_FLOW"
    if z > 1.0:
        return "BULLISH_FLOW"
    if z < -1.0:
        return "BEARISH_FLOW"
    return "NEUTRAL_FLOW"


def conditioned_splits(rows: list[dict], step: int = BACKTEST_STEP) -> dict:
    """Conditioned splits over derivatives & order-flow features (P12.6)."""
    # Funding regime
    by_funding: dict[str, list[dict]] = {}
    for r in rows:
        lbl = _funding_regime_label(r)
        by_funding.setdefault(lbl, []).append(r)

    # CVD flow
    by_cvd: dict[str, list[dict]] = {}
    for r in rows:
        lbl = _cvd_regime_label(r)
        by_cvd.setdefault(lbl, []).append(r)

    return {
        "by_funding": {
            k: trade_stats(v, step=step) for k, v in sorted(by_funding.items())
        },
        "by_cvd": {k: trade_stats(v, step=step) for k, v in sorted(by_cvd.items())},
    }


# ──────────────────────────────────────────────────────────────────────────
# The scorecard
# ──────────────────────────────────────────────────────────────────────────
def _source_inventory(rows: list[dict]) -> dict:
    """P12.11 — which price series this book was built from.

    A scorecard that silently pools a live Binance book with a bid-only
    Dukascopy research import is not one number, it is two. The report says
    so: ``mixed`` is true whenever more than one source contributed, and
    ``one_sided`` names any series that cannot be round-tripped at the
    printed price.
    """
    from data.provenance import describe_source, is_canonical, is_one_sided

    counts: dict[str, int] = {}
    for r in rows:
        key = r.get("source_key") or ""
        counts[key] = counts.get(key, 0) + 1
    keys = sorted(counts, key=lambda k: (-counts[k], k))
    return {
        "keys": keys,
        "counts": counts,
        "mixed": len(keys) > 1,
        "canonical_only": bool(keys) and all(is_canonical(k) for k in keys),
        "one_sided": [k for k in keys if is_one_sided(k)],
        "labels": {k: describe_source(k) for k in keys},
    }


def build_scorecard(
    rows: list[dict],
    *,
    symbol: str = "",
    timeframe: str = "",
    source: str = "",
    min_decided: int = DEFAULT_MIN_DECIDED,
    criteria: dict | None = None,
    note: str = "",
    conditioned: bool = False,
    quality: bool = False,
    step: int = BACKTEST_STEP,
) -> dict:
    """Assemble the boxed report from already-graded rows.

    Pure: same rows in → same report out.  Never raises on an empty sample;
    an empty book is reported as INSUFFICIENT_DATA, which is the truth.
    The verdict is evaluated NET of costs (P12.6).

    ``step`` is the walk-forward bar step used to grade backtest rows, used
    to correct sample counts for window overlap (P12.3.3).  Rows that carry
    their own recorded ``step`` (from the store) override it.

    ``quality`` (P12.4) embeds the Backtest Quality Score 0–100 for the
    same book — same rows, same computation as `python main.py quality`
    (minus the plateau sweep, which needs re-graded neighbourhoods).
    """
    criteria = criteria or VALIDATION_CRITERIA
    rows = [r for r in rows if r.get("r") is not None]
    overall = trade_stats(rows, step=step)
    overall.update(_span(rows))

    # Bar is evaluated NET of costs (P12.6)
    bar_met, bar_unmet = meets_bar(overall, min_decided=min_decided, criteria=criteria)
    if overall["n"] < min_decided:
        status = "INSUFFICIENT_DATA"
        reason = (
            f"{overall['n']} decided trades < min {min_decided} — "
            f"not enough evidence to judge the edge"
        )
    elif bar_met:
        status = "PASS"
        reason = (
            f"expectancy net {overall['expectancy_net']:+.3f}R (gross {overall['expectancy']:+.3f}R), "
            f"WR {overall['win_rate_net']:.1%}, PF {overall['pf_net']} — "
            f"clears the graduation bar"
        )
    else:
        status = "FAIL"
        reason = "; ".join(bar_unmet) or "below the graduation bar"

    symbols = sorted({r["symbol"] for r in rows if r.get("symbol")})
    sources = sorted({r["source"] for r in rows if r.get("source")})

    report = {
        "ok": True,
        "meta": {
            "symbol": symbol or (symbols[0] if len(symbols) == 1 else "ALL"),
            "symbols": symbols,
            "timeframe": timeframe,
            "source": source or "+".join(sources),
            "sources": sources,
            "rows": len(rows),
            "min_decided": min_decided,
            "generated_ts": int(time.time() * 1000),
            "note": note,
            "first_ts": min((r["ts"] for r in rows if r.get("ts")), default=None),
            "last_ts": max((r["ts"] for r in rows if r.get("ts")), default=None),
            "net_evaluation": True,
            "step": step,
        },
        "overall": overall,
        "by_side": _split(rows, "side", order=SIDES, step=step),
        "by_regime": _split(rows, "regime", step=step),
        "by_session": _split(rows, "session", order=SESSION_NAMES, step=step),
        "by_setup": _split(rows, "setup", step=step),
        # P16 — the sentiment colour proof: does what the strip painted
        # actually correlate with what the trades earned? UNKNOWN keeps
        # pre-P16 rows visible instead of silently disappearing.
        "by_sentiment": _split(
            rows, "sentiment_bucket", order=BUCKETS + ("UNKNOWN",), step=step
        ),
        # The deepening hypothesis in its own split: within a coloured
        # condition, does more time-in-condition (DEEP) beat a fresh reading?
        "by_sentiment_depth": _split(
            rows, "sentiment_depth", order=("DEEP", "FRESH", "SLATE"), step=step
        ),
        # P12.11 — the same block per price series, so a pooled book can
        # always be taken apart into the series that produced it.
        "by_source": _split(rows, "source_key", step=step, empty_label=None),
        "sources": _source_inventory(rows),
        "criteria": dict(criteria),
        "bar": {
            "met": bool(bar_met),
            "unmet": bar_unmet,
            "min_decided": min_decided,
            "evaluated_on": "net",
            # P12.3.3: the gate still reads raw N (min_decided revisit is a
            # later decision) — this flag is the honest signal that the
            # overlap-corrected sample is below the floor.
            "n_eff_below_min_decided": overall["n_eff"] < min_decided,
        },
        "verdict": {"status": status, "reason": reason},
    }
    if conditioned:
        report["conditioned"] = conditioned_splits(rows, step=step)
    if quality:
        from data.quality_score import backtest_quality_score

        report["quality"] = backtest_quality_score(
            rows, min_decided=min_decided, criteria=criteria, step=step
        )
    return report


def scorecard_from_db(
    symbol: str | None = None,
    source: str = "all",
    min_decided: int = DEFAULT_MIN_DECIDED,
    include_sim: bool = True,
    db=None,
    since_ts: int | None = None,
    until_ts: int | None = None,
    cost_model: CostModel | None = None,
    conditioned: bool = False,
    quality: bool = False,
    step: int = BACKTEST_STEP,
    source_key: str | None = None,
) -> dict:
    """Scorecard over what the desk has already graded and stored.

    ``source``: ``backtest`` | ``paper`` | ``all`` (both books combined).
    Paper trades exclude simulator samples unless ``include_sim`` — the live
    book and the walk-forward evidence are not the same thing.
    ``since_ts`` / ``until_ts`` bound the signal bar for era-separated runs.
    ``quality`` (P12.4) embeds the Backtest Quality Score block.
    ``source_key`` (P12.11) restricts the book to one price series, e.g.
    ``""`` for the canonical live Binance spot series or
    ``"dukascopy:spot:bid"`` for the XAU research import. ``None`` reads
    every source, and the report always names the sources it mixed.
    """
    if source not in ("backtest", "paper", "all"):
        return {"ok": False, "error": f"unknown source {source!r} (backtest|paper|all)"}

    from data.database import SignalDB

    owned = db is None
    db = db or SignalDB()
    try:
        rows: list[dict] = []
        if source in ("backtest", "all"):
            rows += rows_from_backtest_db(
                db,
                symbol=symbol,
                include_sim=include_sim,
                since_ts=since_ts,
                until_ts=until_ts,
                cost_model=cost_model,
                source_key=source_key,
            )
        if source in ("paper", "all"):
            rows += rows_from_paper_db(
                db,
                symbol=symbol,
                include_sim=include_sim,
                since_ts=since_ts,
                cost_model=cost_model,
                source_key=source_key,
            )
    finally:
        if owned:
            db.close()

    if not rows:
        hint = ""
        if source_key is not None:
            from data.provenance import describe_source

            hint = f" No decided rows carry source {describe_source(source_key)!r}."
        return {
            "ok": False,
            "error": (
                "No decided outcomes stored yet — run "
                "`python main.py backtest --save` (or the paper "
                "runner) first, then re-run the scorecard." + hint
            ),
            "source": source,
            "rows": 0,
            "source_key": source_key,
        }
    return build_scorecard(
        rows,
        symbol=symbol or "",
        source=source,
        min_decided=min_decided,
        note="stored outcomes (no re-grading)",
        conditioned=conditioned,
        quality=quality,
        step=step,
    )


def scorecard_from_store(
    exchange: str = "binance",
    market: str = "perp",
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    bars: int = 1000,
    horizons: list | None = None,
    min_bars: int | None = None,
    step: int = 3,
    min_confidence: int | None = None,
    min_decided: int = DEFAULT_MIN_DECIDED,
    cost_model: CostModel | None = None,
    conditioned: bool = False,
    quality: bool = False,
) -> dict:
    """Scorecard over a fresh walk-forward grade of the stored series.

    Delegates every grading decision to `data.backtester.run_backtest_on_store`
    — this function only summarises what that grader returned.
    """
    from config import BACKTEST_MIN_BARS, MIN_CONFIDENCE
    from data.backtester import run_backtest_on_store

    result = run_backtest_on_store(
        exchange=exchange,
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        horizons=horizons,
        min_bars=BACKTEST_MIN_BARS if min_bars is None else min_bars,
        step=step,
        min_confidence=MIN_CONFIDENCE if min_confidence is None else min_confidence,
    )
    if not result.get("ok", True) or result.get("error"):
        return {
            "ok": False,
            "error": result.get("error", "backtest failed"),
            "source": "store",
        }

    primary = (
        result.get("report", {}).get("meta", {}).get("horizons_hours") or [None]
    )[0]
    rows = rows_from_graded(
        result.get("graded", []),
        symbol=symbol,
        timeframe=timeframe,
        cost_model=cost_model,
        exchange=exchange,
        market=market,
        price_type=result.get("price_type"),
    )
    if not rows:
        return {
            "ok": False,
            "error": (
                f"Graded {len(result.get('graded', []))} plans but "
                f"none reached a decision (all OPEN or "
                f"NOT_TRIGGERED) — widen --bars or --horizons."
            ),
            "source": "store",
        }
    card = build_scorecard(
        rows,
        symbol=symbol,
        timeframe=timeframe,
        source="store",
        min_decided=min_decided,
        note=f"fresh walk-forward grade, primary horizon {primary}h",
        conditioned=conditioned,
        quality=quality,
        step=step,
    )
    card["meta"]["bars_read"] = result.get("bars_read")
    card["meta"]["store_path"] = result.get("store_path")
    card["meta"]["primary_horizon_hours"] = primary
    return card


# ──────────────────────────────────────────────────────────────────────────
# Boxed printer — one command, one block
# ──────────────────────────────────────────────────────────────────────────
W = 82


def _fmt_pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "n/a"


def _fmt(v, spec: str = "+.3f") -> str:
    return format(v, spec) if isinstance(v, (int, float)) else "n/a"


def _fmt_hours(v) -> str:
    return f"{v:.1f}h" if isinstance(v, (int, float)) else "n/a"


def _split_line(label: str, s: dict) -> str:
    pf_net = (
        str(s.get("pf_net", s.get("pf")))
        if (s.get("pf_net") is not None or s.get("pf") is not None)
        else "n/a"
    )
    hold = _fmt_hours(s.get("avg_holding_hours"))
    wr_net = s.get("win_rate_net", s.get("win_rate"))
    e_gross = s.get("expectancy")
    e_net = s.get("expectancy_net", e_gross)
    tot_r_net = s.get("total_r_net", s.get("total_r"))
    return (
        f"  {label:<18} {s['n']:>5} {_fmt_pct(wr_net):>7} "
        f"{_fmt(e_gross):>8} {_fmt(e_net):>8} {pf_net:>7} "
        f"{_fmt(tot_r_net, '+.1f'):>9} {hold:>7}"
    )


def _split_header(title: str) -> str:
    return (
        f"{title}\n"
        f"  {'':<18} {'n':>5} {'WR_net':>7} {'E_gross':>8} {'E_net':>8} {'PF_net':>7} {'totR_net':>9} "
        f"{'hold':>7}"
    )


def print_scorecard(report: dict) -> None:
    """The boxed block.  Everything a review needs, nothing it does not."""
    if not report.get("ok"):
        print("STRATEGY SCORECARD — cannot run")
        print(f"  {report.get('error', 'unknown error')}")
        return

    m, o = report["meta"], report["overall"]
    print("=" * W)
    print(
        f"STRATEGY SCORECARD  {m['symbol']}"
        f"{' ' + m['timeframe'] if m['timeframe'] else ''}"
        f"   source: {m['source']}"
    )
    span = ""
    if m.get("span_days") or o.get("span_days"):
        span = f"   span {o.get('span_days')}d"
    n_eff_bits = ""
    if o.get("n_eff"):
        ov = f", overlap ×{o['overlap']}" if o.get("overlap") else ""
        n_eff_bits = f"   (~{o['n_eff']} independent{ov})"
    print(
        f"decided trades {o['n']}{n_eff_bits}   min_decided {m['min_decided']}{span}"
        f"{'   ' + m['note'] if m.get('note') else ''}"
    )
    print("-" * W)
    ci = ""
    if o.get("expectancy_net_ci95"):
        lo, hi = o["expectancy_net_ci95"]
        ci = f"   95% CI net [{lo:+.3f}, {hi:+.3f}]R (N_eff={o['n_eff']})"
    print(
        f"  expectancy   {_fmt(o['expectancy'])}R gross → {_fmt(o['expectancy_net'])}R net  "
        f"(cost {_fmt(-o['cost_r'])}R: fee {_fmt(o['fee_r'])}R, slip {_fmt(o['slip_r'])}R, fund {_fmt(o['funding_r'])}R)"
    )
    if ci:
        print(f"  expectancy CI{ci}")
    print(
        f"  win rate     {_fmt_pct(o['win_rate'])} gross → {_fmt_pct(o['win_rate_net'])} net "
        f"({o.get('wins_net', o['wins'])}W/{o.get('losses_net', o['losses'])}L net)"
    )
    pf_g = str(o["pf"]) if o["pf"] is not None else "n/a"
    pf_n = (
        str(o.get("pf_net", o["pf"]))
        if o.get("pf_net") is not None or o["pf"] is not None
        else "n/a"
    )
    print(
        f"  profit factor {pf_g} gross → {pf_n} net      "
        f"total R   {_fmt(o['total_r'], '+.2f')}R gross → {_fmt(o.get('total_r_net', o['total_r']), '+.2f')}R net"
    )
    avg_win_g = _fmt(o["avg_win_r"])
    avg_win_n = _fmt(o.get("avg_win_r_net", o["avg_win_r"]))
    avg_loss_g = _fmt(o["avg_loss_r"])
    avg_loss_n = _fmt(o.get("avg_loss_r_net", o["avg_loss_r"]))
    print(
        f"  avg win      {avg_win_g}R gross → {avg_win_n}R net  "
        f"avg loss  {avg_loss_g}R gross → {avg_loss_n}R net"
    )
    dd_g = f"{o['max_drawdown_r']:.2f}R"
    dd_n = f"{o.get('max_drawdown_r_net', o['max_drawdown_r']):.2f}R"
    w_streak = o.get("max_win_streak_net", o["max_win_streak"])
    l_streak = o.get("max_loss_streak_net", o["max_loss_streak"])
    print(
        f"  max drawdown {dd_g} gross → {dd_n} net  "
        f"streaks   {w_streak}W / {l_streak}L net"
    )
    sharpe_g = str(o["sharpe"]) if o["sharpe"] is not None else "n/a"
    sharpe_n = (
        str(o.get("sharpe_net", o["sharpe"]))
        if (o.get("sharpe_net") is not None or o["sharpe"] is not None)
        else "n/a"
    )
    sortino_g = str(o["sortino"]) if o["sortino"] is not None else "n/a"
    sortino_n = (
        str(o.get("sortino_net", o["sortino"]))
        if (o.get("sortino_net") is not None or o["sortino"] is not None)
        else "n/a"
    )
    calmar_g = str(o["calmar"]) if o["calmar"] is not None else "n/a"
    calmar_n = (
        str(o.get("calmar_net", o["calmar"]))
        if (o.get("calmar_net") is not None or o["calmar"] is not None)
        else "n/a"
    )
    sharpe_extra = (
        f"   ({o['trades_per_day']} trades/day — per-trade, NOT annualised)"
        if o.get("trades_per_day") is not None
        else "   (per-trade, not annualised)"
    )
    print(
        f"  Sharpe {sharpe_g} → {sharpe_n} net   "
        f"Sortino {sortino_g} → {sortino_n} net   "
        f"Calmar {calmar_g} → {calmar_n} net{sharpe_extra}"
    )
    hold = o.get("avg_holding_hours")
    if hold is not None:
        print(
            f"  holding time avg {hold:.1f}h   median "
            f"{o['median_holding_hours']:.1f}h   "
            f"({o['holding_samples']}/{o['n']} trades timed)"
        )
    else:
        print(
            "  holding time n/a — these outcomes were graded before "
            "holding time was recorded"
        )
    print("-" * W)
    print(_split_header("by side (long / short):"))
    for side in SIDES:
        s = report["by_side"].get(side)
        if s:
            print(_split_line(side, s))
    print(_split_header("by regime:"))
    for name, s in report["by_regime"].items():
        print(_split_line(name[:18], s))
    print(_split_header("by session (UTC):"))
    for name in SESSION_NAMES:
        s = report["by_session"].get(name)
        if s:
            print(_split_line(name, s))
    print(_split_header("by setup:"))
    for name, s in report["by_setup"].items():
        print(_split_line(name[:18], s))
    # P16 — the sentiment colour proof, in the same boxed block as the CLI.
    if "by_sentiment" in report:
        from engine.sentiment import bucket_label

        print(_split_header("by sentiment colour (P16 — does the colour pay?):"))
        for name, s in report["by_sentiment"].items():
            if s.get("n"):
                print(_split_line(bucket_label(name), s))
        print(_split_header("by colour depth (fresh vs deep — time in condition):"))
        for name, s in report["by_sentiment_depth"].items():
            if s.get("n"):
                print(_split_line(name, s))
    # P12.11 — say which price series this book was built from, and split it.
    srcs = report.get("sources") or {}
    if srcs.get("keys"):
        from data.provenance import describe_source

        if srcs.get("mixed") or not srcs.get("canonical_only"):
            print(_split_header("by source series (P12.11):"))
            for name, s in report.get("by_source", {}).items():
                label = describe_source(name)
                print(_split_line(label[:18], s))
            if srcs.get("mixed"):
                print(
                    "  ⚠ this book POOLS several price series — the headline "
                    "number is a blend, not one market"
                )
            for k in srcs.get("one_sided", []):
                print(
                    f"  ⚠ {describe_source(k)} is one-sided: the printed "
                    f"price is not an executable round trip (research only)"
                )
    if "conditioned" in report:
        print("-" * W)
        print(_split_header("by funding regime:"))
        for name, s in report["conditioned"].get("by_funding", {}).items():
            print(_split_line(name[:18], s))
        print(_split_header("by order flow (CVD):"))
        for name, s in report["conditioned"].get("by_cvd", {}).items():
            print(_split_line(name[:18], s))
    print("-" * W)
    c = report["criteria"]
    v = report["verdict"]
    icon = {"PASS": "🟢", "FAIL": "🔴", "INSUFFICIENT_DATA": "⚪"}.get(
        v["status"], "❓"
    )
    print(
        f"bar (NET): expectancy >= {c['expectancy']:+.2f}R   "
        f"win rate > {c['win_rate']:.0%}   PF >= {c['pf']}   "
        f"decided >= {report['bar']['min_decided']}"
    )
    print(f"VERDICT  {icon} {v['status']}  —  {v['reason']}")
    if report["bar"].get("n_eff_below_min_decided"):
        print(
            f"  ⚠ overlap-corrected sample {o['n_eff']} < min_decided "
            f"{report['bar']['min_decided']} — the raw count overstates the "
            f"evidence ~×{o['overlap']}"
        )
    if v["status"] != "PASS":
        print("  This is a scorecard, not permission. The graduation bar is unchanged.")
    # P12.4 — Backtest Quality Score 0–100 (embedded by --quality).
    q = report.get("quality")
    if q and q.get("ok") and q.get("quality") is not None:
        comp = q.get("components") or {}
        bits = []
        for key in ("edge", "robustness", "sample"):
            b = comp.get(key)
            if b and b.get("score") is not None:
                bits.append(f"{key} {_fmt(b['score'], '.0f')}")
        plat = comp.get("plateau")
        if plat and plat.get("score") is not None:
            bits.append(f"plateau {_fmt(plat['score'], '.0f')}")
        else:
            bits.append("plateau n/a (re-grade sweep via `python main.py quality`)")
        cap_note = (
            ("  🛑 isolated parameter peak — total CAPPED at 50 (a fit, not an edge)")
            if q.get("plateau_cap")
            else ""
        )
        print("=" * W)
        print(
            f"BACKTEST QUALITY  {_fmt(q['quality'], '.1f')}/100  "
            f"band: {q['band']}   "
            f"{' · '.join(bits)}"
        )
        if cap_note:
            print(cap_note)
        print(
            "  A quality score reports robustness; it does not grant "
            "permission. The graduation bar is unchanged."
        )
    print("=" * W)
