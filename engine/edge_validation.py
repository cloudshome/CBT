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

from typing import Iterable, Optional

from data.backtester import GradedPlan, run_backtest
from data.validation import bucket_by_window, walk_forward_windows, window_stats


# The windows that count as *untouched* evidence.  Train and val are where the
# walk effectively selects/calibrates; OOS + recent are the sealed/unseen tail.
# Changing this set changes the meaning of the verdict — keep it stable.
DECISIVE_WINDOWS: tuple[str, ...] = ("oos", "recent")

EDGE_CONFIRMED = "EDGE_CONFIRMED"
NO_EDGE = "NO EDGE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

DEFAULT_MIN_DECIDED = 30          # overall decisive sample floor
DEFAULT_REGIME_MIN_DECIDED = 10   # a regime must reach this to count as sampled
DEFAULT_POSITIVE_REGIME_FRAC = 0.5  # majority of well-sampled regimes must be net-positive


def net_r(g: GradedPlan) -> float:
    """Net R for a graded plan, falling back to gross when costs are absent."""
    if getattr(g, "rr_net", None) is not None:
        return float(g.rr_net)
    return float(g.rr_achieved or 0.0)


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


def regime_edge_report(plans: list[GradedPlan],
                       regime_min_decided: int = DEFAULT_REGIME_MIN_DECIDED,
                       decisive_windows: tuple[str, ...] = DECISIVE_WINDOWS) -> dict:
    """Per-regime and overall edge statistics for a set of decisive plans.

    ``plans`` should already be restricted to the decisive windows.  Returns
    overall stats, per-regime stats, and which regimes are *well-sampled*
    (>= ``regime_min_decided`` decided trades).
    """
    overall = edge_stats(plans)
    per_regime = {
        regime: edge_stats(group)
        for regime, group in segment_by_regime(plans).items()
    }
    sampled = []
    for regime, stats in per_regime.items():
        sampled.append({
            "regime": regime,
            "decided": stats["decided"],
            "expectancy_net": stats.get("expectancy_net"),
            "win_rate_net": stats.get("win_rate_net"),
            "pf_net": stats.get("pf_net"),
            "positive_net": bool(stats.get("expectancy_net") is not None
                                 and stats.get("expectancy_net", 0.0) > 0),
            "well_sampled": stats["decided"] >= regime_min_decided,
        })
    sampled = sorted(sampled, key=lambda r: -r["decided"])
    well_sampled = [r for r in sampled if r["well_sampled"]]
    return {
        "overall": overall,
        "regimes": sampled,
        "regime_min_decided": regime_min_decided,
        "well_sampled_count": len(well_sampled),
        "decisive_windows": list(decisive_windows),
    }


def edge_verdict(report: dict,
                 min_decided: int = DEFAULT_MIN_DECIDED,
                 positive_regime_frac: float = DEFAULT_POSITIVE_REGIME_FRAC,
                 regime_min_decided: int = DEFAULT_REGIME_MIN_DECIDED) -> dict:
    """Decide EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA from a regime report.

    Rules (all evaluated NET of costs):
      1. Fewer than ``min_decided`` decided trades overall -> INSUFFICIENT_DATA.
      2. Overall net expectancy <= 0 -> NO EDGE (honest, never tuned to green).
      3. Among well-sampled regimes (>= regime_min_decided decided each), the
         fraction with positive net expectancy must be >= ``positive_regime_frac``
         -> otherwise NO EDGE (unstable across regimes).
      4. Otherwise EDGE_CONFIRMED (with a note when regime coverage is thin).
    """
    overall = report.get("overall", {})
    decided = overall.get("decided", 0)
    reasons: list[str] = []

    if decided < min_decided:
        return {
            "verdict": INSUFFICIENT_DATA,
            "reasons": [
                f"decided {decided} < min {min_decided} on "
                f"{', '.join(report['decisive_windows'])} windows — cannot "
                "claim an edge from silence",
            ],
            "overall": _public_stats(overall),
            "regimes": report.get("regimes", []),
            "positive_regime_frac": positive_regime_frac,
            "regime_min_decided": regime_min_decided,
            "decisive_windows": report.get("decisive_windows", list(DECISIVE_WINDOWS)),
        }

    exp_net = overall.get("expectancy_net")
    if exp_net is None or exp_net <= 0.0:
        exp = 0.0 if exp_net is None else round(float(exp_net), 3)
        return {
            "verdict": NO_EDGE,
            "reasons": [f"net expectancy {exp:+.3f}R <= 0 — the edge does not "
                        "survive costs on untouched windows"],
            "overall": _public_stats(overall),
            "regimes": report.get("regimes", []),
            "positive_regime_frac": positive_regime_frac,
            "regime_min_decided": regime_min_decided,
            "decisive_windows": report.get("decisive_windows", list(DECISIVE_WINDOWS)),
        }

    # Regime stability.
    well_sampled = [r for r in report.get("regimes", [])
                    if r.get("well_sampled")]
    if well_sampled:
        positive = sum(1 for r in well_sampled if r.get("positive_net"))
        frac = positive / len(well_sampled)
        if frac < positive_regime_frac - 1e-9:
            return {
                "verdict": NO_EDGE,
                "reasons": [f"positive net expectancy in only {positive}/"
                            f"{len(well_sampled)} well-sampled regimes "
                            f"({frac:.0%} < {positive_regime_frac:.0%}) — the "
                            "edge is not stable across regimes"],
                "overall": _public_stats(overall),
                "regimes": report.get("regimes", []),
                "positive_regime_frac": positive_regime_frac,
                "regime_min_decided": regime_min_decided,
                "decisive_windows": report.get("decisive_windows", list(DECISIVE_WINDOWS)),
            }
        stability_note = (f"stable across {len(well_sampled)} well-sampled "
                          f"regime(s)")
    else:
        stability_note = ("stability across regimes not measurable "
                          "(no regime reached the sample floor) — treat this "
                          "confirmation as provisional")

    return {
        "verdict": EDGE_CONFIRMED,
        "reasons": [stability_note],
        "overall": _public_stats(overall),
        "regimes": report.get("regimes", []),
        "positive_regime_frac": positive_regime_frac,
        "regime_min_decided": regime_min_decided,
        "decisive_windows": report.get("decisive_windows", list(DECISIVE_WINDOWS)),
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


def edge_validate_report(df, symbol: str = "BTCUSDT", timeframe: str = "15m",
                         horizons: Optional[list[float]] = None,
                         min_bars: int = 120, step: int = 3,
                         min_confidence: int = 55,
                         min_decided: int = DEFAULT_MIN_DECIDED,
                         regime_min_decided: int = DEFAULT_REGIME_MIN_DECIDED,
                         positive_regime_frac: float = DEFAULT_POSITIVE_REGIME_FRAC,
                         decisive_windows: tuple[str, ...] = DECISIVE_WINDOWS,
                         train_frac: float = 0.60, val_frac: float = 0.15,
                         oos_frac: float = 0.15, recent_frac: float = 0.10) -> dict:
    """Run the no-look-ahead walk and produce the decisive-window edge verdict.

    One pass of the engine over the series, outcomes graded only after the
    signal bar (same grader the desk uses).  Each plan is bucketed by the
    window its *signal bar* belongs to; only ``decisive_windows`` count.  The
    verdict is EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA.
    """
    df = df.reset_index(drop=True).copy()
    if len(df) <= min_bars:
        return {"ok": False,
                "error": f"series has {len(df)} bars; need > min_bars={min_bars}"}

    try:
        windows = walk_forward_windows(len(df), min_bars, train_frac, val_frac,
                                       oos_frac, recent_frac)
    except Exception as exc:  # ValidationWindowError
        return {"ok": False, "error": str(exc)}

    horizons = horizons or [1.0]
    primary = horizons[0]
    result = run_backtest(df, symbol=symbol, timeframe=timeframe,
                          horizons=horizons, min_bars=min_bars, step=step,
                          min_confidence=min_confidence)
    graded = [g for g in result["graded"]
              if abs(g.horizon_hours - primary) < 0.01]

    ts_to_index = {int(t): i for i, t in enumerate(df["ts"])}
    buckets = bucket_by_window(graded, windows, ts_to_index)
    decisive: list[GradedPlan] = []
    for name in decisive_windows:
        decisive.extend(buckets.get(name, []))

    report = regime_edge_report(decisive, regime_min_decided=regime_min_decided,
                                decisive_windows=decisive_windows)
    verdict = edge_verdict(report, min_decided=min_decided,
                           positive_regime_frac=positive_regime_frac,
                           regime_min_decided=regime_min_decided)
    per_window = {name: _public_stats(window_stats(buckets.get(name, [])))
                  for name in ("train", "val", "oos", "recent")}
    return {
        "ok": True,
        "verdict": verdict["verdict"],
        "edge": verdict,
        "windows": per_window,
        "window_bars": {name: list(windows[name]) for name in windows},
        "meta": {
            "symbol": symbol, "timeframe": timeframe,
            "primary_horizon_hours": primary,
            "bars_total": len(df), "bars_analyzed": result["report"]["meta"]["bars_analyzed"],
            "plans_generated": result["report"]["meta"]["plans_generated"],
            "runtime_seconds": result["report"]["meta"]["runtime_seconds"],
            "min_decided": min_decided,
            "regime_min_decided": regime_min_decided,
            "positive_regime_frac": positive_regime_frac,
            "decisive_windows": list(decisive_windows),
            "window_fractions": {"train": train_frac, "val": val_frac,
                                 "oos": oos_frac, "recent": recent_frac},
        },
    }


def format_edge_verdict(report: dict) -> str:
    """Human-readable edge block in the honest NO-EDGE style."""
    if not report.get("ok"):
        return "EDGE VALIDATION — could not run\n  " + str(report.get("error", "unknown"))
    edge = report["edge"]
    meta = report["meta"]
    o = edge["overall"]
    exp = o.get("expectancy_net")
    exp_str = f"{exp:+.3f}R" if exp is not None else "n/a"
    wr = o.get("win_rate_net")
    wr_str = f"{wr*100:.1f}%" if wr is not None else "n/a"
    pf = o.get("pf_net")
    pf_str = f"{pf:.2f}" if pf is not None else "n/a"

    lines = ["=" * 70,
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
             "  by regime (net expectancy):"]
    if not edge["regimes"]:
        lines.append("    (no decided samples on decisive windows)")
    for r in edge["regimes"]:
        rexp = r.get("expectancy_net")
        rexp_str = f"{rexp:+.3f}R" if rexp is not None else "n/a"
        mark = "✓" if r.get("positive_net") else "✗"
        flag = "  well-sampled" if r.get("well_sampled") else "  thin"
        lines.append(f"    {mark} {r['regime']:<22} n={r['decided']:>4}  "
                     f"exp {rexp_str}{flag}")
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
