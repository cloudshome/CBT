---
name: cbt-active-trader
description: "Active Trader Skill for Crypto Brain Terminal (CBT) / SKY. Autonomous market scanning, risk-governed paper & live execution, dynamic M47 trailing ratchets, and fail-closed panic close workflows across BTC, ETH, SOL, and Gold."
---

# CBT Active Trader Skill & Operational Governance

The **Active Trader Skill** equips autonomous agents and quantitative operators with the definitive workflows required to operate, monitor, and trade using the Crypto Brain Terminal (CBT / SKY).

- **Official Repository Target:** `https://github.com/cloudshome/CBT.git`
- **Execution Architecture:** Fail-closed dual-mode (`PAPER` simulation default vs. `PRODUCTION` live exchange routing).
- **Core Assets:** `BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `XAU/USD` (Gold).
- **Primary Timeframes:** `15m` execution horizon, `1h` structural trend, `4h` macro regime.

---

## 1. ARCHITECTURAL OPERATIONAL WORKFLOWS

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. LIVE MARKET SCANNING (Multi-timeframe SMC, CVD, Liquidity Sweeps)        │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. CONSTITUTIONAL RISK CLEARANCE (Half-Kelly, 1.5% Cap, Clock Drift <=500ms)│
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. DUAL-MODE EXECUTION ROUTER (Paper Shadow vs. Live Production Gateway)     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. DYNAMIC TRAILING RATCHETS (M47: Stage 1 @ +1.20R, Stage 2 @ +1.50R)      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. RECONCILIATION & PANIC CLOSE (Canonical State Reconciler, Kill Switch)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. WORKFLOW 1: LIVE MARKET SCANNING

The scanning engine analyzes closed candles across configured timeframes (`15m`, `1h`) to detect valid institutional SMC structures without lookahead bias:

### CLI / Autonomous Scan:
```bash
# Run one-shot multi-asset scan across 15m and 1h
python scripts/sync_forward_paper_book.py --scan

# Run standalone asset intelligence scan
python main.py scan --symbol BTCUSDT --tf 15m --json

# Query complete 8-Pillar institutional desk dossier
python main.py intelligence --symbol BTCUSDT --tf 15m
```

### Scan Evaluation Criteria:
1. **Zero-Lookahead Invariant:** Scans evaluate strictly closed bars (`-1`), never open intrabar ticks.
2. **Directional Wick Absorption:**
   - **LONG:** Last closed bar must be bullish, or exhibit $\ge 35\%$ lower absorption wick.
   - **SHORT:** Last closed bar must be bearish, or exhibit $\ge 35\%$ upper absorption wick.
3. **Multi-Timeframe Confluence:** Minimum confluence score $\ge 65.0$ (Grade A+ setup threshold $\ge 86.0$ when rolling asset PF $< 0.85$).

---

## 3. WORKFLOW 2: RISK-GOVERNED EXECUTION & DUAL-MODE ROUTING

CBT enforces fail-closed execution isolation (`core/risk/execution_isolation.py`). Real money orders can never be dispatched unless all 5 constitutional gates pass simultaneously.

### Execution Modes:
- **`EXECUTION_MODE=PAPER` (Default):** Routes trades to sovereign shadow ledger (`core/portfolio_shadow.py`). Zero exchange credentials required.
- **`EXECUTION_MODE=PRODUCTION`:** Routes orders to `core/execution/live_router.py` and real exchange sockets (`BinanceFuturesConnector`, `BybitV5Connector`).

### Mandatory Live Production Gatekeeper Invariants:
1. `LIVE_EXECUTION_ENABLED="true"` environment flag.
2. Valid, non-mock API credentials registered in `core/auth/credential_vault.py`.
3. System clock drift $\le 500\text{ms}$ with active exchange heartbeat.
4. Cumulative daily drawdown $\le 3.0\%$ circuit breaker.
5. Single-trade notional sizing $\le 1.5\%$ of total portfolio equity (Half-Kelly capped).
6. Hardware Security Key (WebAuthn / FIDO2) physical clearance or active autonomous daemon lease.
7. Master Live Kill Switch disengaged (`live_kill_switch.is_active() == False`).

---

## 4. WORKFLOW 3: DYNAMIC M47 TRAILING RATCHETS

Once a position is entered, CBT actively manages stops and scale-outs via the **M47 Certified Ratchet Geometry**:

1. **Initial Risk Perimeter:** Stop loss anchored to swing structure; position sized so loss at SL equals exactly $-1.0R$ ($\le 1.5\%$ equity).
2. **Stage 1 Risk Reduction (`+1.20R` Intrabar Touch):**
   - Trigger: Intrabar high/low reaches $+1.20R$ profit from entry.
   - Action: Tighten stop loss from $-1.00R$ to $-0.20R$ (cutting $80\%$ of baseline downside risk).
   - *Preserves continuation runners while protecting downside.*
3. **Stage 2 Profit-Lock (`+1.50R` Touch / TP1):**
   - Trigger: Intrabar touch at $+1.50R$.
   - Action: Scale out $15\%$ of position notional; raise stop loss to $+0.35R$ net profit lock.
4. **Final Target (`+3.00R` to `+4.00R` / TP2):**
   - Remaining $85\%$ continues running toward liquidity pool sweeps or structural reversal.

---

## 5. WORKFLOW 4: PANIC CLOSE & EMERGENCY CIRCUIT BREAKERS

In the event of black-swan volatility, exchange outage, or anomalous venue dislocation:

### CLI / Script Panic Close:
```bash
# Emergency Flatten all paper and live open positions immediately
python -c "from core.portfolio_shadow import portfolio_shadow; print(portfolio_shadow.close_all_positions(reason='PANIC_CLOSE'))"

# Activate Master Live Kill Switch (Halts all order transmission instantly)
python -c "from core.execution.kill_switch import live_kill_switch; live_kill_switch.engage(operator='ADMIN_PANIC')"
```

### Telegram Bot Emergency Directives:
- `/panic_close` — Closes all active open positions at market across all desks.
- `/kill_switch on` — Engages emergency master kill switch.
- `/live_preflight <venue> <size>` — Validates preflight clearance before manual orders.

---

## 6. TELEGRAM AI 2-STEP ADMIN CONFIRMATION

Class D live orders requested via Telegram AI require strict 2-step button confirmation:
1. Operator submits trade request via text or button.
2. Gateway verifies caller possesses `TelegramRole.ADMIN`.
3. Prompt displays: Symbol, Direction, Notional USD, Stop Loss, and Risk % of Equity.
4. Action buttons: `[ 🚨 CONFIRM LIVE EXECUTION ]` vs `[ ❌ CANCEL LIVE ]`.
5. Cryptographic token expires in 60 seconds.

---

## 7. INSTALLATION & BOOT-TIME INTEGRITY

```bash
# Clone official repository
git clone https://github.com/cloudshome/CBT.git
cd CBT

# Initialize virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run system preflight & test battery
python scripts/system_preflight.py
pytest tests/test_milestone18_final_certification.py -v
pytest tests/test_binance_futures_production_readiness.py -v

# Launch CBT backend daemon
python cbt_backend.py
```
