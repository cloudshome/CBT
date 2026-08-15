"""data/strategy_score.py — P12.5: the strategy score on the calibrator.

The scorecard (P12.3/P12.6/P12.3.3) answers *"is this book profitable net of
costs, with honest overlap-corrected uncertainty?"*, P12.4 answers *"is the
curve robust, or did it win by luck?"* — P12.5 answers the question the
calibrator (`brain/calibrator.py`) actually acts on:

> **"How much of this setup's observed edge should we trust to repeat —
> and is this the regime it fits, at costs we can survive?"**

Per `docs/FREQTRADE_REVIEW.md` §8 F25 and `docs/BACKTRADER_REVIEW.md` §8 BT12,
the strategy score is the audits' formula:

    Score = E_R × Stability × SampleConfidence − DD/Complexity penalties

landing on the calibrator as four multiplicative components, each 0–100,
computed NET of costs (P12.6) over the same decided rows the scorecard and
quality score read (invariant #10):

  e_r             (35%) — net expectancy vs the graduation bar, shape-
                          discounted — literally P12.4's `edge_score`. A
                          setup with E_net <= 0 scores 0, and because the
                          composite is a product, zero edge ⇒ score 0.
  sample_quality  (35%) — P12.4's `backtest_quality_score()` in full: curve
                          robustness (top-5 concentration / drawdown /
                          chronological segments) × sample confidence
                          (N_eff vs min_decided + CI95 significance). This
                          is the audits' "Stability × SampleConfidence",
                          already built and already judged — we read it, we
                          do not reimplement it.
  regime_fit      (15%) — does the edge persist across the regimes the
                          setup traded in? For a `plan_type` key this is the
                          sample-weighted fraction of regimes with positive
                          E_net (a one-regime edge is real, but the base key
                          is dampened until you know which regime is coming).
                          For a `plan_type::regime` key it is the regime's
                          E_net vs the setup's all-regime E_net (100 = the
                          edge is ≥1.5× stronger here; 66.7 = exactly the
                          setup average; 0 = no edge in this regime).
  execution       (15%) — the share of the gross edge that survives the
                          P12.6 cost model: 1 − avg_cost_r / avg_gross_r.
                          Until micro-live records real slippage / partial
                          fills / latency, modelled fees+spread+funding are
                          the closest honest measure of execution reality.

The composite is a **weighted geometric mean**, not the arithmetic mean
P12.4 uses: the "×" in the audits' formula is deliberate. A strategy must be
good on *every* axis — a single zero multiplies the whole score to zero,
which is exactly what "no edge × anything" means. This is stricter than an
average and it is meant to be.

Design rules (inherited, do not "improve" away):

  * No second grader and no new math engine: `edge_score` / the quality
    score / `trade_stats` are imported from P12.4/P12.3 modules. This file
    only *judges* what they already computed.
  * Deterministic, offline, dependency-free beyond the existing stack —
    `DEMO_MODE=1` and CI stay green.
  * Everything degrades to ``None``/a documented default rather than to a
    guess when the sample cannot support it.
  * The score is a report, not permission: it modulates the calibrator's
    trust dial, never loosens the graduation bar, and never grants a trade.

`multiplier_from_score()` is the calibrator wiring: the P12.5 strategy score
gates how much of the observed gross expectancy is trusted to repeat
(score 50 → the pre-P12.5 formula, score 100 → ×1.5 trust, score 0 → ×0.6
floor). Positive-expectancy setups are only boosted when the evidence is
strong; a fragile curve is dampened, not celebrated.
"""
from __future__ import annotations

import math
from typing import Optional

from config import BACKTEST_STEP, CALIBRATE_GAIN, CALIBRATE_MAX_MULT, CALIBRATE_MIN_MULT
from data.quality_score import backtest_quality_score, edge_score
from data.scorecard import trade_stats
from data.validation import DEFAULT_MIN_DECIDED, VALIDATION_CRITERIA

# Component weights (documented in the module docstring). When a component
# cannot be computed (e.g. sample_quality is None on an empty book) it is
# dropped and the remainder renormalised — but the strategy score itself
# reports None on an empty book, so in practice all four are present.
WEIGHTS: dict[str, float] = {
    "e_r": 0.35,
    "sample_quality": 0.35,
    "regime_fit": 0.15,
    "execution": 0.15,
}

BAND_CUTS = ((80.0, "robust"), (60.0, "acceptable"),
             (40.0, "borderline"), (None, "fragile"))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _band(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    for cut, label in BAND_CUTS:
        if cut is None or score >= cut:
            return label
    return "fragile"


def _net_e(rows: list[dict]) -> float:
    """Net expectancy of a subset, in R — from `trade_stats`, the one source."""
    stats = trade_stats(rows)
    return float(stats.get("expectancy_net", 0.0) or 0.0)


# ──────────────────────────────────────────────────────────────────────────
# Components
# ──────────────────────────────────────────────────────────────────────────
def regime_fit_score(rows: list[dict], *, regime: Optional[str] = None,
                     setup_rows: Optional[list[dict]] = None) -> dict:
    """Does the edge persist across regimes (base key) or fit THIS regime
    (plan_type::regime key)?

    base key (``regime is None``): sample-weighted fraction of the regimes
    the setup traded in with positive E_net. A book that only wins in one
    regime is dampened here — the base key cannot know which regime is next.
    A single-regime book is 100 (that regime IS the book; no conditioning
    data exists, so neutrality is the honest answer).

    regime key: the regime's E_net vs the setup's all-regime E_net
    (``setup_rows``). 100 = edge ≥ 1.5× the setup average; 66.7 = exactly
    average; 0 = no edge in this regime. When the setup's overall edge is
    non-positive but THIS regime is positive, the edge lives only here → 100.
    """
    setup_rows = [r for r in (setup_rows or rows) if r.get("r") is not None]
    if regime is None:
        by_regime: dict[str, list[dict]] = {}
        for r in setup_rows:
            by_regime.setdefault(str(r.get("regime") or "UNKNOWN"), []).append(r)
        if len(by_regime) <= 1:
            return {"score": 100.0, "regimes": 1, "note":
                    "single-regime book — no conditioning to apply (neutral)"}
        total = 0
        positive = 0
        per: dict[str, float] = {}
        for name, sub in by_regime.items():
            e = _net_e(sub)
            per[name] = round(e, 3)
            total += len(sub)
            if e > 0:
                positive += len(sub)
        frac = positive / total if total else 0.0
        return {"score": round(100.0 * frac, 1), "regimes": len(by_regime),
                "fraction_positive": round(frac, 3), "per_regime": per,
                "note": (f"{positive}/{total} samples in regimes with "
                         f"positive E_net ({len(by_regime)} regimes)")}
    # regime-specific key
    key_e = _net_e(rows)
    setup_e = _net_e(setup_rows)
    if setup_e > 0:
        ratio = _clamp(key_e / setup_e, 0.0, 1.5)
        score = 100.0 * ratio / 1.5
        note = (f"E_net in {regime} {key_e:+.3f}R vs setup average "
                f"{setup_e:+.3f}R → ratio {ratio:.2f}")
    elif key_e > 0:
        score, note = 100.0, (f"only positive E_net lives in {regime} "
                              f"({key_e:+.3f}R); setup average {setup_e:+.3f}R")
    else:
        score, note = 0.0, (f"no positive E_net in {regime} "
                            f"({key_e:+.3f}R) and setup average "
                            f"{setup_e:+.3f}R")
    return {"score": round(score, 1), "regime": regime,
            "regime_e_net": round(key_e, 3), "setup_e_net": round(setup_e, 3),
            "note": note}


def execution_score(rows: list[dict]) -> dict:
    """Share of the gross edge that survives the P12.6 cost model.

    ``100 × clamp(1 − avg_cost_r / avg_gross_r, 0, 1)`` when gross expectancy
    is positive — 66 means two thirds of the gross edge survives fees +
    spread + funding, 0 means costs eat the whole edge. A non-positive gross
    edge has nothing to survive → 0 (the e_r factor already zeroes the
    composite in that case; this keeps the component honest on its own).
    Micro-live will replace the modelled cost drag with real fills; until
    then this is the closest honest measure of execution reality.
    """
    n = len(rows)
    if n == 0:
        return {"score": 0.0, "note": "no decided trades"}
    avg_gross = sum(float(r.get("r", 0.0) or 0.0) for r in rows) / n
    avg_cost = sum(float(r.get("cost_r", 0.0) or 0.0) for r in rows) / n
    if avg_gross <= 0:
        return {"score": 0.0, "avg_gross_r": round(avg_gross, 3),
                "avg_cost_r": round(avg_cost, 4),
                "note": f"gross E {avg_gross:+.3f}R <= 0 — nothing to survive costs"}
    share = _clamp(1.0 - avg_cost / avg_gross, 0.0, 1.0)
    return {"score": round(100.0 * share, 1),
            "avg_gross_r": round(avg_gross, 3),
            "avg_cost_r": round(avg_cost, 4),
            "cost_share": round(avg_cost / avg_gross, 4),
            "note": (f"{share:.0%} of gross E {avg_gross:+.3f}R survives "
                     f"avg cost {avg_cost:.4f}R/trade")}


# ──────────────────────────────────────────────────────────────────────────
# The composite (weighted geometric mean — the audits' "×")
# ──────────────────────────────────────────────────────────────────────────
def _geo_mean(parts: list[tuple[str, float]], weights: dict[str, float]) -> float:
    total_w = sum(weights.get(k, 0.0) for k, _ in parts)
    if not parts or total_w <= 0:
        return 0.0
    return 100.0 * math.prod(
        (_clamp(s, 0.0, 100.0) / 100.0) ** (weights[k] / total_w)
        for k, s in parts)


def strategy_score(rows: list[dict], *, plan_type: str = "",
                   regime: Optional[str] = None,
                   setup_rows: Optional[list[dict]] = None,
                   min_decided: int = DEFAULT_MIN_DECIDED,
                   criteria: Optional[dict] = None,
                   step: int = BACKTEST_STEP) -> dict:
    """The P12.5 strategy score 0–100 for one calibration key's decided rows.

    Pure: same rows in → same score out. Never raises on an empty book —
    an empty book reports ``score=None`` with a reason, which is the truth.

    ``regime`` is the key's regime suffix (``None`` for a base ``plan_type``
    key); ``setup_rows`` is the plan_type's decided rows across ALL regimes
    (defaults to ``rows`` when the caller has no wider book — regime-fit then
    degrades to its single-regime neutral). ``step`` is the walk-forward bar
    step used for overlap correction (P12.3.3), exactly as in the scorecard.
    """
    criteria = criteria or VALIDATION_CRITERIA
    rows = [r for r in rows if r.get("r") is not None]
    if not rows:
        return {"ok": True, "score": None, "band": None,
                "components": None, "reason": "no decided trades — nothing to score",
                "plan_type": plan_type, "regime": regime,
                "evaluated_on": "net", "overlap_corrected": True}

    stats = trade_stats(rows, step=step)
    e_r = edge_score(stats, criteria)
    q = backtest_quality_score(rows, min_decided=min_decided,
                               criteria=criteria, step=step)
    sample_q = q.get("quality")  # 0–100 or None (never on a non-empty book)
    rf = regime_fit_score(rows, regime=regime, setup_rows=setup_rows)
    ex = execution_score(rows)

    parts: list[tuple[str, float]] = [
        ("e_r", float(e_r["score"])),
        ("sample_quality", float(sample_q) if sample_q is not None else 0.0),
        ("regime_fit", float(rf["score"])),
        ("execution", float(ex["score"])),
    ]
    score = _geo_mean(parts, WEIGHTS)

    return {
        "ok": True,
        "score": round(score, 1),
        "band": _band(score),
        "weights": dict(WEIGHTS),
        "expectancy_net": stats.get("expectancy_net"),
        "n": stats.get("n"),
        "n_eff": stats.get("n_eff"),
        "components": {
            "e_r": {"score": e_r["score"], "expectancy_net": e_r["expectancy_net"],
                    "bar_expectancy": e_r["bar_expectancy"],
                    "shape": e_r["shape"], "notes": e_r.get("notes", [])},
            "sample_quality": {"score": sample_q, "band": q.get("band"),
                               "quality_block": q},
            "regime_fit": rf,
            "execution": ex,
        },
        "evaluated_on": "net",
        "overlap_corrected": True,
        "plan_type": plan_type,
        "regime": regime,
    }


# ──────────────────────────────────────────────────────────────────────────
# Calibrator wiring — the trust dial
# ──────────────────────────────────────────────────────────────────────────
def multiplier_from_score(expectancy: float,
                          strategy_score_value: Optional[float],
                          gain: float = CALIBRATE_GAIN,
                          mult_min: float = CALIBRATE_MIN_MULT,
                          mult_max: float = CALIBRATE_MAX_MULT,
                          expectancy_net: Optional[float] = None) -> float:
    """Expectancy → calibration multiplier, gated by the strategy score.

    ``mult = clamp(1 + E_anchor × gain × trust, mult_min, mult_max)`` where
    ``trust = clamp(score / 50, 0.6, 1.5)``. A score of 50 is the neutral
    pre-P12.5 formula; a robust, well-sampled, regime-fit, cost-surviving
    setup is trusted up to 1.5×; a fragile or net-negative book is trusted
    at the 0.6 floor — its boost/dampening is shrunk, not celebrated. An
    unknown score (None) is neutral.

    **P12.8 — the sign anchor is NET of costs.** ``E_anchor`` is
    ``expectancy_net`` when it is known, falling back to ``expectancy``
    (gross) only when costs could not be computed for the key. Anchoring on
    gross was a real defect, not a cosmetic one: a setup measured at
    ``E_gross = +0.055R`` / ``E_net = −0.118R`` — positive before costs,
    losing money after them — received multiplier **×1.008**, i.e. the
    engine *raised* confidence on a setup that loses money. Because the
    anchor is now the number the money actually does, any book that does
    not survive its own costs is dampened (``1 + negative × … < 1``) and
    can never be boosted. This is strictly tighter than the previous
    behaviour: it can only lower a multiplier, never raise one.
    """
    trust = 1.0 if strategy_score_value is None \
        else _clamp(float(strategy_score_value) / 50.0, 0.6, 1.5)
    anchor = float(expectancy if expectancy_net is None else expectancy_net)
    return round(max(mult_min, min(mult_max, 1.0 + anchor * gain * trust)), 3)
