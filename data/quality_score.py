"""data/quality_score.py — P12.4: the Backtest Quality Score (0–100).

The scorecard (P12.3/P12.6/P12.3.3) answers *"is this book profitable
net of costs, with honest overlap-corrected uncertainty?"* — this module
answers the second question a desk must ask before trusting a curve:

> **"Is this book *robust*, or did it win by luck?"**

Per `docs/FREQTRADE_REVIEW.md` §8 F5 and `docs/BACKTRADER_REVIEW.md` §8
BT5, P12.4 is a composite 0–100 so that a fragile high-PnL curve cannot
look like a pass:

    Score = E_R × Stability × SampleConfidence − DD/Complexity penalties

realised as four weighted components, each 0–100, computed NET of costs
(P12.6) over overlap-corrected evidence (P12.3.3):

  edge        (35%)  — how far net expectancy sits above the graduation
                       bar, discounted when win rate / profit factor miss
                       the bar's shape (a positive-E book that wins 30%
                       of the time is not the bar's edge).
  robustness  (35%)  — fragility of the cumulative net-R curve:
                       • concentration: top-5 wins' share of gross wins —
                         one lucky 5-trade streak must not BE the edge;
                       • drawdown: max drawdown ÷ |total R| — a curve
                         that gives back half its profit is fragile;
                       • segment consistency: the book split
                         chronologically — profits must persist across
                         time, not arrive in one burst.
  sample      (20%)  — evidence sufficiency, overlap-corrected: N_eff vs
                       min_decided, and whether the 95% CI of E_net still
                       excludes break-even (significance, not just mean).
  plateau     (10%)  — parameter-plateau test (BT5): re-grade the same
                       series over a neighbourhood of a strategy parameter
                       (default: min_confidence ± 5). A setup that only
                       wins at one isolated parameter point scores low and
                       **caps the total at 50** — an isolated peak is not
                       an edge, it is a fit.

Design rules (inherited from the scorecard, do not "improve" away):

  * No second grader and no new math engine: `trade_stats()` from
    `data/scorecard.py` is the single source of the statistics; this
    module only *judges* them. `data/backtester.py` stays the only
    thing that decides WIN / LOSS.
  * Deterministic, offline, dependency-free beyond the existing stack —
    `DEMO_MODE=1` and CI stay green.
  * Every component degrades to ``None``/a documented default rather
    than to a guess when the sample cannot support it. Silence is not
    an edge.
  * The score is a report, not permission. It never changes engine
    weights, never loosens the bar, and never grants a trade.

The plateau sweep (`run_quality_sweep`) is store-only, exactly like the
locked P12.1 protocol: re-grading requires a stored series. The score
itself (`backtest_quality_score`) is pure and works on any decided rows,
which is what lets the scorecard, the CLI, HTTP, and MCP all read the
same computation (invariant #10).
"""

from __future__ import annotations

from collections.abc import Callable

from config import MIN_CONFIDENCE
from data.costs import calculate_trade_cost
from data.scorecard import (
    max_drawdown_r,
    trade_stats,
)
from data.validation import DEFAULT_MIN_DECIDED, VALIDATION_CRITERIA

# Component weights (documented in the module docstring). The plateau is
# dropped and the remainder renormalised when no plateau evidence exists.
WEIGHTS: dict[str, float] = {
    "edge": 0.35,
    "robustness": 0.35,
    "sample": 0.20,
    "plateau": 0.10,
}

#: An isolated-peak plateau caps the total here. A setup whose edge only
#: exists at one parameter point is a fit, not a strategy (BT5).
PLATEAU_CAP = 50.0

BAND_CUTS = (
    (80.0, "robust"),
    (60.0, "acceptable"),
    (40.0, "borderline"),
    (None, "fragile"),
)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _net_r(r: dict) -> float:
    """One row's net R, computing it exactly the way `trade_stats` does."""
    v = r.get("r_net")
    if v is not None:
        return float(v)
    cost = calculate_trade_cost(
        entry=r.get("entry"),
        stop_loss=r.get("stop_loss"),
        action=r.get("side", "BUY"),
        gross_r=float(r.get("r", 0.0)),
        holding_hours=r.get("holding_hours"),
        symbol=r.get("symbol", "BTCUSDT"),
        ts=r.get("ts"),
    )
    return cost.net_r


# ──────────────────────────────────────────────────────────────────────────
# Component 1 — edge (0–100)
# ──────────────────────────────────────────────────────────────────────────
def edge_score(stats: dict, criteria: dict | None = None) -> dict:
    """How far net expectancy sits above the bar, shape-discounted.

    ``e_net`` is mapped linearly: ≤ 0R → 0, at the bar → 50, at 2× the bar
    → 100 (capped). A book that meets E_net but misses the bar's *shape*
    (win rate ≤ 55%, PF < 1.5) is discounted ×0.85 per miss — the bar
    requires all three conditions, so the score does not hand out a pass
    on expectancy alone.
    """
    criteria = criteria or VALIDATION_CRITERIA
    bar_e = float(criteria["expectancy"])
    e_net = float(stats.get("expectancy_net", 0.0) or 0.0)
    raw = 100.0 * _clamp(e_net / (2.0 * bar_e), 0.0, 1.0)

    shape = 1.0
    notes: list[str] = []
    wr_net = stats.get("win_rate_net")
    if wr_net is not None and float(wr_net) <= float(criteria["win_rate"]):
        shape *= 0.85
        notes.append(
            f"win_rate_net {float(wr_net):.1%} <= "
            f"{float(criteria['win_rate']):.0%} → ×0.85"
        )
    pf_net = stats.get("pf_net")
    if pf_net is not None and float(pf_net) < float(criteria["pf"]):
        shape *= 0.85
        notes.append(f"pf_net {pf_net} < {criteria['pf']} → ×0.85")

    return {
        "score": round(raw * shape, 1),
        "expectancy_net": round(e_net, 3),
        "bar_expectancy": bar_e,
        "shape": round(shape, 3),
        "notes": notes,
    }


# ──────────────────────────────────────────────────────────────────────────
# Component 2 — curve robustness (0–100)
# ──────────────────────────────────────────────────────────────────────────
def _top_n_share(net_r: list[float], k: int = 5) -> float | None:
    """Share of gross positive R earned by the best k trades."""
    positive = sorted((v for v in net_r if v > 0), reverse=True)
    total = sum(positive)
    if total <= 0:
        return None
    return round(sum(positive[:k]) / total, 4)


def _segments(net_r: list[float], n: int) -> list[float] | None:
    """Chronological equal-count chunks → mean net R per chunk.

    Returns ``None`` when the book is too small to judge time-persistence
    (fewer than 4 trades → 2 chunks; fewer than 2 chunks → n/a).
    """
    n_seg = 4 if n >= 12 else (2 if n >= 4 else None)
    if n_seg is None:
        return None
    chunk = n // n_seg
    means = []
    for i in range(n_seg):
        part = net_r[i * chunk : (i + 1) * chunk]
        if part:
            means.append(sum(part) / len(part))
    return means


def curve_robustness(rows: list[dict]) -> dict:
    """Fragility of the cumulative net-R curve, in three sub-scores.

    concentration: top-5 wins' share of gross positive R — 0% → 100,
    50% or more → 0 (the edge lives in five trades).
    drawdown:      max drawdown ÷ max(1e-9, |total R|) — 0% → 100,
    50% or more → 0 (the edge gives back half its profit).
    segments:      fraction of chronological chunks with positive mean
    net R — all chunks positive → 100, none → 0. ``None`` when the book
    is too small to split.
    """
    ordered = sorted(rows, key=lambda r: (r.get("ts") is None, r.get("ts")))
    net_r = [_net_r(r) for r in ordered]
    n = len(net_r)
    if n == 0:
        return {
            "score": 0.0,
            "n": 0,
            "concentration": None,
            "drawdown": None,
            "segments": None,
            "notes": ["no decided trades — nothing to be robust about"],
        }

    # concentration
    share = _top_n_share(net_r)
    if share is None:
        conc_score, conc_note = (
            0.0,
            "no positive net R — the book has no edge to be concentrated in",
        )
    else:
        conc_score = 100.0 * _clamp(1.0 - share / 0.5, 0.0, 1.0)
        conc_note = (
            f"top-5 wins = {share:.1%} of gross wins" if share > 0 else "no wins"
        )

    # drawdown
    total_net = sum(net_r)
    dd = max_drawdown_r(net_r)
    if total_net <= 0:
        dd_score, dd_note = 0.0, f"total net R {total_net:+.2f} ≤ 0"
    elif dd <= 0:
        dd_score, dd_note = 100.0, "zero drawdown"
    else:
        ratio = dd / abs(total_net)
        dd_score = 100.0 * _clamp(1.0 - ratio / 0.5, 0.0, 1.0)
        dd_note = f"max DD {dd:.2f}R = {ratio:.1%} of total {total_net:+.2f}R"

    # segments
    seg_means = _segments(net_r, n)
    if seg_means is None:
        seg_score: float | None = None
        seg_note = f"n={n} too small to split chronologically"
        hit: float | None = None
    else:
        hit = sum(1 for m in seg_means if m > 0) / len(seg_means)
        seg_score = 100.0 * hit
        seg_note = (
            f"{sum(1 for m in seg_means if m > 0)}/{len(seg_means)} segments positive"
        )

    # weighted blend (renormalised when segments are unavailable)
    parts: list[tuple[float, float]] = []
    if conc_score is not None:
        parts.append((0.4, conc_score))
    if dd_score is not None:
        parts.append((0.3, dd_score))
    if seg_score is not None:
        parts.append((0.3, seg_score))
    total_w = sum(w for w, _ in parts) or 1.0
    score = sum(w * s for w, s in parts) / total_w if parts else 0.0

    return {
        "score": round(score, 1),
        "n": n,
        "concentration": {
            "score": round(conc_score, 1),
            "share_top5": share,
            "note": conc_note,
        },
        "drawdown": {
            "score": round(dd_score, 1),
            "max_dd_r": round(dd, 3),
            "total_net_r": round(total_net, 3),
            "note": dd_note,
        },
        "segments": {
            "score": round(seg_score, 1) if seg_score is not None else None,
            "positive_fraction": hit,
            "note": seg_note,
        },
        "notes": [conc_note, dd_note, seg_note],
    }


# ──────────────────────────────────────────────────────────────────────────
# Component 3 — sample confidence (0–100)
# ──────────────────────────────────────────────────────────────────────────
def sample_score(
    stats: dict, min_decided: int = DEFAULT_MIN_DECIDED, criteria: dict | None = None
) -> dict:
    """Evidence sufficiency, overlap-corrected.

    size:         N_eff / min_decided — a book with fewer *independent*
                  observations than the floor can never be a confident
                  edge, no matter how pretty its mean is.
    significance: where the 95% CI of E_net sits relative to break-even —
                  lower bound ≥ 0 → 100 (the edge clears zero even at the
                  pessimistic end), ≤ −bar → 0, linear in between. When
                  the CI is unavailable, significance is skipped and the
                  size component carries the score.
    """
    criteria = criteria or VALIDATION_CRITERIA
    bar_e = float(criteria["expectancy"])
    n_eff = float(stats.get("n_eff", 0.0) or 0.0)
    size_score = 100.0 * _clamp(n_eff / max(1, min_decided), 0.0, 1.0)

    ci = stats.get("expectancy_net_ci95")
    sig: float | None = None
    if ci and ci[0] is not None:
        lo = float(ci[0])
        sig = 100.0 * _clamp((lo + bar_e) / max(bar_e, 1e-9), 0.0, 1.0)

    if sig is None:
        score = size_score
        sig_block = None
    else:
        score = 0.5 * size_score + 0.5 * sig
        sig_block = {
            "score": round(sig, 1),
            "ci95_low": round(float(ci[0]), 4),
            "note": "CI lower bound vs break-even",
        }

    return {
        "score": round(score, 1),
        "size": {
            "score": round(size_score, 1),
            "n_eff": round(n_eff, 2),
            "min_decided": min_decided,
        },
        "significance": sig_block,
    }


# ──────────────────────────────────────────────────────────────────────────
# Component 4 — parameter plateau (0–100), the BT5 cap
# ──────────────────────────────────────────────────────────────────────────
def plateau_score(plateau: dict, criteria: dict | None = None) -> dict:
    """The parameter-plateau test (BT5): does the edge persist across a
    neighbourhood of a strategy parameter, or only at one isolated point?

    ``plateau`` shape (produced by `run_quality_sweep`, but any caller
    can supply it — e.g. a future TP-target or stop-distance sweep):

        {"param": "min_confidence",
         "base": 55,
         "points": [{"value": 50, "expectancy_net": 0.21, ...},
                    {"value": 55, "expectancy_net": 0.48, ...},
                    {"value": 60, "expectancy_net": 0.33, ...}]}

    Score = 70% × (fraction of neighbourhood points with E_net > 0) +
    30% × (mean E_net of the neighbourhood ÷ bar). An isolated peak
    (base positive, neighbours negative) scores ~33 and **caps the total
    quality at 50** — a fit, not an edge.
    """
    criteria = criteria or VALIDATION_CRITERIA
    bar_e = float(criteria["expectancy"])
    points = plateau.get("points") or []
    if len(points) < 2:
        return {
            "score": None,
            "cap": False,
            "points": [],
            "note": "fewer than 2 parameter points — plateau not testable",
        }
    positives = [p for p in points if float(p.get("expectancy_net", 0.0) or 0.0) > 0]
    frac_pos = len(positives) / len(points)
    mean_e = sum(float(p.get("expectancy_net", 0.0) or 0.0) for p in points) / len(
        points
    )
    magnitude = _clamp(mean_e / max(bar_e, 1e-9), 0.0, 1.0)
    score = 100.0 * (0.7 * frac_pos + 0.3 * magnitude)
    return {
        "score": round(score, 1),
        "cap": score < PLATEAU_CAP,
        "param": plateau.get("param", "?"),
        "base": plateau.get("base"),
        "fraction_positive": round(frac_pos, 3),
        "mean_expectancy_net": round(mean_e, 3),
        "points": points,
        "note": (
            f"{len(positives)}/{len(points)} points positive, "
            f"mean E_net {mean_e:+.3f}R vs bar {bar_e:+.2f}R"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────
# The composite
# ──────────────────────────────────────────────────────────────────────────
def _band(score: float | None) -> str | None:
    if score is None:
        return None
    for cut, label in BAND_CUTS:
        if cut is None or score >= cut:
            return label
    return "fragile"


def backtest_quality_score(
    rows: list[dict],
    *,
    min_decided: int = DEFAULT_MIN_DECIDED,
    criteria: dict | None = None,
    step: int = 1,
    plateau: dict | None = None,
) -> dict:
    """The P12.4 Backtest Quality Score 0–100 for one book of decided rows.

    Pure: same rows in → same score out. Never raises on an empty book —
    an empty book reports ``quality=None`` with a reason, which is the
    truth (silence is not an edge).

    ``step`` is the walk-forward bar step (overlap correction, P12.3.3);
    rows that carry their own recorded ``step`` override it inside
    ``trade_stats``. ``plateau`` is the optional BT5 evidence — when
    present it participates in the composite and can cap the total at 50.
    """
    criteria = criteria or VALIDATION_CRITERIA
    rows = [r for r in rows if r.get("r") is not None]
    if not rows:
        return {
            "ok": True,
            "quality": None,
            "band": None,
            "components": None,
            "plateau_cap": False,
            "reason": "no decided trades — nothing to score",
            "evaluated_on": "net",
            "overlap_corrected": True,
        }

    stats = trade_stats(rows, step=step)
    edge = edge_score(stats, criteria)
    robustness = curve_robustness(rows)
    sample = sample_score(stats, min_decided, criteria)
    plat = plateau_score(plateau, criteria) if plateau else None

    parts: list[tuple[str, float]] = [
        ("edge", edge["score"]),
        ("robustness", robustness["score"]),
        ("sample", sample["score"]),
    ]
    if plat is not None and plat["score"] is not None:
        parts.append(("plateau", plat["score"]))
    weights = {k: WEIGHTS[k] for k, _ in parts}
    total_w = sum(weights.values()) or 1.0
    quality = sum((weights[k] / total_w) * s for k, s in parts)

    # BT5 cap: an isolated parameter peak is a fit, not an edge.
    plateau_cap = bool(plat and plat["cap"])
    if plateau_cap:
        quality = min(quality, PLATEAU_CAP)

    return {
        "ok": True,
        "quality": round(quality, 1),
        "band": _band(quality),
        "weights": {k: round(w / total_w, 3) for k, w in weights.items()},
        "components": {
            "edge": edge,
            "robustness": robustness,
            "sample": sample,
            "plateau": plat,
        },
        "plateau_cap": plateau_cap,
        "evaluated_on": "net",
        "overlap_corrected": True,
        "n_eff": stats.get("n_eff"),
        "n": stats.get("n"),
    }


# ──────────────────────────────────────────────────────────────────────────
# The plateau sweep (store-only, like the locked P12.1 protocol)
# ──────────────────────────────────────────────────────────────────────────
def _grade_store_book(
    exchange: str,
    market: str,
    symbol: str,
    timeframe: str,
    bars: int,
    horizons: list | None,
    min_bars: int | None,
    step: int,
    min_confidence: int,
    cost_model=None,
) -> dict:
    """One walk-forward grade of the stored series at one parameter point."""
    from config import BACKTEST_MIN_BARS
    from data.backtester import run_backtest_on_store
    from data.scorecard import rows_from_graded

    result = run_backtest_on_store(
        exchange=exchange,
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        horizons=horizons,
        min_bars=BACKTEST_MIN_BARS if min_bars is None else min_bars,
        step=step,
        min_confidence=min_confidence,
    )
    if not result.get("ok", True) or result.get("error"):
        return {"ok": False, "error": result.get("error", "backtest failed")}
    rows = rows_from_graded(
        result.get("graded", []),
        symbol=symbol,
        timeframe=timeframe,
        cost_model=cost_model,
    )
    return {"ok": True, "rows": rows, "meta": result.get("report", {}).get("meta", {})}


def run_quality_sweep(
    *,
    exchange: str = "binance",
    market: str = "perp",
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    bars: int = 1000,
    horizons: list | None = None,
    min_bars: int | None = None,
    step: int = 3,
    min_confidence: int = MIN_CONFIDENCE,
    min_decided: int = DEFAULT_MIN_DECIDED,
    cost_model=None,
    offsets: tuple = (-5, 0, 5),
    conf_min: int = 40,
    conf_max: int = 90,
    grade_fn: Callable | None = None,
) -> dict:
    """P12.4 plateau sweep: re-grade the stored series at every point of a
    strategy-parameter neighbourhood and score the base book with that
    evidence.

    Default parameter: ``min_confidence`` (the engine gate that decides
    which plans exist at all), swept at ±5 around the configured value,
    clamped to ``[conf_min, conf_max]`` (deduplicated). ``grade_fn`` is
    injectable for offline tests; it receives one ``min_confidence`` int
    and must return ``{"ok": True, "rows": [...]}`` or
    ``{"ok": False, "error": ...}``.

    Store-only by design: re-grading requires a stored series, exactly
    like the locked P12.1 protocol. Missing/short series return a clear
    error, never a score.
    """

    grade_fn = grade_fn or (
        lambda conf: _grade_store_book(
            exchange=exchange,
            market=market,
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            horizons=horizons,
            min_bars=min_bars,
            step=step,
            min_confidence=conf,
            cost_model=cost_model,
        )
    )

    # The base parameter point is sacred — grade it even when the offsets
    # clamp onto it (e.g. min_confidence at the floor makes -5 a duplicate).
    base_conf = int(_clamp(min_confidence, conf_min, conf_max))
    confs: list[int] = []
    for offset in offsets:
        conf = int(_clamp(min_confidence + int(offset), conf_min, conf_max))
        if conf not in confs:
            confs.append(conf)
    if base_conf not in confs:
        confs.insert(0, base_conf)

    base_rows: list | None = None
    points: list[dict] = []
    meta: dict = {}
    for conf in confs:
        book = grade_fn(conf)
        if not book.get("ok") or book.get("error"):
            return {"ok": False, "error": book.get("error", "grade failed")}
        rows = book.get("rows") or []
        stats = trade_stats(rows, step=step) if rows else {}
        point = {
            "offset": conf - min_confidence,
            "min_confidence": conf,
            "n": stats.get("n", 0),
            "n_eff": stats.get("n_eff"),
            "expectancy_net": stats.get("expectancy_net", 0.0),
            "win_rate_net": stats.get("win_rate_net"),
            "pf_net": stats.get("pf_net"),
        }
        points.append(point)
        if conf == base_conf:
            base_rows = rows
            meta = book.get("meta") or {}

    if base_rows is None:
        return {"ok": False, "error": "base parameter point not in sweep"}

    plateau = {"param": "min_confidence", "base": base_conf, "points": points}
    quality = backtest_quality_score(
        base_rows, min_decided=min_decided, step=step, plateau=plateau
    )

    return {
        "ok": True,
        **quality,
        "plateau": plateau,
        "meta": {
            **meta,
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange": exchange,
            "market": market,
            "bars": bars,
            "step": step,
            "min_confidence_swept": min_confidence,
            "param_sweep": "min_confidence",
            "offsets": list(offsets),
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Boxed printer — one command, one block (same payload as JSON/HTTP/MCP)
# ──────────────────────────────────────────────────────────────────────────
W = 82


def _fmt(v, spec: str = ".1f") -> str:
    return format(v, spec) if isinstance(v, (int, float)) else "n/a"


def print_quality(report: dict) -> None:
    """The P12.4 boxed block. Works for the sweep report and for the
    embedded scorecard block (a ``quality`` key inside a scorecard)."""
    if not report.get("ok"):
        print("BACKTEST QUALITY — cannot score")
        print(f"  {report.get('error', 'unknown error')}")
        return
    if report.get("quality") is None:
        print("BACKTEST QUALITY — cannot score")
        print(f"  {report.get('reason', 'no decided trades')}")
        return

    print("=" * W)
    print(
        f"BACKTEST QUALITY  {_fmt(report['quality'])}/100   "
        f"band: {report['band']}   evaluated NET of costs, "
        f"overlap-corrected (P12.4)"
    )
    comp = report.get("components") or {}
    weights = report.get("weights") or {}
    w_parts = " · ".join(f"{k} {w:.0%}" for k, w in sorted(weights.items()))
    print(f"weights   {w_parts}")
    print("-" * W)
    if comp.get("edge"):
        e = comp["edge"]
        print(
            f"  edge       {_fmt(e['score']):>6}/100  "
            f"E_net {e['expectancy_net']:+.3f}R vs bar "
            f"{e['bar_expectancy']:+.2f}R  shape ×{e['shape']}"
        )
        for note in e.get("notes", []):
            print(f"              ⚠ {note}")
    if comp.get("robustness"):
        r = comp["robustness"]
        print(f"  robustness {_fmt(r['score']):>6}/100  n={r['n']}")
        if r.get("concentration"):
            c = r["concentration"]
            print(
                f"              concentration {_fmt(c['score']):>5}/100  "
                f"top-5 share "
                f"{_fmt(c['share_top5'], '.1%') if c['share_top5'] is not None else 'n/a'}"
            )
        if r.get("drawdown"):
            d = r["drawdown"]
            print(f"              drawdown      {_fmt(d['score']):>5}/100  {d['note']}")
        if r.get("segments"):
            s = r["segments"]
            seg_s = _fmt(s["score"]) if s["score"] is not None else "n/a"
            print(f"              segments      {seg_s:>5}/100  {s['note']}")
    if comp.get("sample"):
        s = comp["sample"]
        print(
            f"  sample     {_fmt(s['score']):>6}/100  "
            f"N_eff {_fmt(s['size']['n_eff'], '.2f')} vs "
            f"min_decided {s['size']['min_decided']}"
        )
        if s.get("significance"):
            sig = s["significance"]
            print(
                f"              significance  {_fmt(sig['score']):>5}/100  "
                f"CI95 low {sig['ci95_low']:+.3f}R (break-even = 0)"
            )
    if comp.get("plateau") and comp["plateau"].get("score") is not None:
        p = comp["plateau"]
        print(f"  plateau    {_fmt(p['score']):>6}/100  {p['note']}")
        if p.get("cap"):
            print(
                "              🛑 isolated parameter peak — total "
                "CAPPED at 50 (a fit, not an edge)"
            )
    print("-" * W)
    print(
        f"BACKTEST QUALITY VERDICT  "
        f"{'🟢 ' + report['band'] if report['quality'] >= 60 else '🔴 ' + report['band']}  "
        f"{report['quality']}/100"
    )
    print(
        "  A quality score reports robustness; it does not grant "
        "permission. The graduation bar is unchanged."
    )
    print("=" * W)
