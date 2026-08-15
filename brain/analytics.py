"""Risk / execution analytics built on the decided-paper book.

Tools for the "what is my real risk / edge" question that the single
profit-factor number cannot answer:

  * mae_mfe_summary — how far against / for did each trade go, in R?  Tells
    you whether your stops are too tight (MAE routinely approaches your stop)
    or your targets are unreachable (MFE caps well below target).

  * monte_carlo_equity — resample the realised trade outcomes thousands of
    times to get a *distribution* of terminal equity and drawdown, not a single
    hopeful backtest line.  This is the honest picture of variance before you
    trust PROGRESSION=micro.

  * monte_carlo_ruin_table — sweep position size (risk %/trade) and read off
    the expected maximum drawdown, risk-of-ruin, longest losing streak and
    median time-to-recovery.  Uses NET realised R so costs are inside the
    estimate (P12.7).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from config import RISK_PCT


def mae_mfe_summary(db, plan_type: Optional[str] = None) -> dict:
    """MAE / MFE statistics per setup, in R (price excursion / planned risk).

    Returns per-setup aggregates plus an overall insight.  Runs on the real
    paper book (decided_paper_rows with exclude_sim=True): simulator samples
    are calibration evidence, not the live book the desk should review.
    """
    rows = db.decided_paper_rows(exclude_sim=True)
    if not rows:
        return {"available": False, "note": "no decided paper trades yet"}

    by_type: dict[str, dict] = {}
    for r in rows:
        if plan_type and r.get("plan_type") != plan_type:
            continue
        pt = r.get("plan_type") or "unknown"
        entry = r.get("entry")
        sl = r.get("stop_loss")
        risk = abs(entry - sl) if (entry is not None and sl is not None) else None
        mae = r.get("mae")
        mfe = r.get("mfe")
        rr = r.get("rr_achieved")
        mae_r = (mae / risk) if (mae is not None and risk) else None
        mfe_r = (mfe / risk) if (mfe is not None and risk) else None
        bucket = by_type.setdefault(pt, {
            "n": 0, "mae_r": [], "mfe_r": [], "wins": 0, "losses": 0,
        })
        bucket["n"] += 1
        if mae_r is not None:
            bucket["mae_r"].append(mae_r)
        if mfe_r is not None:
            bucket["mfe_r"].append(mfe_r)
        if rr is not None:
            if rr > 0:
                bucket["wins"] += 1
            elif rr < 0:
                bucket["losses"] += 1

    summary = {}
    for pt, b in by_type.items():
        mae_r = b["mae_r"]
        mfe_r = b["mfe_r"]
        win_rate = b["wins"] / max(1, b["wins"] + b["losses"])
        summary[pt] = {
            "n": b["n"],
            "win_rate": round(win_rate, 3),
            "avg_mae_r": round(float(np.mean(mae_r)), 3) if mae_r else None,
            "max_mae_r": round(float(np.max(mae_r)), 3) if mae_r else None,
            "avg_mfe_r": round(float(np.mean(mfe_r)), 3) if mfe_r else None,
            "max_mfe_r": round(float(np.max(mfe_r)), 3) if mfe_r else None,
        }

    # overall insight across every setup the desk has actually traded
    all_mae = [v for b in by_type.values() for v in b["mae_r"]]
    all_mfe = [v for b in by_type.values() for v in b["mfe_r"]]
    insight = _mae_mfe_insight(all_mae, all_mfe)
    return {
        "available": True,
        "by_setup": summary,
        "overall": {
            "n": sum(b["n"] for b in by_type.values()),
            "avg_mae_r": round(float(np.mean(all_mae)), 3) if all_mae else None,
            "avg_mfe_r": round(float(np.mean(all_mfe)), 3) if all_mfe else None,
        },
        "insight": insight,
    }


def _mae_mfe_insight(mae_r: list[float], mfe_r: list[float]) -> list[str]:
    out = []
    if not mae_r or not mfe_r:
        return ["not enough excursion data yet"]
    avg_mae = float(np.mean(mae_r))
    avg_mfe = float(np.mean(mfe_r))
    if avg_mae >= 0.9:
        out.append(f"MAE averages {avg_mae:.2f}R — you are getting stopped out "
                   f"close to your stop; entries are acceptable, keep the risk "
                   f"discipline")
    elif avg_mae <= 0.4:
        out.append(f"MAE averages only {avg_mae:.2f}R against a typical 1R stop — "
                   f"your stops may be too tight; consider whether noise is taking "
                   f"you out before the move")
    if avg_mfe >= 1.5:
        out.append(f"MFE averages {avg_mfe:.2f}R — the setups run well past 1R; a "
                   f"runner (move stop to breakeven at 1R, trail the rest) would "
                   f"capture more")
    elif avg_mfe <= 0.8 and avg_mfe < avg_mae:
        out.append(f"MFE ({avg_mfe:.2f}R) is below MAE ({avg_mae:.2f}R) — trades "
                   f"rarely run in your favour; review entries / setup quality "
                   f"before increasing size")
    if not out:
        out.append(f"MAE {avg_mae:.2f}R vs MFE {avg_mfe:.2f}R — reasonable "
                   f"asymmetry, keep executing")
    return out


def monte_carlo_equity(db, start: float = 10_000.0, risk_pct: float = None,
                       samples: int = 2000, seed: Optional[int] = None) -> dict:
    """Distribution of terminal equity and drawdown from the realised trade book.

    Resamples the decided paper-trade outcomes (with replacement) ``samples``
    times, grows an equity curve at ``risk_pct`` % of equity per trade, and
    reports the median / percentile terminal equity and the drawdown
    distribution.  This is the honest variance picture behind a single
    profit-factor number.
    """
    rows = db.decided_paper_rows(exclude_sim=True)
    outcomes = [float(r["rr_achieved"]) for r in rows
                if r.get("rr_achieved") is not None]
    if not outcomes:
        return {"available": False, "note": "no decided paper trades yet"}

    risk_pct = risk_pct if risk_pct is not None else RISK_PCT
    rng = np.random.default_rng(seed)
    n = len(outcomes)
    terminals = np.zeros(samples)
    max_dds = np.zeros(samples)
    for s in range(samples):
        perm = rng.choice(outcomes, size=n, replace=True)
        equity = start
        peak = start
        dd = 0.0
        for rr in perm:
            equity *= (1.0 + rr * risk_pct / 100.0)
            if equity > peak:
                peak = equity
            dd = max(dd, 1.0 - equity / peak)
        terminals[s] = equity
        max_dds[s] = dd

    return {
        "available": True,
        "start": start,
        "risk_pct": risk_pct,
        "n_trades": n,
        "samples": samples,
        "terminal": {
            "median": round(float(np.median(terminals)), 2),
            "mean": round(float(np.mean(terminals)), 2),
            "p5": round(float(np.percentile(terminals, 5)), 2),
            "p95": round(float(np.percentile(terminals, 95)), 2),
            "prob_profit": round(float(np.mean(terminals > start)), 3),
        },
        "drawdown": {
            "median_pct": round(float(np.median(max_dds)) * 100, 2),
            "p95_pct": round(float(np.percentile(max_dds, 95)) * 100, 2),
        },
    }


def _net_outcome(row: dict) -> float:
    """Return the net R for a decided paper row, computing costs if needed."""
    rr = float(row.get("rr_achieved") or 0.0)
    rr_net = row.get("rr_net")
    if rr_net is not None:
        return float(rr_net)

    from data.costs import calculate_trade_cost

    opened = row.get("opened_ts")
    closed = row.get("closed_ts")
    hold_hours = None
    if opened and closed and closed >= opened:
        hold_hours = (closed - opened) / 3_600_000.0

    cost = calculate_trade_cost(
        entry=row.get("entry"),
        stop_loss=row.get("stop_loss"),
        action=row.get("action", "BUY"),
        gross_r=rr,
        holding_hours=hold_hours,
        symbol=row.get("symbol", "BTCUSDT"),
        ts=closed or opened,
    )
    return cost.net_r


def _historical_metrics(rows: list[dict]) -> dict:
    """Longest loss streak and time-to-recovery from the actual net equity curve."""
    outcomes = [_net_outcome(r) for r in rows]

    # longest losing streak
    cur = max_l = 0
    for rr in outcomes:
        if rr <= 0:
            cur += 1
            max_l = max(max_l, cur)
        else:
            cur = 0

    # time-to-recovery in trades from a peak to the next new high
    peak = 1.0
    equity = 1.0
    in_dd = False
    rec_count = 0
    recoveries = []
    for rr in outcomes:
        equity *= (1.0 + rr * 0.01)  # use 1% as a normalised unit; we only want trades
        if equity > peak:
            if in_dd:
                recoveries.append(rec_count)
            peak = equity
            in_dd = False
            rec_count = 0
        elif equity < peak:
            in_dd = True
            rec_count += 1

    # max drawdown from the same normalised curve
    peak = 1.0
    max_dd = 0.0
    equity = 1.0
    for rr in outcomes:
        equity *= (1.0 + rr * 0.01)
        peak = max(peak, equity)
        if peak:
            max_dd = max(max_dd, 1.0 - equity / peak)

    return {
        "longest_loss_streak": max_l,
        "median_time_to_recovery_trades": (round(float(np.median(recoveries)), 1)
                                           if recoveries else 0.0),
        "max_time_to_recovery_trades": (max(recoveries) if recoveries else 0),
        "max_drawdown_pct": round(max_dd * 100, 2),
    }


def monte_carlo_ruin_table(
    db=None,
    rows: Optional[list[dict]] = None,
    start: float = 10_000.0,
    risk_percents: tuple[float, ...] = (0.25, 0.5, 1.0, 1.5, 2.0),
    ruin_threshold_pct: float = 50.0,
    samples: int = 2_000,
    seed: Optional[int] = None,
) -> dict:
    """Risk-of-ruin sweep across position sizes using NET realised outcomes.

    For each ``risk_pct`` the function simulates ``samples`` equity curves by
    resampling the decided paper-trade net outcomes with replacement.  It
    reports:

      * expected maximum drawdown
      * ruin probability (max drawdown >= ``ruin_threshold_pct``)
      * probability the curve is below its starting equity at the end
      * median / p5 / p95 terminal equity
      * median longest losing streak (trades)
      * median time-to-recovery (trades)

    It also returns the same metrics computed on the actual historical net
    sequence (longest losing streak and time-to-recovery), because the live
    book already experienced one path and that path matters to the desk.

    Simulator walk-forward samples are excluded — this is a live-book risk
    read, not a backtest variance read.
    """
    if rows is None:
        if db is None:
            return {"available": False, "note": "no database or rows provided"}
        rows = db.decided_paper_rows(exclude_sim=True)

    rows = [r for r in rows if r.get("rr_achieved") is not None]
    if not rows:
        return {"available": False, "note": "no decided paper trades yet"}

    outcomes = [_net_outcome(r) for r in rows]
    n = len(outcomes)
    rng = np.random.default_rng(seed)
    ruin_frac = ruin_threshold_pct / 100.0
    historical = _historical_metrics(rows)

    table = []
    for risk_pct in risk_percents:
        growth = risk_pct / 100.0
        max_dds = np.zeros(samples)
        terminals = np.zeros(samples)
        max_loss_streaks = np.zeros(samples, dtype=int)
        time_to_recovery = np.zeros(samples, dtype=int)

        for s in range(samples):
            perm = rng.choice(outcomes, size=n, replace=True)
            equity = start
            peak = start
            dd = 0.0

            # longest losing streak
            cur_l = max_l = 0
            # time-to-recovery
            in_dd = False
            rec_count = 0
            ttr_peak = start

            for rr in perm:
                equity *= (1.0 + rr * growth)
                if equity > peak:
                    peak = equity
                dd = max(dd, 1.0 - equity / peak)

                # streaks (net outcome <= 0 is a loss)
                if rr <= 0:
                    cur_l += 1
                    max_l = max(max_l, cur_l)
                else:
                    cur_l = 0

                # time-to-recovery from a previous peak
                if equity > ttr_peak:
                    if in_dd:
                        time_to_recovery[s] = max(time_to_recovery[s], rec_count)
                    ttr_peak = equity
                    in_dd = False
                    rec_count = 0
                elif equity < ttr_peak:
                    in_dd = True
                    rec_count += 1

            terminals[s] = equity
            max_dds[s] = dd
            max_loss_streaks[s] = max_l

        ruin_prob = round(float(np.mean(max_dds >= ruin_frac)), 3)
        below_start_prob = round(float(np.mean(terminals < start)), 3)
        median_ttr = round(float(np.median(time_to_recovery)), 1)
        mean_ttr = round(float(np.mean(time_to_recovery)), 1)

        table.append({
            "risk_pct": risk_pct,
            "expected_dd_pct": round(float(np.mean(max_dds)) * 100, 2),
            "ruin_prob": ruin_prob,
            "prob_below_start": below_start_prob,
            "terminal_median": round(float(np.median(terminals)), 2),
            "terminal_p5": round(float(np.percentile(terminals, 5)), 2),
            "terminal_p95": round(float(np.percentile(terminals, 95)), 2),
            "max_loss_streak_median": int(np.median(max_loss_streaks)),
            "max_loss_streak_p95": int(np.percentile(max_loss_streaks, 95)),
            "time_to_recovery_median_trades": median_ttr,
            "time_to_recovery_mean_trades": mean_ttr,
        })

    return {
        "available": True,
        "start": start,
        "ruin_threshold_pct": ruin_threshold_pct,
        "n_trades": n,
        "samples": samples,
        "historical": historical,
        "table": table,
    }
