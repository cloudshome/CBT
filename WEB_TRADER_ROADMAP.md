# SKY Web Trader Roadmap

> **Roadmap status:** P17 workstation specification and carried-forward UX
> backlog. The merged product roadmap—including Ubuntu installation, Windows
> `.exe`, Android `.apk`, security, updates, and monitoring—is now
> [`ROADMAP.md`](ROADMAP.md). Where priorities conflict, `ROADMAP.md` wins.

The goal in one sentence: **you install/open SKY and operate the entire system
by clicking—no command is ever memorized.**

## Shipped now — the Trading Workstation

### The chart is real

- Vendored **TradingView Lightweight Charts v4.2.3 production build**
  (`web/static/lightweight-charts.standalone.js`, Apache-2.0). The previous
  file was an explicit stub that drew almost nothing; it is gone.
- `Chart` tab: candlesticks, volume, RSI and MACD panes with **linked time
  scales** (pan/zoom one, all follow), EMA 20/50/200, VWAP and Bollinger
  overlays, support/resistance/pivot lines and **entry / stop / take-profit**
  price lines from the live plan. Every overlay is a checkbox.
- `/api/chart` (`web/chart_data.py`) serves candles, overlays, panes, levels
  and the plan overlay in one call, in Lightweight Charts' epoch-second format.
- **Serialization bug fixed.** `/api/candles` handed raw
  `df.to_dict("records")` to Flask, so a Pandas/NumPy scalar (`int64`,
  `float64`, `NaT`, `NaN`) raised `TypeError` and the page showed analysis
  cards with no chart. Every value now passes through one `_num()` funnel, and
  `tests/test_workstation.py` locks that behaviour in.

### Every function is clickable

| Tab | What it exposes |
|---|---|
| 📊 Chart | full chart workspace, indicator readings, levels with distance-to-price |
| 🎯 Signal desk | BUY/SELL/NO TRADE, entry, stop, target, R:R, confidence, setup, regime, invalidation, why it may fail |
| ⚡ Trades | approve · reject · execute · close, with the risk gate enforced |
| 🎛 Trade manager | open book: live price, current R, stop/TP distance, MAE, MFE, time in trade, management instruction, close & journal buttons |
| 🛡 Risk center | gate + the exact reason it is closed, daily/weekly budget bars, drawdown ladder, Kelly advisory, Monte Carlo risk-of-ruin, trader-state flags, **position-size calculator** |
| 📓 Journal | a real form (rules / emotion / mistake / what happened / what to change) with the auto pre-trade checklist and execution grade |
| 🧑‍🏫 Learning | backtest, calibrate, scorecard splits, simulator, graduation progress |
| ⌘ Command center | **every CLI command as a documented button**: what it does, its inputs, a Run button, its output and links to related actions |
| 🧩 Modules | every engine module and its purpose, searchable |
| ⚙️ System | data health, channel registry, doctor verdict, MCP status |

### Safety kept intact

- `web/command_center.py` is an **allow-list**. Only catalog ids run, arguments
  are an argv list (never a shell string), inputs are type-checked, every run
  has a timeout, and long-lived/interactive commands (`watch`, `paper --watch`,
  `mcp`) are `blocked` with the terminal instruction shown instead.
- `web/position_sizer.py` caps risk at the progression ladder and returns
  **zero size** with the blocking reason whenever the gate is closed.
- Nothing in the UI can place a real order: there is no exchange key.

## Workstation backlog carried into the canonical roadmap

These items are retained as W1–W4 in [`ROADMAP.md`](ROADMAP.md). Production
security and the stable API/job boundary (P18) now precede native wrappers;
none of the workstation work below is discarded.

### Phase 1 — decision clarity

1. Drawing tools and saved chart snapshots attached to the scan record.
2. A "why blocked?" timeline for every historical risk-gate veto.
3. Browser persistence for watchlist, timeframe and risk display settings.
4. Trade plan drawer: thesis, invalidation, size and checklist in one place.

### Phase 2 — chart workstation

1. Replay mode over stored candles, clearly separated from live/paper evidence.
2. Multi-chart layout (2×2) with a synchronized crosshair across assets.
   ✅ shipped v2.43.0 + v2.48.0 (crosshair sync, sync toggles, honest empty
   slots, 1970-date fix).
3. Live streaming updates via `data/ws_client.py` instead of polling.
4. Order-block / FVG / liquidity-sweep zones drawn as chart rectangles.

### Phase 3 — risk and independence

1. Weekly trader review as an exportable page: decisions, violations,
   expectancy, drawdown and the next practice task.
2. Graduation progress by setup with the exact missing evidence shown.
3. Equity curve and R-multiple distribution charts in the Risk center.

### Phase 4 — reliability and distribution

1. Visible stale-data age on every market card + API health caching.
2. Mobile-first compact mode for the ritual and approval flow.
3. Optional authentication before exposing the dashboard outside localhost.
4. Server-sent events so long commands stream output instead of blocking.

## Safety principles

- The desk is advisory; a human approval is required.
- Paper trading remains the default and sends no real orders.
- A closed risk gate cannot be bypassed from normal UI actions.
- Simulator results never count as live paper evidence.
- Every decision should be explainable, reviewable, and journalable.
