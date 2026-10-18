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
    html = (ROOT / "web" / "static" / "terminal.html").read_text(encoding="utf-8")
    return re.findall(r"<script>(.*?)</script>", html, re.DOTALL)[-1]


def _run(api: dict, body: str) -> dict:
    """Execute the dashboard JS with a stubbed fetch and a fake DOM.

    ``api`` maps a URL fragment to the JSON the stubbed fetch returns.
    ``body`` is the JS to run after the dashboard script has loaded.
    """
    harness = f"""
    const API = {json.dumps(api)};
    const elements = {{}};
    function mkEl(id){{
      const cls = new Set();
      return {{ id, innerHTML:'', className:'', textContent:'', value:'',
        checked:true, disabled:false, clientWidth:900, style:{{}},
        options:[], appendChild(){{}}, scrollIntoView(){{}}, classes: cls,
        addEventListener:()=>{{}}, setAttribute:()=>{{}}, querySelector:()=>null,
        querySelectorAll:()=>[],
        classList:{{
          toggle(c, on){{ const want = (on === undefined) ? !cls.has(c) : !!on;
            if(want) cls.add(c); else cls.delete(c); return want; }},
          add(c){{ cls.add(c); }}, remove(c){{ cls.delete(c); }},
          contains(c){{ return cls.has(c); }} }} }};
    }}
    function el(id){{ if(!elements[id]) elements[id]=mkEl(id); return elements[id]; }}
    const CHARTS = [];
    const CREATED = [];
    function mkSeries(kind, chart){{
      const s = {{ kind, lines: [], data: [], opts: null, updates: [],
        setData(d){{ this.data = d || []; }}, setMarkers(){{}},
        update(bar){{ this.updates.push(bar); }},
        createPriceLine(o){{ this.lines.push(o && o.title); }},
        // W2 drawing tools read a click's y coordinate back as a price.
        coordinateToPrice(y){{ return 64000 - Number(y); }},
        priceScale(){{ return {{ applyOptions(){{}} }}; }}, applyOptions(){{}} }};
      chart.series.push(s); return s;
    }}
    global.LightweightCharts = {{ createChart: (target, opts) => {{
      const ts = {{ fitContent(){{}}, applyOptions(){{}},
        coordinateToTime(x){{ return 1780000000 + Number(x) * 900; }},
        subscribeVisibleLogicalRangeChange(fn){{ this.lrHandler = fn; }},
        setVisibleLogicalRange(r){{ (this.lrCalls = this.lrCalls || []).push(r); }} }};
      const chart = {{ pane: target && target.id, cls: (target && target.className) || '',
        height: opts && opts.height, series: [], clickHandler: null, removed: [],
        crosshairHandler: null, crosshairCalls: [], crosshairClears: 0,
        addCandlestickSeries(){{ return mkSeries('candle', this); }},
        addLineSeries(o){{ const s = mkSeries('line', this); s.opts = o || null; return s; }},
        addHistogramSeries(){{ return mkSeries('hist', this); }},
        removeSeries(s){{ const i = this.series.indexOf(s);
          if(i >= 0){{ this.series.splice(i, 1); this.removed.push(s); }} }},
        subscribeClick(fn){{ this.clickHandler = fn; }},
        subscribeCrosshairMove(fn){{ this.crosshairHandler = fn; }},
        setCrosshairPosition(price, time, series){{ this.crosshairCalls.push({{ price, time }}); }},
        clearCrosshairPosition(){{ this.crosshairClears += 1; }},
        timeScale(){{ return ts; }},
        applyOptions(){{}}, remove(){{}} }};
      CHARTS.push(chart); return chart;
    }} }};
    global.window = {{ addEventListener: ()=>{{}}, LightweightCharts: global.LightweightCharts }};
    global.navigator = {{ onLine: true, serviceWorker: {{ ready: Promise.resolve({{ pushManager: {{ getSubscription: () => Promise.resolve(null), subscribe: () => Promise.resolve({{ toJSON: () => ({{}}) }}) }} }}), register: () => Promise.resolve({{ addEventListener: () => {{}} }}), addEventListener: () => {{}} }} }};
    global.window.navigator = global.navigator;
    global.document = {{ getElementById: el, addEventListener: ()=>{{}},
      querySelectorAll: ()=>[],
      createElement: (tag)=>{{ const e = mkEl(tag || 'tmp'); CREATED.push(e); return e; }},
      createTextNode: (t)=>({{ text: String(t) }}) }};
    global.localStorage = {{ store: {{}},
      getItem(k){{ return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null; }},
      setItem(k, v){{ this.store[k] = String(v); }},
      removeItem(k){{ delete this.store[k]; }} }};
    const STORE = global.localStorage.store;
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
    // SSE stub: tests open a stream, then push frames into it by hand.
    const STREAMS = [];
    global.EventSource = class {{
      constructor(url){{ this.url = url; this.handlers = {{}}; this.closed = false;
        STREAMS.push(this); }}
      addEventListener(name, fn){{ this.handlers[name] = fn; }}
      close(){{ this.closed = true; }}
      emit(name, data){{ const fn = this.handlers[name];
        if(fn) fn({{ data: JSON.stringify(data) }}); }}
      fail(){{ if(this.onerror) this.onerror({{}}); }}
    }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = (fn) => {{ if(typeof fn === 'function') fn(); return 0; }};
    global.clearTimeout = () => {{}};

    {_extract_js()}

    (async () => {{
      try {{ {body} }}
      catch (e) {{ console.error('HARNESS ERROR: ' + (e && e.stack || e)); process.exit(1); }}
    }})();
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run(
            [NODE, path], capture_output=True, text=True, encoding="utf-8", timeout=90
        )
        assert r.returncode == 0, f"harness failed:\n{r.stdout}\n{r.stderr}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


def _chart_payload() -> dict:
    times = [1_780_000_000 + i * 900 for i in range(60)]
    return {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "count": len(times),
        "last_price": 63500.0,
        "change_pct": 0.42,
        "candles": [
            {
                "time": t,
                "open": 63000.0 + i,
                "high": 63100.0 + i,
                "low": 62900.0 + i,
                "close": 63050.0 + i,
            }
            for i, t in enumerate(times)
        ],
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
        "levels": [
            {
                "price": 62000.0,
                "kind": "support",
                "label": "Support",
                "color": "#22c55e",
            },
            {
                "price": 64000.0,
                "kind": "resistance",
                "label": "Resistance",
                "color": "#ef4444",
            },
        ],
        "plan": {
            "action": "BUY",
            "entry": 63000.0,
            "stop_loss": 62700.0,
            "take_profit": 63900.0,
            "risk_reward": 3.0,
            "setup": "Buy Pullback",
        },
        "stats": {
            "rsi": 55.0,
            "adx": 24.0,
            "atr": 120.0,
            "atr_pct": 0.19,
            "vwap": 63020.0,
            "ema20": 63000.0,
            "ema200": 62800.0,
            "macd": 1.0,
            "macd_signal": 0.8,
            "volume": 120.0,
            "volume_ratio": 1.2,
            "range_high": 64100.0,
            "range_low": 62900.0,
        },
    }


def test_chart_workspace_feeds_the_chart_engine():
    """Candles, overlays, panes and entry/stop/target lines all reach the chart."""
    out = _run(
        {"/api/chart": _chart_payload()},
        """
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
    """,
    )
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


def test_chart_draws_zone_overlays():
    """W2 — order blocks, FVGs, liquidity, sweep and dealing range all become
    horizontal price lines on the price pane (the data used to be text-only)."""
    payload = _chart_payload()
    payload["zones"] = {
        "order_blocks": [
            {
                "side": "bullish",
                "top": 63100.0,
                "bottom": 62900.0,
                "tested": False,
                "broken": False,
                "kind": "order_block",
            },
            {
                "side": "bearish",
                "top": 64000.0,
                "bottom": 63800.0,
                "tested": True,
                "broken": False,
                "kind": "order_block",
            },
        ],
        "fvgs": [
            {
                "side": "bullish",
                "top": 63500.0,
                "bottom": 63300.0,
                "filled": False,
                "kind": "fvg",
            }
        ],
        "liquidity": [
            {"price": 64500.0, "side": "above", "kind": "liquidity"},
            {"price": 61500.0, "side": "below", "kind": "liquidity"},
        ],
        "sweep": {
            "level": 64400.0,
            "side": "buyside",
            "recovered": True,
            "kind": "sweep",
        },
        "dealing_range": {
            "top": 64200.0,
            "bottom": 61600.0,
            "zone": "premium",
            "position": 0.7,
            "kind": "dealing_range",
        },
    }
    out = _run(
        {"/api/chart": payload},
        """
      ['ovEma','ovVwap','ovBb','ovLevels','ovPlan','ovRsi','ovMacd','ovZones']
        .forEach(id => { el(id).checked = true; });
      await loadChartWorkspace(true);
      const candle = CHARTS.find(c => c.pane === 'chartMain')
        .series.find(s => s.kind === 'candle');
      console.log(JSON.stringify({ lines: candle.lines }));
    """,
    )
    lines = out["lines"]
    # order blocks (2×2) + fvg (2) + liquidity (2) + sweep (1) + range (2) = 9
    assert "OB bull top" in lines and "OB bull low" in lines
    assert "OB bear top (done)" in lines  # tested → dashed + tag
    assert "FVG bull top" in lines
    assert "Buyside liq" in lines and "Sellside liq" in lines
    assert "buyside sweep (recovered)" in lines
    assert "range high (premium)" in lines and "range low (premium)" in lines


def test_replay_mode_is_clearly_labelled_and_stoppable():
    """W2 — replay walks the loaded candles and is unmistakably labelled
    'historical playback', never confused with live or paper evidence."""
    out = _run(
        {"/api/chart": _chart_payload()},
        """
      await loadChartWorkspace(true);
      toggleReplay();
      const running = !!_replay;
      const buttonBefore = elements['replayBtn'].textContent;
      const replayHead = elements['chartHead'].innerHTML;
      // force the replay cursor to the end so the next tick finishes
      if(_replay){ _replay.idx = _replay.candles.length; replayTick(); }
      const runningAfter = !!_replay;
      console.log(JSON.stringify({ running, buttonBefore, replayHead, runningAfter }));
    """,
    )
    assert out["running"] is True, "replay did not start"
    assert "Stop" in out["buttonBefore"], "replay button did not switch to Stop"
    assert "REPLAY — historical playback, not live" in out["replayHead"]
    assert out["runningAfter"] is False, "replay did not stop at the end"


def test_chart_reload_stops_replay_before_redrawing():
    """A reload/series change cannot leave a historical timer running over the
    newly loaded chart or repaint its header as replay."""
    out = _run(
        {"/api/chart": _chart_payload()},
        """
      await loadChartWorkspace(true);
      toggleReplay();
      await loadChartWorkspace(true);
      console.log(JSON.stringify({
        running: !!_replay,
        button: elements['replayBtn'].textContent,
        head: elements['chartHead'].innerHTML,
      }));
    """,
    )
    assert out["running"] is False
    assert out["button"] == "▶ Replay"
    assert "historical playback" not in out["head"]
    assert "63,500" in out["head"]


# ── W2: live candle streaming ────────────────────────────────────────────
LIVE_HELPERS = """
      const priceSeries = () => CHARTS.filter(c => c.pane === 'chartMain').pop()
        .series.find(s => s.kind === 'candle');
      const stream = () => STREAMS[STREAMS.length - 1];
"""


def test_live_stream_updates_the_last_bar_in_place():
    """W2 — a streamed bar reaches series.update(); the chart is not redrawn."""
    out = _run(
        {"/api/chart": _chart_payload()},
        LIVE_HELPERS
        + """
      await loadChartWorkspace(true);
      const panesBefore = CHARTS.length;
      toggleLive();
      const url = stream().url, connecting = elements['liveState'].innerHTML;
      stream().emit('candle', { symbol:'BTCUSDT', tf:'15m', state:'live',
        time: 1780053100, candle: { time: 1780053100, open: 63500, high: 63700,
                                    low: 63400, close: 63650 } });
      console.log(JSON.stringify({ url, connecting,
        panesAdded: CHARTS.length - panesBefore,
        updates: priceSeries().updates,
        head: elements['chartHead'].innerHTML,
        state: elements['liveState'].innerHTML,
        button: elements['liveBtn'].textContent,
        lastCandle: _chartData.candles[_chartData.candles.length - 1] }));
    """,
    )
    assert "/api/chart/stream?symbol=BTCUSDT&tf=15m" in out["url"]
    assert "Connecting" in out["connecting"]
    assert out["panesAdded"] == 0, "a live update must not rebuild the chart"
    assert out["updates"] == [
        {"time": 1780053100, "open": 63500, "high": 63700, "low": 63400, "close": 63650}
    ]
    assert "63,650" in out["head"], "the head price did not follow the stream"
    assert "LIVE" in out["state"] and "1 update" in out["state"]
    assert "Stop live" in out["button"]
    # the loaded candle array follows the stream, so a reload/replay agrees
    assert out["lastCandle"]["close"] == 63650


def test_live_stream_labels_stale_and_broken_feeds_honestly():
    """A silent or failing feed must never look like a quiet market."""
    out = _run(
        {"/api/chart": _chart_payload()},
        LIVE_HELPERS
        + """
      await loadChartWorkspace(true);
      toggleLive();
      stream().emit('status', { symbol:'BTCUSDT', tf:'15m', state:'waiting',
                                age: 8, message:'' });
      const waiting = elements['liveState'].innerHTML;
      stream().emit('status', { symbol:'BTCUSDT', tf:'15m', state:'stale',
                                age: 240, message:'no new data for 240s' });
      const stale = elements['liveState'].innerHTML;
      stream().emit('status', { symbol:'BTCUSDT', tf:'15m', state:'error',
                                age: 300, message:'ConnectionError: unreachable' });
      const failed = elements['liveState'].innerHTML;
      stream().fail();
      console.log(JSON.stringify({ waiting, stale, failed,
        dropped: elements['liveState'].innerHTML,
        updates: priceSeries().updates.length }));
    """,
    )
    assert "LIVE" in out["waiting"] and "waiting for the next bar" in out["waiting"]
    assert "STALE" in out["stale"] and "240s" in out["stale"]
    assert "not as a quiet market" in out["stale"]
    assert "FEED ERROR" in out["failed"] and "unreachable" in out["failed"]
    assert "DISCONNECTED" in out["dropped"] and "reconnecting" in out["dropped"]
    assert out["updates"] == 0, "a status frame must never paint a bar"


def test_live_stream_ignores_frames_for_another_series_and_older_bars():
    out = _run(
        {"/api/chart": _chart_payload()},
        LIVE_HELPERS
        + """
      await loadChartWorkspace(true);
      toggleLive();
      stream().emit('candle', { symbol:'ETHUSDT', tf:'15m', state:'live',
        candle: { time: 1780053100, open: 1, high: 2, low: 0.5, close: 1.5 } });
      const wrongSeries = priceSeries().updates.length;
      stream().emit('candle', { symbol:'BTCUSDT', tf:'15m', state:'live',
        candle: { time: 1770000000, open: 1, high: 2, low: 0.5, close: 1.5 } });
      console.log(JSON.stringify({ wrongSeries, older: priceSeries().updates.length,
        lastClose: _chartData.candles[_chartData.candles.length - 1].close }));
    """,
    )
    assert out["wrongSeries"] == 0, "an ETHUSDT frame painted the BTCUSDT chart"
    assert out["older"] == 0, "an older bar rewrote history"
    assert out["lastClose"] == 63109, "the loaded candles were mutated"


def test_live_stream_follows_the_selected_series_and_yields_to_replay():
    out = _run(
        {"/api/chart": _chart_payload()},
        LIVE_HELPERS
        + """
      await loadChartWorkspace(true);
      toggleLive();
      const first = stream().url;
      chartSetTF('1h'); await new Promise(r => setImmediate(r));
      const reconnected = stream().url;
      const closedOld = STREAMS[0].closed;
      toggleReplay();                       // replay owns the pane
      console.log(JSON.stringify({ first, reconnected, closedOld,
        liveAfterReplay: !!_live, closedAll: STREAMS.every(s => s.closed),
        button: elements['liveBtn'].textContent }));
    """,
    )
    assert "tf=15m" in out["first"] and "tf=1h" in out["reconnected"]
    assert out["closedOld"] is True, "the old stream was left open"
    assert out["liveAfterReplay"] is False, "replay and live shared the pane"
    assert out["closedAll"] is True
    assert out["button"] == "◉ Live"


def test_live_toggle_stops_cleanly():
    out = _run(
        {"/api/chart": _chart_payload()},
        LIVE_HELPERS
        + """
      await loadChartWorkspace(true);
      toggleLive(); toggleLive();
      console.log(JSON.stringify({ live: !!_live, closed: stream().closed,
        state: elements['liveState'].innerHTML,
        button: elements['liveBtn'].textContent }));
    """,
    )
    assert out["live"] is False and out["closed"] is True
    assert "Live stream off" in out["state"]
    assert out["button"] == "◉ Live"


# ── W2: interactive drawing tools ────────────────────────────────────────
DRAW_SEGMENTS = """
      const drawn = () => CHARTS.filter(c => c.pane === 'chartMain').pop()
        .series.filter(s => s.kind === 'line' && s.data.length === 2)
        .map(s => ({ points: s.data, style: s.opts && s.opts.lineStyle,
                     color: s.opts && s.opts.color }));
      const click = (x, y, t) => CHARTS.filter(c => c.pane === 'chartMain').pop()
        .clickHandler({ point: { x: x, y: y }, time: t });
      const flush = () => new Promise(r => setImmediate(r));
"""


def test_trendline_is_placed_by_two_clicks_and_persisted():
    """W2 — the trader clicks two points and a real segment appears on the
    price pane, saved under this symbol + timeframe."""
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('trendline');
      const afterPick = elements['drawStatus'].innerHTML;
      click(0, 500, 1780000000);          // price 63500 at the first bar
      const midway = elements['drawStatus'].innerHTML;
      click(0, 100, 1780009000);          // price 63900, snapped to a real bar
      console.log(JSON.stringify({
        afterPick, midway,
        status: elements['drawStatus'].innerHTML,
        segments: drawn(),
        stored: JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m'] || 'null'),
        list: elements['drawList'].innerHTML,
        toolActive: [...elements['drawTrendline'].classes],
      }));
    """,
    )
    assert "click the first point" in out["afterPick"]
    assert "second point" in out["midway"], "the tool never asked for point two"
    assert len(out["segments"]) == 1, "the trendline never reached the chart"
    seg = out["segments"][0]["points"]
    assert [p["value"] for p in seg] == [63500.0, 63900.0]
    # the second click's time was snapped onto a real bar (900s grid)
    assert seg[0]["time"] == 1780000000 and (seg[1]["time"] - 1780000000) % 900 == 0
    stored = out["stored"]
    assert len(stored) == 1 and stored[0]["kind"] == "trendline"
    assert len(stored[0]["points"]) == 2
    assert "Trendline" in out["list"] and "rising" in out["list"]
    assert "saved" in out["status"]
    assert out["toolActive"] == [], "the tool stayed armed after placing"


def test_ray_runs_to_the_last_bar_and_a_box_draws_both_edges():
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('ray');
      click(0, 200, 1780009000);                       // one click completes
      const ray = drawn();
      setDrawTool('box');
      click(0, 300, 1780018000);
      click(0, 900, 1780027000);
      console.log(JSON.stringify({ ray, all: drawn(),
        stored: JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m'] || 'null'),
        list: elements['drawList'].innerHTML }));
    """,
    )
    assert len(out["ray"]) == 1
    (a, b) = out["ray"][0]["points"]
    assert a["value"] == b["value"] == 63800.0, "a horizontal ray must stay flat"
    assert b["time"] == 1780000000 + 59 * 900, "the ray must reach the last bar"
    box = [s for s in out["all"] if s["style"] == 2]
    assert len(box) == 2, "a box is drawn as its top and bottom edge"
    tops = sorted({p["value"] for s in box for p in s["points"]})
    assert tops == [63100.0, 63700.0]
    assert {s["points"][0]["time"] for s in box} == {min(s["points"][0]["time"] for s in box)}, (
        "box edges must start on one bar"
    )
    assert {s["points"][1]["time"] for s in box} == {max(s["points"][1]["time"] for s in box)}, (
        "box edges must end on one bar"
    )
    assert [d["kind"] for d in out["stored"]] == ["ray", "box"]
    assert "Horizontal ray" in out["list"] and "Box" in out["list"]


def test_drawings_survive_a_reload_and_are_scoped_per_symbol_and_timeframe():
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('ray');
      click(0, 200, 1780009000);
      await loadChartWorkspace(true);                  // reload the same series
      const afterReload = drawn().length;
      chartSetTF('1h'); await flush();                 // different timeframe
      const onOtherTf = drawn().length;
      const otherList = elements['drawList'].innerHTML;
      chartSetTF('15m'); await flush();                // back to the saved one
      console.log(JSON.stringify({ afterReload, onOtherTf, otherList,
        back: drawn().length, keys: Object.keys(STORE).filter(k => k.startsWith('sky.drawings')) }));
    """,
    )
    assert out["afterReload"] == 1, "the drawing vanished on reload"
    assert out["onOtherTf"] == 0, "a 15m drawing leaked onto the 1h chart"
    assert "No drawings on BTCUSDT 1h" in out["otherList"]
    assert out["back"] == 1, "the drawing did not come back with its series"
    assert out["keys"] == ["sky.drawings.v1.BTCUSDT.15m"]


def test_undo_and_clear_remove_drawings_from_storage():
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('ray'); click(0, 200, 1780009000);
      setDrawTool('ray'); click(0, 400, 1780018000);
      const two = drawn().length;
      undoDrawing();
      const afterUndo = { n: drawn().length,
        stored: JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m']).length };
      clearDrawings();
      console.log(JSON.stringify({ two, afterUndo,
        afterClear: drawn().length,
        stored: JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m']),
        status: elements['drawStatus'].innerHTML,
        list: elements['drawList'].innerHTML }));
    """,
    )
    assert out["two"] == 2
    assert out["afterUndo"] == {"n": 1, "stored": 1}
    assert out["afterClear"] == 0 and out["stored"] == []
    assert "Cleared 1 drawing" in out["status"]
    assert "No drawings" in out["list"]


def test_a_single_drawing_can_be_removed_from_the_list():
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('ray'); click(0, 200, 1780009000);
      setDrawTool('ray'); click(0, 400, 1780018000);
      const first = JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m'])[0].id;
      removeDrawing(first);
      const left = JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m']);
      console.log(JSON.stringify({ n: drawn().length, kept: left.length,
        keptPrice: left[0].points[0].price, status: elements['drawStatus'].innerHTML }));
    """,
    )
    assert out["n"] == 1 and out["kept"] == 1
    assert out["keptPrice"] == 63600.0, "the wrong drawing was removed"
    assert "1 left" in out["status"]


def test_drawing_ignores_clicks_outside_the_pane_and_is_disabled_in_replay():
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('trendline');
      CHARTS.filter(c => c.pane === 'chartMain').pop().clickHandler({});   // off-pane
      const offPane = { status: elements['drawStatus'].innerHTML, n: drawn().length };
      toggleReplay();                       // replay replaces the price pane
      setDrawTool('box');
      console.log(JSON.stringify({ offPane, tool: _drawTool, ctx: !!_drawCtx,
        status: elements['drawStatus'].innerHTML }));
    """,
    )
    assert "Click inside the price pane" in out["offPane"]["status"]
    assert out["offPane"]["n"] == 0, "a click with no coordinates drew something"
    assert out["tool"] is None and out["ctx"] is False
    assert "Stop the replay before drawing" in out["status"]


def test_corrupt_saved_drawings_never_break_the_chart():
    """Storage is user-writable. Garbage is dropped, the chart still paints."""
    out = _run(
        {"/api/chart": _chart_payload()},
        DRAW_SEGMENTS
        + """
      STORE['sky.drawings.v1.BTCUSDT.15m'] = JSON.stringify([
        'not-an-object',
        { kind: 'trendline', points: [{ time: 1780000000, price: 'oops' }] },
        { kind: 'nuke', points: [] },
        { id: '<img src=x onerror=alert(1)>', kind: 'ray',
          points: [{ time: 1780009000, price: 63900 }], created: 1 },
      ]);
      await loadChartWorkspace(true);
      const stored = JSON.parse(STORE['sky.drawings.v1.BTCUSDT.15m']);
      console.log(JSON.stringify({ n: drawn().length, candles:
        CHARTS.filter(c => c.pane === 'chartMain').pop()
          .series.find(s => s.kind === 'candle').data.length,
        list: elements['drawList'].innerHTML, storedBefore: stored.length }));
    """,
    )
    assert out["candles"] == 60, "corrupt drawings blanked the chart"
    assert out["n"] == 1, "only the one valid drawing should survive"
    assert "onerror" not in out["list"], "an unsafe id reached the DOM"


def test_drawings_can_be_attached_to_the_journal_note():
    out = _run(
        {"/api/chart": _chart_payload(), "/api/journal": {"journalable": []}},
        DRAW_SEGMENTS
        + """
      await loadChartWorkspace(true);
      setDrawTool('ray'); click(0, 200, 1780009000);
      elements['jNotes'] = el('jNotes');
      el('jNotes').value = 'took the retest';
      attachDrawingsToJournal();
      console.log(JSON.stringify({ tab: _activeTab, notes: elements['jNotes'].value,
        jStatus: elements['jStatus'].innerHTML }));
    """,
    )
    assert out["tab"] == "journal", "attaching did not open the journal"
    assert out["notes"].startswith("took the retest")
    assert "Chart marks — BTCUSDT 15m" in out["notes"]
    assert "Horizontal ray @ 63,800" in out["notes"]
    assert "pick the trade and save" in out["jStatus"]


def test_chart_toggles_hide_panes():
    """Unchecking RSI/MACD removes those panes — the toggles really work."""
    out = _run(
        {"/api/chart": _chart_payload()},
        """
      ['ovEma','ovVwap','ovLevels','ovPlan'].forEach(id => { el(id).checked = true; });
      ['ovBb','ovRsi','ovMacd'].forEach(id => { el(id).checked = false; });
      await loadChartWorkspace(true);
      console.log(JSON.stringify({ panes: CHARTS.map(c => c.pane),
        rsiDisplay: elements['chartRsi'].style.display,
        macdDisplay: elements['chartMacd'].style.display }));
    """,
    )
    assert "chartRsi" not in out["panes"] and "chartMacd" not in out["panes"]
    assert out["rsiDisplay"] == "none" and out["macdDisplay"] == "none"


def test_chart_reports_an_unavailable_feed():
    out = _run(
        {
            "/api/chart": {
                "error": "ConnectionError: binance unreachable",
                "candles": [],
            }
        },
        """
      await loadChartWorkspace(true);
      console.log(JSON.stringify({ head: elements['chartHead'].innerHTML }));
    """,
    )
    assert "unreachable" in out["head"]


def test_trade_manager_shows_live_r_and_management():
    out = _run(
        {
            "/api/trades": {
                "ok": True,
                "count": 1,
                "open": [
                    {
                        "scan_id": 42,
                        "symbol": "BTCUSDT",
                        "timeframe": "15m",
                        "action": "BUY",
                        "plan_type": "Buy Pullback",
                        "status": "OPEN",
                        "entry_price": 63000.0,
                        "current_price": 63450.0,
                        "stop_loss": 62700.0,
                        "take_profit": 63900.0,
                        "current_r": 1.5,
                        "mae": -0.3,
                        "mfe": 1.7,
                        "minutes_in_trade": 95,
                        "management": ["HOLD — thesis intact", "REDUCE — 50% at TP1"],
                    }
                ],
                "recent": [
                    {
                        "scan_id": 41,
                        "symbol": "BTCUSDT",
                        "plan_type": "Sweep",
                        "outcome": "TP_HIT",
                        "rr_achieved": 2.0,
                        "close_reason": "target hit",
                    }
                ],
                "overall": {},
            }
        },
        """
      await loadTradeManager();
      console.log(JSON.stringify({ count: elements['tmCount'].textContent,
        table: elements['tradeManager'].innerHTML,
        recent: elements['tmRecent'].innerHTML }));
    """,
    )
    assert out["count"] == 1
    table = out["table"]
    assert "#42" in table and "Buy Pullback" in table
    assert "+1.50R" in table, "current R is not displayed"
    assert "1h 35m" in table, "time in trade is not humanised"
    assert "-0.30" in table and "1.70" in table  # MAE / MFE
    assert "HOLD — thesis intact" in table
    for action in ("Detail", "Journal", "Close"):
        assert action in table, f"{action} button missing"
    assert "TP_HIT" in out["recent"]


def test_trade_manager_explains_an_empty_book():
    out = _run(
        {
            "/api/trades": {
                "ok": True,
                "count": 0,
                "open": [],
                "recent": [],
                "overall": {},
            }
        },
        """
      await loadTradeManager();
      console.log(JSON.stringify({ html: elements['tradeManager'].innerHTML }));
    """,
    )
    assert "no open positions" in out["html"]


def _risk_payload(allowed: bool) -> dict:
    return {
        "gate": {
            "allowed": allowed,
            "blocked_by": []
            if allowed
            else ["trader state: tired — no trading while these flags are set"],
            "details": {
                "progression": {"level": "student", "label": "Learn: structure + risk"},
                "effective_risk": {"risk_pct": 0.25, "daily": 1.0, "weekly": 2.0},
                "daily_weekly": {
                    "today": {"pct": -0.4, "trades": 2},
                    "week": {"pct": -0.9, "trades": 5},
                },
                "drawdown": {"max_drawdown_pct": 1.8, "level": "normal"},
                "kelly": {"clamped_size": 0.4, "max_risk_pct": 0.5, "win_rate": 0.52},
            },
        },
        "trader_state": {
            "angry": False,
            "tired": not allowed,
            "revenge": False,
            "chasing": False,
        },
        "journal": {"n": 10, "violation_rate": 0.1},
        "monte": {
            "rows": [
                {
                    "risk_pct": 1.0,
                    "expected_drawdown_pct": 12.4,
                    "ruin_prob": 0.02,
                    "worst_losing_streak": 7,
                    "time_to_recover": 21,
                }
            ]
        },
    }


def test_risk_center_explains_a_closed_gate():
    out = _run(
        {"/api/risk": _risk_payload(False)},
        """
      await loadRiskCenter();
      console.log(JSON.stringify({ gate: elements['riskCenterGate'].innerHTML,
        state: elements['traderStateNow'].innerHTML,
        monte: elements['riskMonte'].innerHTML }));
    """,
    )
    assert "GATE CLOSED" in out["gate"]
    assert "Why you cannot trade right now" in out["gate"]
    assert "tired" in out["gate"]
    assert "student" in out["gate"] and "0.25%/trade" in out["gate"]
    assert "Active flags" in out["state"] and "tired" in out["state"]
    assert "12.4%" in out["monte"] and "2.0%" in out["monte"]


def test_risk_center_shows_an_open_gate():
    out = _run(
        {"/api/risk": _risk_payload(True)},
        """
      await loadRiskCenter();
      console.log(JSON.stringify({ gate: elements['riskCenterGate'].innerHTML,
        state: elements['traderStateNow'].innerHTML }));
    """,
    )
    assert "GATE OPEN" in out["gate"]
    assert "Why you cannot trade" not in out["gate"]
    assert "No behavioral flags" in out["state"]


def test_position_sizer_renders_the_numbers():
    out = _run(
        {
            "/api/position-size": {
                "ok": True,
                "recommended_units": 0.0833,
                "risk_amount": 25.0,
                "notional": 5250.0,
                "risk_reward": 3.0,
                "risk_pct_applied": 0.25,
                "progression": "student",
                "ladder_cap_pct": 0.25,
                "stop_distance": 300.0,
                "stop_pct": 0.48,
                "leverage": 1,
                "margin_required": 5250.0,
                "losses_to_daily_limit": 4,
                "losses_to_weekly_limit": 8,
                "gate_open": True,
                "verdict": "Risking 0.25% (25.00) on a 0.48% stop",
                "warnings": ["risk reduced from 1% to 0.25%"],
            }
        },
        """
      await calcPositionSize();
      console.log(JSON.stringify({ html: elements['psResult'].innerHTML }));
    """,
    )
    html = out["html"]
    assert "Units to buy" in html and "Money at risk" in html
    assert "1:3" in html
    assert "4 in a row" in html and "8 in a row" in html
    assert "risk reduced" in html


def test_position_sizer_surfaces_an_error():
    out = _run(
        {
            "/api/position-size": {
                "ok": False,
                "error": "Entry and stop-loss are both required.",
            }
        },
        """
      await calcPositionSize();
      console.log(JSON.stringify({ html: elements['psResult'].innerHTML }));
    """,
    )
    assert "required" in out["html"]


def test_command_center_renders_runnable_actions():
    out = _run(
        {
            "/api/commands": {
                "count": 2,
                "categories": [
                    {
                        "category": "Scan",
                        "commands": [
                            {
                                "id": "scan",
                                "title": "Scan",
                                "category": "Scan",
                                "safety": "write",
                                "what": "One full signal scan.",
                                "cli": "python main.py scan",
                                "related": ["intelligence"],
                                "inputs": [
                                    {
                                        "name": "symbol",
                                        "label": "Asset",
                                        "type": "text",
                                        "default": "BTCUSDT",
                                        "placeholder": "BTCUSDT",
                                    },
                                    {
                                        "name": "json",
                                        "label": "Raw JSON",
                                        "type": "bool",
                                        "default": False,
                                    },
                                ],
                            }
                        ],
                    },
                    {
                        "category": "Integration",
                        "commands": [
                            {
                                "id": "mcp",
                                "title": "MCP server",
                                "category": "Integration",
                                "safety": "blocked",
                                "what": "Long-lived MCP server.",
                                "cli": "python main.py mcp",
                                "related": [],
                                "note": "run in a terminal: python main.py mcp",
                                "inputs": [],
                            }
                        ],
                    },
                ],
            }
        },
        """
      await loadCommands();
      console.log(JSON.stringify({ count: elements['cmdCount'].textContent,
        list: elements['commandList'].innerHTML }));
    """,
    )
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
    out = _run(
        {
            "/api/commands": {
                "count": 1,
                "categories": [
                    {
                        "category": "Risk",
                        "commands": [
                            {
                                "id": "risk",
                                "title": "Risk gate",
                                "category": "Risk",
                                "safety": "read",
                                "what": "Gate status.",
                                "cli": "python main.py risk",
                                "related": [],
                                "inputs": [],
                            }
                        ],
                    }
                ],
            },
            "/api/commands/run": {
                "ok": True,
                "exit_code": 0,
                "cli": "python main.py risk",
                "elapsed_ms": 320,
                "output": "RISK & DISCIPLINE GATE\\n  GATE: OPEN",
            },
        },
        """
      await loadCommands();
      await runCommand('risk');
      console.log(JSON.stringify({ out: elements['cmdOut'].textContent,
        state: elements['cmdRunning'].innerHTML }));
    """,
    )
    assert "GATE: OPEN" in out["out"], "command output is not displayed"
    assert "finished" in out["state"]


def test_module_catalog_lists_modules():
    out = _run(
        {
            "/api/modules": {
                "count": 2,
                "packages": [
                    {
                        "package": "engine",
                        "label": "Signal engine",
                        "count": 2,
                        "modules": [
                            {
                                "name": "engine/signal_engine.py",
                                "module": "engine.signal_engine",
                                "summary": "turns a candle frame into a signal",
                                "lines": 300,
                            },
                            {
                                "name": "engine/rules.py",
                                "module": "engine.rules",
                                "summary": "the scoring rules",
                                "lines": 120,
                            },
                        ],
                    }
                ],
            }
        },
        """
      await loadModules();
      console.log(JSON.stringify({ count: elements['modCount'].textContent,
        list: elements['moduleList'].innerHTML }));
    """,
    )
    assert out["count"] == "2 modules"
    assert "engine/signal_engine.py" in out["list"]
    assert "turns a candle frame into a signal" in out["list"]


def test_journal_form_loads_and_prefills():
    out = _run(
        {
            "/api/journal?scan_id": {
                "ok": True,
                "scan_id": 7,
                "entry": {
                    "followed_rules": 1,
                    "emotion": "calm",
                    "mistake": "none",
                    "notes": "clean execution",
                    "would_change": "size smaller",
                },
                "quality": {
                    "recorded": True,
                    "quality": "A+",
                    "verdict": "Excellent trade",
                },
                "checklist": {
                    "asset": "BTCUSDT",
                    "timeframe": "15m",
                    "setup": "Buy Pullback",
                    "regime": "TRENDING",
                    "htf_bias": "bullish",
                    "entry": 63000.0,
                    "stop_loss": 62700.0,
                    "take_profit": 63900.0,
                    "planned_rr": 3.0,
                    "news_environment": "normal",
                },
                "emotions": ["calm", "anxious"],
                "summary": {"n": 3},
            },
            "/api/journal": {
                "ok": True,
                "emotions": ["calm", "anxious"],
                "journalable": [
                    {"id": 7, "symbol": "BTCUSDT", "action": "BUY", "status": "CLOSED"}
                ],
                "summary": {"n": 3, "violations": 0, "violation_rate": 0.0},
            },
        },
        """
      await loadJournalCenter();
      el('jScan').value = '7';
      await loadJournalEntry();
      console.log(JSON.stringify({ checklist: elements['jChecklist'].innerHTML,
        summary: elements['jSummary'].innerHTML,
        emotion: elements['jEmotion'].value,
        notes: elements['jNotes'].value }));
    """,
    )
    assert "Buy Pullback" in out["checklist"]
    assert "TRENDING" in out["checklist"]
    assert "Excellent trade" in out["checklist"], "execution grade not shown"
    assert "Journalled trades" in out["summary"]
    assert out["emotion"] == "calm"
    assert out["notes"] == "clean execution"


def test_journal_form_saves():
    out = _run(
        {
            "/api/journal": {
                "ok": True,
                "scan_id": 7,
                "entry": {"emotion": "calm"},
                "quality": {"recorded": True, "verdict": "Excellent trade"},
                "emotions": ["calm"],
                "journalable": [],
                "summary": {"n": 1},
            }
        },
        """
      el('jScan').value = '7';
      el('jFollowed').value = '1';
      el('jEmotion').value = 'calm';
      await saveJournal();
      console.log(JSON.stringify({ status: elements['jStatus'].innerHTML }));
    """,
    )
    assert "saved" in out["status"]


def test_journal_form_requires_a_trade():
    out = _run(
        {},
        """
      el('jScan').value = '';
      await saveJournal();
      console.log(JSON.stringify({ status: elements['jStatus'].innerHTML }));
    """,
    )
    assert "pick a trade" in out["status"]


# ── P18.2: the /api/v1 contract card ──────────────────────────────────────
def _v1_version_env(**caps) -> dict:
    capabilities = {
        "live_exchange_execution": False,
        "paper_trading": True,
        "human_approval": True,
        "idempotent_mutations": True,
        "device_tokens": True,
    }
    capabilities.update(caps)
    return {
        "ok": True,
        "error": None,
        "meta": {
            "api_version": 1,
            "server_version": "2.30.0",
            "request_id": "abc",
            "ts": 1,
        },
        "data": {
            "api_version": 1,
            "server_version": "2.30.0",
            "min_client_version": 1,
            "max_client_version": 1,
            "client_version_header": "X-SKY-Client-Version",
            "idempotency_header": "Idempotency-Key",
            "capabilities": capabilities,
        },
    }


def test_api_contract_card_paints_the_version_range():
    out = _run(
        {"/api/v1/version": _v1_version_env()},
        """
      await loadApiV1(false);
      console.log(JSON.stringify({ html: elements['apiv1'].innerHTML }));
    """,
    )
    html = out["html"]
    assert "api v1" in html
    assert "clients v1–v1" in html
    assert "X-SKY-Client-Version" in html


def test_api_contract_card_shows_no_live_execution_honestly():
    """The card must not imply the desk can trade. A ✓ here would be a lie
    the packaging phases would then build a Trade button on."""
    out = _run(
        {"/api/v1/version": _v1_version_env()},
        """
      await loadApiV1(false);
      console.log(JSON.stringify({ html: elements['apiv1'].innerHTML }));
    """,
    )
    html = out["html"]
    assert "✗ live exchange execution" in html
    assert "✓ paper trading" in html
    assert "✓ idempotent mutations" in html


def test_api_contract_card_lists_the_route_catalog():
    routes = {
        "ok": True,
        "error": None,
        "meta": {
            "api_version": 1,
            "server_version": "2.30.0",
            "request_id": "r",
            "ts": 1,
        },
        "data": {
            "count": 2,
            "routes": [
                {
                    "path": "/api/v1/risk",
                    "method": "GET",
                    "role": "viewer",
                    "idempotent": False,
                    "native": False,
                    "legacy": "/api/risk",
                    "summary": "Risk & discipline gate status.",
                },
                {
                    "path": "/api/v1/review",
                    "method": "POST",
                    "role": "operator",
                    "idempotent": True,
                    "native": False,
                    "legacy": "/api/review",
                    "summary": "Approve / reject / execute / close a signal.",
                },
            ],
        },
    }
    out = _run(
        {"/api/v1/routes": routes},
        """
      await loadApiV1Routes();
      console.log(JSON.stringify({ html: elements['apiv1routes'].innerHTML }));
    """,
    )
    html = out["html"]
    assert "/api/v1/review" in html
    assert "operator" in html
    assert "✓ key" in html  # the retry-safe marker
    assert "2 routes" in html


def test_api_contract_card_reports_an_error_without_blanking():
    out = _run(
        {
            "/api/v1/version": {
                "ok": False,
                "data": None,
                "error": {"code": "INTERNAL", "message": "boom", "details": {}},
                "meta": {
                    "api_version": 1,
                    "server_version": "x",
                    "request_id": "r",
                    "ts": 1,
                },
            }
        },
        """
      await loadApiV1(false);
      console.log(JSON.stringify({ html: elements['apiv1'].innerHTML }));
    """,
    )
    assert "boom" in out["html"]


# ── W1: guided evidence build ─────────────────────────────────────────────
def test_guided_evidence_build_submits_selected_series_inline():
    out = _run(
        {},
        """
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
    """,
    )
    assert out["submitted"] == {
        "kind": "evidence",
        "params": {
            "symbol": "ETHUSDT",
            "tf": "1h",
            "market": "spot",
            "since": "90d",
            "bars": 900,
            "rounds": 7,
        },
    }
    assert out["streamUrl"].endswith("/ev123/events")
    assert out["display"] == "block"
    assert "queued" in out["state"]


def test_guided_evidence_restores_active_inline_job_after_reload():
    """Loading the Evidence tab discovers persisted active work and reconnects
    its inline SSE stream instead of redirecting to Command center."""
    active = {
        "job_id": "restored123",
        "kind": "evidence",
        "title": "Build my evidence",
        "status": "running",
        "phase": "Simulator",
        "step_index": 2,
        "step_total": 4,
        "log_tail": "still measuring",
    }
    out = _run(
        {
            "/api/loop-health": {
                "evidence_guidance": {
                    "result": "incomplete",
                    "projection_state": "unknown",
                    "backtest_gap": 40,
                    "paper_gap": 8,
                    "caveat": "Not a promise.",
                }
            },
            "/api/v1/jobs": {"ok": True, "data": {"jobs": [active]}},
            "/api/unlock": {"allowed": False, "blocks": []},
            "/api/evidence": {"setups": [], "count": 0},
        },
        """
      let streamUrl='';
      global.EventSource=class { constructor(url){ streamUrl=url; }
        addEventListener(){} close(){} };
      await loadEvidence();
      console.log(JSON.stringify({
        streamUrl,
        display: elements['evJob'].style.display,
        state: elements['evJobState'].textContent,
        log: elements['evJobLog'].textContent,
      }));
    """,
    )
    assert out["streamUrl"].endswith("/restored123/events")
    assert out["display"] == "block"
    assert "Simulator" in out["state"] and "2/4" in out["state"]
    assert "still measuring" in out["log"]


def test_evidence_guidance_says_no_edge_plainly():
    out = _run(
        {},
        """
      renderEvidenceGuidance({result:'no_edge',headline:'No positive net edge measured.',
        projection_state:'complete',projected_rounds:0,backtest_gap:0,paper_gap:0,
        caveat:'Not a promise.'});
      console.log(JSON.stringify({html:elements['evProjection'].innerHTML}));
    """,
    )
    assert "No positive net edge measured" in out["html"]
    assert "Sample-count gap: complete" in out["html"]
    assert "Not a promise" in out["html"]


# ── W3.5 part 2: 2×2 multi-chart — synchronized crosshair ────────────────
def _multi_api() -> dict:
    """Four slot payloads: the primary series on two timeframes plus two
    other markets, exactly what multiDefaults() selects for BTCUSDT/15m."""
    api = {}
    for symbol, tf in (
        ("BTCUSDT", "15m"),
        ("BTCUSDT", "1h"),
        ("ETHUSDT", "1h"),
        ("XAUUSD", "1h"),
    ):
        p = _chart_payload()
        p["symbol"], p["timeframe"] = symbol, tf
        api[f"/api/chart?symbol={symbol}&tf={tf}"] = p
    return api


MULTI_WAIT = "await new Promise(r => setImmediate(r));"


def test_multi_chart_grid_is_2x2_and_crosshair_stays_synchronized():
    """One pointer over any pane moves the crosshair on all four panes to the
    same bar time and pointer price; leaving the pane clears the others."""
    out = _run(
        _multi_api(),
        f"""
      toggleMultiChart();
      {MULTI_WAIT}
      const mc = CHARTS.filter(c => c.cls === 'multi-chart-canvas');
      // pointer on chart 0 → every other chart gets the same time and price
      mc[0].crosshairHandler({{ time: 1780000000, point: {{ x: 10, y: 50 }},
        seriesData: new Map([[mc[0].series[0], {{ close: 63500 }}]]) }});
      const calls = mc.slice(1).map(c => c.crosshairCalls);
      // pointer leaves → crosshairs cleared on the others, never an error
      mc[0].crosshairHandler({{}});
      // disabling the sync stops propagation immediately
      _multiSyncCrosshair = false;
      mc[1].crosshairCalls = [];
      mc[0].crosshairHandler({{ time: 1780000000, point: {{ x: 10, y: 50 }},
        seriesData: new Map() }});
      console.log(JSON.stringify({{
        cards: mc.length,
        calls, clears: mc.slice(1).map(c => c.crosshairClears),
        afterOff: mc[1].crosshairCalls.length,
        selfUntouched: mc[0].crosshairCalls.length,
        mainHidden: elements['chartMain'].style.display,
        hostVisible: elements['multiChart'].style.display,
        times: mc[0].series[0].data.map(c => c.time),
      }}));
    """,
    )
    assert out["cards"] == 4, "the 2×2 grid did not render four charts"
    assert out["hostVisible"] == "grid" and out["mainHidden"] == "none"
    assert out["selfUntouched"] == 0, "a chart echoed the crosshair back to itself"
    for c in out["calls"]:
        assert c == [{"price": 63950.0, "time": 1780000000}], c
    assert all(clears >= 1 for clears in out["clears"]), (
        "leaving the pane did not clear the other crosshairs"
    )
    assert out["afterOff"] == 0, "the crosshair sync toggle did not stop propagation"
    assert out["times"][0] == 1780000000, "bar times were mangled off the epoch"


def test_multi_chart_zoom_sync_toggle_stops_pan_propagation():
    """Zoom/pan sync defaults on; the toggle cuts it off without a reload."""
    out = _run(
        _multi_api(),
        f"""
      toggleMultiChart();
      {MULTI_WAIT}
      const mc = CHARTS.filter(c => c.cls === 'multi-chart-canvas');
      mc[0].timeScale().lrHandler({{ from: 1, to: 50 }});
      const synced = mc.slice(1).map(c => c.timeScale().lrCalls);
      _multiSyncZoom = false;
      mc[1].timeScale().lrCalls = [];
      mc[0].timeScale().lrHandler({{ from: 10, to: 60 }});
      console.log(JSON.stringify({{ synced, afterOff: mc[1].timeScale().lrCalls.length }}));
    """,
    )
    assert all(r == [{"from": 1, "to": 50}] for r in out["synced"]), out
    assert out["afterOff"] == 0, "the zoom sync toggle did not stop propagation"


def test_multi_chart_renders_missing_data_as_an_explicit_empty_slot():
    """An unsupported pair or a failed feed is an explicit 'no candles' slot,
    never an empty chart that reads as a quiet market."""
    api = _multi_api()
    api["/api/chart?symbol=XAUUSD&tf=1h"] = {
        "error": "ConnectionError: gold feed unreachable",
        "candles": [],
    }
    out = _run(
        api,
        f"""
      toggleMultiChart();
      {MULTI_WAIT}
      const empty = CREATED.filter(e => (e.className || '').includes('multi-chart-empty'));
      console.log(JSON.stringify({{
        cards: CHARTS.filter(c => c.cls === 'multi-chart-canvas').length,
        empty: empty.map(e => e.textContent),
      }}));
    """,
    )
    assert out["cards"] == 3, "the failed slot still painted a chart"
    assert any("no candles for XAUUSD 1h" in t and "unreachable" in t for t in out["empty"]), out


def test_multi_chart_defaults_fill_four_distinct_slots_and_validate_saves():
    """Defaults must fill the 2×2 grid with four DISTINCT views (the old
    defaults collapsed to three when the primary was BTCUSDT); duplicate
    saves collapse, and invalid saved slots fall back to their defaults."""
    out = _run(
        _multi_api(),
        """
      const defaults = multiDefaults();
      const specs = multiChartSpecs();
      saveMultiSlots([{symbol:'ETHUSDT',tf:'4h'},{symbol:'ETHUSDT',tf:'4h'},
                      {symbol:'ETHUSDT',tf:'4h'},{symbol:'ETHUSDT',tf:'4h'}]);
      const afterDedupe = multiChartSpecs().length;
      STORE['sky.multiChartSlots'] = JSON.stringify([
        {symbol:'NOPE',tf:'1s'},{symbol:'BTCUSDT',tf:'15m'},
        {symbol:'ETHUSDT',tf:'1h'},{symbol:'XAUUSD',tf:'1d'}]);
      const validated = multiSlotState();
      console.log(JSON.stringify({ defaults, specCount: specs.length, afterDedupe, validated }));
    """,
    )
    assert out["specCount"] == 4, "default slots are not four distinct views"
    assert len({f"{s['symbol']} {s['tf']}" for s in out["defaults"]}) == 4, out
    assert out["afterDedupe"] == 1, "duplicate slots are not collapsed"
    assert out["validated"][0] == {"symbol": "BTCUSDT", "tf": "15m"}, (
        "an invalid saved slot did not fall back to its default"
    )


def test_multi_candle_data_normalises_ms_and_keeps_seconds():
    """A millisecond timestamp becomes epoch seconds; a seconds timestamp is
    left alone — neither is re-read as a 1970 millisecond date."""
    out = _run(
        _multi_api(),
        """
      const got = multiCandleData([
        { time: 1780000000, open: 1, high: 2, low: 0.5, close: 1.5 },
        { time: 1780000000000, open: 1, high: 2, low: 0.5, close: 1.5 },
        { time: '2026-06-01T00:00:00Z', open: 1, high: 2, low: 0.5, close: 1.5 },
      ]);
      console.log(JSON.stringify({ times: got.map(c => c.time) }));
    """,
    )
    assert out["times"][0] == 1780000000
    assert out["times"][1] == 1780000000
    assert out["times"][2] == 1780272000, out
