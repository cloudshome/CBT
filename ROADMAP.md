# SKY — Professional Trading Terminal

> **Status:** active source of truth
> **Last updated:** 2026-08-20
> **Current software:** v2.48.1
>
> **Vision:** SKY should feel like one professional trading platform, not a
> collection of Python functions and separate dashboard cards. A user opens
> one website, selects a market, studies the chart, asks the AI, creates a
> paper trade, manages it, closes it, and journals it — without seeing
> terminal commands.
>
> This roadmap defines the unified Trade Terminal product. Older roadmap
> files remain as detailed historical specifications; when priorities
> conflict, this file and `TODO.md` win.

---

## 1. Product promise

SKY is a professional trading terminal that never places a real order.

A user should:
1. Open one website — the **Trade Terminal**.
2. Select a market (BTC, ETH, XAU) and a timeframe.
3. Study a professional chart with indicators, zones, and drawings.
4. Ask the AI Copilot to explain the setup.
5. Create a paper trade with prefilled entry, stop, targets, and risk.
6. See the risk-gate verdict before committing.
7. Manage the open position with live R, MAE/MFE, and management advice.
8. Close the position and automatically open the journal.
9. Review performance, evidence, and discipline in one place.
10. Never type a terminal command to do any of the above.

The software goal does **not** change the trading-safety goal:
- SKY remains paper-first and advisory.
- No package contains an automatic exchange-order path.
- The risk gate is enforced on every paper approval.
- The AI is advisory — it prepares a ticket but cannot bypass the gate.

---

## 2. The Trade Terminal — professional layout

```
+----------------------------------------------------------------------------+
| SKY   BTC/USDT v   15m v   Risk Gate: OPEN   Alerts   Account              |
+----------------+----------------------------------+-----------------------+
| WATCHLIST      |       MAIN CHART                | ORDER / AI PANEL      |
|                |  Candles, drawings, zones,       | Paper trade ticket   |
| BTCUSDT  +1.2% |  levels, indicators, overlays  | Buy/Sell, Entry, SL,  |
| ETHUSDT  -0.5% |                                  | TP, Risk %, Size      |
| XAUUSD   +0.3% |                                  | Risk-gate verdict     |
| Search...      |                                  | AI Copilot chat       |
+----------------+----------------------------------+-----------------------+
| Positions | Orders | Trade history | Journal | Alerts | Strategy evidence |
+----------------------------------------------------------------------------+
```

This is the default and primary page. The user rarely needs to leave it.

### Layout principles
- **Left panel:** searchable watchlist with live prices and daily change.
- **Center:** large professional chart (Lightweight Charts) with overlays.
- **Right panel:** paper-trade ticket or AI Copilot (resizable/collapsible).
- **Bottom panel:** tabbed view of positions, orders, history, journal, alerts, evidence.
- **Top bar:** symbol selector, timeframe selector, feed freshness, risk status, alerts, account.
- **Panel sizes, watchlist, symbol, timeframe, and layout are remembered.**
- **Persistent AI Copilot** available as a right-side drawer from every page.

---

## 3. One clear paper-trade workflow

The professional workflow:
1. Select `BTCUSDT`.
2. Choose timeframe.
3. Review the chart and SKY signal.
4. Ask AI: "Explain this setup."
5. Click **Create Paper Trade**.
6. Entry, stop, targets, risk, and size are prefilled.
7. SKY shows the risk-gate verdict and checklist.
8. User confirms.
9. Position immediately appears under the chart.
10. Live R, MAE/MFE, stop, targets, and management advice update.
11. Click **Close Position**.
12. Journal drawer opens automatically.

That is the complete experience: **chart -> understand -> paper trade -> manage -> close -> journal**.

---

## 4. Navigation - six primary areas

The current interface has many functions displayed simultaneously. Professional
software exposes complexity through organized panels and contextual actions.

### Trade (default)
Chart, watchlist, paper order ticket, AI Copilot, positions, and trade management.
The terminal - everything a trader needs in one screen.

### Markets
BTC, ETH, XAU overview: price, trend, funding, open interest, flow, news, and data freshness.

### Portfolio
Paper equity, current exposure, realized R, drawdown, performance, and trade history.

### Journal
Calendar, journal entries, screenshots/drawings, mistakes, emotions, and rule compliance.

### Evidence
Backtests, scorecards, expectancy, sample progress, setup graduation, and validation.

### System
Connections, data health, background jobs, devices, backups, updates, and advanced tools.

"Modules" and "Command Center" remain available under **System -> Advanced**.

---

## 5. Professional visual language

- **Dark neutral background** (`#070b14`) - consistent, calm.
- **Thin borders** (`1px solid #1e3358`) instead of many floating cards.
- **Compact SVG icons** - no emojis in primary navigation.
- **Gren/red** only for market direction and P&L.
- **Amber** for warnings and blocked conditions.
- **Cyan/blue** for neutral SKY actions.
- **Compact typography** - `Inter`, `12-13.5px`, numeric values aligned.
- **Chart gets most of the screen** - resizable panels.
- **Toltips** instead of long explanations occupying space.
- **Loding skeletons** rather than blank areas.
- **Explicit stale, disconnected, waiting, and error states.**
- **Panel sizes, watchlist, symbol, timeframe, and layout are remembered.**

A professional terminal should feel **dense but calm**, not crowded.

---

## 6. Trade ticket design

The right-side paper ticket resembles a real exchange ticket while clearly marked:

> **PAPER - NO REAL ORDER WILL BE SENT**

- Buy / Sell toggle
- Market / Limit / Conditional
- Entry price
- Stop loss
- TP1 / TP2 / TP3
- Risk percentage
- Position size
- Estimated fees and slippage
- Plnned R:R
- Risk-gate result (Open / Blocked with reason)
- Setup evidence
- **Confirm Paper Trade** button

When blocked, the button remains disabled and the exact reason appears beside it.

---

## 7. Bottom trading panel

Like Binance and TradingView, the lower panel has tabs:

- **Oen positions** - entry, SL, TP, current P&L, MAE/MFE, management
- **Pnding plans** - approved but not yet entered
- **Trade history** - closed trades with outcome, R, journal status
- **Aerts** - price, signal, and system alerts
- **Journal** - recent entries, compliance rate
- **Strategy evidence** - per-setup stats, expectancy, sample count
- **Bckground activity** - jobs, health, system events

Selecting a position paints its entry, stop, and targets on the chart and opens
its management controls.---

## 8. Persistent AI Copilot

AI chat is available from every page as a right-side drawer - not hidden inside
a separate technical page.

Quick-action buttons above the chat:
- **Explain this chart**
- **Why is trading blocked?**
- **Review this signal**
- **Review my open position**
- **What invalidates this setup?**
- **Summarize today**
- **Help me journal**
- **Am I ready for graduation?**

The AI automatically receives current context:
- Selected symbol and timeframe
- Visible chart range
- Latest signal and regime
- Risk-gate status
- Open paper positions
- Measured strategy evidence
- Relevant journal history

The response visibly separates:
- **Market facts**
- **SKY interpretation**
- **Risk concerns**
- **Suggested next action**

---

## 9. Home screen

The first screen after login is a concise command dashboard:

- Continue last market
- Risk gate status
- Data freshness
- Open positions
- Today's P&L
- Journal tasks
- Evidence progress
- Important alerts
- **"Oen Trading Terminal"** primary button

It does not show every technical module.

---

## 10. Mobile experience

Mobile uses four primary sections:
- **Markets** - price overview and quick scan
- **Chart** - full chart with taps for trade
- **Position** - open and closed positions
- **AI** - AI Copilot chat

The paper ticket opens as a full-screen sheet. Approval remains online-only;
the current risk status is refreshed immediately before confirmation.

---

## 11. Implementation phases

### Phase T1 - Trade Terminal layout (NEXT)
- Rewrite the dashboard HTML to the professional 3-column layout.
- Watchlist left, chart center, order/AI panel right.
- Bottom panel with tabs (positions, orders, history, journal, alerts, evidence).
- Simplified 6-area navigation.
- Professional dark theme with thin borders and compact typography.
- Trade ticket UI with buy/sell, entry, SL, TP, risk, size.
- AI Copilot drawer with quick-action buttons.

### Phase T2 - Persistent AI Copilot
- AI chat as a right-side drawer on every page.
- Contet-aware quick-action buttons.
- Structured response market facts, SKY interpretation, risk concerns, suggested action).
- Automatic context injection (symbol, timeframe, signal, risk gate, positions).

### Phase T3 - Paper trade workflow
- Click chart -> prefilled ticket.
- Risk-gate verdict shown inline.
- Position management from bottom panel.
- Cloe -> auto-journal flow.
- Live R, MAE/MFE, management advice updates.

### Phase T4 - Professional polish
- Resizable and collapsible panels.
- Panel/symbol/timeframe/layout persistence (localStorage).
- Loading skeletons.
- Explicit stale/disconnected/error states.
- Tooltips for all icons.
- Compact mobile layout.

### Phase T5 - Home screen & onboarding
- Concise post-login command dashboard.
- "Oen Trading Terminal" primary button.
- Onboarding flow for new users.

### Phase T6 - Markets, Portfolio, Journal, Evidence, System pages
- Full content for each of the 6 navigation areas.
- Each page is a focused view, not a card colection.

---

## 12. Merged roadmap history (delivered capability)

| Phases | Delivered capability | Status |
|---|---|---|
| P1–P6 | Signal engine, context, risk, learning, agents, immune system | Shipped |
| P7–P9 | Agent surface, source channels, typed MCP capabilities | Shipped |
| P10 | Owned normalised market history, derivatives, charts, streaming/store | Shipped |
| P11 | Paper evidence and graduation loop | Operational |
| P12 | Locked validation, scorecards, costs, provenance, source isolation | Shipped |
| P13–P14 | Teaching and daily loop-health ritual | Shipped |
| P15–P16 | Market sentiment colour and measured outcomes | Shipped |
| P17 | Clickable Trading Workstation and real-world read-only connections | Foundation shipped |
| P18 | Auth/roles, stable `/api/v1` contract, jobs/SSE, PWA | Shipped (P18.1–P18.4) |
| P19 | Ubuntu Hub package (layout, CLI, units, backup, TLS examples) | Mechanics shipped; signed apt repo + clean-VM drill do not exist yet |
| P20 | Windows companion contract (pairing, client, unsigned recipe) | Contract shipped; signed `.exe` does not exist yet |
| P21 | Android companion contract (Keystore, biometric, deep links, unsigned recipe) | Contract shipped; signed `.apk` does not exist yet |
| P22 | Release engineering and operations (checksums, SBOM, drills) | Foundation shipped; trusted-signer drills pending |
| **T1–T6** | **Professional Trade Terminal** | **In progress (this roadmap)** |

### Deployment profile (production distribution)

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

**Ubuntu Hub is the always-on authority**: one database, one risk gate, and
one evidence book. Windows and Android begin as companion clients — they
monitor and perform only the human actions the authenticated API permits.
This avoids three independent engines producing three different answers.
Production distribution never adds live exchange execution; no package
contains an automatic exchange-order path, and the risk gate is enforced
server-side (authentication and authorization, roles, CSRF, device tokens,
audit). Installers remain planned: signed releases do not exist yet.

---

## 13. Key decisions

1. **Trade Terminal first.** One screen dominates.
2. **Six nav areas.** Trade, Markets, Portfolio, Journal, Evidence, System.
3. **AI Copilot is a persistent drawer.** Available from every page.
4. **Paper-first and advisory.** No exchange-order path; no live order execution in this roadmap.
5. **Risk gate is server-enforced.** No client-side bypass.
6. **Panel layout is remembered.** localStorage for sizes, symbol, timeframe.
7. **Professional dark theme.** Dense but calm, never crowded.
8. **Bottom panel for trading data.** Positions, orders, history, journal, alerts, evidence.
9. **Mobile is four sections.** Markets, Chart, Positions, AI.
10. **Everything is accessible, nothing is visible at once.** Organized panels.