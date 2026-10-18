"""Tests that guard the dashboard's frontend JavaScript.

These catch the exact class of bug that broke the dashboard for the user:
a duplicate `const` declaration (SyntaxError) that makes the whole <script>
refuse to run, or a field-name mismatch that throws only when real data has
non-empty values (e.g. reading `soc.hits[0]` when the backend returns
`influencer_mentions`).

When `node` is available (CI has it), we:
  1. extract the <script> from the HTML template and run `node --check`
  2. execute render() against a synthetic payload AND against a real captured
     payload (data_samples/example_payload.json), asserting every card appears

If node is missing the tests skip (they never fail a machine without node).
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
SAMPLE = ROOT / "data_samples" / "example_payload.json"

NODE = shutil.which("node")

CARDS = [
    "LIVE SIGNAL",
    "CANDLESTICK",
    "MULTI-TIMEFRAME",
    "WHAT THE MARKET OFFERS",
    "CONTEXT — WHAT AFFECTS PRICE",
    "STATE MEMORY",
    "HUMAN APPROVAL QUEUE",
    "PAPER TRADING",
    "RECENT SIGNALS",
    "LEARNING",
    "COACH",
    "CONNECTIONS",
    "SYSTEM HEALTH",
    "AGENTS — MORNING BRIEFING",
    "MCP SERVER",
    "ASK THE DESK",
    "DESK STATUS",
    "STRATEGY SCORECARD",
    "LOOP HEALTH",
    "KEY LEVELS",
    "MARKET SENTIMENT — THE COLOUR IS THE MARKET",
]


def _extract_js() -> str:
    # The terminal template moved out of app.py into web/static/terminal.html
    # (maintainability refactor); the served script is byte-identical.
    html = (ROOT / "web" / "static" / "terminal.html").read_text(encoding="utf-8")
    sm = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert sm, "script block not found"
    return sm.group(1)


def _synthetic_payload() -> dict:
    """A minimal but realistic payload for render()."""
    return {
        "signal": {
            "action": "BUY",
            "asset": "BTCUSDT",
            "timeframe": "15m",
            "confidence": "MEDIUM",
            "signal_id": "BTCUSDT_20260804_0000",
            "entry": 63000.0,
            "stop_loss": 62700.0,
            "take_profit": 63600.0,
            "risk_reward": 2.0,
            "reason": "test",
        },
        "plans": [
            {
                "type": "Buy Pullback",
                "action": "BUY",
                "confidence": 70,
                "confidence_label": "MEDIUM",
                "condition": "IF price pulls back",
                "entry": 63000.0,
                "stop_loss": 62700.0,
                "take_profits": [63600.0],
                "risk_reward": 2.0,
            }
        ],
        "snapshot": {
            "features": {
                "price": 63000.0,
                "trend": "bullish",
                "rsi": 58,
                "adx": 25,
                "volume_ratio": 1.5,
                "above_vwap": True,
                "premium_discount": "discount",
                "event_kind": "bos_up",
                "swing_high": 64000.0,
                "swing_low": 62000.0,
                "atr_pct": 0.2,
                "rsi_divergence": {"bull": 0, "bear": 0},
            },
            "scores": {
                "bull": {"score": 60, "conditions": {"Trend": 15}},
                "bear": {"score": 20, "conditions": {}},
            },
        },
        "mtf": {
            "htf_bias": "bullish",
            "ltf_bias": "neutral",
            "alignment": {"score": 40, "label": "aligned_bull"},
            "views": {
                "1d": {
                    "available": True,
                    "trend": "bull",
                    "rsi": 60,
                    "adx": 26,
                    "event_kind": "bos_up",
                    "premium_discount": "discount",
                },
                "4h": {
                    "available": True,
                    "trend": "bull",
                    "rsi": 58,
                    "adx": 24,
                    "event_kind": None,
                    "premium_discount": "equilibrium",
                },
                "1h": {
                    "available": True,
                    "trend": "bull",
                    "rsi": 55,
                    "adx": 22,
                    "event_kind": None,
                    "premium_discount": "equilibrium",
                },
                "15m": {
                    "available": True,
                    "trend": "bull",
                    "rsi": 54,
                    "adx": 20,
                    "event_kind": None,
                    "premium_discount": "discount",
                },
                "5m": {"available": False},
            },
            "key_levels": {"support": [62000.0], "resistance": [64000.0]},
        },
        "styles": {
            "market_offering": ["Day"],
            "stand_aside": [],
            "styles": {
                "Scalp": {"available": False},
                "Day": {
                    "available": True,
                    "direction": "BUY",
                    "confidence": 70,
                    "horizon": "1 session",
                    "reason": "test",
                },
                "Swing": {"available": False},
                "Momentum": {"available": False},
                "Position": {"available": False},
            },
        },
        "context": {
            "fear_greed": {"available": True, "value": 55},
            "dominance": {"available": False},
            "equities": {"available": False},
            "macro": {"available": True, "events": []},
            "cycle": {"available": True, "phase": "expansion"},
            "geopolitics": {"available": True, "count": 0},
            "social": {
                "available": True,
                "count": 1,
                "influencer_mentions": [{"keyword": "etf"}],
            },
            "risk_regime": {"regime": "neutral"},
        },
        "memory": {"status": "SAME", "reaffirms": 2, "changes": []},
        "market_context": {"futures": False},
        "lifecycle": {"status": "PENDING_REVIEW", "note": "awaiting"},
    }


def _run_harness(payload_json: str) -> None:
    js = _extract_js()
    harness = f"""
    const payload = {payload_json};
    const elements = {{}};
    function el(id){{ if(!elements[id]) elements[id]={{ innerHTML:'', value:'BTCUSDT',
      textContent:'', checked:true, disabled:false, style:{{}}, addEventListener:()=>{{}},
      querySelector:()=>null }}; return elements[id]; }}
    global.window = {{ addEventListener: ()=>{{}} }};
    global.document = {{ getElementById: el, addEventListener: ()=>{{}} }};
    global.fetch = async (url) => ({{ json: async () => {{
      if(String(url).includes('/api/candles')) return {{ candles: [] }};
      return {{}};
    }} }});
    global.AbortController = class {{ constructor(){{ this.signal={{}}; }} abort(){{}} }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = () => 0; global.clearTimeout = () => {{}};
    {js}
    const cards = {json.dumps(CARDS)};
    render(payload);
    const html = elements['app'].innerHTML;
    const missing = cards.filter(c => !html.includes(c));
    if (missing.length) {{ console.error('missing cards:', missing); process.exit(1); }}
    if (!html.length) {{ console.error('empty render'); process.exit(1); }}
    console.log('render OK, cards', cards.length);
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True)
        assert r.returncode == 0, f"render failed:\n{r.stdout}\n{r.stderr}"
    finally:
        Path(path).unlink(missing_ok=True)


def _run_readiness_harness(strip: dict) -> str:
    """Run loadReadiness() against a fixed /api/readiness payload.

    Returns the innerHTML the strip element ends up with, so a field-name
    drift between brain.agent.readiness_strip() and the dashboard is
    caught here rather than in the browser.
    """
    js = _extract_js()
    harness = f"""
    const strip = {json.dumps(strip)};
    const elements = {{}};
    function el(id){{ if(!elements[id]) elements[id]={{ innerHTML:'', className:'',
      value:'BTCUSDT', textContent:'', checked:true, disabled:false, style:{{}},
      addEventListener:()=>{{}}, querySelector:()=>null }}; return elements[id]; }}
    global.window = {{ addEventListener: ()=>{{}} }};
    global.document = {{ getElementById: el, addEventListener: ()=>{{}} }};
    global.fetch = async (url) => ({{ json: async () => {{
      if(String(url).includes('/api/readiness')) return strip;
      if(String(url).includes('/api/candles')) return {{ candles: [] }};
      return {{}};
    }} }});
    global.AbortController = class {{ constructor(){{ this.signal={{}}; }} abort(){{}} }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = () => 0; global.clearTimeout = () => {{}};
    {js}
    loadReadiness().then(() => {{
      const e = elements['readiness'];
      console.log(JSON.stringify({{ html: e.innerHTML, cls: e.className }}));
    }}).catch(err => {{ console.error(err); process.exit(1); }});
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True)
        assert r.returncode == 0, f"loadReadiness failed:\n{r.stdout}\n{r.stderr}"
        return r.stdout.strip().splitlines()[-1]
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_readiness_strip_renders_every_pillar():
    """The strip shows one chip per pillar and the rolled-up verdict."""
    out = json.loads(
        _run_readiness_harness(
            {
                "level": "degraded",
                "ready": False,
                "headline": "desk degraded — channels",
                "pillars": [
                    {
                        "name": "channels",
                        "level": "degraded",
                        "headline": "2/4 channels live",
                        "detail": "news=rss_parallel",
                    },
                    {
                        "name": "immune",
                        "level": "ok",
                        "headline": "4 check(s) ok",
                        "detail": "",
                    },
                    {
                        "name": "risk_gate",
                        "level": "ok",
                        "headline": "gate OPEN",
                        "detail": "no blocks",
                    },
                    {
                        "name": "data",
                        "level": "degraded",
                        "headline": "no stored market history yet",
                        "detail": "run `python main.py backfill`",
                    },
                ],
                "advice": {"action": "PAPER_GRIND", "headline": "keep paper-trading"},
            }
        )
    )
    html = out["html"]
    for pillar in ("channels", "immune", "risk_gate", "data"):
        assert pillar in html, f"readiness strip missing the {pillar!r} chip"
    assert "DESK DEGRADED" in html.upper()
    assert "PAPER_GRIND" in html
    assert out["cls"] == "strip lvl-degraded"


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_readiness_strip_handles_error_payload():
    """A degraded /api/readiness response must still render, not throw."""
    out = json.loads(
        _run_readiness_harness(
            {
                "ok": False,
                "level": "down",
                "headline": "readiness unavailable",
                "pillars": [],
                "error": "RuntimeError: boom",
            }
        )
    )
    assert out["cls"] == "strip lvl-down"
    assert "RuntimeError" in out["html"]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_dashboard_js_syntax():
    js = _extract_js()
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run([NODE, "--check", path], capture_output=True, text=True)
        assert r.returncode == 0, f"JS syntax error:\n{r.stderr}"
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_served_script_is_valid_javascript():
    """Check the *evaluated* template, not the file text.

    ``HTML`` is a plain (non-raw) triple-quoted Python string, so a backslash
    escape written inside the embedded JavaScript is consumed by Python before
    the browser ever sees it: ``'a\\nb'`` becomes a real newline inside a JS
    string literal (an unterminated-string SyntaxError that kills the whole
    dashboard), and ``\\s`` raises a SyntaxWarning today / SyntaxError later.
    The source-text extractor above cannot see either, because it reads the
    characters on disk. This one parses what Flask actually serves.
    """
    from web.app import HTML

    scripts = re.findall(r"<script>(.*?)</script>", HTML, re.DOTALL)
    assert scripts, "no inline script in the served template"
    for i, js in enumerate(scripts):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
            path = f.name
        try:
            r = subprocess.run([NODE, "--check", path], capture_output=True, text=True)
            assert r.returncode == 0, (
                f"served <script> #{i} is not valid JS "
                f"(a backslash escape was probably eaten by Python):\n{r.stderr}"
            )
        finally:
            Path(path).unlink(missing_ok=True)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_render_with_synthetic_payload():
    _run_harness(json.dumps(_synthetic_payload()))


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_render_with_real_sample_payload():
    """Renders with a REAL captured payload (data_samples/example_payload.json)
    so field-name mismatches (e.g. social.influencer_mentions vs .hits) that
    only appear with non-empty real data are caught."""
    assert SAMPLE.exists(), "example_payload.json missing"
    payload = json.loads(SAMPLE.read_text())
    _run_harness(json.dumps(payload))


def _run_sentiment_harness(payload_json: str) -> str:
    """Run render() with an attached ``sentiment`` block and return the state
    of the sentiment strip + mood bar, so colour wiring is guarded here."""
    js = _extract_js()
    harness = f"""
    const payload = {payload_json};
    const elements = {{}};
    function el(id){{ if(!elements[id]) elements[id]={{ innerHTML:'', className:'',
      value:'BTCUSDT', textContent:'', checked:true, disabled:false, style:{{}},
      addEventListener:()=>{{}}, querySelector:()=>null }}; return elements[id]; }}
    global.window = {{ addEventListener: ()=>{{}} }};
    global.document = {{ getElementById: el, addEventListener: ()=>{{}} }};
    global.fetch = async (url) => ({{ json: async () => {{
      if(String(url).includes('/api/candles')) return {{ candles: [] }};
      return {{}};
    }} }});
    global.AbortController = class {{ constructor(){{ this.signal={{}}; }} abort(){{}} }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = () => 0; global.clearTimeout = () => {{}};
    {js}
    render(payload);
    const app = elements['app'].innerHTML;
    console.log(JSON.stringify({{
      card: app.includes('MARKET SENTIMENT — THE COLOUR IS THE MARKET'),
      labelInCard: app.includes('STRONG BULLISH'),
      legend: app.includes('strong bull = deep green'),
      parts: app.includes('engine bull'),
      needle: elements['sentiNeedle'].style.left,
      border: elements['senti'].style.borderColor,
      bar: elements['moodbar'].style.background,
      depth: elements['sentiDepth'].textContent,
      dur: elements['sentiDur'].textContent
    }}));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True)
        assert r.returncode == 0, f"sentiment render failed:\n{r.stdout}\n{r.stderr}"
        return r.stdout.strip().splitlines()[-1]
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_sentiment_strip_colours_bullish_deep_green():
    payload = _synthetic_payload()
    payload["sentiment"] = {
        "available": True,
        "score": 71.0,
        "direction": "bullish",
        "label": "STRONG BULLISH",
        "strength": 0.71,
        "duration_min": 150,
        "duration_text": "2h 30m",
        "persistence": 0.83,
        "intensity": 0.66,
        "color": "hsl(142,74%,37%)",
        "parts": [
            {
                "name": "engine bull − bear scores",
                "weight": 0.5,
                "raw": 40.0,
                "contrib": 20.0,
                "detail": "bull 60 vs bear 20 / 100",
            },
            {
                "name": "MTF alignment",
                "weight": 0.2,
                "raw": 40.0,
                "contrib": 8.0,
                "detail": "aligned",
            },
        ],
        "history": [
            {"ts": 1, "score": 30.0},
            {"ts": 2, "score": 45.0},
            {"ts": 3, "score": 71.0},
        ],
    }
    out = json.loads(_run_sentiment_harness(json.dumps(payload)))
    assert out["card"] and out["labelInCard"] and out["legend"] and out["parts"]
    assert out["bar"] == "hsl(142,74%,37%)", out
    assert out["border"] == "hsl(142,74%,37%)", out
    assert out["needle"] == "85.5%", out
    assert out["depth"] == "66%", out
    assert out["dur"] == "2h 30m", out


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_sentiment_strip_colours_bearish_red_and_neutral_slate():
    payload = _synthetic_payload()
    payload["sentiment"] = {
        "available": True,
        "score": -42.0,
        "direction": "bearish",
        "label": "BEARISH",
        "strength": 0.42,
        "duration_min": 20,
        "duration_text": "20m",
        "persistence": 0.11,
        "intensity": 0.27,
        "color": "hsl(0,67%,47%)",
        "parts": [],
        "history": [],
    }
    out = json.loads(_run_sentiment_harness(json.dumps(payload)))
    assert out["bar"].startswith("hsl(0,67%,47%)"), out
    assert out["needle"] == "29%", out

    payload["sentiment"] = {
        "available": True,
        "score": 3.0,
        "direction": "neutral",
        "label": "NEUTRAL",
        "strength": 0.03,
        "duration_min": 0,
        "duration_text": "—",
        "persistence": 0.0,
        "intensity": 0.0,
        "color": "#5f6d84",
        "parts": [],
        "history": [],
    }
    out = json.loads(_run_sentiment_harness(json.dumps(payload)))
    assert out["bar"] == "#5f6d84", out
    assert out["depth"] == "—", out
    assert out["dur"] == "—", out


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_sentiment_fallback_renders_without_backend_block():
    """A payload WITHOUT a sentiment block (old cached scan) must still render:
    the client-side estimate keeps the colour signal alive."""
    payload = _synthetic_payload()
    payload.pop("sentiment", None)
    js = _extract_js()
    harness = f"""
    const payload = {json.dumps(payload)};
    const elements = {{}};
    function el(id){{ if(!elements[id]) elements[id]={{ innerHTML:'', className:'',
      value:'BTCUSDT', textContent:'', checked:true, disabled:false, style:{{}},
      addEventListener:()=>{{}}, querySelector:()=>null }}; return elements[id]; }}
    global.window = {{ addEventListener: ()=>{{}} }};
    global.document = {{ getElementById: el, addEventListener: ()=>{{}} }};
    global.fetch = async () => ({{ json: async () => ({{}}) }});
    global.AbortController = class {{ constructor(){{ this.signal={{}}; }} abort(){{}} }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = () => 0; global.clearTimeout = () => {{}};
    {js}
    render(payload);
    const app = elements['app'].innerHTML;
    console.log(JSON.stringify({{
      card: app.includes('MARKET SENTIMENT — THE COLOUR IS THE MARKET'),
      estimate: app.includes('estimate — backend will confirm'),
      bar: elements['moodbar'].style.background,
      label: elements['sentiLabel'].textContent
    }}));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True)
        assert r.returncode == 0, f"fallback sentiment render failed:\n{r.stdout}\n{r.stderr}"
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)
    assert out["card"], out
    assert out["estimate"], out
    assert out["bar"].startswith("hsl("), out
    assert out["label"], out


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_auth_form_setup_and_login_js():
    """doSetup() and doLogin() must trim username without TypeError (const reassignment)."""
    js = _extract_js()
    harness = f"""
    const elements = {{
      suUser: {{ value: '  alice  ', style: {{}} }},
      suPass: {{ value: 'secret1234', style: {{}} }},
      suPass2: {{ value: 'secret1234', style: {{}} }},
      suErr: {{ textContent: '', style: {{}} }},
      liUser: {{ value: '  bob  ', style: {{}} }},
      liPass: {{ value: 'secret1234', style: {{}} }},
      liErr: {{ textContent: '', style: {{}} }}
    }};
    function el(id) {{
      if (!elements[id]) elements[id] = {{ value: '', textContent: '', innerHTML: '', style: {{}}, addEventListener: () => {{}} }};
      return elements[id];
    }}
    global.window = {{ addEventListener: () => {{}} }};
    global.document = {{ getElementById: el, addEventListener: () => {{}} }};
    const posted = [];
    global.fetch = async (url, opts) => {{
      posted.push({{ url, body: JSON.parse(opts.body) }});
      return {{ ok: true, json: async () => ({{ ok: true }}) }};
    }};
    global.location = {{ reload: () => {{}} }};
    global.setInterval = () => 0; global.clearInterval = () => {{}};
    global.setTimeout = () => 0; global.clearTimeout = () => {{}};

    {js}

    (async () => {{
      await doSetup();
      await doLogin();
      console.log(JSON.stringify(posted));
    }})().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run([NODE, path], capture_output=True, text=True)
        assert r.returncode == 0, f"auth js failed:\n{r.stdout}\n{r.stderr}"
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out[0] == {
            "url": "/api/auth/setup",
            "body": {"username": "alice", "password": "secret1234"},
        }
        assert out[1] == {
            "url": "/api/auth/login",
            "body": {"username": "bob", "password": "secret1234"},
        }
    finally:
        Path(path).unlink(missing_ok=True)
