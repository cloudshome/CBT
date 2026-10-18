"""Front-end tests for the W3.4 practice mode (Chart-tab ✍ PRACTICE card +
Review-tab PRACTICE CALIBRATION card).

Same approach as tests/test_weekly_js.py: execute the real dashboard
JavaScript in node against stubbed API responses and assert the panels
paint — the form submission POST, the desk-read reveal with visible score
components, the duplicate note, the honest error/empty states, and the
calibration scorecard with the weakest-link coaching line.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "web" / "app.py"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def _extract_js() -> str:
    html = (ROOT / "web" / "static" / "terminal.html").read_text(encoding="utf-8")
    return re.findall(r"<script>(.*?)</script>", html, re.DOTALL)[-1]


def _submit_payload(duplicate: bool = False) -> dict:
    return {
        "duplicate": duplicate,
        "attempt": {
            "id": 7,
            "ts": 1780000000000,
            "day": "2026-05-29",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
        },
        "user": {
            "symbol": "BTCUSDT",
            "tf": "15m",
            "bias": "bullish",
            "decision": "buy",
            "entry": 61250.0,
            "stop": 60800.0,
            "target": 62400.0,
            "confidence": 70,
            "note": "sweep + ob retest",
            "levels_given": True,
        },
        "desk": {
            "available": True,
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "action": "BUY",
            "bias": "bullish",
            "entry": 61200.0,
            "stop": 60750.0,
            "target": 62450.0,
            "risk_reward": 2.78,
            "confidence": "HIGH",
            "plan_type": "Buy Pullback",
            "regime": "TRENDING",
            "atr": 380.0,
            "price": 61248.5,
            "bull_score": 65.0,
            "bear_score": 30.0,
            "signal_id": "BTCUSDT_T",
        },
        "score": {
            "total": 96,
            "earned_max": 100,
            "grade": "A",
            "components": [
                {
                    "name": "directional bias",
                    "points": 35,
                    "max": 35,
                    "detail": "both bullish",
                },
                {
                    "name": "final call (buy / sell / no-trade)",
                    "points": 35,
                    "max": 35,
                    "detail": "both buy",
                },
                {
                    "name": "the ladder (entry / stop / target)",
                    "points": 26,
                    "max": 30,
                    "detail": "entry gap 50.0 vs 1×ref 380.0 → 10/10 · "
                    "stop right side → 10/10 · your R:R 2.55 vs "
                    "≥1.5 floor → 6/10",
                },
            ],
            "bias_match": True,
            "decision_match": True,
            "desk_action": "BUY",
            "desk_bias": "bullish",
            "disclaimer": "Practice score = agreement with the desk's "
            "current read. Study metric only.",
        },
        "disclaimer": "Practice score = agreement with the desk's current read. Study metric only.",
    }


def _card_payload(n: int = 3) -> dict:
    recent = [
        {
            "id": i,
            "day": "2026-08-1" + str(i),
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "user_bias": "bullish",
            "user_decision": "buy",
            "desk_bias": "bullish",
            "desk_action": "BUY",
            "score": 90 - i * 10,
            "grade": "ABC"[i - 1],
        }
        for i in range(1, n + 1)
    ]
    return {
        "window": {
            "days": 30,
            "label": "2026-07-20 → 2026-08-19",
            "since_ts": 1,
            "until_ts": 2,
        },
        "n": n,
        "bias_agreement": 0.667,
        "decision_agreement": 0.333,
        "avg_score": 73.3,
        "best_score": 90,
        "worst_score": 50,
        "grades": {"A": 1, "B": 1, "C": 1},
        "component_means": {"bias": 0.81, "decision": 0.48, "levels": 0.7},
        "weakest_component": "decision",
        "coaching": "Your final call diverges even when direction is close.",
        "recent": recent,
        "disclaimer": "Study metric only — not evidence, feeds no gate.",
    }


_HARNESS_HEAD = r"""
    const API = __API__;
    const POSTS = [];
    const elements = {};
    function mkEl(id){
      const cls = new Set();
      return { id, innerHTML:'', className:'', textContent:'', value:'',
        checked:true, disabled:false, clientWidth:900, style:{},
        options:[], appendChild(){}, scrollIntoView(){}, classes: cls,
        addEventListener:()=>{}, querySelector:()=>null,
        querySelectorAll:()=>[],
        classList:{
          toggle(c, on){ const want = (on === undefined) ? !cls.has(c) : !!on;
            if(want) cls.add(c); else cls.delete(c); return want; },
          add(c){ cls.add(c); }, remove(c){ cls.delete(c); },
          contains(c){ return cls.has(c); } } };
    }
    function el(id){ if(!elements[id]) elements[id]=mkEl(id); return elements[id]; }
    global.LightweightCharts = { createChart: () => ({
      addCandlestickSeries(){ return {setData(){},createPriceLine(){}}; },
      addLineSeries(){ return {setData(){},update(){},setMarkers(){},createPriceLine(){}}; },
      addHistogramSeries(){ return {setData(){},priceScale(){return {applyOptions(){}};}}; },
      timeScale(){ return { fitContent(){}, applyOptions(){} }; },
      applyOptions(){}, remove(){} }) };
    global.window = { addEventListener: ()=>{}, LightweightCharts: global.LightweightCharts };
    global.document = { getElementById: el, addEventListener: ()=>{},
      querySelectorAll: ()=>[], createElement: ()=>mkEl('tmp'), title: 'SKY' };
    global.localStorage = { store: {},
      getItem(k){ return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null; },
      setItem(k, v){ this.store[k] = String(v); },
      removeItem(k){ delete this.store[k]; } };
    global.history = { replaceState: ()=>{} };
    global.location = { hash: '' };
    global.confirm = () => true;
    global.AbortController = class { constructor(){ this.signal={}; } abort(){} };
    global.fetch = async (url, opts) => {
      if(opts && String(opts.method || 'GET').toUpperCase() === 'POST')
        POSTS.push({ url: String(url), body: opts.body || '' });
      const key = Object.keys(API)
        .filter(k => String(url).includes(k))
        .sort((a, b) => b.length - a.length)[0];
      let spec = key ? API[key] : { status: 200, body: {} };
      const status = spec.status === undefined ? 200 : spec.status;
      const payload = spec.body === undefined ? {} : spec.body;
      return { ok: status < 400, status: status, json: async () => payload };
    };
    global.setInterval = () => 0; global.clearInterval = () => {};
    global.setTimeout = (fn) => { if(typeof fn === 'function') fn(); return 0; };

__DASHBOARD_JS__

    (async () => {
      try { __BODY__ }
      catch (e) { console.error('HARNESS ERROR: ' + (e && e.stack || e)); process.exit(1); }
    })();
"""


class _Queue:
    """Per-test fetch responder: explicit queue of (status, body) keyed per URL."""

    def __init__(self, mapping: dict):
        self._queues = {k: list(v) for k, v in mapping.items()}

    def next(self, key):
        q = self._queues[key]
        if not q:
            return {"status": 404, "body": {}}
        status, body = q.pop(0)
        return {"status": status, "body": body}


def _run(api_queues: dict, body: str) -> dict:
    head = _HARNESS_HEAD.replace("__DASHBOARD_JS__", _extract_js())
    queue_js = json.dumps({k: [[s, b] for (s, b) in v] for k, v in api_queues.items()})
    head = head.replace(
        "const API = __API__;",
        "const QUEUES = " + queue_js + ";\n"
        "    const API = {};\n"
        "    for (const k of Object.keys(QUEUES)) {\n"
        "      API[k] = () => { const q = QUEUES[k];\n"
        "        const nxt = q.length ? q.shift() : [404, {}];\n"
        "        return { status: nxt[0], body: nxt[1] }; };\n"
        "    }",
    )
    head = head.replace(
        "      let spec = key ? API[key] : { status: 200, body: {} };",
        "      let spec = key ? API[key]() : { status: 200, body: {} };",
    )
    harness = head.replace("__BODY__", body)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, timeout=90)
        assert r.returncode == 0, f"harness failed:\n{r.stdout}\n{r.stderr}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


_FILL = (
    "el('pracBias').value='bullish'; el('pracDecision').value='buy';"
    "el('pracEntry').value='61250'; el('pracStop').value='60800';"
    "el('pracTarget').value='62400'; el('pracConf').value='70';"
    "el('pracNote').value='sweep + ob retest';"
)

_OUT = (
    "console.log(JSON.stringify({pracResult:document.getElementById('pracResult').innerHTML,"
    "pracMini:document.getElementById('pracMini').textContent,"
    "wkPractice:(document.getElementById('wkPractice')||{}).innerHTML||'',"
    "posts:POSTS.map(p=>({url:p.url,body:JSON.parse(p.body)}))}));"
)


def test_submit_posts_form_and_paints_reveal():
    out = _run(
        {
            "/api/practice": [
                (200, _submit_payload()),
                (200, _card_payload()),
                (200, _card_payload()),
            ]
        },
        _FILL + "\n await submitPractice();\n await loadPracticeScorecard();\n" + _OUT,
    )
    assert len(out["posts"]) == 1
    body = out["posts"][0]["body"]
    assert out["posts"][0]["url"].endswith("/api/practice")
    assert body["bias"] == "bullish" and body["decision"] == "buy"
    assert body["entry"] == 61250 and body["stop"] == 60800 and body["target"] == 62400
    assert body["confidence"] == 70 and body["note"] == "sweep + ob retest"
    assert body["symbol"] and body["tf"]
    r = out["pracResult"]
    assert "desk: BUY" in r and "your read 96/100 · A" in r
    assert "both bullish" in r and "right side" in r
    assert "Study metric only" in r, "disclaimer must ride with the reveal"
    assert "sweep + ob retest" in r


def test_duplicate_note_is_shown_and_not_double_counted():
    out = _run(
        {
            "/api/practice": [
                (200, _submit_payload(duplicate=True)),
                (200, _card_payload()),
            ]
        },
        _FILL + "\n await submitPractice();\n" + _OUT,
    )
    assert "identical read" in out["pracResult"]
    assert "double-counted" in out["pracResult"]


def test_rejected_read_shows_the_server_reason():
    out = _run(
        {
            "/api/practice": [
                (
                    400,
                    {"error": "unknown bias 'moonish' — allowed: bullish, bearish, neutral"},
                )
            ]
        },
        "el('pracBias').value='moonish';\n await submitPractice();\n" + _OUT,
    )
    assert "unknown bias" in out["pracResult"]
    assert "desk:" not in out["pracResult"]


def test_scorecard_card_paints_stats_weakest_and_recent():
    out = _run(
        {"/api/practice": [(200, _card_payload())]},
        "await loadPracticeScorecard();\n" + _OUT,
    )
    w = out["wkPractice"]
    assert "Bias agreement" in w and "66.7%" in w
    assert "Call agreement" in w and "33.3%" in w
    assert "Weakest link" in w and "decision" in w
    assert "final call diverges" in w
    assert "#1" in w and "#3" in w, "recent attempts table paints"
    assert "feeds no gate" in w, "disclaimer must ride with the card"
    assert "3 committed reads" in out["pracMini"]


def test_scorecard_empty_state_is_honest():
    empty = _card_payload(n=0)
    empty.update(
        {
            "bias_agreement": None,
            "decision_agreement": None,
            "avg_score": None,
            "weakest_component": None,
            "coaching": "No practice attempts yet — commit a read on the Chart tab.",
            "grades": {},
            "recent": [],
        }
    )
    out = _run({"/api/practice": [(200, empty)]}, "await loadPracticeScorecard();\n" + _OUT)
    assert "No practice attempts yet" in out["wkPractice"]
    assert "no committed reads yet" in out["pracMini"]


def test_html_exposes_the_practice_cards():
    """The served HTML must contain both cards and their wiring."""
    src = (ROOT / "web" / "static" / "terminal.html").read_text(encoding="utf-8")
    for marker in (
        'id="pracBias"',
        'id="pracDecision"',
        'id="pracEntry"',
        'id="pracStop"',
        'id="pracTarget"',
        'id="pracResult"',
        'id="pracMini"',
        'id="wkPractice"',
        "BEFORE the Signal desk",
        "submitPractice()",
        "loadPracticeScorecard()",
        'id="pracTapeBtn"',
        'id="pracTapeBanner"',
        "submitTapePractice()",
        "freezeReplay()",
        "/api/practice/tape",
    ):
        assert marker in src, f"dashboard missing {marker}"


def _tape_payload() -> dict:
    return {
        "duplicate": False,
        "attempt": {
            "id": 9,
            "ts": 1780000000000,
            "day": "2026-05-29",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "kind": "tape",
        },
        "user": {
            "symbol": "BTCUSDT",
            "tf": "15m",
            "bias": "bullish",
            "decision": "buy",
            "entry": 61250.0,
            "stop": 60800.0,
            "target": 62400.0,
            "confidence": 70,
            "note": "tape",
            "levels_given": True,
        },
        "desk": {
            "kind": "tape",
            "available": True,
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "commit_time": 1780000000000,
            "horizon_bars": 16,
            "future_bars": 16,
            "outcome": "TP_HIT",
            "bars_used": 4,
            "rr_achieved": 2.5,
        },
        "score": {
            "kind": "tape",
            "total": 100,
            "grade": "A",
            "outcome": "TP_HIT",
            "rr_achieved": 2.5,
            "bars_used": 4,
            "components": [
                {
                    "name": "ladder vs the tape",
                    "points": 100,
                    "max": 100,
                    "detail": "target hit in 4 bars (+2.50R)",
                }
            ],
            "disclaimer": "Tape score = what the hidden future bars did. Historical playback only.",
        },
        "disclaimer": "Tape score = what the hidden future bars did. Historical playback only.",
    }


def test_tape_without_replay_refuses_honestly():
    out = _run(
        {"/api/practice/tape": [(200, _tape_payload())]},
        "await submitTapePractice();\n" + _OUT,
    )
    assert "Start Replay" in out["pracResult"]
    assert out["posts"] == []


def test_tape_posts_commit_time_and_paints_outcome():
    setup = (
        "_replay={timer:null,idx:12,candles:["
        "{time:1780000000},{time:1780000900},{time:1780001800},"
        "{time:1780002700},{time:1780003600},{time:1780004500},"
        "{time:1780005400},{time:1780006300},{time:1780007200},"
        "{time:1780008100},{time:1780009000},{time:1780009900}],"
        "candle:{setData:function(){}},speedIdx:0};"
    )
    out = _run(
        {
            "/api/practice/tape": [(200, _tape_payload()), (200, _card_payload())],
            "/api/practice": [(200, _card_payload())],
        },
        setup + _FILL + "\n await submitTapePractice();\n" + _OUT,
    )
    assert any(p["url"].endswith("/api/practice/tape") for p in out["posts"])
    body = next(p["body"] for p in out["posts"] if p["url"].endswith("/api/practice/tape"))
    assert body["commit_time"] == 1780009900
    assert body["horizon_bars"] == 16
    assert body["decision"] == "buy"
    r = out["pracResult"]
    assert "tape: TP_HIT" in r and "your read 100/100 · A" in r
    assert "Historical playback" in r


def test_scorecard_paints_tape_sibling():
    card = _card_payload()
    card["tape"] = {
        "n": 2,
        "avg_score": 50,
        "win_rate": 0.5,
        "outcomes": {"TP_HIT": 1, "STOP_LOSS": 1},
        "recent": [
            {
                "id": 11,
                "day": "2026-08-18",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "user_decision": "buy",
                "outcome": "TP_HIT",
                "score": 100,
                "grade": "A",
            }
        ],
        "coaching": "Tape scores measure the hidden bars.",
        "disclaimer": "Historical playback only.",
    }
    out = _run({"/api/practice": [(200, card)]}, "await loadPracticeScorecard();\n" + _OUT)
    w = out["wkPractice"]
    assert "TAPE — replay outcomes" in w
    assert "Ladder win rate" in w and "50.0%" in w
    assert "TP_HIT" in w and "Historical playback only" in w
