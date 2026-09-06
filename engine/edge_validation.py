"""engine/edge_validation.py — the honest, regime-aware edge verdict (P13).

The strategic consideration for SKY restated the objective as:

> *"Prove whether existing trading intelligence survives increasingly realistic
>   conditions."*

and the ladder as ``Backtest -> Out-of-sample -> Paper``.  This module answers
the first two rungs on the **decisive** windows of the locked
train / val / OOS / recent protocol — the sealed OOS and the untouched recent
tail, i.e. the slices the walk never tuned on.  It then segments those outcomes
**by market regime** and returns one of three verdicts:

* ``EDGE_CONFIRMED``  — decisive sample, net-positive overall, and net-positive
  in a majority of well-sampled regimes;
* ``NO EDGE``         — decisive sample but net-negative overall (or unstable
  across regimes).  Reported honestly; it never tunes parameters to look green;
* ``INSUFFICIENT_DATA`` — not enough decided samples to make a claim.

It is **read-only**: it runs the same no-look-ahead grader the desk uses, never
mutates the store, never moves a threshold, and never places an order.  It is
the ``python main.py edge-validate`` report.

Design notes
------------
* Only *decided* outcomes (``FULL_WIN`` / ``PARTIAL_WIN`` / ``LOSS``) count.
* All statistics are **net of costs** (P12.6) so fees/spread/funding are
  already in the number the verdict reads.
* Regime is read from each graded plan's ``regime`` tag (decision B3), which
  was captured at signal time — never retro-fitted.
* The verdict is deliberately conservative: silence is not an edge, and a
  single hot regime cannot carry an unstable setup.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from data.backtester import GradedPlan, run_backtest
from data.validation import bucket_by_window, walk_forward_windows, window_stats

# The windows that count as *untouched* evidence.  Train and val are where the
# walk effectively selects/calibrates; OOS + recent are the sealed/unseen tail.
# Changing this set changes the meaning of the verdict — keep it stable.
DECISIVE_WINDOWS: tuple[str, ...] = ("oos", "recent")

EDGE_CONFIRMED = "EDGE_CONFIRMED"
NO_EDGE = "NO EDGE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

DEFAULT_MIN_DECIDED = 30  # overall decisive sample floor
DEFAULT_REGIME_MIN_DECIDED = 10  # a regime must reach this to count as sampled
DEFAULT_POSITIVE_REGIME_FRAC = (
    0.5  # majority of well-sampled regimes must be net-positive
)


def net_r(g: GradedPlan) -> float:
    """Net R for a graded plan, falling back to gross when costs are absent."""
    if getattr(g, "rr_net", None) is not None:
        return float(g.rr_net)
    return float(g.rr_achieved or 0.0)


def monte_carlo_decisive(
    plans: list[GradedPlan],
    samples: int = 2_000,
    risk_pct: float = 1.0,
    ruin_threshold_pct: float = 50.0,
    seed: int | None = None,
) -> dict:
    """Monte-Carlo resampling of the decisive-window net R series (P13.5).

    Reports expectancy stability (p5 / p50 / p95), expected maximum drawdown,
    ruin probability, and probability the terminal equity is below start — all
    on the *decisive* (OOS + recent) window outcomes, not on the pooled paper
    book.  This answers whether the edge the verdict is reading is stable or
    one good streak from NO EDGE.

    Parameters
    ----------
    plans : list[GradedPlan]
        Already filtered to the decisive windows and decided outcomes.
    samples : int
        Number of bootstrap resamples (default 2 000).
    risk_pct : float
        Position size per trade as % of equity (default 1.0).
    ruin_threshold_pct : float
        Drawdown % that counts as ruin (default 50.0).
    seed : int, optional
        RNG seed for reproducibility.

    Returns
    -------
    dict with ``available``, ``n_trades``, ``samples``, ``risk_pct``,
    ``expectancy`` (p5/p50/p95), ``drawdown`` (expected median / p95),
    ``ruin_prob``, ``prob_below_start``, ``longest_loss_streak_p50``, and
    ``equity`` (terminal p5 / p50 / p95).
    """
    # Filter to decided outcomes — only FULL_WIN / PARTIAL_WIN / LOSS carry
    # a meaningful R.  UNDECIDED / EXPIRED are not evidence.
    decided = [g for g in plans if g.outcome in ("FULL_WIN", "PARTIAL_WIN", "LOSS")]
    outcomes = np.array([net_r(g) for g in decided], dtype=float)
    n = len(outcomes)
    if n < 2:
        return {
            "available": False,
            "note": f"need >= 2 decided trades for MC; have {n}",
            "n_trades": n,
        }

    rng = np.random.default_rng(seed)
    start = 10_000.0
    growth = risk_pct / 100.0
    ruin_frac = ruin_threshold_pct / 100.0

    terminals = np.zeros(samples)
    max_dds = np.zeros(samples)
    exp_bootstrap = np.zeros(samples)

    for s in range(samples):
        perm = rng.choice(outcomes, size=n, replace=True)
        exp_bootstrap[s] = float(np.mean(perm))
        equity = start
        peak = start
        dd = 0.0
        for rr in perm:
            equity *= 1.0 + rr * growth
            peak = max(peak, equity)
            dd = max(dd, 1.0 - equity / peak)
        terminals[s] = equity
        max_dds[s] = dd

    # Longest losing streak (median across samples)
    streaks = np.zeros(samples, dtype=int)
    for s in range(samples):
        perm = rng.choice(outcomes, size=n, replace=True)
        cur = max_l = 0
        for rr in perm:
            if rr <= 0:
                cur += 1
                max_l = max(max_l, cur)
            else:
                cur = 0
        streaks[s] = max_l

    return {
        "available": True,
        "n_trades": n,
        "samples": samples,
        "risk_pct": risk_pct,
        "ruin_threshold_pct": ruin_threshold_pct,
        "expectancy": {
            "p5": round(float(np.percentile(exp_bootstrap, 5)), 4),
            "p50": round(float(np.percentile(exp_bootstrap, 50)), 4),
            "p95": round(float(np.percentile(exp_bootstrap, 95)), 4),
        },
        "drawdown": {
            "median_pct": round(float(np.median(max_dds)) * 100, 2),
            "p95_pct": round(float(np.percentile(max_dds, 95)) * 100, 2),
        },
        "ruin_prob": round(float(np.mean(max_dds >= ruin_frac)), 3),
        "prob_below_start": round(float(np.mean(terminals < start)), 3),
        "equity": {
            "p5": round(float(np.percentile(terminals, 5)), 2),
            "p50": round(float(np.median(terminals)), 2),
            "p95": round(float(np.percentile(terminals, 95)), 2),
        },
        "longest_loss_streak_p50": int(np.median(streaks)),
        "longest_loss_streak_p95": int(np.percentile(streaks, 95)),
    }


def edge_stats(plans: list[GradedPlan]) -> dict:
    """Statistics for a set of graded plans (mirrors the window scorer)."""
    stats = window_stats(plans)
    # window_stats returns 'decided', win_rate(_net), expectancy(_net),
    # pf(_net), plus the _aggregate fields.  Normalise the R figures we read
    # so callers can rely on net fields being present.
    stats.setdefault("expectancy_net", stats.get("expectancy", 0.0))
    stats.setdefault("win_rate_net", stats.get("win_rate"))
    stats.setdefault("pf_net", stats.get("pf"))
    return stats


def segment_by_regime(plans: Iterable[GradedPlan]) -> dict[str, list[GradedPlan]]:
    """Group graded plans by their signal-time market regime."""
    out: dict[str, list[GradedPlan]] = {}
    for g in plans:
        out.setdefault(g.regime or "UNKNOWN", []).append(g)
    return out


def regime_edge_report(
    plans: list[GradedPlan],
    regime_min_decided: int = DEFAULT_REGIME_MIN_DECIDED,
    decisive_windows: tuple[str, ...] = DECISIVE_WINDOWS,
) -> dict:
    """Per-regime and overall edge statistics for a set of decisive plans.

    ``plans`` should already be restricted to the decisive windows.  Returns
    overall stats, per-regime stats, and which regimes are *well-sampled*
    (>= ``regime_min_decided`` decided trades).
    """
    overall = edge_stats(plans)
    per_regime = {
        regime: edge_stats(group) for regime, group in segment_by_regime(plans).items()
    }
    sampled = []
    for regime, stats in per_regime.items():
        sampled.append(
            {
                "regime": regime,
                "decided": stats["decided"],
                "expectancy_net": stats.get("expectancy_net"),
                "win_rate_net": stats.get("win_rate_net"),
                "pf_net": stats.get("pf_net"),
                "positive_net": bool(
                    stats.get("expectancy_net") is not None
                    and stats.get("expectancy_net", 0.0) > 0
                ),
                "well_sampled": stats["decided"] >= regime_min_decided,
            }
        )
    sampled = sorted(sampled, key=lambda r: -r["decided"])
    well_sampled = [r for r in sampled if r["well_sampled"]]
    return {
        "overall": overall,
        "regimes": sampled,
        "regime_min_decided": regime_min_decided,
        "well_sampled_count": len(well_sampled),
        "decisive_windows": list(decisive_windows),
    }


def edge_verdict(
    report: dict,
    min_decided: int = DEFAULT_MIN_DECIDED,
    positive_regime_frac: float = DEFAULT_POSITIVE_REGIME_FRAC,
    regime_min_decided: int = DEFAULT_REGIME_MIN_DECIDED,
    monte: dict | None = None,
    monte_floor: bool = True,
) -> dict:
    """Decide EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA from a regime report.

    Rules (all evaluated NET of costs):
      1. Fewer than ``min_decided`` decided trades overall -> INSUFFICIENT_DATA.
      2. Overall net expectancy <= 0 -> NO EDGE (honest, never tuned to green).
      3. Among well-sampled regimes (>= regime_min_decided decided each), the
         fraction with positive net expectancy must be >= ``positive_regime_frac``
         -> otherwise NO EDGE (unstable across regimes).
      4. (P13.5) When Monte-Carlo data is available and ``monte_floor`` is True,
         the 5th-percentile net expectancy must be > 0 — otherwise the edge
         is one good streak from NO EDGE.
      5. Otherwise EDGE_CONFIRMED (with a note when regime coverage is thin).
    """
    overall = report.get("overall", {})
    decided = overall.get("decided", 0)
    reasons: list[str] = []
    _decisive = report.get("decisive_windows", list(DECISIVE_WINDOWS))

    if decided < min_decided:
        return {
            "verdict": INSUFFICIENT_DATA,
            "reasons": [
                f"decided {decided} < min {min_decided} on "
                f"{', '.join(_decisive)} windows — cannot "
                "claim an edge from silence",
            ],
            "overall": _public_stats(overall),
            "regimes": report.get("regimes", []),
            "positive_regime_frac": positive_regime_frac,
            "regime_min_decided": regime_min_decided,
            "decisive_windows": _decisive,
            "monte": monte,
        }

    exp_net = overall.get("expectancy_net")
    if exp_net is None or exp_net <= 0.0:
        exp = 0.0 if exp_net is None else round(float(exp_net), 3)
        return {
            "verdict": NO_EDGE,
            "reasons": [
                f"net expectancy {exp:+.3f}R <= 0 — the edge does not "
                "survive costs on untouched windows"
            ],
            "overall": _public_stats(overall),
            "regimes": report.get("regimes", []),
            "positive_regime_frac": positive_regime_frac,
            "regime_min_decided": regime_min_decided,
            "decisive_windows": _decisive,
            "monte": monte,
        }

    # Regime stability.
    well_sampled = [r for r in report.get("regimes", []) if r.get("well_sampled")]
    if well_sampled:
        positive = sum(1 for r in well_sampled if r.get("positive_net"))
        frac = positive / len(well_sampled)
        if frac < positive_regime_frac - 1e-9:
            return {
                "verdict": NO_EDGE,
                "reasons": [
                    f"positive net expectancy in only {positive}/"
                    f"{len(well_sampled)} well-sampled regimes "
                    f"({frac:.0%} < {positive_regime_frac:.0%}) — the "
                    "edge is not stable across regimes"
                ],
                "overall": _public_stats(overall),
                "regimes": report.get("regimes", []),
                "positive_regime_frac": positive_regime_frac,
                "regime_min_decided": regime_min_decided,
                "decisive_windows": _decisive,
                "monte": monte,
            }
        stability_note = f"stable across {len(well_sampled)} well-sampled regime(s)"
    else:
        stability_note = (
            "stability across regimes not measurable "
            "(no regime reached the sample floor) — treat this "
            "confirmation as provisional"
        )

    # P13.5 — Monte-Carlo floor: 5th-percentile expectancy must be > 0.
    if monte and monte.get("available") and monte_floor:
        p5_exp = monte.get("expectancy", {}).get("p5")
        if p5_exp is not None and p5_exp <= 0.0:
            return {
                "verdict": NO_EDGE,
                "reasons": [
                    f"Monte-Carlo 5th-percentile expectancy {p5_exp:+.4f}R "
                    f"<= 0 — the edge is not stable under resampling "
                    f"({monte['n_trades']} decisive trades, "
                    f"{monte['samples']} samples)"
                ],
                "overall": _public_stats(overall),
                "regimes": report.get("regimes", []),
                "positive_regime_frac": positive_regime_frac,
                "regime_min_decided": regime_min_decided,
                "decisive_windows": _decisive,
                "monte": monte,
            }
        stability_note += (
            f"; MC p5 expectancy {p5_exp:+.4f}R > 0 "
            f"({monte['n_trades']} trades, "
            f"{monte['samples']} samples)"
        )

    return {
        "verdict": EDGE_CONFIRMED,
        "reasons": [stability_note],
        "overall": _public_stats(overall),
        "regimes": report.get("regimes", []),
        "positive_regime_frac": positive_regime_frac,
        "regime_min_decided": regime_min_decided,
        "decisive_windows": _decisive,
        "monte": monte,
    }


def _public_stats(stats: dict) -> dict:
    """The fields worth printing for a stats dict."""
    exp_net = stats.get("expectancy_net", stats.get("expectancy", 0.0))
    wr = stats.get("win_rate_net", stats.get("win_rate"))
    pf = stats.get("pf_net", stats.get("pf"))
    return {
        "decided": stats.get("decided", 0),
        "wins": stats.get("wins", 0),
        "losses": stats.get("losses", 0),
        "expectancy_net": (round(float(exp_net), 3) if exp_net is not None else None),
        "win_rate_net": (round(float(wr), 4) if wr is not None else None),
        "pf_net": (round(float(pf), 3) if pf is not None else None),
    }


# ── P13.6 — the compare ladder (Backtest → OOS → Paper) ──────────────────
# One honest surface so the owner sees the degradation ladder: the whole-walk
# backtest, the sealed decisive windows the verdict reads, and the canonical
# live paper book (P11).  It is a comparison surface only — it never approves,
# never moves a threshold, never places an order.


def paper_stats_from_rows(rows: list[dict]) -> dict:
    """Aggregate the canonical live paper book (P11) into public stats.

    ``rows`` are ``SignalDB.live_book_rows()`` — decided (TP_HIT / STOP_LOSS),
    non-simulator, canonical-live source only.  All figures are **net of
    costs** (``rr_net``, with the P12.6 gross fallback when costs are absent),
    exactly like the edge stats, so the paper rung is comparable to the OOS
    rung.  Returns an empty dict when there is no paper evidence yet — the
    ladder then shows the rung as empty instead of inventing a number.
    """
    decided = [r for r in rows if r.get("outcome") in ("TP_HIT", "STOP_LOSS")]
    if not decided:
        return {}

    def net_rr(r: dict) -> float:
        v = r.get("rr_net")
        if v is None:
            v = r.get("rr_achieved")
        return float(v) if v is not None else 0.0

    net = [net_rr(r) for r in decided]
    wins = sum(1 for r in decided if r.get("outcome") == "TP_HIT")
    losses = sum(1 for r in decided if r.get("outcome") == "STOP_LOSS")
    wins_net = sum(1 for v in net if v > 0)
    win_r_net = sum(v for v in net if v > 0)
    loss_r_net = abs(sum(v for v in net if v <= 0))
    return {
        "decided": len(decided),
        "wins": wins,
        "losses": losses,
        "expectancy_net": round(float(np.mean(net)), 3),
        "win_rate_net": round(wins_net / len(decided), 4),
        "pf_net": (
            round(win_r_net / loss_r_net, 3)
            if loss_r_net > 0
            else (99.0 if win_r_net > 0 else None)
        ),
    }


def _ladder_note(rungs: dict) -> str:
    """Honest one-line reading of the ladder (never tunes to green)."""
    oos = rungs.get("oos") or {}
    paper = rungs.get("paper") or {}
    if not oos.get("decided"):
        return (
            "OOS rung empty — the decisive-window sample is too thin; "
            "the ladder cannot show an honest backtest → OOS → paper "
            "degradation yet"
        )
    if not paper.get("decided"):
        return (
            "paper rung empty — no decided canonical live trades yet; "
            "simulator rows never count (P12.13). Keep grinding P11."
        )
    oos_e = oos.get("expectancy_net")
    paper_e = paper.get("expectancy_net")
    if oos_e is None or paper_e is None:
        return (
            "rungs have decided samples but net expectancy is missing on "
            "one of them — treat the ladder as partial"
        )
    if paper_e < oos_e:
        return (
            f"paper expectancy {paper_e:+.3f}R is below OOS "
            f"{oos_e:+.3f}R (Δ {paper_e - oos_e:+.3f}R) — expected "
            "degradation as costs, slippage and human decisions enter "
            "the ladder"
        )
    return (
        f"paper expectancy {paper_e:+.3f}R holds at or above OOS "
        f"{oos_e:+.3f}R — no degradation measured on this book"
    )


def compare_ladder(report: dict, paper_stats: dict) -> dict:
    """Compose the Backtest → OOS → Paper ladder from an edge report.

    ``report`` is the ``edge_validate_report`` result (its ``backtest_stats``
    and ``edge.overall`` are the backtest / OOS rungs).  ``paper_stats`` is
    the ``paper_stats_from_rows`` aggregate of the canonical live book.
    Rungs with no decided samples stay empty (rendered as n/a) — an empty
    rung is honest, an invented number is not.
    """
    backtest = report.get("backtest_stats") or {}
    oos = (report.get("edge") or {}).get("overall") or {}
    rungs = {
        "backtest": (_public_stats(backtest) if backtest else {}),
        "oos": (_public_stats(oos) if oos else {}),
        "paper": (_public_stats(paper_stats) if paper_stats else {}),
    }
    meta = report.get("meta") or {}
    return {
        "rungs": rungs,
        "note": _ladder_note(rungs),
        "decisive_windows": meta.get("decisive_windows", list(DECISIVE_WINDOWS)),
    }


def format_compare_ladder(report: dict) -> str:
    """Human-readable ladder block for ``edge-validate --ladder``."""
    ladder = report.get("ladder")
    if not ladder:
        return ""
    rungs = ladder.get("rungs", {})
    lines = [
        "-" * 70,
        "  COMPARE LADDER  backtest -> OOS -> paper (P13.6):",
        f"  {'rung':<26}{'n':>5}{'exp_net':>10}{'wr_net':>9}{'pf_net':>8}",
    ]
    for name, label in (
        ("backtest", "BACKTEST (all windows)"),
        ("oos", "OOS + RECENT (decisive)"),
        ("paper", "PAPER (canonical live)"),
    ):
        s = rungs.get(name) or {}
        if not s or not s.get("decided"):
            lines.append(f"  {label:<26}{'—':>5}{'n/a':>10}{'':>9}{'':>8}")
            continue
        exp = s.get("expectancy_net")
        wr = s.get("win_rate_net")
        pf = s.get("pf_net")
        exp_s = f"{exp:+.3f}R" if exp is not None else "n/a"
        wr_s = f"{wr * 100:.1f}%" if wr is not None else "n/a"
        pf_s = f"{pf:.2f}" if pf is not None else "n/a"
        lines.append(f"  {label:<26}{s['decided']:>5}{exp_s:>10}{wr_s:>9}{pf_s:>8}")
    lines.append(f"  · {ladder.get('note', '')}")
    lines.append("-" * 70)
    return "\n".join(lines)


def edge_validate_report(
    df,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    horizons: list[float] | None = None,
    min_bars: int = 120,
    step: int = 3,
    min_confidence: int = 55,
    min_decided: int = DEFAULT_MIN_DECIDED,
    regime_min_decided: int = DEFAULT_REGIME_MIN_DECIDED,
    positive_regime_frac: float = DEFAULT_POSITIVE_REGIME_FRAC,
    decisive_windows: tuple[str, ...] = DECISIVE_WINDOWS,
    train_frac: float = 0.60,
    val_frac: float = 0.15,
    oos_frac: float = 0.15,
    recent_frac: float = 0.10,
    monte: bool = False,
    monte_samples: int = 2_000,
    monte_risk_pct: float = 1.0,
    monte_seed: int | None = None,
    paper_rows: list | None = None,
) -> dict:
    """Run the no-look-ahead walk and produce the decisive-window edge verdict.

    One pass of the engine over the series, outcomes graded only after the
    signal bar (same grader the desk uses).  Each plan is bucketed by the
    window its *signal bar* belongs to; only ``decisive_windows`` count.  The
    verdict is EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA.

    When ``monte`` is True (P13.5), resamples the decisive-window net R series
    and incorporates a Monte-Carlo stability floor into the verdict: the 5th-
    percentile net expectancy must be > 0 or the edge is rejected.

    When ``paper_rows`` is provided (P13.6, the canonical live book from
    ``SignalDB.live_book_rows()``), the result also carries a ``ladder`` block
    that juxtaposes the whole-walk backtest, the decisive OOS + recent rung,
    and the canonical paper book — one honest degradation ladder.
    """
    df = df.reset_index(drop=True).copy()
    if len(df) <= min_bars:
        return {
            "ok": False,
            "error": f"series has {len(df)} bars; need > min_bars={min_bars}",
        }

    try:
        windows = walk_forward_windows(
            len(df), min_bars, train_frac, val_frac, oos_frac, recent_frac
        )
    except Exception as exc:  # ValidationWindowError
        return {"ok": False, "error": str(exc)}

    horizons = horizons or [1.0]
    primary = horizons[0]
    result = run_backtest(
        df,
        symbol=symbol,
        timeframe=timeframe,
        horizons=horizons,
        min_bars=min_bars,
        step=step,
        min_confidence=min_confidence,
    )
    graded = [g for g in result["graded"] if abs(g.horizon_hours - primary) < 0.01]

    ts_to_index = {int(t): i for i, t in enumerate(df["ts"])}
    buckets = bucket_by_window(graded, windows, ts_to_index)
    decisive: list[GradedPlan] = []
    for name in decisive_windows:
        decisive.extend(buckets.get(name, []))

    report = regime_edge_report(
        decisive,
        regime_min_decided=regime_min_decided,
        decisive_windows=decisive_windows,
    )

    # P13.5 — Monte-Carlo on the decisive-window R series.
    mc_block: dict | None = None
    if monte:
        mc_block = monte_carlo_decisive(
            decisive, samples=monte_samples, risk_pct=monte_risk_pct, seed=monte_seed
        )

    verdict = edge_verdict(
        report,
        min_decided=min_decided,
        positive_regime_frac=positive_regime_frac,
        regime_min_decided=regime_min_decided,
        monte=mc_block,
    )
    per_window = {
        name: _public_stats(window_stats(buckets.get(name, [])))
        for name in ("train", "val", "oos", "recent")
    }
    meta = {
        "symbol": symbol,
        "timeframe": timeframe,
        "primary_horizon_hours": primary,
        "bars_total": len(df),
        "bars_analyzed": result["report"]["meta"]["bars_analyzed"],
        "plans_generated": result["report"]["meta"]["plans_generated"],
        "runtime_seconds": result["report"]["meta"]["runtime_seconds"],
        "min_decided": min_decided,
        "regime_min_decided": regime_min_decided,
        "positive_regime_frac": positive_regime_frac,
        "decisive_windows": list(decisive_windows),
        "window_fractions": {
            "train": train_frac,
            "val": val_frac,
            "oos": oos_frac,
            "recent": recent_frac,
        },
    }
    if mc_block:
        meta["monte"] = True
    out = {
        "ok": True,
        "verdict": verdict["verdict"],
        "edge": verdict,
        "monte": mc_block,
        "windows": per_window,
        "window_bars": {name: list(windows[name]) for name in windows},
        "meta": meta,
    }
    # P13.6 — compare ladder: whole-walk backtest rung + canonical paper book.
    if paper_rows is not None:
        out["backtest_stats"] = edge_stats(graded)
        out["ladder"] = compare_ladder(out, paper_stats_from_rows(paper_rows))
    return out


def format_edge_verdict(report: dict) -> str:
    """Human-readable edge block in the honest NO-EDGE style."""
    if not report.get("ok"):
        return "EDGE VALIDATION — could not run\n  " + str(
            report.get("error", "unknown")
        )
    edge = report["edge"]
    meta = report["meta"]
    o = edge["overall"]
    exp = o.get("expectancy_net")
    exp_str = f"{exp:+.3f}R" if exp is not None else "n/a"
    wr = o.get("win_rate_net")
    wr_str = f"{wr * 100:.1f}%" if wr is not None else "n/a"
    pf = o.get("pf_net")
    pf_str = f"{pf:.2f}" if pf is not None else "n/a"

    lines = [
        "=" * 70,
        f"EDGE VALIDATION  {meta['symbol']} {meta['timeframe']}  "
        f"primary {meta['primary_horizon_hours']}h",
        "-" * 70,
        f"  decisive windows : {', '.join(meta['decisive_windows'])} "
        f"(unseen by the walk)",
        f"  decided samples  : {o['decided']}   (wins {o['wins']} / "
        f"losses {o['losses']})",
        f"  expectancy (net) : {exp_str}",
        f"  win rate (net)   : {wr_str}",
        f"  profit factor    : {pf_str}",
        "-" * 70,
        "  by regime (net expectancy):",
    ]
    if not edge["regimes"]:
        lines.append("    (no decided samples on decisive windows)")
    for r in edge["regimes"]:
        rexp = r.get("expectancy_net")
        rexp_str = f"{rexp:+.3f}R" if rexp is not None else "n/a"
        mark = "✓" if r.get("positive_net") else "✗"
        flag = "  well-sampled" if r.get("well_sampled") else "  thin"
        lines.append(
            f"    {mark} {r['regime']:<22} n={r['decided']:>4}  exp {rexp_str}{flag}"
        )

    # P13.5 — Monte-Carlo stability block.
    mc = report.get("monte") or edge.get("monte")
    if mc and mc.get("available"):
        lines.append("-" * 70)
        lines.append("  MONTE CARLO (decisive-window resampling):")
        lines.append(
            f"    trades {mc['n_trades']}  samples {mc['samples']}  "
            f"risk {mc['risk_pct']}%/trade"
        )
        e = mc["expectancy"]
        lines.append(
            f"    expectancy  p5 {e['p5']:+.4f}R   "
            f"p50 {e['p50']:+.4f}R   p95 {e['p95']:+.4f}R"
        )
        dd = mc["drawdown"]
        lines.append(
            f"    drawdown    median {dd['median_pct']:.1f}%   p95 {dd['p95_pct']:.1f}%"
        )
        lines.append(
            f"    ruin prob   {mc['ruin_prob'] * 100:.1f}%   "
            f"(>= {mc['ruin_threshold_pct']}% drawdown)"
        )
        lines.append(
            f"    below start {mc['prob_below_start'] * 100:.1f}%   "
            f"loss streak p50 {mc['longest_loss_streak_p50']}"
        )
        eq = mc["equity"]
        lines.append(
            f"    equity      p5 {eq['p5']:,.0f}   "
            f"p50 {eq['p50']:,.0f}   p95 {eq['p95']:,.0f}"
        )
        # MC floor check
        p5_exp = e["p5"]
        if p5_exp > 0:
            lines.append(f"    MC floor    ✓ p5 expectancy {p5_exp:+.4f}R > 0")
        else:
            lines.append(
                f"    MC floor    ✗ p5 expectancy {p5_exp:+.4f}R <= 0 "
                f"— edge not stable under resampling"
            )
    elif mc and not mc.get("available"):
        lines.append("-" * 70)
        lines.append(f"  MONTE CARLO: unavailable — {mc.get('note', 'unknown')}")

    lines.append("-" * 70)
    if edge["verdict"] == EDGE_CONFIRMED:
        lines.append("  VERDICT: EDGE CONFIRMED")
    elif edge["verdict"] == NO_EDGE:
        lines.append("  VERDICT: NO EDGE")
    else:
        lines.append("  VERDICT: INSUFFICIENT DATA")
    for reason in edge["reasons"]:
        lines.append(f"    · {reason}")
    lines.append("=" * 70)
    return "\n".join(lines)
