/* ═══════════════════════════════════════════════════════════════════════
   SKY Trade Terminal — view routing, watchlist, trade ticket, bottom
   panel, AI Copilot. Advisory UI only: every mutation still goes through
   the existing server-side endpoints and the risk gate.
   ═══════════════════════════════════════════════════════════════════════ */

/* ── View routing: 6 primary areas ──────────────────────────────────── */
function isRealBrowser(){
  try{ return typeof window!=='undefined' && !!window.document && window.document===document; }catch(e){ return false; }
}

const NAV_TABS = {
  trade:     [],                                    // terminal has its own loaders
  markets:   ['overview', 'market', 'intelligence'],
  portfolio: ['trades', 'manage', 'risk', 'weekly'],
  journal:   ['journal'],
  evidence:  ['evidence', 'learn'],
  system:    ['connections', 'commands', 'modules', 'system', 'agent'],
};
const LEGACY_NAVS = ['markets', 'portfolio', 'journal', 'evidence', 'system'];
let _currentNav = 'trade';

function navTo(nav){
  _currentNav = nav;
  try{
    document.querySelectorAll('.navbtn').forEach(b=> b.classList.toggle('active', b.dataset.nav===nav));
    const tradeView=document.getElementById('view-trade');
    const legacyView=document.getElementById('view-legacy');
    if(tradeView) tradeView.classList.toggle('active', nav==='trade');
    if(legacyView) legacyView.classList.toggle('active', LEGACY_NAVS.indexOf(nav)>=0);
  }catch(e){}
  try{ if(typeof localStorage !== 'undefined') localStorage.setItem('sky.nav', nav); }catch(e){}
  // load the panels that belong to this area
  const tabs = NAV_TABS[nav] || [];
  if(tabs.length){
    // show only this area's tabpanels inside the legacy shell
    try{
      document.querySelectorAll('.tabpanel').forEach(p=> p.classList.toggle('active', tabs.indexOf(p.dataset.tab)>=0));
    }catch(e){}
    tabs.forEach(t=>{
      try{ if(typeof onTabShown === 'function') onTabShown(t); }catch(e){}
    });
  }
  if(nav === 'trade'){
    loadTerminal();
  }
  try{ if(typeof history !== 'undefined' && history.replaceState) history.replaceState(null, '', '#'+nav); }catch(e){}
}

// re-apply the active panel set after render() rebuilds #app
function applyNavPanels(){
  const nav=_currentNav||'trade';
  const tabs=NAV_TABS[nav]||[];
  if(!tabs.length) return;
  try{
    document.querySelectorAll('.tabpanel').forEach(p=> p.classList.toggle('active', tabs.indexOf(p.dataset.tab)>=0));
  }catch(e){}
}

// allow old switchTab('chart') semantics to land on the terminal
const _origSwitchTab = window.switchTab;
if(typeof _origSwitchTab === 'function'){
  window.switchTab = function(tab){
    if(tab === 'chart' || tab === 'trade'){ navTo('trade'); return; }
    _origSwitchTab(tab);
  };
}

/* ── Terminal lifecycle ─────────────────────────────────────────────── */
let _termLoaded = false;
async function loadTerminal(){
  if(_termLoaded) return;
  _termLoaded = true;
  try{ loadWatchlistPrices(); }catch(e){}
  try{ loadChartWorkspace(false); }catch(e){}
  try{ loadTerminalPositions(); }catch(e){}
  try{ loadTicketMeta(); }catch(e){}
  try{ renderBottomTab('positions'); }catch(e){}
  try{ renderBottomTab('orders'); }catch(e){}
  try{ renderBottomTab('history'); }catch(e){}
  try{ renderBottomTab('journal'); }catch(e){}
  try{ renderBottomTab('evidence'); }catch(e){}
  try{ renderBottomTab('activity'); }catch(e){}
  try{ loadRiskChip(); }catch(e){}
}

// T4 — loading skeletons: shimmer rows painted before any fetch resolves,
// so a slow feed reads as "loading" rather than a blank panel.
function _skeleton(rows){
  rows=rows||3;
  return '<div class="skel skel-row"></div>'.repeat(rows);
}

/* ── Top-bar status chips ───────────────────────────────────────────── */
async function loadRiskChip(){
  const chip=document.getElementById('riskChip'), txt=document.getElementById('riskTxt');
  try{
    const d=await (await fetch('/api/risk')).json();
    const gate=d.gate || d || {};
    const allowed = (gate.allowed !== undefined) ? gate.allowed : (gate.status !== 'blocked');
    if(chip){
      chip.className = 'status-chip ' + (allowed ? 'ok' : 'blocked');
      chip.title = (gate.blocked_by||[]).join('; ') || 'risk gate';
    }
    if(txt) txt.textContent = allowed ? 'gate open' : 'gate blocked';
  }catch(e){
    if(chip){ chip.className='status-chip warn'; chip.title='risk gate unknown'; }
    if(txt) txt.textContent = 'gate ?';
  }
}

async function loadFeedChip(){
  const chip=document.getElementById('feedChip'), txt=document.getElementById('feedTxt');
  try{
    const d=await (await fetch('/api/readiness')).json();
    const lvl=d.level || 'ok';
    if(chip){
      chip.className = 'status-chip ' + (lvl==='ok'?'ok':(lvl==='degraded'?'warn':'blocked'));
      chip.title = (d.detail||[]).map(x=>x.label+': '+x.level).join('; ') || 'data readiness';
    }
    if(txt) txt.textContent = lvl==='ok' ? 'data fresh' : lvl;
  }catch(e){
    if(chip){ chip.className='status-chip warn'; }
    if(txt) txt.textContent = 'data ?';
  }
}

/* ── Terminal watchlist ─────────────────────────────────────────────── */
let _wlPrices = [];
async function loadWatchlistPrices(){
  const list=document.getElementById('wlList'); if(!list) return;
  const had = _wlPrices && _wlPrices.length;
  if(!had){
    list.innerHTML=_skeleton(5);
  }
  try{
    const d=await (await fetch('/api/agents')).json();
    _wlPrices = (d.assets||[]).map(a=>({
      symbol:a.symbol, action:a.desk_action||a.action||'NO TRADE',
      price:a.entry, change:a.change_pct_24h, reason:a.reason||'', conf:a.confidence_pct,
    }));
    renderTerminalWatchlist();
  }catch(e){
    if(!had) list.innerHTML='<div class="b-empty">watchlist unavailable — '+esc(String(e))+'</div>';
  }
}

function renderTerminalWatchlist(){
  const list=document.getElementById('wlList'); if(!list) return;
  const q=((document.getElementById('wlSearch')||{}).value||'').toUpperCase().trim();
  const rows=_wlPrices.filter(w=> !q || w.symbol.includes(q));
  if(!rows.length){
    list.innerHTML='<div class="b-empty">no symbols match</div>';
    return;
  }
  const cur=(document.getElementById('sym')||{}).value||'BTCUSDT';
  list.innerHTML=rows.map(w=>{
    const chg=w.change;
    const chgCls = chg==null ? 'flat' : (chg>=0?'pos':'neg');
    const chgTxt = chg==null ? '—' : ((chg>=0?'+':'')+Number(chg).toFixed(2)+'%');
    return `<div class="wl-row ${w.symbol===cur?'active':''}" onclick="setSymbol('${esc(w.symbol)}')">
      <span class="s">${esc(w.symbol)}</span>
      <span class="p">${w.price? '$'+fmt(w.price,2): '—'}</span>
      <span class="chg ${chgCls}">${chgTxt}</span>
    </div>`;
  }).join('');
}

/* ── Terminal positions (compact, left + bottom) ────────────────────── */
async function loadTerminalPositions(){
  try{
    const d=await (await fetch('/api/trades')).json();
    const rows=d.open||[];
    const open=rows.filter(r=> ['OPEN','WAITING_ENTRY'].includes(r.status||''));
    const count=document.getElementById('wlPosCount');
    if(count) count.textContent=String(open.length);
    const posChip=document.getElementById('posChip'), posTxt=document.getElementById('posTxt');
    if(posChip) posChip.className='status-chip '+(open.length?'warn':'ok');
    if(posTxt) posTxt.textContent=open.length+' open';
    const host=document.getElementById('wlPositions');
    if(host){
      if(!open.length) host.innerHTML='<div class="b-empty">no open positions</div>';
      else host.innerHTML=open.map(p=>{
        const rr=p.current_r!=null?p.current_r:(p.rr_achieved!=null?p.rr_achieved:null);
        const rrTxt=rr==null?'—':((rr>=0?'+':'')+Number(rr).toFixed(2)+'R');
        const rrCls=rr==null?'':(rr>=0?'okc':'err');
        return `<div class="wl-row" onclick="selectBottomPosition('${esc(p.id||p.trade_id||'')}')">
          <span class="s">${esc(p.symbol||'?')}</span>
          <span class="p ${rrCls}">${rrTxt}</span>
        </div>`;
      }).join('');
    }
  }catch(e){}
}

/* ── Trade ticket ───────────────────────────────────────────────────── */
let _ticketSide='BUY', _ticketType='market', _ticketPayload=null;

function ticketSide(side){
  _ticketSide=side;
  document.querySelectorAll('.ticket-side button').forEach(b=>{
    b.classList.toggle('active', (b.classList.contains('buy')&&side==='BUY')||(b.classList.contains('sell')&&side==='SELL'));
  });
  recalcTicket();
}
function ticketType(t){
  _ticketType=t;
  document.querySelectorAll('.ticket-type button').forEach(b=> b.classList.toggle('active', b.dataset.otype===t));
  recalcTicket();
}
function switchOrderTab(tab){
  document.querySelectorAll('.order-tabs button').forEach(b=> b.classList.toggle('active', b.dataset.otab===tab));
  document.querySelectorAll('.otab').forEach(o=> o.classList.toggle('active', o.id==='otab-'+tab));
}

function fillTicketFromSignal(d, opts){
  if(!d) return;
  opts=opts||{};
  _ticketPayload=d;
  const s=d.signal||{}, plans=d.plans||[];
  const plan=plans[0]||{};
  const entry=s.entry||plan.entry||null;
  const sl=s.stop_loss||plan.stop_loss||null;
  const tps=(plan.take_profits&&plan.take_profits.length)?plan.take_profits:
            (s.take_profit?[s.take_profit]:[]);
  const skipInputs = !!(opts.dataOnly && (typeof _ticketDirty!=='undefined' && _ticketDirty));
  const set=(id,v)=> { const el=document.getElementById(id); if(el&&v!=null) el.value=v; };
  if(!skipInputs){
    set('tEntry', entry); set('tSL', sl);
    set('tTP1', tps[0]); set('tTP2', tps[1]); set('tTP3', tps[2]);
  }
  // signal tab
  const tab=document.getElementById('otab-signal');
  if(tab){
    const dec=d.decision||{};
    const decOk=dec.action==='BUY'||dec.action==='SELL';
    const gate=dec.gates||{};
    const blocked=(dec.blocked_by||[]).concat(gate.risk&&gate.risk.blocked_by||[]);
    tab.innerHTML=`
      <div class="flex" style="margin-bottom:6px">
        <span class="pill ${cls(s.action)}">${s.action}</span>
        <b>${esc(s.asset||'')} ${esc(s.timeframe||'')}</b>
        <span class="badge">${esc(s.confidence||'')}</span>
        <span class="badge">${esc(dec.regime_label||'')}</span>
      </div>
      <div class="kv">
        <b>Entry</b><span class="mono">${fmt(s.entry)}</span>
        <b>Stop</b><span class="mono" style="color:var(--red)">${fmt(s.stop_loss)}</span>
        <b>Target</b><span class="mono" style="color:var(--green)">${fmt(s.take_profit)}</span>
        <b>Reason</b><span>${esc(s.reason||'')}</span>
      </div>
      <div class="sep"></div>
      <div class="t-mini"><span>Desk decision</span>
        <span class="pill ${decOk?'BUY':'NOTRADE'}" style="padding:1px 7px;font-size:10px">${decOk?('TRADE '+dec.action):'WAIT — NO TRADE'}</span>
      </div>
      ${blocked.length?`<div class="t-gate blocked">${blocked.map(b=>'✗ '+esc(b)).join('<br>')}</div>`:''}
      <div class="t-mini"><span>Setup</span><span id="tSetup2">${esc(dec.plan_type||plan.type||'—')}</span></div>
      <div class="t-mini"><span>Signal id</span><span class="mono">${esc(s.signal_id||'—')}</span></div>
    `;
  }
  // risk tab
  const rtab=document.getElementById('otab-risk');
  if(rtab){
    const risk=d.risk||d.risk_gate||{};
    rtab.innerHTML=`
      <div class="kv">
        <b>Gate</b><span class="pill ${risk.allowed===false?'NOTRADE':'BUY'}" style="padding:1px 7px;font-size:10px">${risk.allowed===false?'BLOCKED':'OPEN'}</span>
        <b>Daily loss</b><span>${esc(String(risk.daily_pct!=null?risk.daily_pct+'%':'—'))}</span>
        <b>Weekly loss</b><span>${esc(String(risk.weekly_pct!=null?risk.weekly_pct+'%':'—'))}</span>
        <b>Drawdown</b><span>${esc(String(risk.drawdown_pct!=null?risk.drawdown_pct+'%':'—'))}</span>
        <b>Trader state</b><span>${esc(risk.trader_state&&risk.trader_state.blocked?'⚠ blocked':'clear')}</span>
      </div>
      ${(risk.blocked_by||[]).length?`<div class="t-gate blocked">${risk.blocked_by.map(b=>'✗ '+esc(b)).join('<br>')}</div>`:''}
    `;
  }
  recalcTicket();
  try{ loadTicketGate(); }catch(e){}
}

// Fresh server-side gate read for the ticket preview (the confirm endpoint
// re-evaluates it again immediately before the decision).
async function loadTicketGate(){
  try{
    const d=await (await fetch('/api/risk')).json();
    const g=d.gate||{};
    const gateEl=document.getElementById('tGate');
    if(!gateEl) return;
    if(g.allowed===false){
      gateEl.className='t-gate blocked';
      gateEl.innerHTML='Risk gate BLOCKED — '+(g.blocked_by||[]).map(b=>esc(b)).join('; ')+'<br><span class="note">re-checked server-side at confirm</span>';
    }else{
      gateEl.className='t-gate ok';
      gateEl.innerHTML='Risk gate OPEN (live read) — re-checked server-side immediately before confirm.';
    }
  }catch(e){}
}

function recalcTicket(){
  const side=_ticketSide;
  const entry=parseFloat(document.getElementById('tEntry')?.value);
  const sl=parseFloat(document.getElementById('tSL')?.value);
  const tp1=parseFloat(document.getElementById('tTP1')?.value);
  const riskPct=parseFloat(document.getElementById('tRisk')?.value)||0.5;
  const rrEl=document.getElementById('tRR');
  const feeEl=document.getElementById('tFees');
  const riskUsdEl=document.getElementById('tRiskUsd');
  const sizeEl=document.getElementById('tSize');
  const gateEl=document.getElementById('tGate');
  const confirmEl=document.getElementById('tConfirm');
  if(!entry || !sl){
    if(rrEl) rrEl.textContent='—';
    if(confirmEl){ confirmEl.disabled=true; }
    return;
  }
  const risk=Math.abs(entry-sl);
  if(tp1 && risk>0){
    const rr=Math.abs(tp1-entry)/risk;
    if(rrEl) rrEl.textContent=rr.toFixed(2);
  } else if(rrEl) rrEl.textContent='—';
  // T4 — honest sizing: real account balance from /api/ticket/meta, never an
  // invented $100k. Risk dollars and units stay "—" until the account exists.
  const meta=_ticketMeta||{};
  const account=Number(meta.account_balance)||0;
  let size=null;
  if(account>0){
    const riskUsd=account*(riskPct/100);
    if(riskUsdEl) riskUsdEl.textContent='$'+riskUsd.toFixed(0);
    size=riskUsd/risk;
    if(sizeEl) sizeEl.value=isFinite(size)?size.toFixed(size<1?6:4):'—';
    if(sizeEl) sizeEl.title='units so that being wrong costs exactly '+riskPct+'% of account';
  } else {
    if(riskUsdEl) riskUsdEl.textContent='—';
    if(sizeEl){ sizeEl.value='—'; sizeEl.title='Set ACCOUNT_BALANCE in .env to enable sizing'; }
  }
  // T4 — honest fees from the same cost model the backtester uses
  // (round-trip taker fee + full spread + slippage). The % is always shown;
  // the dollar figure needs a sized notional.
  const rtPct=Number(meta.round_trip_cost_pct);
  if(isFinite(rtPct) && rtPct>0){
    if(size && entry>0){
      const notional=size*entry;
      if(feeEl) feeEl.textContent='~$'+(notional*rtPct).toFixed(2)+' ('+(rtPct*100).toFixed(2)+'% rt)';
    } else if(feeEl){
      feeEl.textContent=(rtPct*100).toFixed(2)+'% round-trip';
    }
  } else if(feeEl) feeEl.textContent='—';
  // gate verdict
  const d=_ticketPayload||{};
  const dec=d.decision||{};
  const gate=dec.gates&&dec.gates.risk||{};
  const blocked=(dec.blocked_by||[]).concat(gate.blocked_by||[]);
  if(gateEl){
    if(blocked.length){
      gateEl.className='t-gate blocked';
      gateEl.innerHTML='Risk gate BLOCKED — '+blocked.map(b=>esc(b)).join('; ');
      if(confirmEl) confirmEl.disabled=true;
    } else {
      gateEl.className='t-gate ok';
      gateEl.innerHTML='Risk gate preview <b>OPEN</b> — the server re-checks it immediately before confirm.';
      if(confirmEl) confirmEl.disabled=false;
    }
  }
}

let _ticketMeta=null;
async function loadTicketMeta(){
  try{
    const sym=(document.getElementById('sym')||{}).value||'BTCUSDT';
    const d=await (await fetch('/api/ticket/meta?symbol='+encodeURIComponent(sym))).json();
    if(d && typeof d.account_balance==='number') _ticketMeta=d;
  }catch(e){ _ticketMeta=null; }
  recalcTicket();
}

let _ticketId=null, _ticketSig=null;
function ticketSignature(){
  const v=(id)=>String(document.getElementById(id)?.value||'');
  return [_ticketSide,_ticketType,v('tEntry'),v('tSL'),v('tTP1'),v('tTP2'),v('tTP3'),v('tRisk')].join('|');
}
async function submitPaperTicket(){
  const entry=parseFloat(document.getElementById('tEntry')?.value);
  const sl=parseFloat(document.getElementById('tSL')?.value);
  const tp1=parseFloat(document.getElementById('tTP1')?.value);
  const tp2=parseFloat(document.getElementById('tTP2')?.value);
  const tp3=parseFloat(document.getElementById('tTP3')?.value);
  const riskPct=parseFloat(document.getElementById('tRisk')?.value)||0.5;
  if(!entry||!sl){ showToast('Entry and stop are required','err'); return; }
  if((_ticketSide==='BUY'&&sl>=entry)||(_ticketSide==='SELL'&&sl<=entry)){
    showToast('Stop is on the wrong side of entry for '+_ticketSide,'err'); return;
  }
  // A retried confirm reuses the same ticket id so the server cannot
  // enroll the same ticket twice; editing any field starts a new ticket.
  const sig=ticketSignature();
  if(_ticketSig!==sig){ _ticketId=null; _ticketSig=sig; }
  if(!_ticketId){
    _ticketId='t_'+(typeof crypto!=='undefined'&&crypto.randomUUID
      ?crypto.randomUUID():String(Date.now())+'-'+Math.floor(Math.random()*1e9));
  }
  const d=_ticketPayload||{};
  const s=d.signal||{};
  const plan=(d.plans||[])[0]||{};
  const dec=d.decision||{};
  const confirmEl=document.getElementById('tConfirm');
  if(confirmEl){ confirmEl.disabled=true; confirmEl.textContent='Confirming — server gate check…'; }
  const body={
    ticket_id:_ticketId,
    symbol:s.asset||'BTCUSDT',
    timeframe:s.timeframe||'15m',
    action:_ticketSide,
    ticket_type:_ticketType,
    entry:entry, stop_loss:sl,
    take_profits:[tp1,tp2,tp3].filter(v=>v!=null&&!isNaN(v)),
    risk_pct:riskPct,
    plan_type:plan.type||dec.plan_type||'Manual',
    confidence:plan.confidence!=null?plan.confidence:(dec.confidence||null),
    confidence_label:plan.confidence_label||s.confidence||null,
    reason:plan.condition||dec.reason||'terminal paper ticket',
    sentiment:(d.sentiment&&d.sentiment.available!==false)?{bucket:d.sentiment.bucket,score:d.sentiment.score,intensity:d.sentiment.intensity}:null,
  };
  const post=async(extra)=>{
    const res=await fetch('/api/terminal/confirm',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.assign({},body,extra||{}))});
    let j=null; try{ j=await res.json(); }catch(e){}
    return {res,j};
  };
  const release=()=>{ if(confirmEl){ confirmEl.disabled=false; confirmEl.textContent='Confirm Paper Trade'; } };
  try{
    const first=await post();
    const jd=first.j||{};
    if(!first.res.ok||jd.ok===false){
      if(jd.journal_block&&jd.acknowledge_available){
        const NL=String.fromCharCode(10);
        const ids=((jd.journal_block.trades||[]).map(t=>'#'+t.scan_id+' '+t.outcome).join(NL))||'';
        if(typeof confirm==='function'&&confirm(jd.error+NL+NL+ids+NL+NL+'OK = confirm anyway (audited) · Cancel = go journal now')){
          const second=await post({acknowledge_journal:true});
          if(second.res.ok&&second.j&&second.j.ok){ finishConfirm(second.j); }
          else{ showToast((second.j&&second.j.error)||'still blocked by the desk','err'); }
        }else{
          showToast('Journal first — confirm held','err');
          switchBottomTab('journal');
        }
      }else{
        showToast(jd.error||'blocked by risk gate','err');
        const gateEl=document.getElementById('tGate');
        if(gateEl&&jd.blocked_by&&jd.blocked_by.length){
          gateEl.className='t-gate blocked';
          gateEl.innerHTML='Risk gate BLOCKED (server) — '+jd.blocked_by.map(b=>esc(b)).join('; ')
            +(jd.force_available?'<br><span class="note">Force confirm is enabled (SKY_ALLOW_FORCE_APPROVE) — every force is audited.</span>':'');
        }
      }
      release();
      return;
    }
    finishConfirm(first.j||{});
  }catch(e){
    showToast('Ticket error: '+String(e),'err');
    release();
  }
}
function finishConfirm(j){
  _ticketId=null; // the ticket is used — the next confirm starts a new one
  const t=j.paper_trade||{};
  const waiting=(t.status||'')==='WAITING_ENTRY';
  const confirmEl=document.getElementById('tConfirm');
  if(confirmEl){ confirmEl.disabled=false; confirmEl.textContent='Confirm Paper Trade'; }
  const gateEl=document.getElementById('tGate');
  if(gateEl&&j.gate){
    if(j.gate.blocked_by&&j.gate.blocked_by.length){
      gateEl.className='t-gate blocked';
      gateEl.innerHTML='Risk gate BLOCKED — '+j.gate.blocked_by.map(b=>esc(b)).join('; ');
    }else{
      gateEl.className='t-gate ok';
      gateEl.innerHTML='Risk gate OPEN — paper trade confirmed through the desk approval path.';
    }
  }
  if(waiting){
    showToast('Ticket confirmed — waiting for entry at '+fmt(t.entry),'ok');
  }else if((t.status||'')==='CLOSED'){
    const rrTxt=t.rr_achieved!=null?((t.rr_achieved>=0?'+':'')+Number(t.rr_achieved).toFixed(2)+'R'):'';
    showToast('Paper position #'+(t.id||j.scan_id)+' filled and already closed by the runner — '+esc(t.outcome||'')+' '+rrTxt+' (journal it below)','ok');
    _journalTarget={scan_id:t.scan_id,outcome:t.outcome,rr_achieved:t.rr_achieved,exit_price:t.exit_price};
    try{ switchBottomTab('journal'); }catch(e){}
  }else{
    showToast('Paper position open — #'+(t.id||j.scan_id)+' '+esc(t.action||'')+' '+esc(t.symbol||'')+' @ '+fmt(t.entry_price||t.entry),'ok');
  }
  switchBottomTab('positions');
  try{ loadTerminalPositions(); }catch(e){}
  try{ loadRiskChip(); }catch(e){}
}

/* ── Bottom panel ───────────────────────────────────────────────────── */
let _bottomTab='positions';
let _selectedPosId=null;
function switchBottomTab(tab){
  document.querySelectorAll('.bottom-tabs button').forEach(b=> b.classList.toggle('active', b.dataset.btab===tab));
  document.querySelectorAll('.bottom-content').forEach(c=> c.classList.toggle('active', c.id==='btab-'+tab));
  _bottomTab=tab;
  renderBottomTab(tab);
}

async function renderBottomTab(tab){
  const host=document.getElementById('btab-'+tab); if(!host) return;
  // Alerts has static content (push buttons) painted by the push path — never
  // overwrite it with a skeleton.
  if(tab==='alerts') return;
  // T4 — drop the one-shot cache: every switch re-fetches so a position the
  // runner just closed cannot linger as a stale row. Skeleton while fetching.
  host.innerHTML=_skeleton(3);
  try{
    if(tab==='positions') await paintBottomPositions(host);
    else if(tab==='orders') await paintBottomOrders(host);
    else if(tab==='history') await paintBottomHistory(host);
    else if(tab==='journal') await paintBottomJournal(host);
    else if(tab==='evidence') await paintBottomEvidence(host);
    else if(tab==='activity') await paintBottomActivity(host);
  }catch(e){
    host.innerHTML='<div class="b-empty">'+esc(String(e))+'</div>';
  }
}

// re-fetch one bottom tab (positions after confirm/close, journal after save)
function refreshBottomTab(tab){
  renderBottomTab(tab);
}

async function paintBottomPositions(host){
  const d=await (await fetch('/api/trades')).json();
  const rows=d.open||[];
  if(!rows.length){
    host.innerHTML='<div class="b-empty">no open paper positions — confirm a ticket above to open one</div>';
    _selectedPosId=null;
    return;
  }
  host.innerHTML=`<table class="b-table"><thead><tr>
    <th>#</th><th>Symbol</th><th>Side</th><th>Entry</th><th>SL</th><th>TP</th>
    <th>Current</th><th>R</th><th>MAE / MFE</th><th>Status</th><th></th></tr></thead><tbody>
    ${rows.map(p=>{
      const id=p.id||p.trade_id||'';
      const cur=p.current_price!=null?p.current_price:(p.entry_price||p.entry);
      const rr=p.current_r!=null?p.current_r:(p.rr_achieved!=null?p.rr_achieved:null);
      const mae=p.mae!=null?(Number(p.mae)<0?'':'+')+Number(p.mae).toFixed(2)+'R':'—';
      const mfe=p.mfe!=null?(Number(p.mfe)<0?'':'+')+Number(p.mfe).toFixed(2)+'R':'—';
      return `<tr class="b-pos-row" onclick="selectBottomPosition('${esc(id)}')">
        <td>#${esc(id)}</td>
        <td><b>${esc(p.symbol||'?')}</b></td>
        <td><span class="pill ${cls(p.action||p.side||'')}" style="padding:1px 6px;font-size:9.5px">${esc(p.action||p.side||'—')}</span></td>
        <td class="mono">${fmt(p.entry_price||p.entry)}</td>
        <td class="mono">${fmt(p.stop_loss)}</td>
        <td class="mono">${fmt(p.take_profit||(p.take_profits&&p.take_profits[0]))}</td>
        <td class="mono">${fmt(cur)}</td>
        <td class="mono ${rr!=null?(rr>=0?'okc':'err'):''}">${rr!=null?((rr>=0?'+':'')+rr.toFixed(2)+'R'):'—'}</td>
        <td class="note">${mae} / ${mfe}</td>
        <td><span class="badge">${esc(p.status||'—')}</span></td>
        <td><button class="btn sm no" onclick="event.stopPropagation();terminalClosePosition('${esc(id)}')">Close</button></td>
      </tr>`;
    }).join('')}
  </tbody></table>
  <div id="posDetail"></div>
  <div class="note" style="margin-top:6px">Click a row for management advice; Close records the outcome and opens the journal. Paper only — no real orders.</div>`;
  if(_selectedPosId) selectBottomPosition(_selectedPosId);
}

async function selectBottomPosition(id){
  if(!id) return;
  _selectedPosId=id;
  const host=document.getElementById('posDetail'); if(!host) return;
  try{
    const d=await (await fetch('/api/trades')).json();
    const p=(d.open||[]).find(r=>String(r.id||r.trade_id)===String(id));
    if(!p){ host.innerHTML='<div class="b-empty">position #'+esc(id)+' is no longer open</div>'; return; }
    const rr=p.current_r!=null?p.current_r:null;
    const mgmt=(p.management||[]).map(m=>'<li>'+esc(m)+'</li>').join('');
    host.innerHTML=`
      <div class="t-gate ${rr!=null&&rr>=0?'ok':'warn'}" style="margin:8px 0">
        <b>Position #${esc(id)} — ${esc(p.symbol||'?')} ${esc(p.action||'')}</b>
        <div style="margin-top:4px">live R <b class="${rr!=null?(rr>=0?'okc':'err'):''}">${rr!=null?((rr>=0?'+':'')+rr.toFixed(2)+'R'):'—'}</b>
          · MAE ${p.mae!=null?Number(p.mae).toFixed(2)+'R':'—'} · MFE ${p.mfe!=null?Number(p.mfe).toFixed(2)+'R':'—'}
          ${p.minutes_in_trade!=null?' · '+p.minutes_in_trade+' min':''}
          ${p.status==='WAITING_ENTRY'?' · waiting for entry '+fmt(p.entry):''}</div>
      </div>
      <div class="kv">
        <b>Entry</b><span class="mono">${fmt(p.entry_price||p.entry)}</span>
        <b>Stop</b><span class="mono" style="color:var(--red)">${fmt(p.stop_loss)}</span>
        <b>Target</b><span class="mono" style="color:var(--green)">${fmt(p.take_profit)}</span>
        <b>Current</b><span class="mono">${fmt(p.current_price)}</span>
        <b>Setup</b><span>${esc(p.plan_type||'—')}</span>
        <b>Status</b><span class="badge">${esc(p.status||'—')}</span>
      </div>
      <div class="note" style="margin:6px 0"><b>Management advice</b><ul style="margin:4px 0 0 16px;padding:0">${mgmt||'<li>—</li>'}</ul></div>
      <div class="flex" style="gap:8px">
        <button class="btn no" onclick="terminalClosePosition('${esc(id)}')">Close Position</button>
        <button class="btn ghost sm" onclick="refreshBottomTab('positions')">↻ Refresh</button>
      </div>`;
  }catch(e){
    host.innerHTML='<div class="b-empty">management unavailable — '+esc(String(e))+'</div>';
  }
}

let _journalTarget=null;
async function terminalClosePosition(id){
  if(typeof confirm==='function' && !confirm('Close paper position #'+id+' at the last market price? The outcome is recorded and the journal opens.')) return;
  try{
    const res=await fetch('/api/terminal/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({trade_id:id})});
    let d=null; try{ d=await res.json(); }catch(e){}
    if(!res.ok||!d||d.ok===false){ showToast((d&&d.error)||'close failed','err'); return; }
    _selectedPosId=null;
    if(d.status==='CLOSED'){
      showToast('Closed #'+id+' — '+d.outcome+' '+(d.rr_achieved!=null?((d.rr_achieved>=0?'+':'')+d.rr_achieved+'R'):'')+' @ '+fmt(d.exit_price),'ok');
      _journalTarget={scan_id:d.scan_id,outcome:d.outcome,rr_achieved:d.rr_achieved,exit_price:d.exit_price};
      refreshBottomTab('positions');
      switchBottomTab('journal'); // close → journal, automatically
    }else{
      showToast('Cancelled #'+id+' — it was still waiting for its entry','ok');
      refreshBottomTab('positions');
    }
    try{ loadTerminalPositions(); }catch(e){}
  }catch(e){ showToast(String(e),'err'); }
}

async function paintBottomOrders(host){
  try{
    const d=await (await fetch('/api/pending')).json();
    const rows=d.pending||d.signals||d.reviews||[];
    if(!rows.length){ host.innerHTML='<div class="b-empty">no pending plans</div>'; return; }
    host.innerHTML=`<table class="b-table"><thead><tr>
      <th>#</th><th>Symbol</th><th>Side</th><th>Entry</th><th>SL</th><th>TP</th><th>Conf</th><th>Status</th><th></th></tr></thead><tbody>
      ${rows.map(r=>`
        <tr>
          <td>#${esc(r.id||r.scan_id||'')}</td>
          <td><b>${esc(r.symbol||'')}</b></td>
          <td><span class="pill ${cls(r.action||'')}" style="padding:1px 6px;font-size:9.5px">${esc(r.action||'—')}</span></td>
          <td class="mono">${fmt(r.entry)}</td>
          <td class="mono">${fmt(r.stop_loss)}</td>
          <td class="mono">${fmt(r.take_profit)}</td>
          <td>${esc(r.confidence_label||r.confidence||'—')}</td>
          <td><span class="badge">${esc(r.status||'—')}</span></td>
          <td><button class="btn sm ok" onclick="decide(${r.id||r.scan_id||0},'APPROVED')">Approve</button>
              <button class="btn sm no" onclick="decide(${r.id||r.scan_id||0},'REJECTED')">✗</button></td>
        </tr>`).join('')}
      </tbody></table>`;
  }catch(e){
    host.innerHTML='<div class="b-empty">pending unavailable — '+esc(String(e))+'</div>';
  }
}

async function paintBottomHistory(host){
  const d=await (await fetch('/api/history')).json();
  const rows=d.history||d.scans||d.rows||[];
  if(!rows.length){ host.innerHTML='<div class="b-empty">no trade history yet</div>'; return; }
  host.innerHTML=`<table class="b-table"><thead><tr>
    <th>#</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Outcome</th><th>Status</th><th>When</th></tr></thead><tbody>
    ${rows.slice(0,40).map(r=>`
      <tr onclick="openModal(${r.id||r.scan_id||0})" style="cursor:pointer">
        <td>#${esc(r.id||r.scan_id||'')}</td>
        <td><b>${esc(r.symbol||'')}</b></td>
        <td><span class="pill ${cls(r.action||'')}" style="padding:1px 6px;font-size:9.5px">${esc(r.action||'—')}</span></td>
        <td class="mono">${fmt(r.entry)}</td>
        <td class="mono">${r.rr_achieved!=null?((r.rr_achieved>=0?'+':'')+Number(r.rr_achieved).toFixed(2)+'R'):'—'}</td>
        <td><span class="badge">${esc(r.status||'—')}</span></td>
        <td class="note">${esc((r.created_at||'').slice(0,16))}</td>
      </tr>`).join('')}
    </tbody></table>`;
}

async function paintBottomJournal(host){
  const d=await (await fetch('/api/journal')).json();
  const entries=d.journalable||d.entries||d.journals||[];
  const stats=d.stats||d.summary||{};
  let form='';
  // T3 — close opens the journal automatically: an inline entry form for
  // the trade that was just closed (followed_rules is the headline field).
  if(_journalTarget){
    try{
      const chk=await (await fetch('/api/journal?scan_id='+encodeURIComponent(_journalTarget.scan_id))).json();
      if(chk.entry&&chk.entry.followed_rules!=null){ _journalTarget=null; }
      else{
        const rrTxt=_journalTarget.rr_achieved!=null?((_journalTarget.rr_achieved>=0?'+':'')+Number(_journalTarget.rr_achieved).toFixed(2)+'R'):'';
        form=`
        <div class="j-form">
          <div class="flex" style="justify-content:space-between;margin-bottom:4px">
            <b style="font-size:11px;text-transform:uppercase">Journal this trade — scan #${esc(_journalTarget.scan_id)}</b>
            <button class="btn sm ghost" onclick="_journalTarget=null;refreshBottomTab('journal')">✕</button>
          </div>
          <div class="note" style="margin:4px 0 8px">Outcome <b class="${_journalTarget.rr_achieved!=null&&_journalTarget.rr_achieved>=0?'okc':'err'}">${esc(_journalTarget.outcome||'—')} ${esc(rrTxt)}</b> @ ${fmt(_journalTarget.exit_price)} — your journal answer unlocks the next approval.</div>
          <div class="t-row">
            <div class="t-field"><label>Did you follow your system?</label>
              <select id="jFollowed"><option value="1">Yes — followed the rules</option><option value="0">No — broke a rule</option></select></div>
            <div class="t-field"><label>Emotion</label>
              <select id="jEmotion">${(d.emotions||[]).map(e=>'<option value="'+esc(e)+'">'+esc(e)+'</option>').join('')}</select></div>
          </div>
          <div class="t-field"><label>Mistake (optional)</label><input id="jMistake" placeholder="what went wrong, if anything"></div>
          <div class="t-field"><label>Notes</label><textarea id="jNotes" rows="2" placeholder="context, what you would change…"></textarea></div>
          <button class="btn primary" onclick="saveTerminalJournal()">Save journal</button>
        </div>`;
      }
    }catch(e){}
  }
  host.innerHTML=`
    ${form}
    ${stats.n!=null?`<div class="flex" style="margin-bottom:8px">
      <span class="badge">${stats.n} recorded</span>
      <span class="badge">violations ${stats.violations||0}</span>
      <span class="badge">rate ${stats.violation_rate!=null?(Number(stats.violation_rate)*100).toFixed(1)+'%':'—'}</span>
    </div>`:''}
    ${entries.length?`<table class="b-table"><thead><tr>
      <th>Trade</th><th>Status</th><th>Followed rules</th><th>Emotion</th><th>Mistake</th><th>Notes</th></tr></thead><tbody>
      ${entries.slice(0,25).map(j=>`
        <tr>
          <td><b>#${esc(j.scan_id||j.trade_id||'')}</b>${j.symbol?' '+esc(j.symbol):''}</td>
          <td><span class="badge">${esc(j.status||'—')}</span></td>
          <td>${j.followed_rules==null?'<span class="badge" style="color:var(--amber)">missing</span>':(j.followed_rules?'<span class="badge" style="color:var(--green)">yes</span>':'<span class="badge" style="color:var(--red)">no</span>')}</td>
          <td>${esc(j.emotion||'—')}</td>
          <td>${esc((j.mistake||'—').slice(0,40))}</td>
          <td class="note">${esc((j.notes||'—').slice(0,60))}</td>
        </tr>`).join('')}
      </tbody></table>`:'<div class="b-empty">no journal entries yet — close a trade and its journal form opens here</div>'}
    `;
}

async function saveTerminalJournal(){
  if(!_journalTarget){ showToast('no journal target','err'); return; }
  try{
    const res=await fetch('/api/journal',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({scan_id:_journalTarget.scan_id,
        followed_rules:(document.getElementById('jFollowed')?.value||'1')==='1',
        emotion:document.getElementById('jEmotion')?.value||'',
        mistake:document.getElementById('jMistake')?.value||'',
        notes:document.getElementById('jNotes')?.value||''})});
    const d=await res.json();
    if(!res.ok||d.ok===false){ showToast(d.error||'journal save failed','err'); return; }
    showToast('Journal saved for scan #'+_journalTarget.scan_id,'ok');
    _journalTarget=null;
    refreshBottomTab('journal');
    try{ loadTerminalPositions(); }catch(e){}
  }catch(e){ showToast(String(e),'err'); }
}

async function paintBottomEvidence(host){
  try{
    const d=await (await fetch('/api/evidence')).json();
    const p=d.progress||d.graduation||{};
    const setups=d.setups||p.by_setup||[];
    host.innerHTML=`
      <div class="flex" style="margin-bottom:8px">
        <span class="badge">${p.paper_samples!=null?'paper samples '+p.paper_samples:'—'}</span>
        <span class="badge">${p.backtest_samples!=null?'backtest '+p.backtest_samples:'—'}</span>
        <span class="badge">${p.expectancy_net!=null?'E_net '+(p.expectancy_net>=0?'+':'')+Number(p.expectancy_net).toFixed(2)+'R':'—'}</span>
        <span class="badge">${p.compliance!=null?'compliance '+(Number(p.compliance)*100).toFixed(0)+'%':'—'}</span>
      </div>
      ${Object.keys(setups).length?`<table class="b-table"><thead><tr>
        <th>Setup</th><th>Samples</th><th>E_net</th><th>Proven</th></tr></thead><tbody>
        ${Object.entries(setups).map(([k,v])=>`
          <tr><td><b>${esc(k)}</b></td>
          <td>${v.paper_samples!=null?v.paper_samples:(v.n||'—')}</td>
          <td class="mono ${v.expectancy_net>=0?'okc':'err'}">${v.expectancy_net!=null?((v.expectancy_net>=0?'+':'')+Number(v.expectancy_net).toFixed(2)+'R'):'—'}</td>
          <td>${v.proven?'<span class="badge" style="color:var(--green)">proven</span>':'<span class="badge">unproven</span>'}</td></tr>`).join('')}
        </tbody></table>`:'<div class="b-empty">no setup evidence yet — build evidence in the Evidence tab</div>'}
    `;
  }catch(e){
    host.innerHTML='<div class="b-empty">evidence unavailable — '+esc(String(e))+'</div>';
  }
}

async function paintBottomActivity(host){
  try{
    const d=await (await fetch('/api/v1/jobs')).json();
    const jobs=(d.data&&d.data.jobs)||d.jobs||[];
    host.innerHTML=`
      ${jobs.length?`<table class="b-table"><thead><tr>
        <th>Job</th><th>Kind</th><th>Status</th><th>Progress</th></tr></thead><tbody>
        ${jobs.slice(0,12).map(j=>`
          <tr>
            <td><b>${esc(j.id||'')}</b></td>
            <td>${esc(j.kind||'')}</td>
            <td><span class="badge">${esc(j.status||'')}</span></td>
            <td>${j.progress!=null?j.progress:''}</td>
          </tr>`).join('')}
        </tbody></table>`:'<div class="b-empty">no background jobs running</div>'}
      <div class="note" style="margin-top:6px">Full controls in System → Command Center.</div>
    `;
  }catch(e){
    host.innerHTML='<div class="b-empty">jobs unavailable</div>';
  }
}

/* ── AI Copilot ─────────────────────────────────────────────────────── */
function openAiDrawer(){ const d=document.getElementById('aiDrawer'); if(d) d.classList.add('open'); }
function closeAiDrawer(){ const d=document.getElementById('aiDrawer'); if(d) d.classList.remove('open'); }

function aiContext(){
  const sym=(document.getElementById('sym')||{}).value||'BTCUSDT';
  const tf=(document.getElementById('tf')||{}).value||'15m';
  const d=window._skyPayload||{};
  const s=d.signal||{};
  const dec=d.decision||{};
  const gate=dec.gates&&dec.gates.risk||{};
  const parts=[];
  parts.push('Selected market: '+sym+' on '+tf);
  if(s.action) parts.push('Latest engine signal: '+s.action+' ('+(s.confidence||'')+') for '+sym+' — reason: '+(s.reason||''));
  if(dec.action) parts.push('Desk decision: '+dec.action+(dec.plan_type?' ('+dec.plan_type+')':'')+(dec.regime_label?' — regime '+dec.regime_label:''));
  if((dec.blocked_by||[]).length) parts.push('Desk blocked because: '+(dec.blocked_by||[]).join('; '));
  if(gate.blocked_by&&gate.blocked_by.length) parts.push('Risk gate blocked because: '+gate.blocked_by.join('; '));
  if(d.mtf) parts.push('MTF: HTF '+d.mtf.htf_bias+' / LTF '+d.mtf.ltf_bias+' (alignment '+(d.mtf.alignment&&d.mtf.alignment.label||'?')+')');
  if(d.sentiment) parts.push('Sentiment: '+(d.sentiment.label||d.sentiment.bucket||'neutral'));
  const _nl=String.fromCharCode(10);
  return parts.join(_nl);
}

function aiAsk(question){
  const input=document.getElementById('aiInput');
  if(input) input.value=question;
  aiSend('drawer');
}

// T2 — prepare the ticket from the desk plan. Advisory only: fills the
// ticket fields and switches to the Ticket tab, but never confirms and
// never touches the server. The human still reviews and Confirms.
function aiPrepareTicket(){
  const d=window._skyPayload||{};
  const s=d.signal||{};
  const dec=d.decision||{};
  const action=(dec.action==='BUY'||dec.action==='SELL')?dec.action
              :(s.action==='BUY'||s.action==='SELL')?s.action:null;
  if(!action){
    showToast('No actionable desk plan right now — the desk says stand aside','err');
    return;
  }
  ticketSide(action);
  ticketType('market');
  fillTicketFromSignal(d);
  switchOrderTab('ticket');
  showToast('Ticket prepared from the desk plan — advisory only; you still review & Confirm','ok');
}

function aiAppendMsg(container, who, text, sections){
  const msg=document.createElement('div');
  msg.className='ai-msg '+who;
  if(sections){
    let html='';
    for(const [k,v] of Object.entries(sections)){
      if(!v) continue;
      html+='<div class="ai-sec">'+esc(k.toUpperCase())+'</div>'+esc(v)+String.fromCharCode(10);
    }
    msg.innerHTML=html;
  } else {
    msg.textContent=text;
  }
  container.appendChild(msg);
  container.scrollTop=container.scrollHeight;
}

function aiAppendSources(container, sources){
  const msg=document.createElement('div');
  msg.className='ai-msg bot ai-sources';
  msg.textContent='Sources: '+(sources||[]).join(' · ');
  container.appendChild(msg);
  container.scrollTop=container.scrollHeight;
}

async function aiSend(which){
  const isDrawer = which==='drawer';
  const input=isDrawer?document.getElementById('aiInput'):document.getElementById('otabAiInput');
  const chat=isDrawer?document.getElementById('aiChat'):document.getElementById('otabChat');
  if(!input||!chat) return;
  const q=input.value.trim();
  if(!q) return;
  input.value='';
  aiAppendMsg(chat,'user',q);
  const typing=document.createElement('div');
  typing.className='ai-typing'; typing.textContent='SKY is thinking…';
  chat.appendChild(typing);
  try{
    // Tell the desk which market the trader is looking at — the backend
    // answers about THIS symbol/timeframe, not the server default.
    const sym=(document.getElementById('sym')||{}).value||'BTCUSDT';
    const tf=(document.getElementById('tf')||{}).value||'15m';
    const ctx=aiContext();
    const res=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q, context:ctx, symbol:sym, tf:tf})});
    const d=await res.json();
    typing.remove();
    // The backend returns answer as a list of lines; join them, then render
    // its own structured sections when present. Never double-print the raw
    // text — the sections ARE the answer, formatted.
    const answer = Array.isArray(d.answer)
      ? d.answer.join(String.fromCharCode(10))
      : (d.answer||d.message||(d.error?('⚠ '+d.error):'no answer'));
    const sections = Array.isArray(d.sections)
      ? d.sections.filter(s=> s && String(s.body||'').trim())
      : null;
    if(sections && sections.length){
      const byTitle={};
      for(const s of sections){
        byTitle[s.title||'Answer'] = s.body;
      }
      aiAppendMsg(chat,'bot',null,byTitle);
    } else {
      aiAppendMsg(chat,'bot',String(answer));
    }
    if(d.sources&&d.sources.length){
      aiAppendSources(chat,d.sources);
    }
  }catch(e){
    typing.remove();
    aiAppendMsg(chat,'bot','⚠ '+String(e));
  }
}

/* ── init ───────────────────────────────────────────────────────────── */
(function(){
  try{
    const nav=localStorage.getItem('sky.nav');
    const h=(typeof location!=='undefined'&&location.hash||'').replace('#','');
    const target=h&&['trade','markets','portfolio','journal','evidence','system'].includes(h)?h:(nav||'trade');
    document.querySelectorAll('.navbtn').forEach(b=> b.classList.toggle('active', b.dataset.nav===target));
    const tradeView=document.getElementById('view-trade');
    const legacyView=document.getElementById('view-legacy');
    if(tradeView) tradeView.classList.toggle('active', target==='trade');
    if(legacyView) legacyView.classList.toggle('active', LEGACY_NAVS.indexOf(target)>=0);
    _currentNav=target;
    if(!isRealBrowser()) return;   // jsdom/CI harness: no auto-loading
    if(target==='trade'){
      try{ loadTerminal(); }catch(e){}
    } else {
      const tabs=NAV_TABS[target]||[];
      try{
        document.querySelectorAll('.tabpanel').forEach(p=> p.classList.toggle('active', tabs.indexOf(p.dataset.tab)>=0));
      }catch(e){}
    }
  }catch(e){}
})();

// store the last payload so the ticket/copilot can use it
(function(){
  const _r=window.render;
  if(typeof _r==='function'){
    window.render=function(d){
      window._skyPayload=d;
      try{ fillTicketFromSignal(d, {dataOnly: typeof _ticketDirty!=='undefined' && !!_ticketDirty}); }catch(e){}
      const out=_r(d);
      try{ applyNavPanels(); }catch(e){}
      return out;
    };
  }
})();

// periodic refresh of terminal surfaces
(function(){
  if(!isRealBrowser()) return;
  try{
    setInterval(()=>{
      if(_currentNav!=='trade') return;
      try{ loadWatchlistPrices(); }catch(e){}
      try{ loadTerminalPositions(); }catch(e){}
      try{ loadRiskChip(); }catch(e){}
      try{ loadFeedChip(); }catch(e){}
      // keep the visible bottom tab fresh — positions R / MAE / MFE live
      try{ if(_bottomTab==='positions'&&!_journalTarget) refreshBottomTab('positions'); }catch(e){}
    }, 60000);
  }catch(e){}
})();
