"""T5 — Home screen & onboarding tests.

Same approach as tests/test_terminal_js.py: execute the real served dashboard
JavaScript in node against stubbed API responses and assert the post-login
command dashboard actually wires up:

  * Home is the landing view when no hash/saved preference exists;
  * the cards paint from the existing /api/risk, /api/readiness, /api/trades
    and /api/loop-health payloads (gate, data freshness, positions, P&L,
    journal tasks, evidence progress, focus) — no new endpoint;
  * a blocked gate, a journal-first hold and trader-state flags surface the
    real reasons, not vague colours;
  * a dead feed paints an explicit error + retry, never a silently blank card;
  * onboarding appears for a fresh desk and its dismissal persists;
  * "Open Trading Terminal" navigates into the Trade view and the Continue
    button carries the remembered market/timeframe.

They skip when node is unavailable, exactly like the existing JS tests.
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


_HARNESS_HEAD = r"""
    const API = __API__;
    const POSTS = [];
    const TOASTS = [];
    const elements = {};
    const OFFERED = new Set(['BTCUSDT','ETHUSDT','XAUUSD','XAUUSDT',
                             '15m','30m','1h','4h','1d']);
    function mkEl(id){
      const cls = new Set();
      return { id, innerHTML:'', className:'', textContent:'', value:'',
        checked:true, disabled:false, clientWidth:900, style:{},
        options:[], appendChild(){}, remove(){}, scrollIntoView(){}, classes: cls,
        addEventListener:()=>{}, setAttribute:()=>{},
        querySelector:()=>null, querySelectorAll:()=>[],
        classList:{
          toggle(c, on){ const want = (on === undefined) ? !cls.has(c) : !!on;
            if(want) cls.add(c); else cls.delete(c); return want; },
          add(c){ cls.add(c); }, remove(c){ cls.delete(c); },
          contains(c){ return cls.has(c); } } };
    }
    function el(id){ if(!elements[id]) elements[id]=mkEl(id); return elements[id]; }
    global.window = { addEventListener: ()=>{} };
    global.document = { getElementById: el, addEventListener: ()=>{},
      querySelectorAll: ()=>[], createElement: ()=>mkEl('tmp'), title: 'SKY',
      querySelector: (sel) => {
        const m = /data-(?:sym|tf)=\"([^\"]+)\"/.exec(sel || '');
        if(m && OFFERED.has(m[1])) return mkEl('q');
        return null;
      } };
    global.localStorage = { store: {},
      getItem(k){ return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null; },
      setItem(k, v){ this.store[k] = String(v); },
      removeItem(k){ delete this.store[k]; } };
    global.history = { replaceState: ()=>{} };
    global.location = { hash: '' };
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
    global.setTimeout = (fn, ms) => { if(typeof ms === 'number' && ms > 100) return 0; if(typeof fn === 'function') fn(); return 0; };
    global.clearTimeout = () => {};

__DASHBOARD_JS__

    const _toast = showToast;
    showToast = (m, k) => { TOASTS.push(String(m) + '|' + k); };

    (async () => {
      try { __BODY__ }
      catch (e) { console.error('HARNESS ERROR: ' + (e && e.stack || e)); process.exit(1); }
    })();
"""


def _run(api: dict, body: str) -> dict:
    harness = (
        _HARNESS_HEAD.replace("__API__", json.dumps(api))
        .replace("__DASHBOARD_JS__", _extract_js())
        .replace("__BODY__", body)
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, timeout=90)
        assert r.returncode == 0, f"harness failed:\n{r.stdout}\n{r.stderr}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


_DRAIN = "for(let i=0;i<20;i++) await new Promise(r=>setTimeout(r,0));"

_OUT = """
console.log(JSON.stringify({
  posts: POSTS, toasts: TOASTS,
  nav: _currentNav,
  homeActive: el('view-home').classList.contains('active'),
  tradeActive: el('view-trade').classList.contains('active'),
  greet: el('homeGreet').textContent || '',
  cont: el('homeContinue').textContent || '',
  gate: el('homeBodyGate').innerHTML || '',
  gateCls: el('homeDotGate').className || '',
  data: el('homeBodyData').innerHTML || '',
  dataCls: el('homeDotData').className || '',
  pos: el('homeBodyPositions').innerHTML || '',
  pnl: el('homeBodyPnl').innerHTML || '',
  pnlCls: el('homeDotPnl').className || '',
  journal: el('homeBodyJournal').innerHTML || '',
  journalCls: el('homeDotJournal').className || '',
  evidence: el('homeBodyEvidence').innerHTML || '',
  focus: el('homeBodyFocus').innerHTML || '',
  focusCls: el('homeDotFocus').className || '',
  onboard: el('homeOnboard').innerHTML || '',
  onboardShown: el('homeOnboard').style.display || '',
  meta: el('homeMeta').textContent || '',
  hideIntro: localStorage.getItem('sky.home.hideIntro') || null }));
"""


def _risk_open() -> dict:
    return {
        "status": 200,
        "body": {
            "gate": {
                "allowed": True,
                "blocked_by": [],
                "details": {
                    "daily_weekly": {
                        "today": {"n": 1, "r_sum": 0.38, "pct": 0.19},
                        "week": {"n": 3, "r_sum": 0.55, "pct": 0.275},
                        "daily_limit": 2.0,
                        "weekly_limit": 4.0,
                        "daily_blocked": False,
                        "weekly_blocked": False,
                    }
                },
            }
        },
    }


def _risk_blocked() -> dict:
    return {
        "status": 200,
        "body": {
            "gate": {
                "allowed": False,
                "blocked_by": [
                    "daily loss limit reached (-2.10% ≤ -2%)",
                    "trader state: angry — no trading while these flags are set",
                ],
                "details": {
                    "daily_weekly": {
                        "today": {"n": 3, "r_sum": -1.05, "pct": -2.1},
                        "week": {"n": 4, "r_sum": -0.6, "pct": -1.2},
                        "daily_limit": 2.0,
                        "weekly_limit": 4.0,
                        "daily_blocked": True,
                        "weekly_blocked": False,
                    }
                },
            }
        },
    }


def _readiness_ok() -> dict:
    return {
        "status": 200,
        "body": {
            "level": "ok",
            "ready": True,
            "headline": "desk ready",
            "pillars": [
                {"name": "channels", "level": "ok", "headline": "1 channel live"},
                {"name": "immune", "level": "ok", "headline": "immune clear"},
                {"name": "risk_gate", "level": "ok", "headline": "gate OPEN"},
                {
                    "name": "data",
                    "level": "degraded",
                    "headline": "no stored market history yet",
                    "detail": "run backfill",
                },
            ],
        },
    }


def _trades_open() -> dict:
    return {
        "status": 200,
        "body": {
            "ok": True,
            "count": 1,
            "open": [
                {
                    "id": 3,
                    "symbol": "BTCUSDT",
                    "action": "BUY",
                    "entry": 60000.0,
                    "stop_loss": 59000.0,
                    "take_profit": 62000.0,
                    "current_price": 60500.0,
                    "current_r": 0.5,
                    "plan_type": "Sweep Reversal",
                }
            ],
            "recent": [],
            "overall": {},
        },
    }


def _loop_busy() -> dict:
    return {
        "status": 200,
        "body": {
            "ready": False,
            "gate": {"open": True, "blocked_by": [], "flags": []},
            "advice": {"action": "WAIT", "headline": "No A+ setup — stand by"},
            "loop": {
                "real_paper_n": 7,
                "wins": 3,
                "losses": 4,
                "expectancy_net": 0.12,
                "win_rate": 0.43,
                "profit_factor": 1.3,
                "compliance": 0.95,
                "eligible": 7,
                "missing_journals": 0,
                "pending_reviews": 2,
                "open_exposure": 1,
            },
            "graduation": {
                "ready": False,
                "samples_proven": False,
                "criteria": [
                    {"name": "expectancy", "bar": 0.5, "current": 0.12, "met": False},
                    {"name": "win_rate", "bar": 0.55, "current": 0.43, "met": False},
                    {"name": "pf", "bar": 1.5, "current": 1.3, "met": False},
                    {"name": "compliance", "bar": 0.9, "current": 0.95, "met": True},
                ],
                "by_setup": [
                    {
                        "plan_type": "Sweep Reversal",
                        "primary": True,
                        "backtest_n": 120,
                        "backtest_target": 100,
                        "paper_n": 3,
                        "paper_target": 20,
                        "expectancy_net": 0.2,
                        "win_rate_net": 0.5,
                        "proven": False,
                    }
                ],
            },
        },
    }


def _loop_fresh() -> dict:
    return {
        "status": 200,
        "body": {
            "ready": False,
            "gate": {"open": True, "blocked_by": [], "flags": []},
            "advice": {"action": "WAIT", "headline": "No setups yet — paper first"},
            "loop": {
                "real_paper_n": 0,
                "missing_journals": 0,
                "pending_reviews": 0,
                "open_exposure": 0,
            },
            "graduation": {
                "ready": False,
                "samples_proven": False,
                "criteria": [],
                "by_setup": [
                    {
                        "plan_type": "Sweep Reversal",
                        "primary": True,
                        "backtest_n": 0,
                        "backtest_target": 100,
                        "paper_n": 0,
                        "paper_target": 20,
                        "proven": False,
                    }
                ],
            },
        },
    }


def _api_full() -> dict:
    return {
        "/api/risk": _risk_open(),
        "/api/readiness": _readiness_ok(),
        "/api/trades": _trades_open(),
        "/api/loop-health": _loop_busy(),
    }


def test_home_is_the_landing_view_without_saved_preference():
    # empty localStorage + empty hash → the init IIFE lands on Home
    out = _run(_api_full(), _OUT)
    assert out["nav"] == "home"
    assert out["homeActive"] is True
    assert out["tradeActive"] is False


def test_home_paints_gate_readiness_positions_and_evidence():
    out = _run(_api_full(), "await loadHome();" + _DRAIN + _OUT)
    assert "OPEN" in out["gate"], out["gate"]
    assert out["gateCls"].endswith("ok")
    assert "desk ready" in out["data"]
    assert "no stored market history yet" in out["data"]  # data pillar line
    assert out["dataCls"].endswith("ok")
    assert "1 open" in out["pos"] and "BTCUSDT" in out["pos"]
    assert "+0.50R" in out["pos"]  # live R painted
    assert "+0.19%" in out["pnl"] and "hard limit −2.0%" in out["pnl"]  # day % + limit
    assert out["pnlCls"].endswith("ok")
    assert "1/4 criteria" in out["evidence"]  # only compliance met
    assert "n=7 real paper" in out["evidence"]
    assert "Sweep Reversal" in out["evidence"]
    assert "3/20" in out["evidence"] and "120/100" in out["evidence"]
    assert "clear" in out["journal"] and "2 pending review" in out["journal"]
    assert "WAIT" in out["focus"]
    # desk already busy → no onboarding
    assert out["onboardShown"] == "none"
    assert "/api/loop-health" in out["meta"]
    assert not out["posts"]  # read-only: zero mutations


def test_home_blocked_gate_and_journal_hold_show_the_real_reasons():
    api = {
        "/api/risk": _risk_blocked(),
        "/api/readiness": {
            "status": 200,
            "body": {
                "level": "blocked",
                "headline": "desk blocked — risk gate closed",
                "pillars": [],
            },
        },
        "/api/trades": _trades_open(),
        "/api/loop-health": [
            {
                "status": 200,
                "body": {
                    **_loop_busy()["body"],
                    "gate": {"open": False, "blocked_by": ["x"], "flags": ["angry"]},
                    "loop": {**_loop_busy()["body"]["loop"], "missing_journals": 1},
                },
            }
        ],
    }
    out = _run(api, "await loadHome();" + _DRAIN + _OUT)
    assert "BLOCKED" in out["gate"]
    assert "daily loss limit" in out["gate"]  # the real reason
    assert out["gateCls"].endswith("warn")
    assert "-2.10%" in out["pnl"]  # a losing day, net
    assert out["pnlCls"].endswith("bad")  # daily limit tripped
    assert "daily loss limit reached" in out["pnl"]
    assert "1 unjournaled" in out["journal"]
    assert "journal-first" in out["journal"]
    assert out["journalCls"].endswith("warn")
    assert "angry" in out["focus"]  # trader-state flag visible
    assert out["focusCls"].endswith("warn")


def test_home_feed_failure_paints_explicit_retry_not_blank():
    api = {
        "/api/risk": {"status": 500, "body": {"error": "boom"}},
        "/api/readiness": _readiness_ok(),
        "/api/trades": _trades_open(),
        "/api/loop-health": _loop_busy(),
    }
    out = _run(api, "await loadHome();" + _DRAIN + _OUT)
    assert "could not load" in out["gate"] and "boom" in out["gate"]
    assert "retry" in out["gate"]
    assert "could not load" in out["pnl"]  # same feed, second card
    assert "desk ready" in out["data"]  # neighbours still paint
    assert "1 open" in out["pos"]
    assert "1/4 criteria" in out["evidence"]


def test_home_onboarding_shows_for_fresh_desk_and_dismiss_persists():
    api = {
        "/api/risk": {
            "status": 200,
            "body": {
                "gate": {
                    "allowed": True,
                    "blocked_by": [],
                    "details": {
                        "daily_weekly": {
                            "today": {"n": 0, "r_sum": 0.0, "pct": 0.0},
                            "week": {"n": 0, "r_sum": 0.0, "pct": 0.0},
                            "daily_limit": 2.0,
                            "weekly_limit": 4.0,
                            "daily_blocked": False,
                            "weekly_blocked": False,
                        }
                    },
                }
            },
        },
        "/api/readiness": _readiness_ok(),
        "/api/trades": {
            "status": 200,
            "body": {"ok": True, "count": 0, "open": [], "recent": [], "overall": {}},
        },
        "/api/loop-health": _loop_fresh(),
    }
    out = _run(
        api,
        "await loadHome();"
        + _DRAIN
        + """
      dismissHomeIntro();
      await loadHome();
      """
        + _DRAIN
        + _OUT,
    )
    # onboarding appeared for the fresh desk and points at the paper loop
    assert "0 open" in out["pos"]
    # paintHome ran twice: the second pass must keep it hidden after dismiss
    assert out["hideIntro"] == "1"
    assert out["onboardShown"] == "none"


def test_home_onboarding_visible_before_dismiss():
    api = {
        "/api/risk": _risk_open(),
        "/api/readiness": _readiness_ok(),
        "/api/trades": {
            "status": 200,
            "body": {"ok": True, "count": 0, "open": [], "recent": [], "overall": {}},
        },
        "/api/loop-health": _loop_fresh(),
    }
    out = _run(api, "await loadHome();" + _DRAIN + _OUT)
    assert out["onboardShown"] == "block"
    assert "paper loop" in out["onboard"]
    assert "no real exchange order" in out["onboard"]
    assert "Open Trading Terminal" in out["onboard"]
    assert "journal" in out["onboard"]  # loop ends in the journal


def test_open_trading_terminal_navigates_and_continue_labels_the_market():
    api = _api_full()
    out = _run(
        api,
        """
      localStorage.setItem('sky.symbol', 'ETHUSDT');
      localStorage.setItem('sky.timeframe', '1h');
      await loadHome();
      """
        + _DRAIN
        + """
      _termLoaded = true;      // terminal already initialised on this page
      openTradingTerminal();
      """
        + _OUT,
    )
    assert out["cont"] == "Continue ETHUSDT · 1h"  # remembered market
    assert out["nav"] == "trade"
    assert out["tradeActive"] is True
    assert out["homeActive"] is False


def test_home_markup_is_served_in_the_page():
    # python-side guard: the Home view, its nav button and the primary CTA
    # are part of the served template (JS validity is covered by
    # test_served_script_is_valid_javascript in test_dashboard_js.py).
    txt = (ROOT / "web" / "static" / "terminal.html").read_text(encoding="utf-8")
    assert 'id="view-home"' in txt
    assert 'data-nav="home"' in txt
    assert "Open Trading Terminal" in txt
    assert 'id="homeOnboard"' in txt
    for card in (
        "homeBodyGate",
        "homeBodyData",
        "homeBodyPositions",
        "homeBodyPnl",
        "homeBodyJournal",
        "homeBodyEvidence",
        "homeBodyFocus",
    ):
        assert f'id="{card}"' in txt
