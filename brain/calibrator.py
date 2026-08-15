"""brain/calibrator.py

The self-improvement loop. After enough historical backtest outcomes and
approved live-market paper outcomes accumulate in the database, the calibrator
computes a per-plan-type "calibration profile":

    multiplier = clamp(1 + expectancy * gain, min_mult, max_mult)

* Positive-expectancy setups (e.g. Buy Pullback) get a multiplier > 1
  → their confidence is boosted in future signals.
* Negative-expectancy setups (e.g. Breakout Buy in our first run) get
  a multiplier < 1 → dampened; if they are bad enough and well-sampled
  they can be dropped entirely (CALIBRATE_FILTER).

The profile is stored in the DB and loaded by `analyze_frame` → `build_plans`,
so the engine literally improves with every backtest you run. With zero data
the profile is empty and every multiplier is 1.0 (neutral — no behaviour
change), so calibration is strictly additive.

**P12.5 — strategy score on the calibrator.** Since 2.16.0 every profile
entry also carries the strategy score (`E_R × sample-quality × regime-fit ×
execution`, `data/strategy_score.py`): sample-quality reads P12.4's
`backtest_quality_score()` in full, so a fragile, weakly-sampled, or
cost-doomed curve can no longer earn a boost on gross expectancy alone. The
multiplier formula keeps its sign anchor (positive-gross setups are boosted,
negative ones dampened or filtered) but the P12.5 score is now the *trust
dial*: `mult = clamp(1 + E_gross × gain × trust, min, max)` with
`trust = clamp(score/50, 0.6, 1.5)` — a robust edge is trusted up to 1.5×,
a fragile one is shrunk to the 0.6 floor.
"""
from __future__ import annotations

import time
from typing import Optional

from config import (CALIBRATE_MIN_N, CALIBRATE_MIN_PAPER_N, CALIBRATE_GAIN,
                    CALIBRATE_MAX_MULT, CALIBRATE_MIN_MULT, CALIBRATE_FILTER,
                    CALIBRATE_FILTER_THRESHOLD, TP_RR_MIN, TP_RR_MAX,
                    BACKTEST_STEP)
from data.database import SignalDB
from data.validation import DEFAULT_MIN_DECIDED

WIN_SET = {"FULL_WIN", "PARTIAL_WIN"}


def profile_key(plan_type: str, regime: str = "") -> str:
    """Composite calibration key: ``plan_type`` or ``plan_type::regime``."""
    return f"{plan_type}::{regime}" if regime else plan_type


def compute_expectancy_by_type(db: SignalDB, horizons: Optional[list[float]] = None) -> dict:
    """Expectancy (average R) per plan type from backtests + paper outcomes."""
    # Historical walk-forward grades and live-market paper outcomes are both
    # useful evidence, but remain separate tables so the dashboard can show
    # them honestly.  The calibration pass deliberately combines only decided
    # outcomes: TP_HIT behaves like a win; STOP_LOSS behaves like a loss.
    rows = db.conn.execute(
        """WITH decided AS (
                 SELECT plan_type, outcome, rr_achieved, 'backtest' AS source
                 FROM backtest_results
                 WHERE outcome IN ('FULL_WIN','PARTIAL_WIN','LOSS')
                 UNION ALL
                 SELECT plan_type,
                        CASE outcome WHEN 'TP_HIT' THEN 'FULL_WIN'
                                     WHEN 'STOP_LOSS' THEN 'LOSS' END AS outcome,
                        rr_achieved, 'paper' AS source
                 FROM paper_trades
                 WHERE outcome IN ('TP_HIT','STOP_LOSS')
             )
             SELECT plan_type,
                    COUNT(*) n,
                    SUM(CASE WHEN outcome IN ('FULL_WIN','PARTIAL_WIN') THEN 1 ELSE 0 END) wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) losses,
                    SUM(CASE WHEN source='backtest' THEN 1 ELSE 0 END) backtest_samples,
                    SUM(CASE WHEN source='paper' THEN 1 ELSE 0 END) paper_samples,
                    AVG(rr_achieved) avg_rr
             FROM decided
             GROUP BY plan_type"""
    ).fetchall()
    out = {}
    for r in rows:
        n = r["n"] or 0
        wins = r["wins"] or 0
        losses = r["losses"] or 0
        decided = wins + losses
        avg_rr = r["avg_rr"] or 0.0
        out[r["plan_type"]] = {
            "n": n,
            "wins": wins,
            "losses": losses,
            "backtest_samples": r["backtest_samples"] or 0,
            "paper_samples": r["paper_samples"] or 0,
            "win_rate": round(wins / decided, 3) if decided else None,
            "expectancy": round(avg_rr, 3),
        }
    return out


def _decided_by_key(db: SignalDB) -> dict:
    """Expectancy per (plan_type, regime) from backtests + paper outcomes."""
    rows = db.conn.execute(
        """WITH decided AS (
                 SELECT plan_type, regime, outcome, rr_achieved, 'backtest' AS source
                 FROM backtest_results
                 WHERE outcome IN ('FULL_WIN','PARTIAL_WIN','LOSS')
                 UNION ALL
                 SELECT plan_type, regime,
                        CASE outcome WHEN 'TP_HIT' THEN 'FULL_WIN'
                                     WHEN 'STOP_LOSS' THEN 'LOSS' END AS outcome,
                        rr_achieved, 'paper' AS source
                 FROM paper_trades
                 WHERE outcome IN ('TP_HIT','STOP_LOSS')
             )
             SELECT plan_type, COALESCE(NULLIF(regime,''),'') AS regime,
                    COUNT(*) n,
                    SUM(CASE WHEN outcome IN ('FULL_WIN','PARTIAL_WIN') THEN 1 ELSE 0 END) wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) losses,
                    SUM(CASE WHEN source='backtest' THEN 1 ELSE 0 END) backtest_samples,
                    SUM(CASE WHEN source='paper' THEN 1 ELSE 0 END) paper_samples,
                    AVG(rr_achieved) avg_rr,
                    AVG(CASE WHEN outcome IN ('FULL_WIN','PARTIAL_WIN') THEN rr_achieved END) avg_win_rr
             FROM decided
             GROUP BY plan_type, regime"""
    ).fetchall()
    out = {}
    for r in rows:
        n = r["n"] or 0
        wins = r["wins"] or 0
        losses = r["losses"] or 0
        decided = wins + losses
        key = profile_key(r["plan_type"], r["regime"])
        out[key] = {
            "n": n,
            "wins": wins,
            "losses": losses,
            "backtest_samples": r["backtest_samples"] or 0,
            "paper_samples": r["paper_samples"] or 0,
            "win_rate": round(wins / decided, 3) if decided else None,
            "expectancy": round(r["avg_rr"] or 0.0, 3),
            "avg_win_rr": round(r["avg_win_rr"], 3) if r["avg_win_rr"] is not None else None,
        }
    return out


def _decided_rows_by_key(db: SignalDB) -> tuple[dict, dict]:
    """Decided rows per calibration key, plus per plan_type across regimes.

    Reuses the scorecard's row adapters (`data/scorecard.py`) so the rows
    feeding P12.5 are the exact same row shape the scorecard and P12.4 read
    (ts / side / setup / regime / r / r_net / cost_r / …) — one computation,
    many surfaces (invariant #10). Paper samples are included, matching the
    calibrator's aggregate SQL (the paper book is real evidence too).

    Returns ``(rows_by_key, setup_rows_by_type)`` where keys are
    ``plan_type`` or ``plan_type::regime`` (see `profile_key`).
    """
    from data.scorecard import rows_from_backtest_db, rows_from_paper_db

    backtest_rows = rows_from_backtest_db(db, include_sim=True)
    paper_rows = rows_from_paper_db(db, include_sim=True)

    rows_by_key: dict[str, list[dict]] = {}
    setup_rows_by_type: dict[str, list[dict]] = {}
    for r in backtest_rows + paper_rows:
        key = profile_key(r.get("setup") or "?", r.get("regime") or "")
        rows_by_key.setdefault(key, []).append(r)
        setup_rows_by_type.setdefault(r.get("setup") or "?", []).append(r)
    return rows_by_key, setup_rows_by_type


def build_profile(db: SignalDB, filter_neg: bool = CALIBRATE_FILTER,
                  min_n: int = CALIBRATE_MIN_N,
                  min_paper_n: int = CALIBRATE_MIN_PAPER_N,
                  min_decided: int = DEFAULT_MIN_DECIDED,
                  criteria: Optional[dict] = None,
                  step: int = BACKTEST_STEP) -> dict:
    """Turn decided backtest/paper stats into a calibration profile.

    Trust thresholds follow the roadmap (decisions A6/B10): a setup is only
    *proven* after >= ``min_n`` backtest samples AND >= ``min_paper_n`` decided
    paper samples with positive expectancy.  Below that it is kept neutral
    (no boost) and flagged ``proven=False`` so the risk gate can refuse it in
    the lower progression levels.

    **P12.5**: every entry that passes the sample gate also carries the
    strategy score 0–100 (`E_R × sample-quality × regime-fit × execution`,
    `data/strategy_score.py`) and a quality-gated multiplier. The score is a
    report field; it never loosens the graduation bar and never grants a
    trade — it only decides how much of the observed expectancy the engine
    is allowed to trust when scaling confidence.
    """
    from data.strategy_score import multiplier_from_score, strategy_score

    stats = _decided_by_key(db)
    rows_by_key, setup_rows_by_type = _decided_rows_by_key(db)
    profile: dict = {}
    for key, st in stats.items():
        n = st["n"]
        if n < min_n:
            continue  # not enough samples to trust — keep neutral
        exp = st["expectancy"]
        plan_type, _, regime = key.partition("::")

        # P12.5 — the strategy score for this key's own decided rows.
        rows = rows_by_key.get(key, [])
        score_block = None
        if rows:
            score_block = strategy_score(
                rows, plan_type=plan_type, regime=(regime or None),
                setup_rows=setup_rows_by_type.get(plan_type, rows),
                min_decided=min_decided, criteria=criteria, step=step)
        score_val = score_block.get("score") if score_block else None

        mult = multiplier_from_score(exp, score_val)
        filtered = bool(filter_neg and exp < CALIBRATE_FILTER_THRESHOLD)
        proven = bool(st["backtest_samples"] >= min_n and
                      st["paper_samples"] >= min_paper_n and exp > 0)
        # Data-driven TP target (decision A2): measured average winner, clamped
        # to a sane range; None keeps the engine default until there is evidence.
        tp_rr = None
        if st["avg_win_rr"] is not None:
            tp_rr = round(max(TP_RR_MIN, min(TP_RR_MAX, st["avg_win_rr"])), 2)
        profile[key] = {
            "multiplier": round(mult, 3),
            "expectancy": exp,
            "expectancy_net": (score_block.get("expectancy_net")
                               if score_block else None),
            "samples": n,
            "backtest_samples": st["backtest_samples"],
            "paper_samples": st["paper_samples"],
            "win_rate": st["win_rate"],
            "filtered": filtered,
            "proven": proven,
            "tp_rr": tp_rr,
            # P12.5 — strategy score 0–100 (E_R × sample-quality ×
            # regime-fit × execution) + its band and per-component block.
            "strategy_score": score_val,
            "strategy_band": (score_block.get("band") if score_block else None),
            "strategy_components": (score_block.get("components")
                                    if score_block else None),
        }
    return profile


def suggest_tp_rr_by_type(profile: dict, regime: str = "") -> dict:
    """Map plan_type -> suggested TP distance in R from the profile (A2).

    When a regime is given, regime-specific entries win; otherwise the best-
    sampled entry per plan type is used.
    """
    out: dict[str, dict] = {}
    for key, e in profile.items():
        if not e.get("tp_rr"):
            continue
        plan_type = key.split("::")[0]
        if regime and key.endswith(f"::{regime}"):
            cur = out.get(plan_type)
            if cur is None or e["samples"] > cur["samples"]:
                out[plan_type] = e
        elif not regime and "::" not in key:
            out[plan_type] = e
    if not regime:
        # Fall back to the best-sampled entry per plan type across regimes.
        by_type: dict[str, dict] = {}
        for key, e in profile.items():
            if not e.get("tp_rr"):
                continue
            pt = key.split("::")[0]
            cur = by_type.get(pt)
            if cur is None or e["samples"] > cur["samples"]:
                by_type[pt] = e
        for pt, e in by_type.items():
            out.setdefault(pt, e)
    return {pt: e["tp_rr"] for pt, e in out.items()}


def learn(profile_path: Optional[str] = None) -> dict:
    """Run the calibration pass over the current database."""
    with SignalDB() as db:
        profile = build_profile(db)
        db.save_calibration(profile)
    return {"profile": profile, "note": "saved to DB — engine will use it on the next scan"}


def apply_calibration(conf: int, plan_type: str, calibration: dict,
                      regime: str = "") -> tuple[int, bool]:
    """Apply the calibration profile to one plan's confidence.
    Returns (adjusted_confidence, filtered_out)."""
    if not calibration:
        return conf, False
    entry = calibration.get(profile_key(plan_type, regime))
    if entry is None:
        entry = calibration.get(plan_type)
    if not entry:
        return conf, False
    if entry.get("filtered"):
        return conf, True
    mult = entry.get("multiplier", 1.0)
    return max(5, min(100, int(round(conf * mult)))), False


def describe(profile: dict) -> str:
    if not profile:
        return "No calibration yet — run `python main.py learn` after a backtest with --save."
    lines = ["Calibration profile (applied to future signals; ✓ = proven setup):"]
    for pt, e in sorted(profile.items(), key=lambda kv: kv[1]["samples"], reverse=True):
        proven = "✓" if e.get("proven") else " "
        score = e.get("strategy_score")
        band = e.get("strategy_band")
        score_bits = (f"score {score:.0f}/100 {band}" if score is not None
                      else "score n/a")
        if e["filtered"]:
            lines.append(f"  {proven} {pt:<24} FILTERED (E {e['expectancy']:+.2f}R, "
                         f"{score_bits}, n={e['samples']})")
        else:
            lines.append(f"  {proven} {pt:<24} x{e['multiplier']:.2f}  "
                         f"({score_bits}, E {e['expectancy']:+.2f}R "
                         f"→ net {e['expectancy_net'] if e.get('expectancy_net') is not None else e['expectancy']:+.2f}R, "
                         f"win {e['win_rate']*100:.0f}%, bt={e['backtest_samples']} pp={e['paper_samples']}, "
                         f"tp_rr={e['tp_rr']})")
    lines.append("  strategy score = E_R × sample-quality × regime-fit × "
                 "execution (P12.5, evaluated NET of costs)")
    return "\n".join(lines)


# keep import-time reference so `time` is used (updated_at stamping lives in db)
_ = time.time
