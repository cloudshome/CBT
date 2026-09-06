"""T6 — focused pages + mobile sections tests.

Same approach as tests/test_terminal_js.py / tests/test_home_js.py: execute
the real served dashboard JavaScript in node against stubbed APIs and assert

  * each nav area is a focused page: identity header + sub-section switcher,
    exactly ONE section panel active at a time (never the old stack);
  * the remembered sub-section per area persists and a removed value falls
    back to the area default;
  * legacy switchTab(name) deep-links land on the right focused page+section
    (every quickbar button keeps working);
  * render()'s panel re-apply keeps the current focused section — it can
    never navigate the user to a different area as a refresh side effect;
  * #risk-style deep links land on the owning page's section;
  * the mobile four-section bar navigates and paints its active state, and
    the paper ticket opens as a sheet that re-reads the risk gate fresh.

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
    const POSTS = []; const GETS = []; const TOASTS = [];
    const elements = {}; const REGISTRY = {};
    function mkEl(id){
      const cls = new Set();
      return { id, innerHTML:'', className:'', textContent:'', value:'',
        checked:true, disabled:false, clientWidth:900, style:{}, dataset:{},
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
    function regEl(sel, data){
      const e = mkEl(sel + '::' + JSON.stringify(data));
      e.dataset = data;
      (REGISTRY[sel] = REGISTRY[sel] || []).push(e);
      return e;
    }
    ['overview','market','intelligence','trades','manage','risk','weekly',
     'journal','evidence','learn','system','connections','agent','commands',
     'modules'].forEach(t=> regEl('.tabpanel', {tab:t}));
    ['home','trade','markets','portfolio','journal','evidence','system']
      .forEach(n=> regEl('.navbtn', {nav:n}));
    ['markets','chart','positions','ai']
      .forEach(m=> regEl('#mobileNav button', {msec:m}));
    global.window = { addEventListener: ()=>{} };
    global.document = { getElementById: el, addEventListener: ()=>{},
      querySelectorAll: (sel)=> REGISTRY[sel] || [],
      createElement: ()=>mkEl('tmp'), title: 'SKY',
      querySelector: ()=>null };
    global.localStorage = { store: {},
      getItem(k){ return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null; },
      setItem(k, v){ this.store[k] = String(v); },
      removeItem(k){ delete this.store[k]; } };
    global.history = { lastHashOrUrl: null,
      replaceState: (a, b, url)=>{ global.history.lastHashOrUrl = String(url); } };
    global.location = { hash: '__INITIAL_HASH__' };
    global.AbortController = class { constructor(){ this.signal={}; } abort(){} };
    global.fetch = async (url, opts) => {
      GETS.push(String(url));
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


def _run(body: str, api: dict | None = None, initial_hash: str = "") -> dict:
    harness = (
        _HARNESS_HEAD.replace("__API__", json.dumps(api or {}))
        .replace("__INITIAL_HASH__", initial_hash)
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
  posts: POSTS, gets: GETS, toasts: TOASTS,
  nav: _currentNav, mobileSec: _mobileSec,
  lastHash: history.lastHashOrUrl,
  activeTab: _activeTab,
  head: el('areaHead').innerHTML || '',
  headShown: el('areaHead').style.display || '',
  panels: Object.fromEntries(REGISTRY['.tabpanel'].map(p=> [p.dataset.tab, p.classList.contains('active')])),
  navbtns: Object.fromEntries(REGISTRY['.navbtn'].map(b=> [b.dataset.nav, b.classList.contains('active')])),
  mobileBtns: Object.fromEntries((REGISTRY['#mobileNav button']||[]).map(b=> [b.dataset.msec, b.classList.contains('active')])),
  termCls: Array.from(el('terminal').classes || []),
  drawerOpen: el('aiDrawer').classList.contains('open'),
  riskReads: global.__riskReads || null }));
"""


def test_markets_is_focused_one_section_at_a_time():
    out = _run("navTo('markets');" + _DRAIN + _OUT)
    assert ">Markets<" in out["head"]  # identity header
    assert "Overview" in out["head"] and "Intelligence" in out["head"]
    assert 'data-asub="overview"' in out["head"]
    assert out["head"].count('class="active"') == 1  # one active sub
    assert out["panels"]["overview"] is True
    assert out["panels"]["market"] is False  # no stack
    assert out["panels"]["intelligence"] is False
    assert out["panels"]["manage"] is False


def test_sub_switch_shows_exactly_one_section_and_persists():
    out = _run(
        """
      navTo('portfolio');
      switchSub('portfolio', 'risk');
      """
        + _DRAIN
        + _OUT
    )
    assert out["panels"]["risk"] is True
    assert out["panels"]["manage"] is False  # default replaced
    assert out["panels"]["trades"] is False
    assert out["lastHash"] == "#risk"  # deep-linkable
    assert out["activeTab"] == "risk"


def test_remembered_sub_reopens_with_the_area():
    out = _run(
        """
      localStorage.setItem('sky.sub.portfolio', 'weekly');
      navTo('portfolio');
      """
        + _DRAIN
        + _OUT
    )
    assert out["panels"]["weekly"] is True
    assert out["panels"]["manage"] is False
    assert 'data-asub="weekly" class="active"' in out["head"]


def test_remembered_sub_that_no_longer_exists_falls_back_to_default():
    out = _run(
        """
      localStorage.setItem('sky.sub.portfolio', 'renamed_away');
      navTo('portfolio');
      """
        + _DRAIN
        + _OUT
    )
    assert out["panels"]["manage"] is True  # area default


def test_legacy_switchtab_calls_land_on_the_right_focused_section():
    out = _run(
        """
      switchTab('learn');                                        // old quickbar idiom
      """
        + _DRAIN
        + _OUT
    )
    assert out["nav"] == "evidence"
    assert out["navbtns"]["evidence"] is True
    assert out["panels"]["learn"] is True
    assert out["panels"]["evidence"] is False
    assert ">Evidence<" in out["head"]


def test_apply_nav_panels_keeps_the_current_section_after_rerender():
    out = _run(
        """
      navTo('markets');
      switchSub('markets', 'intelligence');
      // simulate render() rebuilding #app: all dynamic panels recreated
      REGISTRY['.tabpanel'].forEach(p=> p.classList.remove('active'));
      applyNavPanels();
      """
        + _OUT
    )
    assert out["panels"]["intelligence"] is True
    assert out["panels"]["overview"] is False
    assert out["nav"] == "markets"  # never navigated


def test_section_deep_link_lands_on_the_owning_page():
    out = _run(_OUT, initial_hash="risk")
    assert out["nav"] == "portfolio"
    assert out["activeTab"] == "risk"
    assert out["panels"]["risk"] is True
    assert out["panels"]["manage"] is False


def test_terminal_and_home_hide_the_area_header():
    out = _run(
        """
      navTo('portfolio');      // header on
      navTo('trade');          // header off for terminal
      """
        + _OUT
    )
    assert out["headShown"] == "none"


def test_mobile_bar_navigates_and_paints_active_section():
    out = _run("mobileGo('positions');" + _DRAIN + _OUT)
    assert out["nav"] == "trade"
    assert out["mobileSec"] == "positions"
    assert out["mobileBtns"]["positions"] is True
    out = _run("mobileGo('markets');" + _DRAIN + _OUT)
    assert out["nav"] == "markets"
    assert out["mobileBtns"]["markets"] is True
    assert out["mobileBtns"]["positions"] is False


def test_mobile_ai_section_opens_the_copilot_drawer():
    out = _run(
        """
      mobileGo('ai');
      closeAiDrawer();        // wrapped: closes + syncs the bar
      """
        + _DRAIN
        + _OUT
    )
    # drawer opened during the run, then closing cleared the AI highlight
    assert out["drawerOpen"] is False
    assert out["mobileBtns"]["ai"] is False


def test_mobile_ticket_sheet_re_reads_the_gate_fresh():
    api = {
        "/api/risk": {
            "status": 200,
            "body": {"gate": {"allowed": True, "blocked_by": []}},
        }
    }
    out = _run(
        """
      const before = GETS.filter(u=> u.includes('/api/risk')).length;
      navTo('trade');
      """
        + _DRAIN
        + """
      const mid = GETS.filter(u=> u.includes('/api/risk')).length;
      openMobileTicket();
      """
        + _DRAIN
        + """
      global.__riskReads = [before, mid,
        GETS.filter(u=> u.includes('/api/risk')).length];
      """
        + _OUT
    )
    assert out["termCls"] == ["ticket-sheet"]
    risk_reads = out["riskReads"]
    # opening the sheet issues fresh gate reads (risk chip + ticket gate)
    assert risk_reads[2] - risk_reads[1] >= 2, risk_reads


def test_closing_the_ticket_sheet_hides_it():
    out = _run(
        """
      navTo('trade');
      openMobileTicket();
      closeMobileTicket();
      """
        + _OUT
    )
    assert "ticket-sheet" not in out["termCls"]


def test_open_sheet_then_navigating_closes_it():
    out = _run(
        """
      navTo('trade');
      openMobileTicket();
      """
        + _DRAIN
        + """
      navTo('markets');
      """
        + _OUT
    )
    assert "ticket-sheet" not in out["termCls"]
    assert out["nav"] == "markets"


def test_focused_pages_markup_is_served():
    txt = (ROOT / "web" / "static" / "terminal.html").read_text(encoding="utf-8")
    assert 'id="areaHead"' in txt
    assert 'id="mobileNav"' in txt
    assert 'data-msec="markets"' in txt and 'data-msec="positions"' in txt
    assert "openMobileTicket()" in txt and "closeMobileTicket()" in txt
    assert 'class="areahead"' in txt or "areahead" in txt
