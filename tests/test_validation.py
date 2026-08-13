"""Tests for P12.1 and P12.2 validation integrity.

All offline: the protocol logic is tested on synthetic GradedPlan lists,
plus one end-to-end run over deterministic synthetic candles (the same
walk-forward grader the desk already uses — no look-ahead by construction).
The P12.2 source guard is also tested against a deliberately future-peeking
``shift(-n)`` feature so CI fails if the scanner ever stops catching it.
"""
from __future__ import annotations

import json

import pytest

from data.backtester import GradedPlan
from data.validation import (
    DEFAULT_MIN_DECIDED, VALIDATION_CRITERIA, LookaheadViolation,
    ValidationWindowError, assert_no_lookahead, bucket_by_window,
    config_fingerprint, load_seal, meets_bar, protocol_verdict,
    run_validation, scan_lookahead, walk_forward_windows, window_stats,
    write_seal,
)


# ── helpers ────────────────────────────────────────────────────────────────

def gp(ts: int, plan_type: str = "Buy Pullback", outcome: str = "FULL_WIN",
       rr: float = 2.0, horizon: float = 1.0, action: str = "BUY") -> GradedPlan:
    return GradedPlan(ts=ts, plan_type=plan_type, action=action,
                      confidence_pct=80, entry=100.0, trigger_level=None,
                      horizon_hours=horizon, outcome=outcome, rr_achieved=rr)


def _window(plans: list, min_decided: int = DEFAULT_MIN_DECIDED) -> dict:
    stats = window_stats(plans)
    stats["bar_met"], stats["bar_unmet"] = meets_bar(stats, min_decided)
    return stats


def _strong_window(n_wins: int = 24, n_losses: int = 16) -> list:
    """A window that meets the graduation bar: WR 60%, E +0.8R, PF 3.0."""
    return ([gp(i, outcome="FULL_WIN", rr=2.0) for i in range(n_wins)]
            + [gp(1000 + i, outcome="LOSS", rr=-1.0) for i in range(n_losses)])


def _weak_window() -> list:
    """A window that misses the bar: all losses."""
    return [gp(2000 + i, outcome="LOSS", rr=-1.0) for i in range(40)]


# ── window split ───────────────────────────────────────────────────────────

def test_walk_forward_windows_tile_the_analyzed_range():
    windows = walk_forward_windows(n_bars=1000, min_bars=120)
    assert list(windows) == ["train", "val", "oos", "recent"]
    assert windows["train"][0] == 120          # starts at warm-up end
    assert windows["recent"][1] == 1000        # ends at the last bar
    cursor = 120
    for name in ("train", "val", "oos", "recent"):
        start, end = windows[name]
        assert (start, end) == (cursor, cursor + (end - start)), \
            f"{name} window must be contiguous"
        assert end > start, f"{name} window must be non-empty"
        cursor = end
    assert cursor == 1000
    # train absorbs the rounding remainder and is the largest window
    sizes = {n: b - a for n, (a, b) in windows.items()}
    assert sizes["train"] == 880 - 132 - 132 - 88 == 528


def test_walk_forward_windows_reject_bad_fractions():
    with pytest.raises(ValidationWindowError):
        walk_forward_windows(1000, 120, train_frac=0.5, val_frac=0.2,
                             oos_frac=0.2, recent_frac=0.2)  # sums to 1.1
    with pytest.raises(ValidationWindowError):
        walk_forward_windows(1000, 120, train_frac=0.0, val_frac=0.3,
                             oos_frac=0.3, recent_frac=0.4)  # zero window
    with pytest.raises(ValidationWindowError):
        walk_forward_windows(1000, 120, train_frac=1.0, val_frac=0.0,
                             oos_frac=0.0, recent_frac=0.0)  # degenerate


def test_walk_forward_windows_reject_short_series():
    with pytest.raises(ValidationWindowError):
        walk_forward_windows(120, 120)          # nothing beyond warm-up
    with pytest.raises(ValidationWindowError):
        walk_forward_windows(125, 120, min_window_bars=3)  # can't fit 4 windows


# ── bucketing ──────────────────────────────────────────────────────────────

def test_bucket_by_window_uses_signal_bar_not_exit_bar():
    windows = {"train": (10, 20), "val": (20, 30)}
    ts_to_index = {t: i for i, t in enumerate(range(1000, 1040))}
    plans = [gp(1010), gp(1015), gp(1025), gp(1035)]  # idx 10,15 → train; 25 → val; 35 → nowhere
    buckets = bucket_by_window(plans, windows, ts_to_index)
    assert len(buckets["train"]) == 2
    assert len(buckets["val"]) == 1
    assert buckets["train"][0].ts == 1010 and buckets["val"][0].ts == 1025


# ── bar checks ─────────────────────────────────────────────────────────────

def test_meets_bar_passes_a_strong_window():
    stats = window_stats(_strong_window())
    met, unmet = meets_bar(stats, min_decided=30)
    assert met and not unmet
    assert stats["decided"] == 40
    assert stats["win_rate"] == 0.6
    assert stats["expectancy"] == pytest.approx(0.8)
    assert stats["pf"] == pytest.approx(3.0)


def test_meets_bar_reports_every_unmet_reason():
    stats = window_stats(_weak_window())
    met, unmet = meets_bar(stats, min_decided=30)
    assert not met
    assert any("expectancy" in u for u in unmet)
    assert any("win_rate" in u for u in unmet)
    assert any("pf" in u for u in unmet)


def test_meets_bar_never_passes_on_too_few_samples():
    stats = window_stats([gp(1, outcome="FULL_WIN", rr=3.0)] * 3)
    met, unmet = meets_bar(stats, min_decided=30)
    assert not met
    assert any("decided" in u for u in unmet)  # silence is not an edge


# ── protocol verdicts ──────────────────────────────────────────────────────

def test_verdict_cannot_pass_on_train_alone():
    """P12.1 done-when: a setup that passes train but fails val is FAIL."""
    results = {
        "train": _window(_strong_window()),
        "val": _window(_weak_window()),
        "oos": _window(_strong_window()),
        "recent": _window(_strong_window()),
    }
    verdict = protocol_verdict(results)
    assert verdict["status"] == "FAIL"
    assert not verdict["protocol_pass"]
    assert "val" in verdict["reason"]


def test_verdict_pass_requires_train_and_val():
    results = {
        "train": _window(_strong_window()),
        "val": _window(_strong_window()),
        "oos": _window(_strong_window()),
        "recent": _window(_strong_window()),
    }
    verdict = protocol_verdict(results)
    assert verdict["status"] == "PASS"
    assert verdict["protocol_pass"]


def test_verdict_pass_with_warnings_when_sealed_window_fails():
    results = {
        "train": _window(_strong_window()),
        "val": _window(_strong_window()),
        "oos": _window(_weak_window()),
        "recent": _window(_strong_window()),
    }
    verdict = protocol_verdict(results)
    assert verdict["status"] == "PASS_WITH_WARNINGS"
    assert verdict["protocol_pass"]
    assert any("OOS" in w for w in verdict["warnings"])


def test_verdict_insufficient_data():
    few = [gp(1, outcome="FULL_WIN", rr=2.0), gp(2, outcome="LOSS", rr=-1.0)]
    results = {
        "train": _window(few),
        "val": _window(_strong_window()),
        "oos": _window(_strong_window()),
        "recent": _window(_strong_window()),
    }
    verdict = protocol_verdict(results)
    assert verdict["status"] == "INSUFFICIENT_DATA"
    assert not verdict["protocol_pass"]


# ── sealed envelope ────────────────────────────────────────────────────────

def test_seal_roundtrip_and_fingerprint_gate(tmp_path):
    cfg = {"symbol": "BTCUSDT", "timeframe": "15m", "train_frac": 0.6}
    fp = config_fingerprint(cfg)
    payload = {"ok": True, "verdicts": {"ALL": {"status": "PASS"}}}
    path = write_seal(tmp_path, "binance_perp_BTCUSDT_15m", fp, payload)
    assert path.exists()
    assert load_seal(tmp_path, "binance_perp_BTCUSDT_15m", fp) == payload
    # a different config fingerprint must NOT reuse the old seal
    other_fp = config_fingerprint({**cfg, "train_frac": 0.7})
    assert load_seal(tmp_path, "binance_perp_BTCUSDT_15m", other_fp) is None
    # unknown key → nothing
    assert load_seal(tmp_path, "nope", fp) is None


def test_seal_records_reseals_in_history(tmp_path):
    fp = config_fingerprint({"x": 1})
    write_seal(tmp_path, "k", fp, {"v": 1})
    write_seal(tmp_path, "k", fp, {"v": 2}, reseal=True)
    data = json.loads((tmp_path / "k.json").read_text())
    assert len(data["history"]) == 2
    assert data["history"][0]["reseal"] is False
    assert data["history"][1]["reseal"] is True
    assert load_seal(tmp_path, "k", fp) == {"v": 2}


# ── end-to-end protocol run (offline synthetic candles) ────────────────────

def test_run_validation_end_to_end_and_seal_reuse(tmp_path):
    from tests.conftest import make_ohlcv
    df = make_ohlcv(n=450, seed=11)
    kwargs = dict(symbol="BTCUSDT", timeframe="15m", horizons=[1.0],
                  min_bars=150, step=5, min_confidence=0, min_decided=1,
                  seal_dir=tmp_path, seal_key="e2e")
    first = run_validation(df, **kwargs)
    assert first["ok"]
    assert list(first["windows"]) == ["train", "val", "oos", "recent"]
    cursor = 150
    for name in ("train", "val", "oos", "recent"):
        start, end = first["windows"][name]["bars"]
        assert (start, end) == (cursor, cursor + (end - start))
        cursor = end
    assert cursor == 450
    assert first["verdicts"]["ALL"]["status"] in {
        "PASS", "PASS_WITH_WARNINGS", "FAIL", "INSUFFICIENT_DATA"}
    assert first["seal"]["fingerprint"]
    assert first["seal"]["resealed"] is False

    # The sealed payload must describe its own envelope (regression: the
    # seal was once written before `report["seal"]` existed, so a reused
    # envelope looked like sealing was disabled).
    stored = load_seal(tmp_path, "e2e", first["seal"]["fingerprint"])
    assert stored["seal"] and stored["seal"]["fingerprint"]
    assert stored["seal"]["path"] == first["seal"]["path"]

    # Identical rerun → the sealed envelope is reused, no silent re-derivation.
    second = run_validation(df, **kwargs)
    assert second["ok"] and second.get("sealed_reused") is True
    assert second["verdicts"] == first["verdicts"]
    assert second["seal"]["path"] == first["seal"]["path"]

    # Re-opening requires an explicit, recorded reseal.
    third = run_validation(df, **{**kwargs, "reseal": True})
    assert third["ok"] and not third.get("sealed_reused")
    assert third["seal"]["resealed"] is True


def test_run_validation_refuses_too_short_series(tmp_path):
    from tests.conftest import make_ohlcv
    df = make_ohlcv(n=100, seed=3)
    result = run_validation(df, min_bars=120, seal_dir=tmp_path, seal_key="x")
    assert not result["ok"]
    assert "min_bars" in result["error"]


def test_run_validation_refuses_bad_window_fractions(tmp_path):
    from tests.conftest import make_ohlcv
    df = make_ohlcv(n=400, seed=3)
    result = run_validation(df, min_bars=150, train_frac=0.6, val_frac=0.2,
                            oos_frac=0.2, recent_frac=0.2,
                            seal_dir=tmp_path, seal_key="x")
    assert not result["ok"]
    assert "fractions" in result["error"]


def test_criteria_are_the_live_graduation_bar():
    """The validation bar and the graduation gate must never diverge."""
    from data.simulator import GRADUATION_CRITERIA
    assert VALIDATION_CRITERIA == dict(GRADUATION_CRITERIA)
    assert VALIDATION_CRITERIA["expectancy"] == 0.50
    assert VALIDATION_CRITERIA["win_rate"] == 0.55
    assert VALIDATION_CRITERIA["pf"] == 1.5


# ── P12.2 lookahead guard ─────────────────────────────────────────────────

def test_lookahead_guard_passes_first_party_sources():
    """CI's unit form scans the real feature/signal source tree."""
    report = scan_lookahead()
    assert report["ok"], report
    assert report["status"] == "PASS"
    assert report["files_scanned"] > 0
    assert report["violations"] == []


def test_lookahead_guard_rejects_shift_negative_n(tmp_path):
    """The P12.2 done-when: a future-peeking ``shift(-n)`` fails."""
    bad = tmp_path / "future_feature.py"
    bad.write_text(
        "def feature(frame, n):\n"
        "    return frame['close'].shift(-n)\n"
        "\n"
        "def another_future_feature(frame, n):\n"
        "    return frame['close'].shift(periods=-n)\n",
        encoding="utf-8",
    )
    report = scan_lookahead([bad])
    assert not report["ok"]
    assert report["status"] == "FAIL"
    assert len(report["violations"]) == 2
    assert all(v["kind"] == "negative_shift" for v in report["violations"])
    assert report["violations"][0]["line"] == 2
    with pytest.raises(LookaheadViolation, match="lookahead guard failed"):
        assert_no_lookahead([bad])


def test_lookahead_guard_allows_past_shift_and_ignores_docstrings(tmp_path):
    safe = tmp_path / "causal_feature.py"
    safe.write_text(
        '"""Documentation may mention shift(-n) without executing it."""\n'
        "def feature(frame):\n"
        "    return frame['close'].shift(1)\n",
        encoding="utf-8",
    )
    report = scan_lookahead([safe])
    assert report["ok"], report
    assert report["violations"] == []


def test_validate_lookahead_cli_json_and_exit_code(tmp_path, capsys):
    """The reviewable CLI path uses the same unit scanner and fail code."""
    from main import main

    safe = tmp_path / "safe.py"
    safe.write_text("def feature(frame):\n    return frame.close.shift(1)\n", encoding="utf-8")
    assert main(["validate", "lookahead", "--path", str(safe), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"

    bad = tmp_path / "bad.py"
    bad.write_text("def feature(frame):\n    return frame.close.shift(-1)\n", encoding="utf-8")
    assert main(["validate", "lookahead", "--path", str(bad), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
