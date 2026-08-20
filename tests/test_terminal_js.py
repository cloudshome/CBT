"""T3 — Trade Terminal frontend tests.

Same approach as tests/test_weekly_js.py: execute the real served dashboard
JavaScript in node against a queued, POST-capturing fetch stub and assert the
terminal actually *wires* the paper-trade loop:

  * Confirm posts the full ticket to /api/terminal/confirm and opens the
    positions tab when the server enrolls the position;
  * a server-side gate block paints the real verdict into the ticket;
  * the journal-first discipline holds the confirm until acknowledged;
  * the positions tab paints live R / MAE / MFE and a Close button;
  * Close records the outcome and opens the journal drawer, whose Save
    posts to the existing /api/journal form.

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
    html = re.search(r'HTML = r?"""(.*?)"""', APP.read_text(), re.S).group(1)
    return re.findall(r"<script>(.*?)</script>", html, re.S)[-1]


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
        addEventListener:()=>{}, setAttribute:()=>{}, querySelector:()=>null,
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
      const chart = { pane: target && target.id, height: opts && opts.height,
        series: [],
        addCandlestickSeries(){ const s={lines:[], data:null,
          setData(d){ this.data=d; this.sets=(this.sets||0)+1; },
          update(d){ this.lastUpdate=d; },
          createPriceLine(){ const pl={}; this.lines.push(pl); return pl; },
          removePriceLine(){}}; this.series.push(s); return s; },
        addLineSeries(o){ const s={kind:'line',data:null,opts:o||null,
          setData(d){ this.data = d; this.sets=(this.sets||0)+1; }, update(){}, setMarkers(){},
          createPriceLine(){return {};}, removePriceLine(){}}; this.series.push(s); return s; },
        addHistogramSeries(){ const s={kind:'hist',data:null, setData(d){ this.data=d; this.sets=(this.sets||0)+1; }};
          this.series.push(s); return s; },
        timeScale(){ if(!this._ts) this._ts = {
            range: {from:10, to:50}, fitted:0, restored:0, scrolled:0,
            fitContent(){ this.fitted++; },
            applyOptions(){},
            getVisibleLogicalRange(){ return this.range; },
            setVisibleLogicalRange(r){ this.range=r; this.restored++; },
            subscribeVisibleLogicalRangeChange(fn){ this._sub=fn; },
            scrollToRealTime(){ this.scrolled++; }
          }; return this._ts; },
        applyOptions(){}, remove(){ this.removed = true; },
        removeSeries(){} };
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


_OUT = ("console.log(JSON.stringify({posts: POSTS, toasts: TOASTS, "
        "positionsTab: (elements['btab-positions']||{}).innerHTML || '', "
        "journalTab: (elements['btab-journal']||{}).innerHTML || '', "
        "posDetail: (elements['posDetail']||{}).innerHTML || '', "
        "gate: (elements['tGate']||{}).innerHTML || '', "
        "gateCls: (elements['tGate']||{}).className || '', "
        "confirmDisabled: (elements['tConfirm']||{}).disabled, "
        "confirmText: (elements['tConfirm']||{}).textContent || '', "
        "confirmPrompt: global.__lastConfirm || null }));")


def _ticket_setup() -> str:
    return """
      _ticketPayload = { signal: { asset:'BTCUSDT', timeframe:'15m', confidence:'MEDIUM' },
        plans: [{ type:'Manual', confidence:70, condition:'IF test setup' }],
        decision: {} };
      el('tEntry').value = 60000; el('tSL').value = 59000;
      el('tTP1').value = 62000; el('tTP2').value = ''; el('tTP3').value = '';
      el('tRisk').value = '0.5';
    """


_DRAIN = "for(let i=0;i<10;i++) await new Promise(r=>setTimeout(r,0));"


def _confirm_ok() -> dict:
    return {"status": 200, "body": {
        "ok": True, "scan_id": 7, "status": "EXECUTED",
        "gate": {"allowed": True, "blocked_by": []},
        "paper_trade": {"id": 3, "scan_id": 7, "status": "OPEN",
                        "symbol": "BTCUSDT", "action": "BUY",
                        "entry": 60000.0, "entry_price": 60000.0,
                        "stop_loss": 59000.0, "take_profit": 62000.0,
                        "plan_type": "Manual"}}}


def _trades_open() -> dict:
    return {"status": 200, "body": {
        "ok": True, "count": 1,
        "open": [{"id": 3, "scan_id": 7, "status": "OPEN", "symbol": "BTCUSDT",
                  "action": "BUY", "entry": 60000.0, "entry_price": 60000.0,
                  "stop_loss": 59000.0, "take_profit": 62000.0,
                  "current_price": 60500.0, "current_r": 0.5,
                  "mae": -0.1, "mfe": 0.6, "minutes_in_trade": 10,
                  "plan_type": "Manual",
                  "management": ["HOLD — thesis intact.",
                                 "REDUCE — close ~50% at TP1 62000.00."]}]}}


def test_confirm_posts_the_ticket_and_opens_positions():
    api = {"/api/terminal/confirm": _confirm_ok(),
           "/api/trades": _trades_open()}
    out = _run(api, _ticket_setup() + """
      await submitPaperTicket();
      """ + _DRAIN + """
    """ + _OUT)
    assert len(out["posts"]) == 1, out["posts"]
    body = json.loads(out["posts"][0]["body"])
    assert body["action"] == "BUY" and body["entry"] == 60000
    assert body["stop_loss"] == 59000 and body["take_profits"] == [62000]
    assert body["ticket_id"] and body["ticket_type"] == "market"
    assert any("Paper position open" in t for t in out["toasts"])
    assert "OPEN" in out["gate"]
    assert "BTCUSDT" in out["positionsTab"] and "Close" in out["positionsTab"]
    assert "+0.50R" in out["positionsTab"]
    assert "MAE" in out["positionsTab"] and "MFE" in out["positionsTab"]


def test_confirm_server_gate_block_paints_the_real_verdict():
    api = {"/api/terminal/confirm": {"status": 409, "body": {
        "error": "Risk gate CLOSED — setup unproven (Manual): 0 backtest / 0 paper samples",
        "blocked_by": ["setup unproven (Manual): 0 backtest / 0 paper samples"],
        "force_available": False}}}
    out = _run(api, _ticket_setup() + """
      await submitPaperTicket();
      """ + _DRAIN + """
    """ + _OUT)
    assert "BLOCKED" in out["gate"] and "setup unproven" in out["gate"]
    assert any("Risk gate CLOSED" in t for t in out["toasts"])
    assert out["confirmDisabled"] is False  # re-enabled for a corrected ticket
    assert out["positionsTab"] == ""        # never navigated to positions


def test_confirm_journal_first_discipline_holds_until_acknowledged():
    api = {"/api/terminal/confirm": [
        {"status": 409, "body": {
            "error": "Journal-first discipline: 1 decided real trade(s) unjournaled",
            "journal_block": {"missing": 1,
                              "trades": [{"scan_id": 9, "outcome": "TP_HIT"}]},
            "acknowledge_available": True}},
        {"status": 200, "body": {
            "ok": True, "scan_id": 10, "status": "APPROVED",
            "gate": {"allowed": True, "blocked_by": []},
            "paper_trade": {"id": 4, "scan_id": 10, "status": "WAITING_ENTRY",
                            "entry": 1000.0}}},
    ], "/api/journal": {"status": 200, "body": {
        "journalable": [], "emotions": ["calm"], "summary": {}}}}
    # Cancel the audited escape → held, journal tab opens, exactly one POST.
    out = _run(api, _ticket_setup() + """
      global.__confirmAnswer = false;
      await submitPaperTicket();
      """ + _DRAIN + """
    """ + _OUT)
    assert len(out["posts"]) == 1
    assert "#9 TP_HIT" in (out["confirmPrompt"] or "")
    assert any("Journal first" in t for t in out["toasts"])

    # Accept the audited escape → acknowledged retry lands.
    out = _run(api, _ticket_setup() + """
      global.__confirmAnswer = true;
      await submitPaperTicket();
      """ + _DRAIN + """
    """ + _OUT)
    assert len(out["posts"]) == 2
    assert json.loads(out["posts"][1]["body"])["acknowledge_journal"] is True
    assert any("Ticket confirmed" in t for t in out["toasts"])


def test_positions_row_opens_inline_management_card():
    api = {"/api/trades": _trades_open()}
    out = _run(api, """
      await paintBottomPositions(el('btab-positions'));
      await selectBottomPosition('3');
      """ + _DRAIN + """
    """ + _OUT)
    assert "BTCUSDT" in out["positionsTab"]
    assert "Close Position" in out["posDetail"]
    assert "Management advice" in out["posDetail"]
    assert "HOLD" in out["posDetail"] and "REDUCE" in out["posDetail"]
    assert "live R" in out["posDetail"] and "+0.50R" in out["posDetail"]
    assert "Close" in out["positionsTab"]


def test_close_records_outcome_and_opens_the_journal_drawer():
    api = {
        "/api/terminal/close": {"status": 200, "body": {
            "ok": True, "trade_id": 3, "scan_id": 7, "status": "CLOSED",
            "outcome": "TP_HIT", "exit_price": 61500.0, "rr_achieved": 1.5,
            "journal_required": True}},
        "/api/trades": {"status": 200, "body": {"ok": True, "open": []}},
        "/api/journal?scan_id=": {"status": 200, "body": {
            "ok": True, "entry": None, "emotions": ["calm", "fear"]}},
        "/api/journal": [
            {"status": 200, "body": {"journalable": [], "emotions": ["calm"],
                                     "summary": {}}},
            {"status": 200, "body": {"ok": True, "scan_id": 7,
                                     "entry": {"followed_rules": 1}}}],
    }
    out = _run(api, """
      global.__confirmAnswer = true;
      await terminalClosePosition(3);
      """ + _DRAIN + """
      const drawerBefore = elements['btab-journal'].innerHTML;
      global.__drawerBefore = drawerBefore;
      await saveTerminalJournal();
    """ + _OUT.replace("confirmPrompt: global.__lastConfirm || null }",
                       "confirmPrompt: global.__lastConfirm || null, "
                       "drawerBefore: global.__drawerBefore || '' }"))
    assert any("Closed #3" in t for t in out["toasts"])
    assert "Journal this trade" in out["drawerBefore"]
    assert "TP_HIT" in out["drawerBefore"] and "+1.50R" in out["drawerBefore"]
    # the save went through the existing journal form endpoint
    saved = [p for p in out["posts"] if "/api/journal" in p["url"]]
    assert saved and json.loads(saved[0]["body"])["scan_id"] == 7
    assert json.loads(saved[0]["body"])["followed_rules"] is True
    assert any("Journal saved" in t for t in out["toasts"])


def test_confirm_retry_reuses_the_same_ticket_id():
    api = {"/api/terminal/confirm": [
        {"status": 200, "body": _confirm_ok()["body"]},
        {"status": 200, "body": dict(_confirm_ok()["body"], duplicate=True)},
    ], "/api/trades": _trades_open()}
    out = _run(api, _ticket_setup() + """
      const _origFetch = fetch; let failing = true; const sentIds = [];
      fetch = async (url, opts) => {
        if(String(url).includes('/api/terminal/confirm')){
          try{ sentIds.push(JSON.parse(opts.body).ticket_id); }catch(e){}
          if(failing){ failing = false; throw new Error('network lost'); }
        }
        return _origFetch(url, opts);
      };
      await submitPaperTicket();   // response lost — the ticket id survives
      await submitPaperTicket();   // retried confirm reuses the same id
      global.__sentIds = sentIds;
      """ + _DRAIN + """
    """ + _OUT.replace("confirmPrompt: global.__lastConfirm || null }",
                       "confirmPrompt: global.__lastConfirm || null, "
                       "sentIds: global.__sentIds || [] }"))
    assert len(out["sentIds"]) == 2, "both attempts must send a ticket id"
    assert out["sentIds"][0] == out["sentIds"][1], \
        "a retried confirm must reuse its ticket id"
    assert any("Ticket error" in t for t in out["toasts"]), out["toasts"]
    assert any("Paper position open" in t for t in out["toasts"])



_CHART_SEED = """
      el('sym').value = 'BTCUSDT'; el('tf').value = '15m';
      _chartSym = 'BTCUSDT'; _chartTf = '15m';
      _chartData = {
        symbol:'BTCUSDT', timeframe:'15m', last_price:100, change_pct:1,
        candles: Array.from({length:80}, (_,i)=>({time:i+1, open:100, high:101, low:99, close:100+i/100})),
        overlays: { ema20:[{time:1,value:100}], ema50:[], ema200:[], vwap:[{time:1,value:100}] },
        panes: { volume:[{time:1,value:1,color:'#22c55e'}], rsi:[{time:1,value:50}], macd:[{time:1,value:1}], macd_hist:[], macd_signal:[] },
        levels: [], plan: {}, stats: {rsi:50, adx:20}
      };
      drawChart({fit:true});
"""

_REFRESH_OUT = ("console.log(JSON.stringify({chartCount: CHARTS.length, "
                "removed: CHARTS.filter(c=>c.removed).length, "
                "fitted: CHARTS.reduce((n,c)=>n+((c._ts&&c._ts.fitted)||0),0), "
                "restored: CHARTS.reduce((n,c)=>n+((c._ts&&c._ts.restored)||0),0), "
                "scrolled: CHARTS.reduce((n,c)=>n+((c._ts&&c._ts.scrolled)||0),0), "
                "sets: (CHARTS[0]&&CHARTS[0].series[0]&&CHARTS[0].series[0].sets)||0, "
                "wl: (elements['wlList']||{}).innerHTML||'', "
                "entry: (elements['tEntry']||{}).value||'', "
                "updated: (elements['updated']||{}).textContent||'', "
                "feed: (elements['feedTxt']||{}).textContent||'', "
                "toasts: TOASTS, "
                "liveFollow: !!_chartLiveFollow, "
                "sym: (elements['sym']||{}).value||'', "
                "range: (CHARTS[0]&&CHARTS[0]._ts&&CHARTS[0]._ts.range)||null "
                "}));")


def test_quiet_refresh_does_not_recreate_chart_or_fit_content():
    """A 30s data refresh must update series in place, never remount or fitContent."""
    out = _run({}, _CHART_SEED + """
      const before = CHARTS.length;
      const fittedBefore = CHARTS.reduce((n,c)=>n+((c._ts&&c._ts.fitted)||0),0);
      CHARTS[0].timeScale().range = {from:5, to:20};
      _chartLiveFollow = false;
      _chartViewport = {from:5, to:20};
      _chartData.candles = _chartData.candles.concat([{time:81, open:101, high:102, low:100, close:101}]);
      drawChart({preserveViewport:true});
      global.__before = before;
      global.__fittedBefore = fittedBefore;
    """ + _DRAIN + """
    """ + _REFRESH_OUT.replace("chartCount: CHARTS.length",
                               "chartCount: CHARTS.length, before: global.__before, fittedBefore: global.__fittedBefore"))
    assert out["chartCount"] == out["before"] == out.get("before", out["chartCount"])
    assert out["removed"] == 0
    assert out["fitted"] == out.get("fittedBefore", out["fitted"]), out
    assert out["sets"] >= 2  # initial + in-place update
    assert out["range"]["from"] == 5 and out["range"]["to"] == 20


def test_historical_viewport_survives_refresh_live_follows():
    out = _run({}, _CHART_SEED + """
      CHARTS[0].timeScale().range = {from:8, to:18};
      _chartLiveFollow = false;
      _chartViewport = {from:8, to:18};
      drawChart({preserveViewport:true});
      const hist = Object.assign({}, CHARTS[0].timeScale().range);
      _chartLiveFollow = true;
      drawChart({preserveViewport:true});
      global.__hist = hist;
      global.__scrolled = CHARTS[0].timeScale().scrolled;
    """ + _DRAIN + """
    """ + "console.log(JSON.stringify({hist: global.__hist, scrolled: global.__scrolled, liveFollow: !!_chartLiveFollow, restored: CHARTS[0]._ts.restored}));")
    assert out["hist"]["from"] == 8 and out["hist"]["to"] == 18
    assert out["scrolled"] >= 1
    assert out["restored"] >= 1


def test_watchlist_refresh_never_blanks_existing_rows():
    api = {"/api/agents": {"status": 200, "body": {
        "assets": [{"symbol":"BTCUSDT","entry":60000,"change_pct_24h":1.2,
                    "desk_action":"BUY","reason":"x","confidence_pct":70}]}}}
    out = _run(api, """
      await loadWatchlistPrices();
      const first = el('wlList').innerHTML;
      const origFetch = fetch;
      let started = false;
      fetch = async (url, opts) => {
        if(String(url).includes('/api/agents')){
          started = true;
          if(el('wlList').innerHTML.indexOf('loading prices')>=0)
            global.__blanked = true;
        }
        return origFetch(url, opts);
      };
      const p = loadWatchlistPrices();
      global.__during = el('wlList').innerHTML;
      await p;
      global.__first = first;
      global.__after = el('wlList').innerHTML;
    """ + _DRAIN + """
    """ + "console.log(JSON.stringify({first: global.__first, during: global.__during, after: global.__after, blanked: !!global.__blanked}));")
    assert "BTCUSDT" in out["first"]
    assert "loading prices" not in (out["during"] or "")
    assert not out["blanked"]
    assert "BTCUSDT" in out["after"]


def test_quiet_scan_keeps_ticket_and_does_not_toast_failure():
    api = {
        "/api/scan": [
            {"status": 200, "body": {
                "signal": {"action":"BUY","asset":"BTCUSDT","timeframe":"15m",
                           "entry": 61000, "stop_loss": 60000, "take_profit": 63000,
                           "confidence":"MEDIUM","reason":"boot"},
                "plans": [{"entry":61000,"stop_loss":60000,"take_profits":[63000],"type":"Manual"}],
                "decision": {"action":"BUY"},
                "snapshot": {"features":{}, "scores":{}},
            }},
            {"status": 502, "body": {"error": "upstream down"}},
        ]
    }
    out = _run(api, """
      el('sym').value='BTCUSDT'; el('tf').value='15m';
      el('tEntry').value='111'; _ticketDirty = true;
      await load(false, true);
      const afterOk = el('tEntry').value;
      await load(false, true);
    """ + _DRAIN + """
    """ + "console.log(JSON.stringify({entry: elements['tEntry'].value, afterOk: null, updated: elements['updated'].textContent, toasts: TOASTS, payload: !!__lastPayload}));")
    # first quiet success must not overwrite a dirty ticket
    assert out["entry"] == "111"
    assert "Data stale" in (out["updated"] or "") or "stale" in (out["updated"] or "").lower()
    assert not any("Refresh failed" in t for t in out["toasts"])


def test_stale_scan_response_cannot_overwrite_newer():
    api = {"/api/scan": {"status": 200, "body": {
        "signal": {"action":"SELL","asset":"ETHUSDT","timeframe":"15m","entry":1},
        "plans": [], "decision": {}, "snapshot": {"features":{}, "scores":{}},
    }}}
    out = _run(api, """
      el('sym').value='BTCUSDT'; el('tf').value='15m';
      const orig = fetch;
      const deferred = [];
      fetch = async (url, opts) => {
        if(String(url).includes('/api/scan')){
          return await new Promise(resolve => deferred.push(resolve));
        }
        return orig(url, opts);
      };
      const p1 = load(false, true);
      const p2 = load(false, true);
      // resolve newer first, then older
      deferred[1]({ ok:true, status:200, json: async () => ({
        signal:{action:'BUY',asset:'BTCUSDT',timeframe:'15m',entry:2,reason:'new'},
        plans:[], decision:{}, snapshot:{features:{},scores:{}}
      })});
      await Promise.resolve();
      deferred[0]({ ok:true, status:200, json: async () => ({
        signal:{action:'SELL',asset:'ETHUSDT',timeframe:'15m',entry:9,reason:'old'},
        plans:[], decision:{}, snapshot:{features:{},scores:{}}
      })});
      await p1; await p2;
    """ + _DRAIN + """
    """ + "console.log(JSON.stringify({reason: (__lastPayload&&__lastPayload.signal&&__lastPayload.signal.reason)||'', action: (__lastPayload&&__lastPayload.signal&&__lastPayload.signal.action)||''}));")
    assert out["reason"] == "new"
    assert out["action"] == "BUY"


def test_symbol_survives_quiet_refresh():
    api = {"/api/scan": {"status": 200, "body": {
        "signal": {"action":"BUY","asset":"ETHUSDT","timeframe":"1h","entry":1},
        "plans": [], "decision": {}, "snapshot": {"features":{}, "scores":{}},
    }}}
    out = _run(api, """
      el('sym').value='ETHUSDT'; el('tf').value='1h';
      await load(false, true);
    """ + _DRAIN + """
    """ + "console.log(JSON.stringify({sym: elements['sym'].value, tf: elements['tf'].value, live: (elements['updated']||{}).textContent||''}));")
    assert out["sym"] == "ETHUSDT"
    assert out["tf"] == "1h"
    assert "Data live" in out["live"]


def test_thirty_second_refresh_updates_data_only():
    """The auto-refresh callback is load(false, true). It must not remount
    the chart, jump the viewport, blank the watchlist, or clobber a dirty ticket."""
    api = {
        "/api/scan": {"status": 200, "body": {
            "signal": {"action": "BUY", "asset": "BTCUSDT", "timeframe": "15m",
                       "entry": 77777, "stop_loss": 70000, "take_profit": 80000,
                       "confidence": "MEDIUM", "reason": "tick"},
            "plans": [{"entry": 77777, "stop_loss": 70000, "take_profits": [80000],
                       "type": "Manual"}],
            "decision": {"action": "BUY"},
            "snapshot": {"features": {}, "scores": {}},
        }},
        "/api/agents": {"status": 200, "body": {
            "assets": [{"symbol": "BTCUSDT", "entry": 60000, "change_pct_24h": 1.2,
                        "desk_action": "BUY", "reason": "x", "confidence_pct": 70}]}},
    }
    out = _run(api, _CHART_SEED + """
      await loadWatchlistPrices();
      el('tEntry').value = '111'; _ticketDirty = true;
      CHARTS[0].timeScale().range = {from:12, to:30};
      _chartLiveFollow = false; _chartViewport = {from:12, to:30};
      const n0 = CHARTS.length;
      const fitted0 = CHARTS.reduce((n,c)=>n+((c._ts&&c._ts.fitted)||0),0);
      const wl0 = el('wlList').innerHTML;
      await load(false, true);   // 30s auto-refresh tick
      global.__out = {
        n0, n1: CHARTS.length, removed: CHARTS.filter(c=>c.removed).length,
        fitted0, fitted1: CHARTS.reduce((n,c)=>n+((c._ts&&c._ts.fitted)||0),0),
        range: CHARTS[0].timeScale().range,
        entry: el('tEntry').value, wl0, wl1: el('wlList').innerHTML,
        updated: el('updated').textContent, toasts: TOASTS,
        live: (window._skyPayload&&window._skyPayload.signal&&window._skyPayload.signal.reason)||''
      };
    """ + _DRAIN + """
    """ + "console.log(JSON.stringify(global.__out));")
    assert out["n1"] == out["n0"]
    assert out["removed"] == 0
    assert out["fitted1"] == out["fitted0"]
    assert out["range"]["from"] == 12 and out["range"]["to"] == 30
    assert out["entry"] == "111"
    assert "BTCUSDT" in out["wl0"] and "BTCUSDT" in out["wl1"]
    assert "loading prices" not in out["wl1"]
    assert out["live"] == "tick"
    assert "Data live" in out["updated"]
    assert not any("Refresh failed" in t for t in out["toasts"])
