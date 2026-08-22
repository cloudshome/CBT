"""Tests for W3.4 — practice mode (brain/practice.py).

The practice mirror has the same honesty rules the whole project lives by:
fail-closed validation, deterministic scoring with visible components, an
advisory grade that quotes (never moves) the graduation bar, and — most
importantly — practice rows are coaching memory that **no** live-book,
risk-gate or graduation surface ever reads. Those invariants are pinned here.
"""
from __future__ import annotations

import json
import time

import pytest

from data.database import SignalDB
from brain.practice import (DISCLAIMER, RR_FLOOR, TAPE_DISCLAIMER, TAPE_KIND,
                            desk_read_from_payload, format_practice_scorecard,
                            locate_commit, practice_scorecard, score_attempt,
                            score_tape, submit_attempt, submit_tape_attempt,
                            validate_tape_request, validate_user_read,
                            walk_tape)

DAY = 86_400_000


# ── fixtures ────────────────────────────────────────────────────────────


def _payload(action="BUY", bull=65, bear=30, entry=100.0, stop=99.0,
             target=102.5, atr=0.5, regime="TRENDING") -> dict:
    sig = {"signal_id": "BTC_T", "asset": "BTCUSDT", "timeframe": "15m",
           "action": action, "entry": entry, "stop_loss": stop,
           "take_profit": target, "risk_reward": 2.5, "confidence": "HIGH"}
    if action == "NO TRADE":
        sig.update({"entry": None, "stop_loss": None, "take_profit": None,
                    "risk_reward": 0.0, "confidence": "LOW"})
    return {"signal": sig,
            "plans": [{"plan_type": "Buy Pullback", "primary": True}],
            "snapshot": {"features": {"atr": atr, "price": entry or 100.1,
                                      "regime_name": regime},
                         "scores": {"bull": {"score": bull},
                                    "bear": {"score": bear}}}}


def _desk(**kw) -> dict:
    return desk_read_from_payload(_payload(**kw), "BTCUSDT", "15m")


def _read(**kw) -> dict:
    base = {"symbol": "BTCUSDT", "tf": "15m", "bias": "bullish",
            "decision": "buy", "entry": 100.1, "stop": 99.0, "target": 102.6,
            "confidence": 70, "note": ""}
    base.update(kw)
    return validate_user_read(base)


@pytest.fixture
def db(tmp_path):
    d = SignalDB(tmp_path / "p.db")
    yield d
    d.close()


# ── desk read extraction ────────────────────────────────────────────────


def test_desk_read_extracts_action_bias_levels():
    d = _desk()
    assert d["available"] and d["action"] == "BUY" and d["bias"] == "bullish"
    assert d["entry"] == 100.0 and d["stop"] == 99.0 and d["target"] == 102.5
    assert d["atr"] == 0.5 and d["regime"] == "TRENDING"
    assert d["plan_type"] == "Buy Pullback" and d["signal_id"] == "BTC_T"


def test_desk_read_bias_tie_is_neutral_and_missing_is_unknown():
    assert _desk(bull=40, bear=40)["bias"] == "neutral"
    p = _payload()
    p["snapshot"]["scores"] = {}
    assert desk_read_from_payload(p)["bias"] is None


def test_desk_read_no_trade_clears_levels():
    d = _desk(action="NO TRADE", bull=20, bear=55)
    assert d["action"] == "NO TRADE" and d["bias"] == "bearish"
    assert d["entry"] is None and d["target"] is None


def test_desk_read_never_raises_on_garbage():
    assert desk_read_from_payload(None)["available"] is False
    assert desk_read_from_payload({})["available"] is False
    assert desk_read_from_payload({"signal": None})["available"] is True


# ── validation: fail closed ─────────────────────────────────────────────


def test_validate_rejects_unknown_bias_and_decision():
    with pytest.raises(ValueError, match="unknown bias"):
        validate_user_read(_read_raw(bias="moonish"))
    with pytest.raises(ValueError, match="unknown decision"):
        validate_user_read(_read_raw(decision="ape-in"))


def test_validate_rejects_partial_ladder():
    with pytest.raises(ValueError, match="half-plan"):
        validate_user_read(_read_raw(stop=None))
    with pytest.raises(ValueError, match="half-plan"):
        validate_user_read(_read_raw(target=None))


def test_validate_rejects_bad_numbers_and_confidence():
    with pytest.raises(ValueError, match="positive price"):
        validate_user_read(_read_raw(entry=-5))
    with pytest.raises(ValueError, match="confidence"):
        validate_user_read(_read_raw(confidence=140))


def test_validate_cleans_symbol_and_caps_note():
    out = validate_user_read(_read_raw(symbol=" btc/usdt ", note="x" * 900))
    assert out["symbol"] == "BTCUSDT"
    assert len(out["note"]) == 500


def _read_raw(**kw) -> dict:
    base = {"symbol": "BTCUSDT", "tf": "15m", "bias": "bullish",
            "decision": "buy", "entry": 100.1, "stop": 99.0, "target": 102.6,
            "confidence": 70, "note": "ok"}
    base.update(kw)
    return base


# ── deterministic scoring ───────────────────────────────────────────────


def test_perfect_read_scores_100_grade_A():
    sc = score_attempt(_read(), _desk())
    assert sc["total"] == 100 and sc["grade"] == "A"
    assert sc["bias_match"] and sc["decision_match"]
    assert sc["disclaimer"] == DISCLAIMER


def test_bias_components_exact_neutral_opposite():
    assert score_attempt(_read(), _desk())["components"][0]["points"] == 35
    n = score_attempt(_read(bias="neutral"), _desk())["components"][0]
    assert n["points"] == 15 and "one side neutral" in n["detail"]
    o = score_attempt(_read(bias="bearish"), _desk())["components"][0]
    assert o["points"] == 0 and "opposite" in o["detail"]


def test_decision_missed_vs_overruled():
    miss = score_attempt(_read(decision="no_trade", entry=None, stop=None,
                               target=None), _desk())
    assert miss["components"][1]["points"] == 15 and "missed" in miss["components"][1]["detail"]
    over = score_attempt(_read(decision="buy", entry=None, stop=None,
                               target=None), _desk(action="NO TRADE"))
    assert over["components"][1]["points"] == 0
    assert "overruled the desk's NO TRADE filter" in over["components"][1]["detail"]


def test_no_ladder_renormalizes_over_70():
    sc = score_attempt(_read(entry=None, stop=None, target=None), _desk())
    assert sc["earned_max"] == 70 and sc["total"] == 100  # 35+35 on 70 → 100
    assert sc["components"][2]["points"] is None
    assert "no entry/stop/target" in sc["components"][2]["detail"]


def test_ladder_unscored_when_desk_is_no_trade():
    sc = score_attempt(_read(bias="bearish", decision="no_trade"),
                       _desk(action="NO TRADE", bull=20, bear=55, atr=None),
                       )
    assert sc["earned_max"] == 70 and sc["total"] == 100
    assert "desk itself is NO TRADE" in sc["components"][2]["detail"]


def test_ladder_proximity_tiers_and_wrong_side_and_rr_floor():
    # gap 0.1 ≤ 0.5*ATR(0.5) → 10; stop right side → 10; RR 2.27 ≥ 1.5 → 10
    sc = score_attempt(_read(), _desk())
    assert sc["components"][2]["points"] == 30
    # far entry → 0 entry points
    far = score_attempt(_read(entry=103.0, stop=102.0, target=105.0), _desk())
    assert "entry gap" in far["components"][2]["detail"]
    assert far["components"][2]["points"] < 30
    # wrong stop side for a buy → side points lost
    bad_side = score_attempt(_read(stop=101.5, target=103.0), _desk())
    assert "WRONG side" in bad_side["components"][2]["detail"]
    # RR below the 1.5 floor → RR points reduced
    thin = score_attempt(_read(entry=100.1, stop=99.6, target=100.5), _desk())
    assert f"≥{RR_FLOOR} floor" in thin["components"][2]["detail"]
    assert thin["components"][2]["points"] < 30


def test_score_requires_available_desk():
    with pytest.raises(ValueError, match="desk read unavailable"):
        score_attempt(_read(), {"available": False})


# ── persistence + dedupe ────────────────────────────────────────────────


def test_submit_persists_and_dedupes_identical_reads(db):
    now = int(time.time() * 1000)
    out = submit_attempt(db, _read_raw(), _desk(), now_ms=now)
    assert out["attempt"]["id"] == 1 and out["score"]["total"] == 100
    dup = submit_attempt(db, _read_raw(), _desk(), now_ms=now + 5_000)
    assert dup["duplicate"] is True and dup["attempt"]["id"] == 1
    rows = db.practice_attempts()
    assert len(rows) == 1, "the double-submit must not inflate history"
    changed = submit_attempt(db, _read_raw(bias="bearish"), _desk(),
                             now_ms=now + 6_000)
    assert changed["duplicate"] is False
    assert len(db.practice_attempts()) == 2


def test_submit_refuses_to_record_without_desk_read(db):
    with pytest.raises(ValueError, match="not recorded"):
        submit_attempt(db, _read_raw(), {"available": False})
    assert db.practice_attempts() == []


def test_submit_rejects_malformed_body_fail_closed(db):
    with pytest.raises(ValueError):
        submit_attempt(db, _read_raw(decision="yolo"), _desk())
    assert db.practice_attempts() == []


# ── the calibration mirror ──────────────────────────────────────────────


def test_scorecard_aggregates_and_names_weakest(db):
    now = int(time.time() * 1000)
    submit_attempt(db, _read_raw(), _desk(), now_ms=now - 2 * DAY)
    submit_attempt(db, _read_raw(bias="bearish", decision="no_trade"),
                   _desk(), now_ms=now - 1 * DAY)
    card = practice_scorecard(db, days=30, now_ms=now)
    json.dumps(card)  # JSON-safe without default=str
    assert card["n"] == 2
    assert card["bias_agreement"] == 0.5
    assert card["decision_agreement"] == 0.5
    assert card["grades"].get("A") == 1
    assert card["weakest_component"] in ("bias", "decision")
    assert card["coaching"] and card["disclaimer"] == DISCLAIMER
    assert len(card["recent"]) == 2
    assert card["recent"][0]["id"] == 2, "newest first"


def test_scorecard_empty_is_honest(db):
    card = practice_scorecard(db)
    assert card["n"] == 0 and card["bias_agreement"] is None
    assert card["avg_score"] is None and card["weakest_component"] is None
    assert "No practice attempts yet" in card["coaching"]
    assert card["tape"]["n"] == 0 and card["tape"]["win_rate"] is None


def test_scorecard_perfect_agreement_claims_no_weakest(db):
    now = int(time.time() * 1000)
    submit_attempt(db, _read_raw(), _desk(), now_ms=now)
    card = practice_scorecard(db, now_ms=now)
    assert card["weakest_component"] is None
    assert "Full agreement" in card["coaching"]


def test_scorecard_window_excludes_old_attempts(db):
    now = int(time.time() * 1000)
    submit_attempt(db, _read_raw(), _desk(), now_ms=now - 45 * DAY)
    submit_attempt(db, _read_raw(bias="bearish", decision="no_trade"),
                   _desk(), now_ms=now)
    card = practice_scorecard(db, days=30, now_ms=now)
    assert card["n"] == 1


def test_format_report_smoke(db):
    now = int(time.time() * 1000)
    submit_attempt(db, _read_raw(), _desk(), now_ms=now)
    text = format_practice_scorecard(practice_scorecard(db, now_ms=now))
    assert "PRACTICE CALIBRATION" in text and "weakest" in text.lower()
    assert DISCLAIMER.split(".")[0] in text


# ── the standing safety invariant: practice feeds NO live surface ───────


def test_practice_rows_never_reach_the_live_book_or_graduation(db):
    from brain.weekly import weekly_review
    from data.simulator import paper_progress
    before_rows = db.live_book_rows()
    before_week = weekly_review(db)["all_time"]["n"]
    before_progress = paper_progress(db)
    now = int(time.time() * 1000)
    for i in range(3):
        submit_attempt(db, _read_raw(note=f"read {i}" + str(i * 37)),
                       _desk(), now_ms=now + i * 200_000)
    assert len(db.practice_attempts()) == 3
    assert db.live_book_rows() == before_rows
    assert weekly_review(db)["all_time"]["n"] == before_week
    assert paper_progress(db) == before_progress


# ── HTTP surface ────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "p.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    from web.app import make_app
    app = make_app()
    app.testing = True
    return app.test_client()


def test_api_practice_get_shape(client):
    r = client.get("/api/practice")
    assert r.status_code == 200
    d = r.get_json()
    for key in ("n", "bias_agreement", "decision_agreement", "component_means",
                    "weakest_component", "coaching", "recent", "disclaimer"):
        assert key in d
    assert d["n"] == 0


def test_api_practice_post_validation_fail_closed(client):
    r = client.post("/api/practice", json=_read_raw(bias="to-da-moon"))
    assert r.status_code == 400
    assert "unknown bias" in r.get_json()["error"]
    g = client.get("/api/practice").get_json()
    assert g["n"] == 0, "nothing recorded on a rejected read"


def test_api_practice_post_happy_path(client, monkeypatch):
    import web.routes_system as _rsys
    monkeypatch.setattr(_rsys, "compute_payload",
                        lambda *a, **k: _payload())
    r = client.post("/api/practice", json=_read_raw())
    assert r.status_code == 200
    d = r.get_json()
    assert d["score"]["total"] == 100 and d["score"]["grade"] == "A"
    assert d["desk"]["action"] == "BUY" and d["desk"]["bias"] == "bullish"
    g = client.get("/api/practice").get_json()
    assert g["n"] == 1 and g["bias_agreement"] == 1.0


def test_api_practice_post_engine_failure_records_nothing(client, monkeypatch):
    import web.routes_system as _rsys

    def _boom(*a, **k):
        raise ConnectionError("no feed")
    monkeypatch.setattr(_rsys, "compute_payload", _boom)
    r = client.post("/api/practice", json=_read_raw())
    assert r.status_code == 502
    assert "not recorded" in r.get_json()["error"]
    assert client.get("/api/practice").get_json()["n"] == 0


def test_api_practice_post_never_creates_a_scan(client, monkeypatch):
    """save=False: a practice read must not enter the review queue."""
    import web.routes_system as _rsys
    monkeypatch.setattr(_rsys, "compute_payload",
                        lambda *a, **k: _payload())
    r = client.post("/api/practice", json=_read_raw())
    assert r.status_code == 200
    from data.database import SignalDB
    with SignalDB() as db:
        n_scans = db.conn.execute("SELECT COUNT(*) c FROM scans").fetchone()["c"]
        assert n_scans == 0
        assert len(db.practice_attempts()) == 1


# ── CLI surface ─────────────────────────────────────────────────────────


# ── W3.6 replay tape ────────────────────────────────────────────────────


def _bar(ts, o, h, low, c):
    return {"ts": ts, "open": o, "high": h, "low": low, "close": c}


def _series(start=1_780_000_000_000, n=30, step=900_000, close=100.0):
    """Flat series: enough history to commit in the middle and still have
    a forward window."""
    return [_bar(start + i * step, close, close + 0.2, close - 0.2, close)
            for i in range(n)]


def _rising_after(commit_i=10, n=30, start=1_780_000_000_000, step=900_000):
    """Flat until commit, then climbs so a 100/99/102.5 buy hits TP."""
    out = []
    for i in range(n):
        ts = start + i * step
        if i <= commit_i:
            out.append(_bar(ts, 100.0, 100.3, 99.8, 100.0))
        else:
            # climb: bar commit+1 already through 102.5
            out.append(_bar(ts, 100.5, 103.0, 100.4, 102.8))
    return out


def _falling_after(commit_i=10, n=30, start=1_780_000_000_000, step=900_000):
    out = []
    for i in range(n):
        ts = start + i * step
        if i <= commit_i:
            out.append(_bar(ts, 100.0, 100.3, 99.8, 100.0))
        else:
            out.append(_bar(ts, 99.5, 99.6, 98.4, 98.6))
    return out


def _ambiguous_after(commit_i=10, n=30, start=1_780_000_000_000, step=900_000):
    out = []
    for i in range(n):
        ts = start + i * step
        if i <= commit_i:
            out.append(_bar(ts, 100.0, 100.3, 99.8, 100.0))
        else:
            # one candle spans both stop 99 and target 102.5
            out.append(_bar(ts, 100.0, 103.0, 98.5, 101.0))
    return out


def test_tape_rejects_missing_commit_and_bad_horizon():
    with pytest.raises(ValueError, match="commit_time is required"):
        validate_tape_request(_read_raw())
    with pytest.raises(ValueError, match="horizon_bars"):
        validate_tape_request(_read_raw(commit_time=1_780_000_000, horizon_bars=2))
    with pytest.raises(ValueError, match="horizon_bars"):
        validate_tape_request(_read_raw(commit_time=1_780_000_000, horizon_bars="nope"))


def test_tape_rejects_wrong_side_ladder():
    with pytest.raises(ValueError, match="BUY paper trade requires"):
        validate_tape_request(_read_raw(commit_time=1_780_000_000,
                                        stop=101.5, target=103.0))


def test_locate_commit_accepts_seconds_or_ms():
    candles = _series()
    ms = candles[10]["ts"]
    assert locate_commit(candles, ms) == 10
    assert locate_commit(candles, ms // 1000) == 10
    with pytest.raises(ValueError, match="not a loaded candle"):
        locate_commit(candles, 1)


def test_walk_buy_ladder_hits_target():
    candles = _rising_after()
    user = _read()
    walk = walk_tape(user, candles[11:27], candles[10])
    assert walk["outcome"] == "TP_HIT"
    assert walk["rr_achieved"] > 0
    assert walk["bars_used"] == 1
    sc = score_tape(user, walk)
    assert sc["kind"] == TAPE_KIND and sc["total"] == 100 and sc["grade"] == "A"
    assert sc["disclaimer"] == TAPE_DISCLAIMER


def test_walk_buy_ladder_hits_stop_and_ambiguous_is_stop_first():
    user = _read()
    stop = walk_tape(user, _falling_after()[11:27], _falling_after()[10])
    assert stop["outcome"] == "STOP_LOSS" and stop["rr_achieved"] == -1.0
    assert score_tape(user, stop)["total"] == 0
    amb = walk_tape(user, _ambiguous_after()[11:27], _ambiguous_after()[10])
    assert amb["outcome"] == "STOP_LOSS" and amb["ambiguous"] is True
    assert "stop-first" in score_tape(user, amb)["components"][0]["detail"]


def test_walk_no_trade_scores_chop_vs_move():
    user = _read(decision="no_trade", entry=None, stop=None, target=None)
    flat = walk_tape(user, _series()[11:27], _series()[10])
    assert flat["outcome"] == "STOOD_ASIDE"
    assert score_tape(user, flat)["total"] == 100
    move = walk_tape(user, _rising_after()[11:27], _rising_after()[10])
    assert score_tape(user, move)["total"] == 25


def test_walk_direction_only_scores_side():
    user = _read(entry=None, stop=None, target=None)
    good = walk_tape(user, _rising_after()[11:27], _rising_after()[10])
    assert good["outcome"] == "DIRECTION" and good["move_atr"] > 0.5
    assert score_tape(user, good)["total"] == 85
    bad = walk_tape(user, _falling_after()[11:27], _falling_after()[10])
    assert score_tape(user, bad)["total"] == 0


def test_walk_expired_window_partial_when_mfe_is_real(db):
    user = _read()
    # future bars tick up 0.4 (never reach 102.5) so the window expires
    start, step = 1_780_000_000_000, 900_000
    commit = _bar(start, 100.0, 100.3, 99.8, 100.0)
    future = [_bar(start + (i + 1) * step, 100.1, 101.2, 100.0, 100.4)
              for i in range(16)]
    walk = walk_tape(user, future, commit)
    assert walk["outcome"] == "EXPIRED"
    assert walk["mfe"] >= 1.0
    assert score_tape(user, walk)["total"] == 40


def test_submit_tape_persists_dedupes_and_refuses_short_window(db):
    now = int(time.time() * 1000)
    candles = _rising_after()
    body = _read_raw(commit_time=candles[10]["ts"], horizon_bars=16)
    out = submit_tape_attempt(db, body, candles, now_ms=now)
    assert out["score"]["outcome"] == "TP_HIT" and out["attempt"]["id"] == 1
    assert out["desk"]["kind"] == TAPE_KIND
    dup = submit_tape_attempt(db, body, candles, now_ms=now + 5_000)
    assert dup["duplicate"] is True and dup["attempt"]["id"] == 1
    assert len(db.practice_attempts()) == 1
    with pytest.raises(ValueError, match="hidden bars"):
        submit_tape_attempt(db, _read_raw(commit_time=candles[-2]["ts"]),
                            candles, now_ms=now + 200_000)


def test_tape_rows_never_move_desk_agreement_or_live_book(db):
    from brain.weekly import weekly_review
    from data.simulator import paper_progress
    now = int(time.time() * 1000)
    submit_attempt(db, _read_raw(), _desk(), now_ms=now)
    before = practice_scorecard(db, now_ms=now)
    before_rows = db.live_book_rows()
    before_week = weekly_review(db)["all_time"]["n"]
    before_progress = paper_progress(db)
    candles = _rising_after()
    submit_tape_attempt(db, _read_raw(commit_time=candles[10]["ts"],
                                      note="tape read"),
                        candles, now_ms=now + 200_000)
    after = practice_scorecard(db, now_ms=now + 200_000)
    assert after["n"] == before["n"] == 1
    assert after["bias_agreement"] == before["bias_agreement"] == 1.0
    assert after["tape"]["n"] == 1
    assert after["tape"]["outcomes"].get("TP_HIT") == 1
    assert db.live_book_rows() == before_rows
    assert weekly_review(db)["all_time"]["n"] == before_week
    assert paper_progress(db) == before_progress
    text = format_practice_scorecard(after)
    assert "TAPE (replay)" in text and "TP_HIT" in text


def test_api_tape_post_happy_path(client, monkeypatch):
    candles = _rising_after()
    monkeypatch.setattr("brain.practice.load_ohlc", lambda *a, **k: candles)
    r = client.post("/api/practice/tape",
                    json=_read_raw(commit_time=candles[10]["ts"]))
    assert r.status_code == 200
    d = r.get_json()
    assert d["score"]["kind"] == TAPE_KIND
    assert d["score"]["outcome"] == "TP_HIT"
    assert d["score"]["total"] == 100
    g = client.get("/api/practice").get_json()
    assert g["n"] == 0, "tape must not inflate desk-agreement n"
    assert g["tape"]["n"] == 1


def test_api_tape_post_validation_fail_closed(client):
    r = client.post("/api/practice/tape", json=_read_raw())
    assert r.status_code == 400
    assert "commit_time" in r.get_json()["error"]
    assert client.get("/api/practice").get_json()["tape"]["n"] == 0


def test_api_tape_never_creates_a_scan_or_paper_row(client, monkeypatch):
    candles = _rising_after()
    monkeypatch.setattr("brain.practice.load_ohlc", lambda *a, **k: candles)
    r = client.post("/api/practice/tape",
                    json=_read_raw(commit_time=candles[10]["ts"]))
    assert r.status_code == 200
    from data.database import SignalDB
    with SignalDB() as db:
        n_scans = db.conn.execute("SELECT COUNT(*) c FROM scans").fetchone()["c"]
        n_paper = db.conn.execute("SELECT COUNT(*) c FROM paper_trades").fetchone()["c"]
        assert n_scans == 0 and n_paper == 0
        assert len(db.practice_attempts()) == 1


def test_cli_practice_json(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "p.db"))
    import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "p.db"))
    import main as m
    rc = m.cmd_practice(type("A", (), {"days": 30, "json": True})())
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["n"] == 0 and "disclaimer" in payload
