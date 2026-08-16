# SKY Web Trader Roadmap

## Shipped now

- One-screen professional trading desk dashboard.
- Overview, Market, Intelligence, Trades, Learn, and System workspaces.
- Live watchlist for BTC, ETH, and XAU/GOLD aliases.
- Candlestick and volume chart, timeframe switching, MTF structure, sentiment colour, funding/OI/L-S, CVD, and context panels.
- Readiness verdict combining channels, immune state, risk gate, and data quality.
- Human approval queue with approve/reject/execute/close lifecycle.
- Paper-only runner with outcome tracking, MAE/MFE, and journal discipline.
- Scorecard, calibration, coach, glossary, natural-language desk questions, MCP and diagnostics.
- **Daily ritual** button: refreshes readiness, loop health, risk gate, desk advice, health, paper state, queue, and history without placing orders.
- Visible workflow guide so the trader does not need to memorize CLI commands.

## Next build order

### Phase 1 — decision clarity

1. Add a persistent trade plan drawer: thesis, invalidation, size, and checklist in one place.
2. Add a “why blocked?” timeline for every risk-gate veto.
3. Add a journal form directly in the signal modal, with required emotion/rules/mistake fields.
4. Add browser persistence for preferred watchlist, timeframe, and risk display settings.

### Phase 2 — chart workstation

1. Add synchronized crosshair and timeframe-linked chart panels.
2. Add entry, stop, take-profit, support, resistance, and invalidation overlays.
3. Add drawing notes and saved chart snapshots to the scan record.
4. Add a replay mode using stored candles, clearly separated from live/paper evidence.

### Phase 3 — risk and independence

1. Add account-equity and risk-per-trade calculator with hard caps from the risk gate.
2. Add daily/weekly loss budget progress bars and “stop trading” lockout explanation.
3. Add graduation progress by setup with the exact missing evidence shown.
4. Add exportable weekly review: decisions, violations, expectancy, drawdown, and next practice task.

### Phase 4 — reliability and distribution

1. Add API health caching and a visible stale-data age on every market card.
2. Add mobile-first compact mode for the ritual and approval flow.
3. Add dashboard integration tests for every critical action and safety gate.
4. Add optional authentication before exposing the dashboard outside localhost.

## Safety principles

- The desk is advisory; a human approval is required.
- Paper trading remains the default and sends no real orders.
- A closed risk gate cannot be bypassed from normal UI actions.
- Simulator results never count as live paper evidence.
- Every decision should be explainable, reviewable, and journalable.
