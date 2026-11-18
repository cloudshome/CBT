# SKY / CBT — Milestone 61.1 Autonomous Pipeline Call Graph
## Active Execution Flow vs. Disconnected Research Engine

- **Date:** 2026-11-18
- **Scope:** End-to-end tracing from Market Data to `PortfolioShadow.open_position()`
- **Status:** **CALL_GRAPH_DISCONNECT_IDENTIFIED**

---

## 1. CALL GRAPH ARCHITECTURE COMPARISON

```
========================================================================================
CURRENT ACTIVE RUNTIME CALL GRAPH (PATH 1: SKY ORCHESTRATOR)
========================================================================================
[1. Market Data Streamer / Binance WebSocket]
       │
       ▼ (fetches 15m/1h/4h OHLCV candles)
[2. AutonomousTrader.scan_and_execute_cycle()]
       │
       ▼ (calls line 240)
[3. sky_orchestrator.analyze_market()]
       │
       ├─► Volatility Engine (ATR, Volatility Regime)
       ├─► Liquidity / SMC Engine (Sweeps, FVGs, Order Blocks)
       ├─► MTF Engine (Multi-timeframe alignment)
       ├─► Market Regime Engine (Trending vs Ranging)
       ├─► Setup Engine (_evaluate_setup_a, _evaluate_setup_b, _evaluate_setup_c)
       │       │
       │       ├─► Setup B: Rejects if 4h HTF trend is NEUTRAL or RANGING [BLOCKER 3]
       │       └─► Setup C: Permanently rejects (is_qualified = False)
       │
       ▼ (evaluates best qualified setup)
[4. Bayesian Setup Evaluator (get_bayesian_setup_stats)]
       │
       ├─► Queries closed shadow trades where opened_at >= 1793469018542
       ├─► Sample size = 0 (Cold Start)
       ├─► Prior: p_win = 0.50, r_win = 1.45R
       ├─► Confluence adjustment: p_eff = 0.50 + 0.004*(conf - 75) = 0.528
       ├─► Friction deduction: c_friction_r ≈ 0.16R
       ├─► Net EV: (0.528 * 1.45) - (0.472 * 1.0) - 0.16 = +0.1336R
       ├─► Risk Hurdle: Net EV >= +0.25R -> FAILS!
       │
       ▼ [BLOCKER 1: DEADLOCK]
   RETURNS DecisionAction.NO_TRADE ("NET_EV_HURDLE_FAILED (+0.13R < +0.25R)")
       │
       ▼
   AutonomousTrader aborts loop -> NEVER CREATES TradeProposal!
   (Execution never reaches CentralTradingMind or PortfolioShadow)
```

```
========================================================================================
DISCONNECTED RESEARCH & CERTIFICATION SIGNAL ENGINE (PATH 2: M57/M60 ENGINE)
========================================================================================
[1. CandleStore (Parquet 1.2M Candles)]
       │
       ▼
[2. data/backtester.py: run_backtest()]
       │
       ▼ (calls engine/rules.py)
[3. engine/rules.py: build_plans()]
       │
       ├─► "Immediate Buy / Sell"
       ├─► "Buy / Sell Pullback"
       ├─► "Breakout Buy"
       ├─► "Sweep Reversal Buy / Sell"
       └─► "FVG Retest Buy / Sell"
       │
       ▼ (graded under EXECUTION_MODEL = "impact")
   Produced 848 Sealed OOS Trades (WR: 60.14%, E[R]: +0.3594R, PF: 1.8067)
       │
       ▼ [BLOCKER 4: DISCONNECTED]
   THIS ENGINE IS COMPLETELY UNWIRED FROM AutonomousTrader!
   AutonomousTrader has zero imports or invocations of build_plans or analyze_frame!
```

```
========================================================================================
CENTRAL TRADING MIND DOWNSTREAM GATES (IF PROPOSALS WERE FORWARDED)
========================================================================================
[1. TradeProposal received by CentralTradingMind.evaluate_and_route()]
       │
       ├─► Invariant 2b: Thesis Substring Blacklist [BLOCKER 5]
       │       Rejects: "SWEEP REVERSAL", "BREAKOUT BUY", "SMC_ORDER_BLOCK", etc.
       │       (Blocks canonical M57/M60 plan types by raw string matching)
       │
       ├─► Invariant 2f: 30-Day Qualification Mode [BLOCKER 2]
       │       QUALIFICATION_MODE = "true" (default)
       │       Restricted strictly to: {"BTCUSDT", "BTCUSD", "ETHUSDT", "ETHUSD"}
       │       (Blocks SOLUSDT [298 trades] and PAXGUSDT [225 trades])
       │
       ▼ (if passed)
[2. Master Risk Gate & Portfolio Allocation]
       │
       ▼ (line 761)
[3. PortfolioShadow.open_position()]
       │
       ▼
[4. SQLite shadow_positions ledger]
```
