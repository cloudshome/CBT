"""Front-end tests for the W3 Weekly Review tab + journal-first gate.

Same approach as tests/test_workstation_js.py: execute the real dashboard
JavaScript in node against stubbed API responses and assert the panels paint
the numbers — the weekly stats, the R-distribution, the violations card, the
graduation tracker, the ritual checkboxes, and the journal-first approve flow.
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
    return re.findall(r"<script>(.*?)</script>", html, re.S)[-1]


def _weekly_payload() -> dict:
    """A seeded-book-shaped weekly review payload (mirrors brain/weekly.py)."""
    return {
        "window": {"days": 7, "label": "2026-08-12 → 2026-08-19",
                   "since_ts": 1, "until_ts": 2},
        "week": {"n": 3, "wins": 2, "losses": 1, "win_rate": 0.6667,
                 "expectancy_net": 0.8333, "expectancy_gross": 0.8333,
                 "profit_factor": 3.5, "total_r_net": 2.5,
                 "avg_win_r": 1.75, "avg_loss_r": -1.0,
                 "best_r": 2.0, "worst_r": -1.0},
        "all_time": {"n": 5, "wins": 3, "losses": 2, "win_rate": 0.6,
                     "expectancy_net": 0.5, "expectancy_gross": 0.5,
                     "profit_factor": 2.25, "total_r_net": 2.5,
                     "avg_win_r": 1.5, "avg_loss_r": -1.0,
                     "best_r": 2.0, "worst_r": -1.0},
        "r_distribution": [
            {"bucket": "≤ -2R", "n": 0, "pct": 0.0},
            {"bucket": "(-2R,-1R]", "n": 2, "pct": 40.0},
            {"bucket": "(-1R,-0.5R]", "n": 0, "pct": 0.0},
            {"bucket": "(-0.5R,0R)", "n": 0, "pct": 0.0},
            {"bucket": "0R breakeven", "n": 0, "pct": 0.0},
            {"bucket": "(0R,+0.5R]", "n": 0, "pct": 0.0},
            {"bucket": "(+0.5R,+1R]", "n": 1, "pct": 20.0},
            {"bucket": "(+1R,+2R]", "n": 2, "pct": 40.0},
            {"bucket": "> +2R", "n": 0, "pct": 0.0},
        ],
        "r_distribution_week": [],
        "source": "canonical live book (simulator excluded, research books excluded)",
        "equity_curve": [
            {"scan_id": 1, "closed_ts": 1780000000000, "rr": 2.0, "pnl": 50.0,
             "equity": 10050.0},
            {"scan_id": 2, "closed_ts": 1780000100000, "rr": -1.0, "pnl": -25.12,
             "equity": 10024.88},
            {"scan_id": 3, "closed_ts": 1780000200000, "rr": 1.5, "pnl": 37.59,
             "equity": 10062.47},
        ],
        "drawdown": {"max_drawdown_pct": 0.25, "final_equity": 10062.47},
        "violations": {
            "eligible": 5, "journaled": 2, "missing_journals": 3,
            "missing_scan_ids": [5, 4, 3], "violations": 1, "compliance": 0.2,
            "compliance_bar": 0.9, "by_mistake": {"entered early": 1},
            "by_emotion": {"greedy": 1},
            "recent": [{"scan_id": 2, "ts": 1780000100000, "day": "2026-05-29",
                        "outcome": "STOP_LOSS", "mistake": "entered early",
                        "emotion": "greedy", "in_window": True,
                        "followed_rules": 0},
                       {"scan_id": 1, "ts": 1780000000000, "day": "2026-05-29",
                        "outcome": "TP_HIT", "mistake": "none",
                        "emotion": "calm", "in_window": True,
                        "followed_rules": 1}],
            "in_window": 1,
            "source": "canonical live (Binance spot)",
        },
        "journal_gate": {"missing": 3, "scan_ids": [5, 4, 3],
                         "trades": [{"scan_id": 3, "day": "2026-08-18",
                                     "plan_type": "Buy Pullback",
                                     "outcome": "TP_HIT"}]},
        "graduation_tracker": [{
            "plan_type": "Buy Pullback", "primary": True,
            "backtest_n": 0, "backtest_target": 100, "backtest_pct": 0.0,
            "paper_n": 6, "paper_target": 20, "paper_pct": 30.0,
            "expectancy_net": 0.5, "win_rate_net": 0.6, "proven": False,
            "missing": ["100 more unique backtest samples (0/100)",
                        "14 more real paper samples (6/20)"],
        }],
        "next_practice_task": {
            "name": "journal_first",
            "title": "Journal 3 unjournaled trade(s) before anything else",
            "detail": "Missing journals lower compliance (P12.14).",
            "action": "unjournaled scans: #5, #4, #3",
        },
        "grade": {"grade": "C", "score": 55, "max": 100,
                  "components": [
                      {"name": "rule compliance ≥ 90%", "current": 20.0,
                       "points": 0, "max": 30},
                      {"name": "every decided trade journaled", "current": "2/5",
                       "points": 5, "max": 20},
                      {"name": "≥1 real paper decision closed this week",
                       "current": 3, "points": 10, "max": 10},
                      {"name": "week net expectancy > 0R", "current": 0.8333,
                       "points": 25, "max": 25},
                      {"name": "week not below its all-time net expectancy",
                       "current": "+0.833R", "points": 15, "max": 15},
                  ],
                  "note": "advisory self-review only — not the real gate"},
        "bar": {"expectancy": 0.5, "win_rate": 0.55, "pf": 1.5,
                "compliance": 0.9,
                "note": "bars are unchanged and NET of costs"},
        "generated_ts": 1780000000,
    }


def _ritual_payload(done: dict | None = None) -> dict:
    done = done or {}
    steps = []
    for i, name in enumerate(("readiness", "loop", "gate", "act"), start=1):
        steps.append({"step": i, "name": name, "ok": True,
                      "label": f"{name} ok", "command": f"python main.py {name}",
                      "done": bool(done.get(name)),
                      "done_ts": done.get(name)})
    n_done = sum(1 for s in steps if s["done"])
    return {"day": "2026-08-19", "steps": steps, "done": n_done, "total": 4,
            "complete": n_done == 4,
            "note": "Ticks are a human memory, not permission."}


_HARNESS_HEAD = r"""
    const API = __API__;
    const POSTS = [];
    const TOASTS = [];
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
    const CHARTS = [];
    global.LightweightCharts = { createChart: (target, opts) => {
      const priceScaleStub = { applyOptions(){} };
      const chart = { pane: target && target.id, height: opts && opts.height,
        series: [],
        addCandlestickSeries(){ const s={lines:[],setData(d){this.data=d;},createPriceLine(){}};
          this.series.push(s); return s; },
        addLineSeries(o){ const s={kind:'line',data:null,opts:o||null,
          setData(d){ this.data = d; }, update(){}, setMarkers(){},
          createPriceLine(){} };
          this.series.push(s); return s; },
        addHistogramSeries(){ const s={kind:'hist',setData(){},
          priceScale(){ return priceScaleStub; }};
          this.series.push(s); return s; },
        timeScale(){ return { fitContent(){}, applyOptions(){} }; },
        applyOptions(){}, remove(){ this.removed = true; } };
      CHARTS.push(chart); return chart;
    } };
    global.window = { addEventListener: ()=>{}, LightweightCharts: global.LightweightCharts };
    global.document = { getElementById: el, addEventListener: ()=>{},
      querySelectorAll: ()=>[], createElement: ()=>mkEl('tmp'),
      title: 'SKY' };
    global.localStorage = { store: {},
      getItem(k){ return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null; },
      setItem(k, v){ this.store[k] = String(v); },
      removeItem(k){ delete this.store[k]; } };
    global.history = { replaceState: ()=>{} };
    global.location = { hash: '' };
    global.confirm = (msg) => { global.__lastConfirm = msg; return !!global.__confirmAnswer; };
    global.AbortController = class { constructor(){ this.signal={}; } abort(){} };
    global.fetch = async (url, opts) => {
      if(opts && String(opts.method || 'GET').toUpperCase() === 'POST')
        POSTS.push({ url: String(url), body: opts.body || '' });
      const key = Object.keys(API)
        .filter(k => String(url).includes(k))
        .sort((a, b) => b.length - a.length)[0];
      let spec = key ? API[key] : { status: 200, body: {} };
      if(Array.isArray(spec)) spec = spec.length ? spec.shift() : { status: 404, body: {} };
      const status = spec.status === undefined ? 200 : spec.status;
      const payload = spec.body === undefined ? {} : spec.body;
      return { ok: status < 400, status: status, json: async () => payload };
    };
    global.setInterval = () => 0; global.clearInterval = () => {};
    global.setTimeout = (fn) => { if(typeof fn === 'function') fn(); return 0; };
    global.clearTimeout = () => {};

__DASHBOARD_JS__

    // capture toasts after the script defines them
    const _toast = showToast;
    showToast = (m, k) => { TOASTS.push(String(m) + '|' + k); };

    (async () => {
      try { __BODY__ }
      catch (e) { console.error('HARNESS ERROR: ' + (e && e.stack || e)); process.exit(1); }
    })();
"""


def _run(api: dict, body: str) -> dict:
    """Execute the dashboard JS with a queued, POST-capturing stubbed fetch."""
    harness = (_HARNESS_HEAD
               .replace("__API__", json.dumps(api))
               .replace("__DASHBOARD_JS__", _extract_js())
               .replace("__BODY__", body))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, timeout=90)
        assert r.returncode == 0, f"harness failed:\n{r.stdout}\n{r.stderr}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


_OUT = "console.log(JSON.stringify({wkStats, wkTask, wkDist, wkViol, wkTrack, ritList, ritCount, posts: POSTS, toasts: TOASTS, charts: CHARTS.length, tab: (typeof _activeTab!=='undefined'?_activeTab:null), confirm: global.__lastConfirm || null}));"


def test_weekly_tab_paints_every_panel():
    body = f"""
      await loadWeekly();
      await loadRitual();
      const wkStats=document.getElementById('wkStats').innerHTML;
      const wkTask=document.getElementById('wkTask').innerHTML;
      const wkDist=document.getElementById('wkDist').innerHTML;
      const wkViol=document.getElementById('wkViol').innerHTML;
      const wkTrack=document.getElementById('wkTrack').innerHTML;
      const ritList=document.getElementById('ritualList').innerHTML;
      const ritCount=document.getElementById('ritCount').textContent;
      {_OUT}
    """
    out = _run({"/api/weekly": {"status": 200, "body": _weekly_payload()},
                "/api/ritual": {"status": 200, "body": _ritual_payload()}},
               body)
    s = out["wkStats"]
    assert "week" in s.lower() or "+0.833R" in s
    assert "grade" in s.lower() and "C" in out["wkStats"]
    assert "+0.833R" in out["wkStats"], out["wkStats"][:400]
    assert "Journal 3 unjournaled trade" in out["wkTask"]
    assert "unjournaled scans" in out["wkTask"]
    assert "(-2R,-1R]" in out["wkDist"] and "(+1R,+2R]" in out["wkDist"]
    assert "2 (40%)" in out["wkDist"] or "40.0" in out["wkDist"]
    v = out["wkViol"]
    assert "2/5" in v and "entered early" in v and "greedy" in v
    assert "#5" in v and "#4" in v and "#3" in v
    t = out["wkTrack"]
    assert "Buy Pullback" in t and "0/100" in t and "6/20" in t
    assert "100 more unique backtest samples" in t
    # the equity stub chart was created with 3 deduped points
    assert out["charts"] >= 1
    # ritual checklist painted four steps, none ticked
    for step in ("readiness", "loop", "gate", "act"):
        assert f"'{step}'" in out["ritList"] or step in out["ritList"]
    assert out["ritList"].count("checkbox") == 4
    assert out["ritCount"] == "0/4"


def test_ritual_tick_posts_and_repaints():
    body = f"""
      await loadRitual();
      await toggleRitual('loop', true);
      const wkStats='', wkTask='', wkDist='', wkViol='', wkTrack='';
      const ritList=document.getElementById('ritualList').innerHTML;
      const ritCount=document.getElementById('ritCount').textContent;
      {_OUT}
    """
    out = _run({"/api/ritual": {"status": 200,
                                "body": _ritual_payload({"loop": 1780000000000})}}, body)
    assert len(out["posts"]) == 1, out["posts"]  # exactly one mutation POST
    posted = json.loads(out["posts"][0]["body"])
    assert posted == {"step": "loop", "done": True}
    assert out["posts"][0]["url"] == "/api/ritual"
    # repainted with the tick: 1/4 + a "ticked" timestamp
    assert out["ritCount"] == "1/4"
    assert "ticked" in out["ritList"]


def test_decide_journal_block_acknowledge_flow():
    """approve → 409 journal_block → confirm OK → POST acknowledge_journal
    → success toast. Cancel → jump to the journal tab, no second POST."""
    journal_block = {"ok": False, "status": 409, "body": {
        "error": "Journal-first discipline: 1 decided real trade(s) unjournaled",
        "journal_block": {"missing": 1, "scan_ids": [900],
                          "trades": [{"scan_id": 900, "day": "2026-08-19",
                                      "plan_type": "Buy Pullback",
                                      "outcome": "TP_HIT"}]},
        "acknowledge_available": True,
    }}
    body = f"""
      global.__confirmAnswer = true;
      try {{ await decide(123, 'APPROVED', null); }} catch(e) {{ /* refresh tail */ }}
      const wkStats='', wkTask='', wkDist='', wkViol='', wkTrack='',
        ritList='', ritCount='';
      {_OUT}
    """
    out = _run({"/api/review": [journal_block,
                                {"status": 200, "body": {"ok": True, "scan_id": 123,
                                                         "status": "APPROVED"}}],
                "/api/pending": {"status": 200, "body": {"pending": []}},
                "/api/paper": {"status": 200, "body": {"trades": []}},
                "/api/history": {"status": 200, "body": {"history": []}},
                "/api/learning": {"status": 200, "body": {"profile": {}}},
                "/api/watchlist": {"status": 200, "body": {"items": []}}},
               body)
    assert len(out["posts"]) == 2, out["posts"]
    first, second = out["posts"]
    assert first["url"] == "/api/review" and second["url"] == "/api/review"
    assert "acknowledge_journal" not in first["body"]
    assert json.loads(second["body"])["acknowledge_journal"] is True
    assert any("journal acknowledged" in t for t in out["toasts"]), out["toasts"]
    assert out["confirm"] and "#900" in out["confirm"]


def test_decide_journal_block_cancel_goes_to_journal():
    journal_block = {"ok": False, "status": 409, "body": {
        "error": "Journal-first discipline: 1 decided real trade(s) unjournaled",
        "journal_block": {"missing": 1, "scan_ids": [900], "trades": []},
        "acknowledge_available": True,
    }}
    body = f"""
      global.__confirmAnswer = false;
      try {{ await decide(123, 'APPROVED', null); }} catch(e) {{ /* refresh tail */ }}
      const wkStats='', wkTask='', wkDist='', wkViol='', wkTrack='',
        ritList='', ritCount='';
      {_OUT}
    """
    out = _run({"/api/review": [journal_block]}, body)
    assert len(out["posts"]) == 1, out["posts"]  # held — no silent approve
    assert out["tab"] == "journal", out["tab"]
    assert any("Journal first" in t for t in out["toasts"]), out["toasts"]


def test_weekly_empty_book_is_honest_not_blank():
    empty = _weekly_payload()
    empty["week"] = {"n": 0, "wins": 0, "losses": 0, "win_rate": None,
                     "expectancy_net": None, "expectancy_gross": None,
                     "profit_factor": None, "total_r_net": 0.0,
                     "avg_win_r": None, "avg_loss_r": None,
                     "best_r": None, "worst_r": None}
    empty["all_time"] = dict(empty["week"])
    empty["equity_curve"] = []
    empty["r_distribution"] = []
    empty["graduation_tracker"] = []
    empty["violations"]["missing_journals"] = 0
    empty["violations"]["missing_scan_ids"] = []
    empty["violations"]["compliance"] = None
    empty["grade"] = {"grade": "—", "score": 25, "max": 100, "components": [],
                      "note": "advisory only"}
    body = f"""
      await loadWeekly();
      const wkStats=document.getElementById('wkStats').innerHTML;
      const wkTask=document.getElementById('wkTask').innerHTML;
      const wkDist=document.getElementById('wkDist').innerHTML;
      const wkViol=document.getElementById('wkViol').innerHTML;
      const wkTrack=document.getElementById('wkTrack').innerHTML;
      const wkEquity=document.getElementById('wkEquity').innerHTML;
      const ritList='', ritCount='';
      {{
        const _tmp={{wkStats, wkTask, wkDist, wkViol, wkTrack, wkEquity,
          posts: POSTS, toasts: TOASTS, charts: CHARTS.length}};
        console.log(JSON.stringify(_tmp));
      }}
    """
    out = _run({"/api/weekly": {"status": 200, "body": empty}}, body)
    assert "n/a" in out["wkStats"]  # honest unknowns, not fake zeros
    assert out["charts"] == 0  # no fake equity chart
    assert "not enough decided trades" in out["wkEquity"]
    assert "no decided trades" in out["wkDist"]
    assert "no setups on record" in out["wkTrack"]
