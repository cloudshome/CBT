"""Front-end tests for the Trading Workstation panels.

The dashboard's value is that every function is a *clickable* control. These
tests execute the real dashboard JavaScript against stubbed API responses and
assert that each workstation panel actually paints the numbers a trader needs:

  * the chart workspace feeds candles, overlays, panes and price lines into
    the charting engine (the stub used to silently draw nothing);
  * the trade manager shows live R, MAE/MFE and management instructions;
  * the risk center explains *why* a closed gate is closed;
  * the position sizer renders units, money at risk and the verdict;
  * the command center lists every action with a Run button;
  * the module catalog lists the engine's modules.

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


def _run(api: dict, body: str) -> dict:
    """Execute the dashboard JS with a stubbed fetch and a fake DOM.

    ``api`` maps a URL fragment to the JSON the stubbed fetch returns.
    ``body`` is the JS to run after the dashboard script has loaded.
    """
    harness = f"""
    const API = {json.dumps(api)};
    const elements = {{}};
    function mkEl(id){{
      return {{ id, innerHTML:'', className:'', textContent:'', value:'',
        checked:true, disabled:false, clientWidth:900, style:{{}},
        options:[], appendChild(){{}}, scrollIntoView(){{}},
        addEventListener:()=>{{}}, querySelector:()=>null,
        querySelectorAll:()=>[], classList:{{ toggle(){{}}, add(){{}}, remove(){{}} }} }};
    }}
    function el(id){{ if(!elements[id]) elements[id]=mkEl(id); return elements[id]; }}
    const CHARTS = [];
    function mkSeries(kind, chart){{
      const s = {{ kind, lines: [], data: [],
        setData(d){{ this.data = d || []; }}, setMarkers(){{}},
        createPriceLine(o){{ this.lines.push(o && o.title); }},
        priceScale(){{ return {{ applyOptions(){{}} }}; }}, applyOptions(){{}} }};
      chart.series.push(s); return s;
    }}
    global.LightweightCharts = {{ createChart: (target, opts) => {{
      const chart = {{ pane: target && target.id, height: opts && opts.height, series: [],
        addCandlestickSeries(){{ return mkSeries('candle', this); }},
        addLineSeries(){{ return mkSeries('line', this); }},
        addHistogramSeries(){{ return mkSeries('hist', this); }},
        timeScale(){{ return {{ fitContent(){{}}, applyOptions(){{}},
          subscribeVisibleLogicalRangeChange(){{}}, setVisibleLogicalRange(){{}} }}; }},
        applyOptions(){{}}, remove(){{}} }};
      CHARTS.push(chart); return chart;
    }} }};
    global.window = {{ addEventListener: ()=>{{}}, LightweightCharts: global.LightweightCharts }};
    global.document = {{ getElementById: el, addEventListener: ()=>{{}},
      querySelectorAll: ()=>[], createElement: ()=>mkEl('tmp') }};
    global.localStorage = {{ getItem: ()=>null, setItem: ()=>{{}} }};
    global.history = {{ replaceState: ()=>{{}} }};
    global.location = {{ hash: '' }};
    global.fetch = async (url) => {{
      // longest match wins so '/api/commands/run' never resolves to '/api/commands'
      const key = Object.keys(API)
        .filter(k => String(url).includes(k))
        .sort((a, b) => b.length - a.length)[0];
      return {{ json: async () => key ? API[key] : {{}} }};
    }};
    global.AbortController = class {{ constructor(){{ this.signal={{}}; }} abort(){{}} }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = (fn) => {{ if(typeof fn === 'function') fn(); return 0; }};
    global.clearTimeout = () => {{}};

    {_extract_js()}

    (async () => {{
      try {{ {body} }}
      catch (e) {{ console.error('HARNESS ERROR: ' + (e && e.stack || e)); process.exit(1); }}
    }})();
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True, timeout=90)
        assert r.returncode == 0, f"harness failed:\n{r.stdout}\n{r.stderr}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


def _chart_payload() -> dict:
    times = [1_780_000_000 + i * 900 for i in range(60)]
    return {
        "symbol": "BTCUSDT", "timeframe": "15m", "count": len(times),
        "last_price": 63500.0, "change_pct": 0.42,
        "candles": [{"time": t, "open": 63000.0 + i, "high": 63100.0 + i,
                     "low": 62900.0 + i, "close": 63050.0 + i}
                    for i, t in enumerate(times)],
        "overlays": {
            "ema20": [{"time": t, "value": 63000.0} for t in times],
            "ema50": [{"time": t, "value": 62900.0} for t in times],
            "ema200": [{"time": t, "value": 62800.0} for t in times],
            "vwap": [{"time": t, "value": 63020.0} for t in times],
            "bb_upper": [{"time": t, "value": 63400.0} for t in times],
            "bb_lower": [{"time": t, "value": 62600.0} for t in times],
        },
        "panes": {
            "volume": [{"time": t, "value": 120.0, "color": "#22c55e"} for t in times],
            "rsi": [{"time": t, "value": 55.0} for t in times],
            "macd": [{"time": t, "value": 1.0} for t in times],
            "macd_signal": [{"time": t, "value": 0.8} for t in times],
            "macd_hist": [{"time": t, "value": 0.2} for t in times],
            "adx": [{"time": t, "value": 24.0} for t in times],
        },
        "levels": [{"price": 62000.0, "kind": "support", "label": "Support",
                    "color": "#22c55e"},
                   {"price": 64000.0, "kind": "resistance", "label": "Resistance",
                    "color": "#ef4444"}],
        "plan": {"action": "BUY", "entry": 63000.0, "stop_loss": 62700.0,
                 "take_profit": 63900.0, "risk_reward": 3.0, "setup": "Buy Pullback"},
        "stats": {"rsi": 55.0, "adx": 24.0, "atr": 120.0, "atr_pct": 0.19,
                  "vwap": 63020.0, "ema20": 63000.0, "ema200": 62800.0,
                  "macd": 1.0, "macd_signal": 0.8, "volume": 120.0,
                  "volume_ratio": 1.2, "range_high": 64100.0, "range_low": 62900.0},
    }


def test_chart_workspace_feeds_the_chart_engine():
    """Candles, overlays, panes and entry/stop/target lines all reach the chart."""
    out = _run({"/api/chart": _chart_payload()}, """
      ['ovEma','ovVwap','ovBb','ovLevels','ovPlan','ovRsi','ovMacd']
        .forEach(id => { el(id).checked = true; });
      await loadChartWorkspace(true);
      console.log(JSON.stringify({
        panes: CHARTS.map(c => ({ pane: c.pane,
          series: c.series.map(s => ({ kind: s.kind, points: s.data.length, lines: s.lines })) })),
        head: elements['chartHead'].innerHTML,
        stats: elements['chartStats'].innerHTML,
        levels: elements['chartLevels'].innerHTML,
      }));
    """)
    panes = {p["pane"]: p for p in out["panes"]}
    assert "chartMain" in panes, "price pane was never created"
    main = panes["chartMain"]["series"]
    candle = next(s for s in main if s["kind"] == "candle")
    assert candle["points"] == 60, "candles never reached the chart"
    # every overlay drew a line series
    assert sum(1 for s in main if s["kind"] == "line") >= 6
    # the plan and the key levels became horizontal price lines
    assert {"ENTRY", "STOP", "TARGET"} <= set(candle["lines"])
    assert "Support" in candle["lines"] and "Resistance" in candle["lines"]
    # volume + RSI + MACD panes exist and hold data
    for pane in ("chartVol", "chartRsi", "chartMacd"):
        assert pane in panes, f"{pane} missing"
        assert any(s["points"] for s in panes[pane]["series"]), f"{pane} has no data"
    assert "63,500" in out["head"] and "RSI" in out["head"]
    assert "Buy Pullback" in out["stats"]
    assert "Support" in out["levels"]


def test_chart_toggles_hide_panes():
    """Unchecking RSI/MACD removes those panes — the toggles really work."""
    out = _run({"/api/chart": _chart_payload()}, """
      ['ovEma','ovVwap','ovLevels','ovPlan'].forEach(id => { el(id).checked = true; });
      ['ovBb','ovRsi','ovMacd'].forEach(id => { el(id).checked = false; });
      await loadChartWorkspace(true);
      console.log(JSON.stringify({ panes: CHARTS.map(c => c.pane),
        rsiDisplay: elements['chartRsi'].style.display,
        macdDisplay: elements['chartMacd'].style.display }));
    """)
    assert "chartRsi" not in out["panes"] and "chartMacd" not in out["panes"]
    assert out["rsiDisplay"] == "none" and out["macdDisplay"] == "none"


def test_chart_reports_an_unavailable_feed():
    out = _run({"/api/chart": {"error": "ConnectionError: binance unreachable",
                               "candles": []}}, """
      await loadChartWorkspace(true);
      console.log(JSON.stringify({ head: elements['chartHead'].innerHTML }));
    """)
    assert "unreachable" in out["head"]


def test_trade_manager_shows_live_r_and_management():
    out = _run({"/api/trades": {
        "ok": True, "count": 1, "open": [{
            "scan_id": 42, "symbol": "BTCUSDT", "timeframe": "15m",
            "action": "BUY", "plan_type": "Buy Pullback", "status": "OPEN",
            "entry_price": 63000.0, "current_price": 63450.0,
            "stop_loss": 62700.0, "take_profit": 63900.0,
            "current_r": 1.5, "mae": -0.3, "mfe": 1.7,
            "minutes_in_trade": 95,
            "management": ["HOLD — thesis intact", "REDUCE — 50% at TP1"],
        }],
        "recent": [{"scan_id": 41, "symbol": "BTCUSDT", "plan_type": "Sweep",
                    "outcome": "TP_HIT", "rr_achieved": 2.0,
                    "close_reason": "target hit"}],
        "overall": {}}}, """
      await loadTradeManager();
      console.log(JSON.stringify({ count: elements['tmCount'].textContent,
        table: elements['tradeManager'].innerHTML,
        recent: elements['tmRecent'].innerHTML }));
    """)
    assert out["count"] == 1
    table = out["table"]
    assert "#42" in table and "Buy Pullback" in table
    assert "+1.50R" in table, "current R is not displayed"
    assert "1h 35m" in table, "time in trade is not humanised"
    assert "-0.30" in table and "1.70" in table          # MAE / MFE
    assert "HOLD — thesis intact" in table
    for action in ("Detail", "Journal", "Close"):
        assert action in table, f"{action} button missing"
    assert "TP_HIT" in out["recent"]


def test_trade_manager_explains_an_empty_book():
    out = _run({"/api/trades": {"ok": True, "count": 0, "open": [],
                                "recent": [], "overall": {}}}, """
      await loadTradeManager();
      console.log(JSON.stringify({ html: elements['tradeManager'].innerHTML }));
    """)
    assert "no open positions" in out["html"]


def _risk_payload(allowed: bool) -> dict:
    return {"gate": {
        "allowed": allowed,
        "blocked_by": [] if allowed else ["trader state: tired — no trading while these flags are set"],
        "details": {
            "progression": {"level": "student", "label": "Learn: structure + risk"},
            "effective_risk": {"risk_pct": 0.25, "daily": 1.0, "weekly": 2.0},
            "daily_weekly": {"today": {"pct": -0.4, "trades": 2},
                             "week": {"pct": -0.9, "trades": 5}},
            "drawdown": {"max_drawdown_pct": 1.8, "level": "normal"},
            "kelly": {"clamped_size": 0.4, "max_risk_pct": 0.5, "win_rate": 0.52},
        }},
        "trader_state": {"angry": False, "tired": not allowed,
                         "revenge": False, "chasing": False},
        "journal": {"n": 10, "violation_rate": 0.1},
        "monte": {"rows": [{"risk_pct": 1.0, "expected_drawdown_pct": 12.4,
                            "ruin_prob": 0.02, "worst_losing_streak": 7,
                            "time_to_recover": 21}]}}


def test_risk_center_explains_a_closed_gate():
    out = _run({"/api/risk": _risk_payload(False)}, """
      await loadRiskCenter();
      console.log(JSON.stringify({ gate: elements['riskCenterGate'].innerHTML,
        state: elements['traderStateNow'].innerHTML,
        monte: elements['riskMonte'].innerHTML }));
    """)
    assert "GATE CLOSED" in out["gate"]
    assert "Why you cannot trade right now" in out["gate"]
    assert "tired" in out["gate"]
    assert "student" in out["gate"] and "0.25%/trade" in out["gate"]
    assert "Active flags" in out["state"] and "tired" in out["state"]
    assert "12.4%" in out["monte"] and "2.0%" in out["monte"]


def test_risk_center_shows_an_open_gate():
    out = _run({"/api/risk": _risk_payload(True)}, """
      await loadRiskCenter();
      console.log(JSON.stringify({ gate: elements['riskCenterGate'].innerHTML,
        state: elements['traderStateNow'].innerHTML }));
    """)
    assert "GATE OPEN" in out["gate"]
    assert "Why you cannot trade" not in out["gate"]
    assert "No behavioral flags" in out["state"]


def test_position_sizer_renders_the_numbers():
    out = _run({"/api/position-size": {
        "ok": True, "recommended_units": 0.0833, "risk_amount": 25.0,
        "notional": 5250.0, "risk_reward": 3.0, "risk_pct_applied": 0.25,
        "progression": "student", "ladder_cap_pct": 0.25,
        "stop_distance": 300.0, "stop_pct": 0.48, "leverage": 1,
        "margin_required": 5250.0, "losses_to_daily_limit": 4,
        "losses_to_weekly_limit": 8, "gate_open": True,
        "verdict": "Risking 0.25% (25.00) on a 0.48% stop",
        "warnings": ["risk reduced from 1% to 0.25%"]}}, """
      await calcPositionSize();
      console.log(JSON.stringify({ html: elements['psResult'].innerHTML }));
    """)
    html = out["html"]
    assert "Units to buy" in html and "Money at risk" in html
    assert "1:3" in html
    assert "4 in a row" in html and "8 in a row" in html
    assert "risk reduced" in html


def test_position_sizer_surfaces_an_error():
    out = _run({"/api/position-size": {
        "ok": False, "error": "Entry and stop-loss are both required."}}, """
      await calcPositionSize();
      console.log(JSON.stringify({ html: elements['psResult'].innerHTML }));
    """)
    assert "required" in out["html"]


def test_command_center_renders_runnable_actions():
    out = _run({"/api/commands": {"count": 2, "categories": [
        {"category": "Scan", "commands": [
            {"id": "scan", "title": "Scan", "category": "Scan", "safety": "write",
             "what": "One full signal scan.", "cli": "python main.py scan",
             "related": ["intelligence"], "inputs": [
                 {"name": "symbol", "label": "Asset", "type": "text",
                  "default": "BTCUSDT", "placeholder": "BTCUSDT"},
                 {"name": "json", "label": "Raw JSON", "type": "bool", "default": False}]}]},
        {"category": "Integration", "commands": [
            {"id": "mcp", "title": "MCP server", "category": "Integration",
             "safety": "blocked", "what": "Long-lived MCP server.",
             "cli": "python main.py mcp", "related": [],
             "note": "run in a terminal: python main.py mcp", "inputs": []}]}]}}, """
      await loadCommands();
      console.log(JSON.stringify({ count: elements['cmdCount'].textContent,
        list: elements['commandList'].innerHTML }));
    """)
    html = out["list"]
    assert out["count"] == "2 actions"
    assert "One full signal scan." in html, "the explanation is not shown"
    assert "python main.py scan" in html, "the CLI equivalent is not shown"
    assert "runCommand('scan')" in html, "no Run button for a runnable action"
    assert "in_scan_symbol" in html, "declared inputs are not rendered"
    # a blocked command shows the terminal instruction instead of a Run button
    assert "runCommand('mcp')" not in html
    assert "run in a terminal" in html


def test_command_center_runs_an_action_and_shows_output():
    out = _run({"/api/commands": {"count": 1, "categories": [
                    {"category": "Risk", "commands": [
                        {"id": "risk", "title": "Risk gate", "category": "Risk",
                         "safety": "read", "what": "Gate status.",
                         "cli": "python main.py risk", "related": [], "inputs": []}]}]},
                "/api/commands/run": {"ok": True, "exit_code": 0,
                                      "cli": "python main.py risk",
                                      "elapsed_ms": 320,
                                      "output": "RISK & DISCIPLINE GATE\\n  GATE: OPEN"}}, """
      await loadCommands();
      await runCommand('risk');
      console.log(JSON.stringify({ out: elements['cmdOut'].textContent,
        state: elements['cmdRunning'].innerHTML }));
    """)
    assert "GATE: OPEN" in out["out"], "command output is not displayed"
    assert "finished" in out["state"]


def test_module_catalog_lists_modules():
    out = _run({"/api/modules": {"count": 2, "packages": [
        {"package": "engine", "label": "Signal engine", "count": 2, "modules": [
            {"name": "engine/signal_engine.py", "module": "engine.signal_engine",
             "summary": "turns a candle frame into a signal", "lines": 300},
            {"name": "engine/rules.py", "module": "engine.rules",
             "summary": "the scoring rules", "lines": 120}]}]}}, """
      await loadModules();
      console.log(JSON.stringify({ count: elements['modCount'].textContent,
        list: elements['moduleList'].innerHTML }));
    """)
    assert out["count"] == "2 modules"
    assert "engine/signal_engine.py" in out["list"]
    assert "turns a candle frame into a signal" in out["list"]


def test_journal_form_loads_and_prefills():
    out = _run({"/api/journal?scan_id": {
                    "ok": True, "scan_id": 7,
                    "entry": {"followed_rules": 1, "emotion": "calm",
                              "mistake": "none", "notes": "clean execution",
                              "would_change": "size smaller"},
                    "quality": {"recorded": True, "quality": "A+",
                                "verdict": "Excellent trade"},
                    "checklist": {"asset": "BTCUSDT", "timeframe": "15m",
                                  "setup": "Buy Pullback", "regime": "TRENDING",
                                  "htf_bias": "bullish", "entry": 63000.0,
                                  "stop_loss": 62700.0, "take_profit": 63900.0,
                                  "planned_rr": 3.0, "news_environment": "normal"},
                    "emotions": ["calm", "anxious"], "summary": {"n": 3}},
                "/api/journal": {"ok": True, "emotions": ["calm", "anxious"],
                                 "journalable": [{"id": 7, "symbol": "BTCUSDT",
                                                  "action": "BUY", "status": "CLOSED"}],
                                 "summary": {"n": 3, "violations": 0,
                                             "violation_rate": 0.0}}}, """
      await loadJournalCenter();
      el('jScan').value = '7';
      await loadJournalEntry();
      console.log(JSON.stringify({ checklist: elements['jChecklist'].innerHTML,
        summary: elements['jSummary'].innerHTML,
        emotion: elements['jEmotion'].value,
        notes: elements['jNotes'].value }));
    """)
    assert "Buy Pullback" in out["checklist"]
    assert "TRENDING" in out["checklist"]
    assert "Excellent trade" in out["checklist"], "execution grade not shown"
    assert "Journalled trades" in out["summary"]
    assert out["emotion"] == "calm"
    assert out["notes"] == "clean execution"


def test_journal_form_saves():
    out = _run({"/api/journal": {"ok": True, "scan_id": 7,
                                 "entry": {"emotion": "calm"},
                                 "quality": {"recorded": True,
                                             "verdict": "Excellent trade"},
                                 "emotions": ["calm"], "journalable": [],
                                 "summary": {"n": 1}}}, """
      el('jScan').value = '7';
      el('jFollowed').value = '1';
      el('jEmotion').value = 'calm';
      await saveJournal();
      console.log(JSON.stringify({ status: elements['jStatus'].innerHTML }));
    """)
    assert "saved" in out["status"]


def test_journal_form_requires_a_trade():
    out = _run({}, """
      el('jScan').value = '';
      await saveJournal();
      console.log(JSON.stringify({ status: elements['jStatus'].innerHTML }));
    """)
    assert "pick a trade" in out["status"]


# ── P18.2: the /api/v1 contract card ──────────────────────────────────────
def _v1_version_env(**caps) -> dict:
    capabilities = {"live_exchange_execution": False, "paper_trading": True,
                    "human_approval": True, "idempotent_mutations": True,
                    "device_tokens": True}
    capabilities.update(caps)
    return {"ok": True, "error": None,
            "meta": {"api_version": 1, "server_version": "2.30.0",
                     "request_id": "abc", "ts": 1},
            "data": {"api_version": 1, "server_version": "2.30.0",
                     "min_client_version": 1, "max_client_version": 1,
                     "client_version_header": "X-SKY-Client-Version",
                     "idempotency_header": "Idempotency-Key",
                     "capabilities": capabilities}}


def test_api_contract_card_paints_the_version_range():
    out = _run({"/api/v1/version": _v1_version_env()}, """
      await loadApiV1(false);
      console.log(JSON.stringify({ html: elements['apiv1'].innerHTML }));
    """)
    html = out["html"]
    assert "api v1" in html
    assert "clients v1–v1" in html
    assert "X-SKY-Client-Version" in html


def test_api_contract_card_shows_no_live_execution_honestly():
    """The card must not imply the desk can trade. A ✓ here would be a lie
    the packaging phases would then build a Trade button on."""
    out = _run({"/api/v1/version": _v1_version_env()}, """
      await loadApiV1(false);
      console.log(JSON.stringify({ html: elements['apiv1'].innerHTML }));
    """)
    html = out["html"]
    assert "✗ live exchange execution" in html
    assert "✓ paper trading" in html
    assert "✓ idempotent mutations" in html


def test_api_contract_card_lists_the_route_catalog():
    routes = {"ok": True, "error": None,
              "meta": {"api_version": 1, "server_version": "2.30.0",
                       "request_id": "r", "ts": 1},
              "data": {"count": 2, "routes": [
                  {"path": "/api/v1/risk", "method": "GET", "role": "viewer",
                   "idempotent": False, "native": False, "legacy": "/api/risk",
                   "summary": "Risk & discipline gate status."},
                  {"path": "/api/v1/review", "method": "POST", "role": "operator",
                   "idempotent": True, "native": False, "legacy": "/api/review",
                   "summary": "Approve / reject / execute / close a signal."}]}}
    out = _run({"/api/v1/routes": routes}, """
      await loadApiV1Routes();
      console.log(JSON.stringify({ html: elements['apiv1routes'].innerHTML }));
    """)
    html = out["html"]
    assert "/api/v1/review" in html
    assert "operator" in html
    assert "✓ key" in html          # the retry-safe marker
    assert "2 routes" in html


def test_api_contract_card_reports_an_error_without_blanking():
    out = _run({"/api/v1/version": {
        "ok": False, "data": None,
        "error": {"code": "INTERNAL", "message": "boom", "details": {}},
        "meta": {"api_version": 1, "server_version": "x", "request_id": "r", "ts": 1}}},
        """
      await loadApiV1(false);
      console.log(JSON.stringify({ html: elements['apiv1'].innerHTML }));
    """)
    assert "boom" in out["html"]


# ── W1: guided evidence build ─────────────────────────────────────────────
def test_guided_evidence_build_submits_selected_series_inline():
    out = _run({}, """
      let submitted=null, streamUrl='';
      global.EventSource=class { constructor(url){ streamUrl=url; }
        addEventListener(){} close(){} };
      global.fetch=async (url, opts)=>{
        submitted=JSON.parse(opts.body);
        return {json:async()=>({ok:true,data:{duplicate:false,job:{
          job_id:'ev123',kind:'evidence',title:'Build my evidence',status:'queued',
          step_index:0,step_total:4,phase:'queued',log_tail:''}}})};
      };
      el('evSymbol').value='ETHUSDT'; el('evTf').value='1h';
      el('evMarket').value='spot'; el('evSince').value='90d';
      el('evBars').value='900'; el('evRounds').value='7';
      await buildEvidence();
      console.log(JSON.stringify({submitted,streamUrl,display:elements['evJob'].style.display,
        state:elements['evJobState'].textContent}));
    """)
    assert out["submitted"] == {"kind": "evidence", "params": {
        "symbol": "ETHUSDT", "tf": "1h", "market": "spot", "since": "90d",
        "bars": 900, "rounds": 7}}
    assert out["streamUrl"].endswith("/ev123/events")
    assert out["display"] == "block"
    assert "queued" in out["state"]


def test_evidence_guidance_says_no_edge_plainly():
    out = _run({}, """
      renderEvidenceGuidance({result:'no_edge',headline:'No positive net edge measured.',
        projection_state:'complete',projected_rounds:0,backtest_gap:0,paper_gap:0,
        caveat:'Not a promise.'});
      console.log(JSON.stringify({html:elements['evProjection'].innerHTML}));
    """)
    assert "No positive net edge measured" in out["html"]
    assert "Sample-count gap: complete" in out["html"]
    assert "Not a promise" in out["html"]
