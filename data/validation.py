"""data/validation.py — P12.1 protocol + P12.2 lookahead guard.

The Quant Validation Engine (P12, per `docs/FREQTRADE_REVIEW.md` §8 F5/F6
and `docs/BACKTRADER_REVIEW.md` §8 BT5/BT6) begins with the one protocol
every later milestone trusts: a **chronologically locked train / val /
OOS / recent** window split over a stored series, graded by our own
walk-forward backtester (`data/backtester.py`) — the engine re-runs at
every bar on data *up to that bar only*, so there is no look-ahead by
construction.

Locked protocol (do not loosen without reopening F6/BT6 in writing):

  ``train``   earliest window. The ONLY window whose outcomes may feed
              ``learn`` (calibration). A setup that passes train ALONE
              has not passed.
  ``val``     must ALSO meet the bar. Passing = train AND val.
  ``oos``     the sealed envelope: graded, reported, never used to tune,
              calibrate, or pass. An identical run reuses the stored seal
              instead of silently re-deriving it; re-opening requires an
              explicit ``reseal``, which is recorded in the seal history.
  ``recent``  newest window — the walk-forward reality check (sealed,
              exactly like OOS).

The bar is the **live graduation gate's own criteria**
(`data/simulator.GRADUATION_CRITERIA`): expectancy >= 0.50 R,
win rate > 0.55, profit factor >= 1.5 — measured on the primary horizon
over *decided* trades — plus a minimum number of decided trades per
window. Research and graduation therefore speak the same language.

Everything in this module is a report. Nothing places orders, changes
engine weights, or feeds the calibrator.

P12.2 adds ``python main.py validate lookahead``: a deterministic AST guard
for explicit negative pandas row shifts in first-party feature/signal code.
It is intentionally narrower than recursive-state analysis, which remains a
later extension; it does not claim that a source scan replaces the locked
walk-forward protocol.
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from config import (BACKTEST_HORIZONS, BACKTEST_MIN_BARS, BACKTEST_STEP,
                    MIN_CONFIDENCE)
from data.backtester import WIN_SET, _aggregate, run_backtest
from data.simulator import GRADUATION_CRITERIA  # the live graduation bar

WINDOW_NAMES = ("train", "val", "oos", "recent")

#: P12.1 uses the exact graduation bar the desk already enforces — the
#: protocol and the live gate must never diverge. `min_decided` is the
#: validation-specific sample floor (the gate's CALIBRATE_MIN_N analog).
VALIDATION_CRITERIA: dict[str, float] = dict(GRADUATION_CRITERIA)

DEFAULT_WINDOW_FRACTIONS = {"train": 0.60, "val": 0.15,
                            "oos": 0.15, "recent": 0.10}
DEFAULT_MIN_DECIDED = 30
DEFAULT_SEAL_DIR = Path("data/store/validation")  # under gitignored data/store/


class ValidationWindowError(ValueError):
    """The requested series cannot be split into the locked protocol."""


class LookaheadViolation(ValueError):
    """A feature source contains an explicitly future-looking row shift."""


# P12.2 deliberately starts with the cheap, deterministic guard that catches
# the most common future-peeking feature: ``series.shift(-n)``.  The default
# roots cover the first-party feature/signal code, while callers and CI can
# narrow the scan to a file or directory for a focused unit check.  Recursive
# state-initialisation analysis remains a later P12.2 extension (as promised
# by the Freqtrade/Backtrader review); this scanner does not pretend to do it.
LOOKAHEAD_DEFAULT_PATHS = ("engine", "brain", "data")
_LOOKAHEAD_SKIP_DIRS = {
    ".git", ".venv", "__pycache__", "node_modules", "store", "store_demo",
    ".pytest_cache", ".tox", ".nox", "build", "dist", "out", "target",
}


def _validation_repo_root() -> Path:
    """Return the repository root without depending on the caller's cwd."""
    return Path(__file__).resolve().parent.parent


def _scan_python_files(paths: Iterable[str | Path], root: Path) -> tuple[list[Path], list[dict]]:
    """Expand scan roots into deterministic Python files and input errors."""
    files: list[Path] = []
    errors: list[dict] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if not path.exists():
            errors.append({"path": path.as_posix(), "error": "path does not exist"})
            continue
        if path.is_file():
            if path.suffix == ".py":
                files.append(path)
            else:
                errors.append({"path": path.as_posix(),
                               "error": "lookahead scan paths must be Python files or directories"})
            continue
        candidates = []
        for candidate in path.rglob("*.py"):
            if any(part in _LOOKAHEAD_SKIP_DIRS for part in candidate.parts):
                continue
            candidates.append(candidate.resolve())
        files.extend(candidates)
    # A path can be supplied twice (for example, a root plus a focused file).
    # De-duplicate before parsing so the report and line counts are stable.
    unique = sorted(set(files), key=lambda p: p.as_posix())
    return unique, errors


def _negative_shift_expression(node: ast.AST) -> bool:
    """Whether an AST expression is syntactically a negative row offset.

    ``shift(-n)`` is intentionally rejected even when ``n`` is a runtime
    variable: a future-looking offset is unsafe unless it is made explicit in
    a separate, reviewed target/labeling path.  Constant negative arithmetic
    and the common ``0 - n`` spelling are rejected too.
    """
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return True
    if (isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)):
        return node.value < 0
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
        return isinstance(node.left, ast.Constant) and node.left.value == 0
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
        return _negative_shift_expression(node.left) or _negative_shift_expression(node.right)
    return False


def _shift_period_expression(call: ast.Call) -> Optional[ast.AST]:
    """Return the row-offset argument of a pandas-like ``shift`` call."""
    if call.args:
        return call.args[0]
    for keyword in call.keywords:
        if keyword.arg in {"periods", "n"}:
            return keyword.value
    return None


class _LookaheadVisitor(ast.NodeVisitor):
    """Collect negative ``shift`` calls while ignoring comments/docstrings."""

    def __init__(self, source: str, display_path: str):
        self.source = source
        self.display_path = display_path
        self.violations: list[dict] = []

    @staticmethod
    def _is_shift_call(node: ast.Call) -> bool:
        func = node.func
        return ((isinstance(func, ast.Attribute) and func.attr == "shift")
                or (isinstance(func, ast.Name) and func.id == "shift"))

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 — ast visitor API
        if self._is_shift_call(node):
            offset = _shift_period_expression(node)
            if offset is not None and _negative_shift_expression(offset):
                expression = ast.get_source_segment(self.source, node) or "shift(...)"
                self.violations.append({
                    "path": self.display_path,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "expression": expression,
                    "kind": "negative_shift",
                    "message": "negative shift reads future rows; use only past/current data",
                })
        self.generic_visit(node)


def scan_lookahead(paths: Optional[Iterable[str | Path]] = None,
                   root: Optional[str | Path] = None) -> dict:
    """Scan first-party feature code for explicit future-looking row shifts.

    This is the P12.2 unit/CI form.  A negative pandas-style ``shift``
    offset—``shift(-1)``, ``shift(-n)``, or ``shift(periods=-n)``—is a hard
    failure.  The scanner is source-based and therefore deterministic,
    offline, and independent of market data.  It intentionally reports
    syntax/read errors as failures rather than silently skipping a file.

    ``paths`` may contain files or directories. Relative paths resolve from
    the repository root, not from whatever directory launched the command.
    With no paths, ``engine/``, ``brain/``, and ``data/`` are scanned while
    generated stores and caches are ignored.
    """
    repo_root = Path(root).resolve() if root else _validation_repo_root()
    if isinstance(paths, (str, Path)):
        requested = [paths]
    else:
        requested = list(paths) if paths is not None else list(LOOKAHEAD_DEFAULT_PATHS)
    files, errors = _scan_python_files(requested, repo_root)
    violations: list[dict] = []
    scanned_files: list[str] = []

    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path.as_posix())
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append({"path": path.as_posix(),
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            display = path.relative_to(repo_root).as_posix()
        except ValueError:
            display = path.as_posix()
        scanned_files.append(display)
        visitor = _LookaheadVisitor(source, display)
        visitor.visit(tree)
        violations.extend(visitor.violations)

    ok = not errors and not violations
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "scanner": "p12.2-negative-shift",
        "paths": [str(p) for p in requested],
        "files_scanned": len(scanned_files),
        "scanned_files": scanned_files,
        "violations": violations,
        "errors": errors,
    }


def lookahead_report(paths: Optional[Iterable[str | Path]] = None,
                     root: Optional[str | Path] = None) -> dict:
    """Named report alias for callers that prefer the P12 report vocabulary."""
    return scan_lookahead(paths=paths, root=root)


def assert_no_lookahead(paths: Optional[Iterable[str | Path]] = None,
                        root: Optional[str | Path] = None) -> dict:
    """Raise ``LookaheadViolation`` unless the requested source scan passes."""
    report = scan_lookahead(paths=paths, root=root)
    if not report["ok"]:
        details = [
            f"{v['path']}:{v['line']} {v['expression']}"
            for v in report["violations"]
        ]
        details.extend(f"{e['path']}: {e['error']}" for e in report["errors"])
        raise LookaheadViolation("lookahead guard failed: " + "; ".join(details))
    return report


def print_lookahead(report: dict) -> None:
    """Print the compact boxed output for ``validate lookahead``."""
    print("=" * 74)
    print("LOOKAHEAD VALIDATION  P12.2")
    print(f"scanner {report.get('scanner', '?')}  files={report.get('files_scanned', 0)}")
    for violation in report.get("violations", []):
        print(f"  ❌ {violation['path']}:{violation['line']} "
              f"{violation['expression']} — {violation['message']}")
    for error in report.get("errors", []):
        print(f"  ❌ {error['path']} — {error['error']}")
    if report.get("ok"):
        print("LOOKAHEAD VERDICT  🟢 PASS — no negative shift was found")
    else:
        print("LOOKAHEAD VERDICT  🔴 FAIL — future-looking source must be removed")
    print("=" * 74)


# ──────────────────────────────────────────────────────────────────────────
# Window split (locked protocol)
# ──────────────────────────────────────────────────────────────────────────

def walk_forward_windows(n_bars: int, min_bars: int,
                         train_frac: float = 0.60, val_frac: float = 0.15,
                         oos_frac: float = 0.15, recent_frac: float = 0.10,
                         min_window_bars: int = 1) -> dict[str, tuple[int, int]]:
    """Split bar indices ``[min_bars, n_bars)`` into locked windows.

    Chronological and contiguous: ``train`` earliest, ``recent`` newest.
    The engine warm-up (bars ``0..min_bars``) belongs to no window — it is
    the shared look-back every window's first scan is entitled to, exactly
    like a live scan at that bar would have had.

    Returns ``{name: (start, end)}`` with inclusive start / exclusive end.
    Raises ``ValidationWindowError`` on bad fractions or a series too short
    to honour the four-way split.
    """
    usable = n_bars - min_bars
    if usable <= 0:
        raise ValidationWindowError(
            f"series of {n_bars} bars has nothing beyond min_bars={min_bars}")
    fracs = (train_frac, val_frac, oos_frac, recent_frac)
    if any(f is None or not (0.0 < f < 1.0) for f in fracs):
        raise ValidationWindowError(
            f"window fractions must each be in (0, 1): {fracs}")
    if abs(sum(fracs) - 1.0) > 1e-6:
        raise ValidationWindowError(
            f"window fractions must sum to 1.0: {fracs} = {sum(fracs):.4f}")
    # val/oos/recent get their exact (floored) share; train absorbs the
    # remainder so the split is always contiguous and exact.
    val_n = int(usable * val_frac)
    oos_n = int(usable * oos_frac)
    recent_n = int(usable * recent_frac)
    train_n = usable - val_n - oos_n - recent_n
    sizes = [train_n, val_n, oos_n, recent_n]
    if min(sizes) < min_window_bars:
        raise ValidationWindowError(
            f"usable bars {usable} too short for split {sizes} "
            f"(min window {min_window_bars})")
    cursor = min_bars
    windows: dict[str, tuple[int, int]] = {}
    for name, size in zip(WINDOW_NAMES, sizes):
        windows[name] = (cursor, cursor + size)
        cursor += size
    assert cursor == n_bars, "window split must tile the analyzed range"
    return windows


# ──────────────────────────────────────────────────────────────────────────
# Bucketing + window statistics
# ──────────────────────────────────────────────────────────────────────────

def bucket_by_window(graded: list, windows: dict[str, tuple[int, int]],
                     ts_to_index: dict[int, int]) -> dict[str, list]:
    """Bucket graded plans by the *signal bar's* window.

    The signal's bar index (via its timestamp) decides the window — a plan
    signalled inside ``train`` never counts toward ``val``, no matter where
    its exit landed.
    """
    buckets: dict[str, list] = {name: [] for name in windows}
    index_to_window: dict[int, str] = {}
    for name, (start, end) in windows.items():
        for idx in range(start, end):
            index_to_window[idx] = name
    for g in graded:
        idx = ts_to_index.get(int(g.ts))
        if idx is None:
            continue
        name = index_to_window.get(idx)
        if name is not None:
            buckets[name].append(g)
    return buckets


def window_stats(plans: list) -> dict:
    """Decided-trade statistics for one window (primary horizon already
    filtered by the caller). Mirrors `_aggregate` but adds profit factor,
    which the graduation bar needs."""
    decided = [g for g in plans if g.outcome in ("FULL_WIN", "PARTIAL_WIN",
                                                 "LOSS")]
    agg = _aggregate(plans)
    wins_r = sum(g.rr_achieved for g in decided if g.rr_achieved > 0)
    loss_r = abs(sum(g.rr_achieved for g in decided if g.rr_achieved < 0))
    pf = round(wins_r / loss_r, 3) if loss_r > 0 else (99.0 if wins_r > 0
                                                       else None)
    return {**agg, "decided": len(decided), "pf": pf}


def meets_bar(stats: dict, min_decided: int = DEFAULT_MIN_DECIDED,
              criteria: Optional[dict[str, float]] = None) -> tuple[bool, list[str]]:
    """Apply the graduation bar to one window's statistics.

    Returns ``(met, unmet_reasons)``. A window with fewer decided trades
    than ``min_decided`` can never pass — silence is not an edge.
    """
    criteria = criteria or VALIDATION_CRITERIA
    unmet: list[str] = []
    n = stats.get("decided", 0)
    if n < min_decided:
        unmet.append(f"decided {n} < min {min_decided}")
        return False, unmet
    e = stats.get("expectancy", 0.0)
    wr = stats.get("win_rate")
    pf = stats.get("pf")
    if e < criteria["expectancy"]:
        unmet.append(f"expectancy {e:+.3f}R < {criteria['expectancy']:+.2f}R")
    if wr is None or wr <= criteria["win_rate"]:
        unmet.append(f"win_rate {wr if wr is not None else 'n/a'} "
                     f"<= {criteria['win_rate']}")
    if pf is None or pf < criteria["pf"]:
        unmet.append(f"pf {pf if pf is not None else 'n/a'} "
                     f"< {criteria['pf']}")
    return (not unmet), unmet


def protocol_verdict(window_results: dict[str, dict],
                     min_decided: int = DEFAULT_MIN_DECIDED) -> dict:
    """The P12.1 pass rule over per-window results.

    - ``INSUFFICIENT_DATA`` — train or val has too few decided trades.
    - ``FAIL``             — train or val misses the bar. A setup that
      passes train ALONE has not passed.
    - ``PASS``             — train AND val meet the bar, and the sealed
      oos/recent windows confirm.
    - ``PASS_WITH_WARNINGS`` — train AND val meet the bar, but a sealed
      window does not (overfit suspicion; the pass stands, the warning
      is loud).
    """
    train = window_results.get("train")
    val = window_results.get("val")
    oos = window_results.get("oos")
    recent = window_results.get("recent")
    if not train or not val:
        return {"protocol_pass": False, "status": "INSUFFICIENT_DATA",
                "reason": "train and val windows are required", "warnings": []}
    if train["decided"] < min_decided or val["decided"] < min_decided:
        return {"protocol_pass": False, "status": "INSUFFICIENT_DATA",
                "reason": f"train decided={train['decided']}, val "
                          f"decided={val['decided']} (min {min_decided})",
                "warnings": []}
    train_met, train_unmet = train["bar_met"], train["bar_unmet"]
    val_met, val_unmet = val["bar_met"], val["bar_unmet"]
    oos_met = bool(oos and oos["bar_met"])
    recent_met = bool(recent and recent["bar_met"])
    if not (train_met and val_met):
        reasons = ([f"train: {u}" for u in train_unmet]
                   + [f"val: {u}" for u in val_unmet])
        return {"protocol_pass": False, "status": "FAIL",
                "reason": "; ".join(reasons),
                "warnings": [],
                "train_met": train_met, "val_met": val_met,
                "oos_met": oos_met, "recent_met": recent_met}
    warnings: list[str] = []
    if not oos_met:
        warnings.append("sealed OOS window does not meet the bar "
                        f"({'; '.join(oos['bar_unmet'])}) — overfit suspicion")
    if not recent_met:
        warnings.append("sealed recent window does not meet the bar "
                        f"({'; '.join(recent['bar_unmet'])})")
    return {"protocol_pass": True,
            "status": "PASS" if not warnings else "PASS_WITH_WARNINGS",
            "reason": "train and val meet the graduation bar",
            "warnings": warnings,
            "train_met": train_met, "val_met": val_met,
            "oos_met": oos_met, "recent_met": recent_met}


# ──────────────────────────────────────────────────────────────────────────
# Sealed OOS envelope (BT6: the final OOS set is sealed)
# ──────────────────────────────────────────────────────────────────────────

def config_fingerprint(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _seal_file(seal_dir: str | Path, seal_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in seal_key)
    return Path(seal_dir) / f"{safe}.json"


def load_seal(seal_dir: str | Path, seal_key: str,
              fingerprint: str) -> Optional[dict]:
    """Return the stored seal payload iff the config fingerprint matches.

    A config mismatch (different windows, symbol, engine settings, …) never
    reuses an old seal — that would silently re-derive OOS under different
    rules, which is exactly what the envelope forbids.
    """
    path = _seal_file(seal_dir, seal_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("fingerprint") != fingerprint:
        return None
    history = data.get("history") or []
    return history[-1].get("payload") if history else None


def write_seal(seal_dir: str | Path, seal_key: str, fingerprint: str,
               payload: dict, reseal: bool = False) -> Path:
    """Persist the sealed result, appending to the seal history.

    Every re-opening is recorded with a timestamp — the envelope has a
    paper trail and a run can never pretend it was opened for the first
    time.
    """
    path = _seal_file(seal_dir, seal_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        data = {"fingerprint": fingerprint, "seal_key": seal_key, "history": []}
    data["fingerprint"] = fingerprint
    data.setdefault("history", []).append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reseal": bool(reseal),
        "payload": payload,
    })
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


# ──────────────────────────────────────────────────────────────────────────
# The protocol runner
# ──────────────────────────────────────────────────────────────────────────

def run_validation(df: pd.DataFrame, symbol: str = "BTCUSDT",
                   timeframe: str = "15m",
                   horizons: Optional[list[float]] = None,
                   min_bars: int = BACKTEST_MIN_BARS,
                   step: int = BACKTEST_STEP,
                   min_confidence: int = MIN_CONFIDENCE,
                   train_frac: float = 0.60, val_frac: float = 0.15,
                   oos_frac: float = 0.15, recent_frac: float = 0.10,
                   min_decided: int = DEFAULT_MIN_DECIDED,
                   seal_dir: Optional[str | Path] = None,
                   seal_key: Optional[str] = None,
                   reseal: bool = False) -> dict:
    """Run the locked train/val/OOS/recent protocol over a candle frame.

    One walk-forward pass over the series (engine re-run at every step on
    data up to that bar only), then every graded plan is bucketed by the
    window its *signal bar* belongs to, each window is measured against the
    graduation bar, and the sealed envelopes are honoured.

    Returns ``{"ok": ..., "protocol": ..., "windows": ..., "verdicts": ...,
    "seal": ...}`` — a report, never a trade.
    """
    horizons = horizons or BACKTEST_HORIZONS
    df = df.reset_index(drop=True).copy()
    if len(df) <= min_bars:
        return {"ok": False,
                "error": f"series has {len(df)} bars; need > min_bars="
                         f"{min_bars} for any validation window"}
    try:
        windows = walk_forward_windows(len(df), min_bars, train_frac,
                                       val_frac, oos_frac, recent_frac)
    except ValidationWindowError as exc:
        return {"ok": False, "error": str(exc)}

    seal_cfg = {"symbol": symbol, "timeframe": timeframe,
                "horizons": horizons, "min_bars": min_bars, "step": step,
                "min_confidence": min_confidence,
                "train_frac": train_frac, "val_frac": val_frac,
                "oos_frac": oos_frac, "recent_frac": recent_frac,
                "min_decided": min_decided, "bars": len(df),
                "criteria": VALIDATION_CRITERIA}
    fingerprint = config_fingerprint(seal_cfg)
    seal_enabled = bool(seal_dir and seal_key)
    if seal_enabled and not reseal:
        cached = load_seal(seal_dir, seal_key, fingerprint)
        if cached is not None:
            cached["sealed_reused"] = True
            return cached

    started = time.time()
    result = run_backtest(df, symbol=symbol, timeframe=timeframe,
                          horizons=horizons, min_bars=min_bars, step=step,
                          min_confidence=min_confidence)
    graded = result["graded"]
    primary = horizons[0]
    primary_graded = [g for g in graded if abs(g.horizon_hours - primary) < 0.01]
    ts_to_index = {int(t): i for i, t in enumerate(df["ts"])}
    buckets = bucket_by_window(primary_graded, windows, ts_to_index)

    # Per-window stats for the combined edge and for every plan type that
    # appeared anywhere (so per-setup verdicts are on the same window map).
    plan_types = sorted({g.plan_type for g in primary_graded})
    window_results: dict[str, dict] = {}
    for name in WINDOW_NAMES:
        window_results[name] = window_stats(buckets[name])
        window_results[name]["bar_met"], window_results[name]["bar_unmet"] = \
            meets_bar(window_results[name], min_decided)
        window_results[name]["bars"] = windows[name]

    verdicts: dict[str, dict] = {"ALL": protocol_verdict(window_results,
                                                         min_decided)}
    for ptype in plan_types:
        per_type: dict[str, dict] = {}
        for name in WINDOW_NAMES:
            plans = [g for g in buckets[name] if g.plan_type == ptype]
            stats = window_stats(plans)
            stats["bar_met"], stats["bar_unmet"] = meets_bar(stats, min_decided)
            stats["bars"] = windows[name]
            per_type[name] = stats
        verdicts[ptype] = protocol_verdict(per_type, min_decided)

    report = {
        "ok": True,
        "meta": {
            **result["report"]["meta"],
            "window_fractions": {"train": train_frac, "val": val_frac,
                                 "oos": oos_frac, "recent": recent_frac},
            "min_decided": min_decided,
            "criteria": VALIDATION_CRITERIA,
            "primary_horizon_hours": primary,
            "protocol": "train/val/oos/recent — train+val pass; oos/recent sealed",
        },
        "windows": {name: {"bars": windows[name],
                           "signals": len(buckets[name]),
                           "stats": {k: v for k, v in window_results[name].items()
                                     if k not in ("bar_met", "bar_unmet")},
                           "bar_met": window_results[name]["bar_met"],
                           "bar_unmet": window_results[name]["bar_unmet"]}
                    for name in WINDOW_NAMES},
        "protocol": window_results,
        "verdicts": verdicts,
        "seal": None,
    }
    if seal_enabled:
        # Set the seal record BEFORE writing it — the stored payload must
        # describe its own envelope (path, fingerprint, reseal flag).
        report["seal"] = {"path": _seal_file(seal_dir, seal_key).as_posix(),
                          "fingerprint": fingerprint,
                          "resealed": bool(reseal)}
        write_seal(seal_dir, seal_key, fingerprint, report, reseal)
    report["meta"]["runtime_seconds"] = round(time.time() - started, 2)
    return report


def run_validation_on_store(exchange: str = "binance", market: str = "perp",
                            symbol: str = "BTCUSDT", timeframe: str = "15m",
                            bars: int = 2000,
                            horizons: Optional[list[float]] = None,
                            min_bars: int = BACKTEST_MIN_BARS,
                            step: int = 3,
                            min_confidence: int = MIN_CONFIDENCE,
                            train_frac: float = 0.60, val_frac: float = 0.15,
                            oos_frac: float = 0.15, recent_frac: float = 0.10,
                            min_decided: int = DEFAULT_MIN_DECIDED,
                            seal_dir: Optional[str | Path] = None,
                            store_root: Optional[str | Path] = None,
                            reseal: bool = False) -> dict:
    """P12.1 over the stored Parquet series (P10.11's data path).

    The protocol requires multi-window history, which only the store can
    provide — a live 500-candle fetch cannot hold four locked windows.
    Missing or short series return a clear error, never a verdict. The
    sealed envelope is protocol-mandated here: seal_dir defaults to
    ``data/store/validation/`` (gitignored).
    """
    from data.store import CandleStore
    store = CandleStore(root=store_root) if store_root else CandleStore()
    if seal_dir is None:
        seal_dir = DEFAULT_SEAL_DIR
    df = store.read(exchange, market, symbol, timeframe)
    if df.empty:
        return {"ok": False,
                "error": f"No stored candles for {exchange}/{market}/"
                         f"{symbol}/{timeframe} — run `python main.py "
                         f"backfill` first"}
    if len(df) <= min_bars:
        return {"ok": False,
                "error": f"Only {len(df)} bars stored (need > min_bars="
                         f"{min_bars} for a four-window split)",
                "stored": len(df), "min_bars": min_bars}
    df = df.tail(bars).reset_index(drop=True)
    seal_key = f"{exchange}_{market}_{symbol}_{timeframe}"
    report = run_validation(df, symbol=symbol, timeframe=timeframe,
                            horizons=horizons, min_bars=min_bars, step=step,
                            min_confidence=min_confidence,
                            train_frac=train_frac, val_frac=val_frac,
                            oos_frac=oos_frac, recent_frac=recent_frac,
                            min_decided=min_decided, seal_dir=seal_dir,
                            seal_key=seal_key, reseal=reseal)
    report["store_source"] = True
    report["store_path"] = store._series_dir(
        exchange, market, symbol, timeframe).as_posix()
    report["bars_read"] = len(df)
    return report


# ──────────────────────────────────────────────────────────────────────────
# Boxed protocol report
# ──────────────────────────────────────────────────────────────────────────

def print_verdict(report: dict) -> None:
    if not report.get("ok"):
        print("QUANT VALIDATION — cannot run")
        print(f"  {report.get('error', 'unknown error')}")
        return
    meta = report["meta"]
    print("=" * 74)
    print(f"QUANT VALIDATION  {meta['symbol']} {meta['timeframe']}   "
          f"primary horizon {meta['primary_horizon_hours']}h")
    fracs = meta["window_fractions"]
    print(f"windows  train {fracs['train']:.0%} / val {fracs['val']:.0%} / "
          f"oos {fracs['oos']:.0%} / recent {fracs['recent']:.0%}   "
          f"min_decided {meta['min_decided']}   "
          f"bars={meta['bars_total']} plans={meta['plans_generated']} "
          f"({meta['runtime_seconds']}s)")
    print("-" * 74)
    print(f"{'window':<8} {'bars':<22} {'sig':>5} {'dec':>5} {'WR':>6} "
          f"{'E':>7} {'PF':>6}  bar")
    for name in WINDOW_NAMES:
        w = report["windows"][name]
        s = w["stats"]
        wr = s["win_rate"]
        wr_s = f"{wr*100:.0f}%" if wr is not None else "n/a"
        pf_s = f"{s['pf']}" if s["pf"] is not None else "n/a"
        mark = "met ✅" if w["bar_met"] else "missed ❌"
        print(f"{name:<8} [{w['bars'][0]:>6},{w['bars'][1]:>6})  "
              f"{w['signals']:>5} {s['decided']:>5} {wr_s:>6} "
              f"{s['expectancy']:>+7.2f} {pf_s:>6}  {mark}")
    print("-" * 74)
    verdict = report["verdicts"].get("ALL", {})
    icon = {"PASS": "🟢", "PASS_WITH_WARNINGS": "🟡",
            "FAIL": "🔴", "INSUFFICIENT_DATA": "⚪"}.get(
                verdict.get("status"), "❓")
    print(f"ENGINE VERDICT  {icon} {verdict.get('status')}  —  "
          f"{verdict.get('reason')}")
    for w in verdict.get("warnings", []):
        print(f"  ⚠ {w}")
    print("-" * 74)
    print("per-setup verdicts (strategy = setup × regime × asset):")
    for ptype, v in sorted(report["verdicts"].items()):
        if ptype == "ALL":
            continue
        print(f"  {ptype:<28} {v.get('status'):<20} "
              f"train_met={bool(v.get('train_met'))} "
              f"val_met={bool(v.get('val_met'))} "
              f"oos_met={bool(v.get('oos_met'))} "
              f"recent_met={bool(v.get('recent_met'))}")
    seal = report.get("seal")
    if seal:
        reuse = " (reused sealed result)" if report.get("sealed_reused") else ""
        resealed = " RESEALED — envelope re-opened!" if seal.get("resealed") else ""
        print("-" * 74)
        print(f"seal: {seal['path']}  fp={seal['fingerprint']}"
              f"{reuse}{resealed}")
    else:
        print("-" * 74)
        print("seal: disabled (no seal_dir/seal_key) — OOS NOT sealed")
    print("=" * 74)
