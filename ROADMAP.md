# SKY — Combined Roadmap

> **Status:** active source of truth
> **Last updated:** 2026-08-20
> **Current software:** v2.52.0
> **Suite at this version:** 1282 passed / 1 skipped (offline)
>
> **This file + `TODO.md` win** when other roadmaps, anatomy notes, or
> workstation plans conflict. Older files remain as historical
> specifications, not competing queues.
>
> Written after reviewing merged PRs through **#72**. Every status
> below is a claim about the repository, not a wish.

---

## 0. The aim (never changes)

**Become a fully independent, consistently profitable trader.**

Independence means the owner can sit at one desk, read BTC / ETH /
GOLD with his own data and his own rules, take only high-expectancy
setups, protect capital, and **steadily accumulate real BTC, ETH, and
GOLD**. SKY is the brain and the discipline — not a bot that places
orders.

Capital preservation always comes before capital growth. A trader who
loses 50% needs a 100% gain just to break even.

| Half of independence | Meaning | Status |
|---|---|---|
| **Decision independence** | Own engine, risk gate, human-approval loop | ✅ P1–P9 |
| **Data independence** | Own stored market history | ✅ P10.1–P10.12 |
| **Validation independence** | Research-grade proof on our grader + our store | ✅ P12.1–P12.18 *tooling*; real-host XAU evidence still open |
| **Operating independence** | Click the desk; do not memorise CLI | 🔄 Trade Terminal T1 + T2 + T3 + T4(pt.1) shipped (v2.52.0); T4 pt.2, T5–T6 remaining |
| **Evidence independence** | Canonical live paper book that can open the graduation bar | 🔄 **P11 — this is the money path** |

Those halves cannot substitute for each other. A beautiful terminal
does not prove an edge. A signed installer does not open the
graduation bar. A passing test suite is not profitability.

### The 4-step path to real capital

```
[1 PAPER]                     [2 PROOF]
 live paper on real data        learn + stats + scorecard
 100–200 decided trades         E_net ≥ +0.50R, WR_net > 55%,
 PROGRESSION=simulator          PF_net ≥ 1.5, compliance ≥ 90%,
                                ≥100 backtest + ≥20 paper / setup
            │                              │
            ▼                              ▼
[3 MICRO]                     [4 ACCUMULATE]
 PROGRESSION=micro              sweep profits into cold
 0.5% risk / trade              BTC, ETH, GOLD / PAXG
 −1.5% daily stop               (portfolio DCA — never
 only after BOTH:               averaging down a loser)
   • bar says READY
   • owner explicitly approves
```

**Step 3 is blocked today.** The bar is closed on real data. Do not
build an exchange-order adapter while it is closed. If live micro
ever happens, it is a SKY-owned thin adapter with per-order human
confirmation — never Freqtrade, never a third-party strategy runtime.

---

## 1. Three lanes that cannot substitute for each other

Work is chosen by **environment**, then by how directly it moves the
aim.

```
┌─────────────────────────────────────────────────────────────────────┐
│ LANE A — MONEY PATH (real-data Hub)                                 │
│ Canonical paper grind → journal every decided trade → NET proof     │
│ → graduation READY → explicit owner approval → micro at trivial size│
│ Then accumulate BTC / ETH / GOLD.                                   │
│                                                                     │
│ Also on this host: P12.12 XAU evidence (research-only; never        │
│ self-promotes). XAU stays non-tradeable until human review.         │
├─────────────────────────────────────────────────────────────────────┤
│ LANE B — PRODUCT PATH (sandbox-feasible code)                       │
│ Trade Terminal so the owner never types a command for the daily     │
│ loop: chart → understand → paper ticket → gate → manage → close →   │
│ journal. Phases T1–T6. T1 + T2 + T3 + T4(pt.1) shipped (full loop).│
│ Next: T4 part 2 — panels/persistence/states/tooltips/mobile.          │
├─────────────────────────────────────────────────────────────────────┤
│ LANE C — DISTRIBUTION PATH (trusted signers only)                   │
│ Ubuntu Hub is the one authority. Browser/PWA, Windows .exe and      │
│ Android .apk are companions. P18–P22.1–P22.3 are source contracts.  │
│ Remaining: compile, sign, and drill on real hosts.                  │
│ Packaging never unlocks trading.                                    │
└─────────────────────────────────────────────────────────────────────┘
```

**Priority rule:** Lane A outranks Lane B polish. Lane C cannot be
finished from this sandbox. Do not invent P11 samples, XAU seals, or
signed installers here.

---

## 2. Current software — honest snapshot (v2.52.0)

What a user actually has after `python3 main.py`:

| Surface | Honest state |
|---|---|
| Default page | **Trade Terminal** layout (watchlist / chart / ticket / bottom tabs / 6-area nav) |
| Chart | Lightweight Charts v4.2.3 with EMA/VWAP/BB, RSI, MACD, zones, drawings, replay, live SSE stream, 2×2 multi-chart (zoom + crosshair sync) |
| Paper ticket | Prefills from the latest scan; sizes; shows a live server gate read; Confirm is **disabled while the gate says blocked** |
| Confirm Paper Trade | **Enrolls the real paper trade (T3).** Ticket → scan row → fresh server gate → APPROVED (desk path) → paper-runner position in the bottom panel → live R/MAE/MFE → Close records the outcome → journal drawer opens. Market tickets fill at entry; limit/conditional wait for the level. Still paper-only. |
| AI Copilot | Drawer + 9 quick actions + `/api/ask` with symbol/timeframe context. Answers render as titled sections with a Sources footer (v2.51.0); Prepare-ticket pre-fills the ticket (advisory). AI cannot approve. |
| Other five nav areas | Existing panels **grouped**, not rewritten |
| Risk gate / graduation / `/api/v1` / jobs / PWA / auth | Untouched by v2.50.0 (T3 calls the existing desk approval + paper runner; no threshold, no order path) |
| Visual QA | **Not done.** No browser in the sandbox that shipped T1. |
| Graduation bar | **Closed.** First real-data grind: +0.348R gross / 36.8% WR / PF 1.55 — below the NET bar. |
| XAU | Research-only. `xau-evidence` tooling exists; this checkout has no real basis/seal. |
| Signed `.deb` / `.exe` / `.apk` | **Do not exist yet.** Do not download unofficial installers. |
| Exchange order path | **Does not exist.** No trading credentials in the app. |

---

## 3. Product promise — the Trade Terminal

SKY should feel like **one professional trading platform**, not a
collection of Python functions and separate dashboard cards.

A user should:

1. Open one website — the **Trade Terminal**.
2. Select a market (BTC, ETH, XAU display) and a timeframe.
3. Study a professional chart with indicators, zones, and drawings.
4. Ask the AI Copilot to explain the setup.
5. Create a **paper** trade with prefilled entry, stop, targets, and risk.
6. See the **server-side** risk-gate verdict before committing.
7. Manage the open position with live R, MAE/MFE, and management advice.
8. Close the position and automatically open the journal.
9. Review performance, evidence, and discipline in one place.
10. Never type a terminal command to do any of the above.

The software goal does **not** change the trading-safety goal:

- SKY remains paper-first and advisory until the bar opens **and** the
  owner separately approves micro-live.
- No package contains an automatic exchange-order path.
- The risk gate is enforced on every paper approval (server-side).
- The AI is advisory — it may prepare a ticket; it cannot bypass the gate.
- Simulator rows never count as live paper evidence.
- Research books (Dukascopy XAU, non-canonical sources) can neither
  unlock nor block canonical live graduation or live risk.

---

## 4. Trading promise — the bar does not move

The graduation gate (`data/simulator.py`, all surfaces) promotes to
micro **only** when the primary setup family, on the **canonical live
book**, **NET of costs**, shows:

1. Expectancy **≥ +0.50R** (`E_net`)
2. Win rate **> 55%** (`WR_net`)
3. Profit factor **≥ 1.5** (`PF_net`)
4. Rule compliance **≥ 90%** (decided, non-simulator, canonical-live
   journals; missing journals fail closed)
5. Sample proof: **≥ 100 backtest + ≥ 20 paper** per primary setup

Restating gross → net was **not** loosening. Measuring gross quietly
made the bar ~40% easier than intended.

**Do not change those numbers to make the desk feel more active.**

Golden rules (see `BLUEPRINT.md`):

1. Protect capital above all. A stopped-out trade that followed rules
   is a good trade.
2. Enforce the risk gate. Daily / weekly / drawdown ladder are hard
   limits, judged **net of costs**.
3. Respect behavioral flags (`angry` / `tired` / `revenge` / `chasing`).
4. Follow the playbooks (BTC 4H→1H→15M; ETH gated by BTC; GOLD
   London/NY + US-data stand-aside).
5. Let the math compound. Do not hunt a new family before this one
   clears the bar.
6. Never average down. The risk budget is immutable before entry.
   Step-4 accumulation is portfolio DCA of *profits*, not a losing
   position.

---

## 5. The Trade Terminal — professional layout

```
+----------------------------------------------------------------------------+
| SKY   BTC/USDT v   15m v   Risk Gate: OPEN   Alerts   Account              |
+----------------+----------------------------------+------------------------+
| WATCHLIST      |       MAIN CHART                 | ORDER / AI PANEL       |
|                |  Candles, drawings, zones,       | Paper trade ticket     |
| BTCUSDT  +1.2% |  levels, indicators, overlays    | Buy/Sell, Entry, SL,   |
| ETHUSDT  -0.5% |                                  | TP, Risk %, Size       |
| XAUUSD   +0.3% |                                  | Risk-gate verdict      |
| Search...      |                                  | AI Copilot chat        |
+----------------+----------------------------------+------------------------+
| Positions | Orders | Trade history | Journal | Alerts | Strategy evidence  |
+----------------------------------------------------------------------------+
```

This is the default and primary page. The user rarely needs to leave it.

### Layout principles

- **Left panel:** searchable watchlist with prices and daily change.
- **Center:** large professional chart (Lightweight Charts) with overlays.
- **Right panel:** paper-trade ticket or AI Copilot (resizable/collapsible).
- **Bottom panel:** tabbed positions, pending plans, history, journal,
  alerts, evidence, background jobs.
- **Top bar:** symbol, timeframe, feed freshness, risk status, alerts,
  account.
- **Panel sizes, watchlist, symbol, timeframe, and layout are remembered.**
- **Persistent AI Copilot** as a right-side drawer from every page.

v2.49.0 shipped the *arrangement* and v2.50.0 shipped the
Confirm→position→close→journal loop (T3). Remembered panel sizes and
loading skeletons are still T4.

---

## 6. One clear paper-trade workflow

The professional workflow (this is the product expression of Lane A):

1. Select `BTCUSDT`.
2. Choose timeframe.
3. Review the chart and SKY signal.
4. Ask AI: "Explain this setup."
5. Click **Create Paper Trade**.
6. Entry, stop, targets, risk, and size are prefilled.
7. SKY shows the **server-side** risk-gate verdict and checklist.
8. User confirms.
9. Position immediately appears under the chart.
10. Live R, MAE/MFE, stop, targets, and management advice update.
11. Click **Close Position**.
12. Journal drawer opens automatically.

That is the complete experience:
**chart → understand → paper trade → manage → close → journal.**

**v2.50.0 status of that loop:** all twelve steps run in the terminal.
Step 8 goes through the *existing* desk approval path (ticket scan →
fresh server-side risk-gate read → APPROVED) and the paper runner
enrolls the position — market tickets fill at the confirmed entry,
limit/conditional tickets wait for the level. Steps 9–12 live in the
bottom panel: live R / MAE / MFE / management advice, Close Position
recording the real economic outcome, and the journal drawer opening
automatically. Still paper-only; still no exchange order.

---

## 7. Navigation — six primary areas

### Trade (default)

Chart, watchlist, paper order ticket, AI Copilot, positions, and trade
management. Everything a trader needs in one screen.

### Markets

BTC, ETH, XAU overview: price, trend, funding, open interest, flow,
news, and data freshness.

### Portfolio

Paper equity, current exposure, realized R, drawdown, performance, and
trade history.

### Journal

Calendar, journal entries, screenshots/drawings, mistakes, emotions,
and rule compliance.

### Evidence

Backtests, scorecards, expectancy, sample progress, setup graduation,
and validation.

### System

Connections, data health, background jobs, devices, backups, updates,
and advanced tools.

Modules and Command Center remain under **System → Advanced**.

v2.49.0 grouped the legacy panels into these six names. T6 is when
each area becomes a focused page rather than a stack of old cards.

---

## 8. Professional visual language

Measured from the shipped terminal CSS (`web/static/terminal_head.html`):

- **Page background** `#0b0e14`. Theme-color / PWA icons use `#070b14`.
- **Thin borders** `1px solid #1e2533` (not a second palette).
- **Compact SVG icons** — no emojis in primary navigation.
- **Green/red** only for market direction and P&L.
- **Amber** for warnings and blocked conditions.
- **Cyan/blue** for neutral SKY actions.
- **Compact typography** — Inter, ~12.5px, numeric values aligned.
- **Chart gets most of the screen** — resizable panels (T4).
- **Tooltips** instead of long explanations occupying space (T4).
- **Loading skeletons** rather than blank areas (T4).
- **Explicit stale, disconnected, waiting, and error states.**
- **Panel sizes, watchlist, symbol, timeframe, and layout are remembered** (T4).

A professional terminal should feel **dense but calm**, not crowded.

---

## 9. Trade ticket design

The right-side paper ticket resembles a real exchange ticket while
clearly marked:

> **PAPER — NO REAL ORDER WILL BE SENT**

- Buy / Sell toggle
- Market / Limit / Conditional
- Entry price
- Stop loss
- TP1 / TP2 / TP3
- Risk percentage
- Position size
- Estimated fees and slippage (must use `data/costs.py`, not a
  hardcoded 0.1% of entry)
- Planned R:R
- Risk-gate result (Open / Blocked with reason)
- Setup evidence
- **Confirm Paper Trade** button

When blocked, the button remains disabled and the exact reason appears
beside it. Disable state must follow a **fresh** `/api/risk` (or
`/api/v1` equivalent) read, not only the last scan payload.

Confirm must go through the existing approval path. It must not invent
a second order channel.

---

## 10. Bottom trading panel

- **Open positions** — entry, SL, TP, current P&L, MAE/MFE, management
- **Pending plans** — approved but not yet entered
- **Trade history** — closed trades with outcome, R, journal status
- **Alerts** — price, signal, and system alerts
- **Journal** — recent entries, compliance rate
- **Strategy evidence** — per-setup stats, expectancy, sample count
- **Background activity** — jobs, health, system events

Selecting a position paints its entry, stop, and targets on the chart
and opens its management controls inline (live R, MAE/MFE,
management advice, Close Position).

Bottom-tab contents must refresh; they must not cache forever after
the first paint.

---

## 11. Persistent AI Copilot

AI chat is available from every page as a right-side drawer — not
hidden inside a separate technical page.

Quick-action buttons above the chat:

- **Explain this chart**
- **Why is trading blocked?**
- **Review this signal**
- **Review my open position**
- **What invalidates this setup?**
- **Summarize today**
- **Help me journal**
- **Am I ready for graduation?**

The AI automatically receives current context: selected symbol and
timeframe, visible chart range, latest signal and regime, risk-gate
status, open paper positions, measured strategy evidence, relevant
journal history.

The response visibly separates:

- **Market facts**
- **SKY interpretation**
- **Risk concerns**
- **Suggested next action**

AI may **prepare** a ticket. AI may **never** approve, never bypass
the gate, never place an order.

---

## 12. Home screen and mobile

### Home (T5)

The first screen after login is a concise command dashboard:

- Continue last market
- Risk gate status
- Data freshness
- Open positions
- Today's P&L
- Journal tasks
- Evidence progress
- Important alerts
- **"Open Trading Terminal"** primary button

It does not show every technical module.

### Mobile

Four primary sections:

- **Markets** — price overview and quick scan
- **Chart** — full chart with taps for trade
- **Position** — open and closed positions
- **AI** — AI Copilot chat

The paper ticket opens as a full-screen sheet. Approval remains
online-only; the current risk status is refreshed immediately before
confirmation.

---

## 13. Phase T1–T6 — product lane (honest status)

### T1 — Trade Terminal layout · ✅ shipped v2.49.0 (PR #72)

- 3-column terminal as the default page
- Watchlist left, chart center, order/AI panel right
- Bottom panel with tabs
- Six-area navigation
- Professional dark theme
- Trade ticket UI (buy/sell, entry, SL, TP, risk, size)
- AI Copilot drawer scaffold

**Not in T1 (do not claim them):** visual QA on a real browser;
Confirm creating a paper position; resizable/persisted panel sizes;
focused Markets/Portfolio/Journal/Evidence/System pages.

### T2 — Persistent AI Copilot · ✅ shipped v2.51.0

Shipped in v2.49.0: drawer, eight quick actions, context injection,
attempted sectioned replies. Shipped in v2.51.0 (T2 polish):

- Reliable structured sections — the backend returns `sections` +
  `sources` on every answer; the Copilot renders titled sections with a
  dashed Sources footer and never double-prints the raw text
- Per-answer citations/sources — every intent names the grounding surface
  (`risk gate — brain.risk_gate.evaluate`, `open paper book —
  SignalDB.live_open_rows`, …)
- **Prepare ticket from AI** (never approves) — pre-fills side/type/
  entry/SL/TP from the desk plan and switches to the Ticket tab
- Context: open positions + measured evidence — the exposure answer adds
  the canonical live-book count and per-plan-type calibrated expectancy,
  and the Copilot asks about the selected symbol/timeframe

### T3 — Paper-trade workflow wiring · ✅ shipped v2.50.0

This is the product expression of the money path.

- **Confirm runs the existing desk path.** `POST /api/terminal/confirm`
  turns the ticket into a real scan row (PENDING_REVIEW), re-reads the
  risk & discipline gate **fresh on the server** immediately before the
  APPROVED decision, applies the journal-first discipline exactly like
  `/api/review` (same audited `acknowledge_journal` escape, same
  `SKY_ALLOW_FORCE_APPROVE` force semantics), then the paper runner
  enrolls + fills the position. Market tickets fill at the confirmed
  entry; limit/conditional tickets wait for the level.
- **Position appears under the chart** — the bottom positions tab
  re-fetches on confirm; the watchlist chip updates.
- **Live R, MAE/MFE, management advice update in the terminal** — the
  positions tab reads `/api/trades` (same live-open book the Trade
  Manager uses) and refreshes while visible.
- **Close records the outcome and opens the journal automatically.**
  `POST /api/terminal/close` advances the scan lifecycle like the desk
  close decision, records the real economic outcome in the existing
  `TP_HIT` / `STOP_LOSS` buckets (`close_reason` says it was a manual
  terminal close), and the journal drawer opens with a prefilled form
  (`followed_rules` headline) posting to the existing `/api/journal`.
  A `WAITING_ENTRY` position is cancelled honestly — nothing traded,
  nothing journaled.
- **Still paper-only. Still no exchange order.**

### T4 — Professional polish · 🔄 part 1 shipped v2.52.0

Shipped in v2.52.0:

- **Honest ticket fees/size** — `GET /api/ticket/meta` serves the real
  `ACCOUNT_BALANCE` + the per-symbol cost model; the ticket sizes from that
  balance (shows **—** with a "set ACCOUNT_BALANCE" hint when unset — the
  invented $100k default is gone) and estimates fees from the desk's real
  round-trip fee/spread/slippage model.
- **Loading skeletons** — shimmer rows for the watchlist and bottom tabs.
- **Bottom tabs re-fetch** — the one-shot cache is dropped; switching always
  re-fetches so a runner-closed position cannot linger as a stale row.

Remaining (T4 part 2):

- Resizable and collapsible panels
- localStorage for panel sizes / watchlist / symbol / timeframe / layout
- Explicit stale / disconnected / error states in the terminal
- Tooltips for all icons
- Compact mobile layout

### T5 — Home screen and onboarding

- Concise post-login command dashboard
- "Open Trading Terminal" primary button
- Onboarding for new users that points at the paper loop, not at CLI

### T6 — Focused pages

- Full content for Markets / Portfolio / Journal / Evidence / System
- Each page is a focused view, not a card collection
- Mobile four-section layout

**Verification for every T step:** keep
`test_served_script_is_valid_javascript` and the jsdom harnesses
green; add regressions for any new terminal behaviour; full suite
≥ 1282 / 1; wheel gate green; `config.VERSION` =
`pyproject.toml` = `sky-shell-v…` lockstep.

---

## 14. Parallel real-host work (does not wait for T6)

These stay open regardless of terminal progress.

| ID | Work | Where | Status |
|---|---|---|---|
| **P11** | Canonical live paper grind; journal every decided real trade; re-run `stats` / `learn` / `agent ask "am I ready for micro?"` | Real-data Hub | 🔄 gate closed |
| **P12.12** | Import/version-pin Dukascopy XAU bid *or* ask; locked train/val/OOS/recent; archive `xau-evidence --json`. Never create/reseal from the audit. Passing dossier = human-review eligibility only | Real-data Hub | 🔄 tooling shipped; no real evidence in this checkout |
| **P22** | Compile, sign, and clean-target drill on trusted Ubuntu / Windows / Android hosts. `p22_complete` may flip only with operator evidence | Trusted signers | 🔄 P22.1–P22.3 contracts shipped; no signed artifact |
| **TODO-8** | Repo admin verifies `main` protection (required PRs + both CI jobs) | GitHub admin | 🔄 unverified (HTTP 403) |
| **Visual QA** | Open the terminal at desktop and mobile widths on a real browser | Real host | 🔄 not done |

**Blocked future build:** micro-live and any order-placement adapter.
Requires the unchanged bar **and** explicit owner approval. A passing
XAU dossier is neither condition.

---

## 15. Delivered capability (merged history)

| Phases | Delivered capability | Status |
|---|---|---|
| P1–P6 | Signal engine, context, risk, learning, agents, immune system | ✅ Shipped |
| P7–P9 | Agent surface, source channels, typed MCP capabilities | ✅ Shipped |
| P10 | Owned normalised market history, derivatives, charts, store | ✅ Shipped (P10.1–P10.12, PR #18) |
| P11 | Paper evidence and graduation loop | 🔄 Operational; bar closed on real data |
| P12 | Locked validation, scorecards, costs, provenance, source isolation | ✅ Tooling shipped (P12.1–P12.18). Real-host XAU evidence open |
| P13–P14 | Teaching coach, daily loop-health ritual | ✅ Shipped |
| P15–P16 | Market sentiment colour and measured outcomes | ✅ Shipped |
| P17 | Clickable Trading Workstation + read-only real-world connections | ✅ Foundation shipped |
| W1 | Guided evidence build (fail-closed, honest projection, no-edge) | ✅ Shipped v2.32.0 |
| W2 | Zones, replay, live stream, drawings | ✅ Shipped v2.33.0 |
| W3 / W3.4 / W3.6 | Weekly review, ritual memory, journal-first gate, practice, tape | ✅ Shipped v2.41.0–v2.46.0 |
| W3.5 | 2×2 multi-chart zoom + crosshair sync | ✅ Shipped v2.43.0 + v2.48.0 |
| W4 | Agent tab + Ubuntu PC is the Hub (one research agent) | ✅ Shipped v2.44.0–v2.45.0 |
| P18 | Auth/roles, `/api/v1`, jobs/SSE, PWA (+ VAPID push v2.47.0) | ✅ Shipped (P18.1–P18.4) |
| P19 | Ubuntu Hub package (layout, CLI, units, backup, TLS examples) | ✅ Mechanics shipped; signed apt repo + clean-VM drill do not exist yet |
| P20 | Windows companion contract (pairing, client, unsigned recipe) | ✅ Contract shipped; signed `.exe` does not exist yet |
| P21 | Android companion contract (Keystore, biometric, unsigned recipe) | ✅ Contract shipped; signed `.apk` does not exist yet |
| P22 | Release engineering (checksums, SBOM, drill contracts) | ✅ Foundation shipped; trusted-signer drills pending |
| **T1–T6** | **Professional Trade Terminal** | **T1 + T2 + T3 + T4(pt.1) shipped v2.52.0; T4 pt.2, T5–T6 remaining** |

Freqtrade (F1–F8) and Backtrader (BT1–BT8) stay **rejected**. Needle 2
(N1–N8) stays parked. Do not reopen those audits to install a bot or
a second grader.

---

## 16. Deployment profile (production distribution)

```text
                         HTTPS
 Windows .exe  ───────────┐
 Android .apk  ───────────┼──► Ubuntu SKY Hub
 Browser / installed PWA ─┘       ├─ Flask/Gunicorn application API
                                  ├─ scanner + paper monitor services
                                  ├─ SQLite + Parquet evidence store (one DB)
                                  ├─ risk gate + audit log
                                  └─ backups + health supervision
```

**Ubuntu Hub is the always-on authority:** one database, one risk
gate, and one evidence book. Windows and Android begin as companion
clients — they monitor and perform only the human actions the
authenticated API permits. This avoids three independent engines
producing three different answers.

Production distribution never adds live order execution. The risk
gate is enforced server-side (authentication and authorization,
roles, CSRF, device tokens, audit). Installers remain planned:
signed releases do not exist yet.

---

## 17. Binding decisions

1. **Aim first.** Every session is judged by whether it moved paper
   proof, honest measurement, or the owner's ability to run that loop
   without CLI. Features that move neither are out of scope.
2. **Trade Terminal first on the product lane.** One screen dominates.
3. **Six nav areas.** Trade, Markets, Portfolio, Journal, Evidence, System.
4. **AI Copilot is a persistent drawer.** Advisory only.
5. **Paper-first and advisory.** No exchange-order path in this
   roadmap, and no live order execution anywhere in it. Micro-live is
   a later, separately approved adapter after the bar opens.
6. **Risk gate is server-enforced.** No client-side bypass.
7. **Net of costs.** Hard limits, proven-gate, and graduation read
   `E_net` / `net_r_of_row()`. Gross-only edges are not an edge.
8. **Canonical live only** for permission and live risk. Research
   books are visible, never authoritative.
9. **Journal-first.** Missing journals hold the next approval. The
   audited escape is intentional, not a bug.
10. **One Hub.** Packaging never creates a second brain.
11. **Panel layout is remembered** (T4).
12. **Professional dark theme.** Dense but calm.
13. **Mobile is four sections.** Markets, Chart, Positions, AI.
14. **Everything is accessible, nothing is visible at once.**

---

## 18. Explicitly out of scope

Do not add these to the queue. Full rationale lives in `TODO.md` and
the named review docs.

- Autonomous exchange order placement
- Freqtrade / Hyperopt / FreqAI / any exchange-order bot (F1–F8)
- Backtrader as dependency, adapter, or second grader (BT1–BT8)
- Needle 2 as an in-process router (N1–N8)
- New strategy-module catalog before the primary family clears the bar
- Auto capital allocation across strategies
- Averaging down / martingale
- Pooling Dukascopy XAU into live calibration
- Manufacturing P11 samples, XAU seals, or signed installers in CI
- Social-platform scraping, cookie extraction, audio transcription
- PostgreSQL / Redis / Docker / FastAPI / React as a rewrite
- Paid data vendors for the current phase
- Loosening `+0.50R / 55% / PF 1.5 / 90% compliance / 100+20`

---

## 19. Ordered next work

Choose by environment. Do not start a lower item while a higher item
in the **same** environment is unblocked.

### Real-data Hub (Lane A — money path)

1. `python main.py daily` then `paper --watch`. Review every candidate
   by hand. Journal every decided canonical-live trade.
2. Weekly `scorecard --conditioned --source store` and `validate --source store --tf 15m`.
3. Rerun `learn` so existing rows adopt P12.11 source keys (live
   profile unchanged; never substitute demo/synthetic).
4. When ready: Dukascopy XAU procedure + `xau-evidence --json`
   (`docs/XAU_PROMOTION_EVIDENCE.md`). Research-only.
5. Ask `am I ready for micro?` only against that book. If the answer
   is no, keep grinding. Do not move the bar.

### Sandbox / this checkout (Lane B — product path)

1. **Visual QA** if a real browser is available; otherwise skip and
   do not fake screenshots.
2. **Visual QA of the T3 loop** — if a real browser is available:
   confirm a ticket, watch the position appear, close it, journal it.
   Fix visual issues only; do not fake screenshots.
3. **T2 polish — ✅ shipped v2.51.0** (sections + sources, prepare
   ticket from AI, richer context).
4. **T4 — 🔄 part 1 shipped v2.52.0** (honest sizing/fees via
   `/api/ticket/meta`, loading skeletons, drop the one-shot bottom-tab
   cache). **Part 2** remains: resizable/persisted panels, localStorage
   layout, stale/error states, tooltips, compact mobile.
5. **T5** then **T6**.

Keep the suite green. Bump `config.VERSION` / `pyproject.toml` /
`sky-shell-v…` together. Parse the *served* dashboard script, not the
file text.

### Trusted signers (Lane C)

Execute the P22.3 catalog on real Windows / Android / Ubuntu hosts.
Attach operator evidence. Do not mark `p22_complete` from catalog JSON
or Linux CI.

---

## 20. How to read the other roadmap files

| File | Role now |
|---|---|
| **`ROADMAP.md` (this file)** | Combined source of truth |
| `TODO.md` | Prioritised session queue (must match this file) |
| `BLUEPRINT.md` | Aim, 4-step path, golden rules |
| `AI_ANATOMY_ROADMAP.md` | Historical P1–P12 anatomy |
| `WEB_TRADER_ROADMAP.md` | Historical workstation / W1–W4 spec |
| `ROADMAP_AGENT_REACH_UPGRADE.md` | Historical P7–P9 + D1–D5 |
| `docs/DATA_INFRASTRUCTURE_ROADMAP.md` | Historical P10 |
| `docs/PATH_TO_REAL_MONEY.md` | 2026-08-14 audit that reordered P12 (fees-first, real data) |
| `docs/PR_REVIEW_2026-08-20.md` | Review of recent PRs that produced this snapshot |
