# M34 Paper-Shadow Deployment Report & Operator Runbook
**Document:** `docs/M34_PAPER_SHADOW_DEPLOYMENT_REPORT.md`  
**Classification:** Live Paper-Shadow Deployment & Operational Protocol  
**Authority:** Paper-Trading Reliability Engineer & Quantitative Architect  
**Date:** 2026-11-04  
**Prospective Ledger:** [`research/live_paper_practice_manifest.jsonl`](file:///c:/Users/azims/CBT/research/live_paper_practice_manifest.jsonl)  
**Permanent Invariant:** `REAL_CAPITAL_ENABLED = False`

---

## 1. Executive Summary & Deployment Clearance

Following full causal, statistical, and execution qualification, `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE` has been authorized for **Live 24/7 Paper-Shadow Deployment**.

### 1.1 Deployment Parameters & Monitored Universe
- **Strategy Identifier:** `HTF_ORDER_BLOCK_KRONOS_CONFLUENCE_v1_0`
- **Frozen Configuration Hash:** `f929db221c5f35d259fa1d798fe111e1f185c7cb17c5b3c37318357497ecb38b`
- **Operating Universe:**
  1. `BTCUSDT` Perpetual (1H Timeframe)
  2. `BTCUSDT` Perpetual (4H Timeframe)
  3. `ETHUSDT` Perpetual (1H Timeframe)
- **Execution Mode:** Local Simulation Only (`REAL_CAPITAL_ENABLED = False`)
- **Order Model:** Mixed Execution (Passive Maker Limit Entry + Contingent Taker Stop + Passive Maker Target)
- **Primary Single-Writer Node:** Ubuntu 24/7 Server

---

## 2. Warmup & Candle Continuity Architecture

To prevent the historical truncation bug:
1. **Parquet Bootstrap Warmup:** On startup, the engine boots from canonical Parquet data, loading a minimum of 1,000 closed 1H bars and 500 closed 4H bars to ensure ATR(14), EMA(200), swing pivots, and Kronos context tensors are fully warmed up.
2. **WebSocket Stitching:** The live WebSocket feed connects and reconciles incoming candles with historical parquet storage by timestamp.
3. **Closed-Bar Finality:** A setup is evaluated **only when a 1H or 4H candle is confirmed closed** by the exchange. In-progress forming candles cannot trigger trades.
4. **Stale Data Firewall:** If the feed has a lag $> 60\text{ seconds}$ past expected candle close, paper entries are paused and an alert is emitted.

---

## 3. Real-Time Signal & Simulated Order Lifecycle

```
[OBSERVED]
    │
    ▼
[SETUP_DETECTED] ──(Displacement + OB Retest)
    │
    ▼
[KRONOS_PENDING] ──(Query Direction & Uncertainty)
    │
    ├─► Rejection (Misaligned / σ > 0.55) ──► [NO_TRADE_LOGGED]
    │
    ▼
[APPROVED] ──(Risk Guardian Clearance <= $25 Risk)
    │
    ▼
[ORDER_PENDING] ──(Passive Limit Placed at OB Boundary)
    │
    ├─► Expiry / Invalidation (No fill after 48 bars or structure shift) ──► [CANCELLED]
    │
    ▼
[FILLED] ──(Simulated penetration >= 0.05 * ATR)
    │
    ├─► Stop Breached ──► [CLOSED_STOP_LOSS] (-1.0R - costs)
    ├─► Target Reached ──► [CLOSED_TAKE_PROFIT] (+2.5R - costs)
    └─► Horizon Timeout ──► [CLOSED_TIMEOUT]
```

---

## 4. Prospective Append-Only Ledger

Every decision (including rejections and `NO_TRADE` events) is appended to:
```
research/live_paper_practice_manifest.jsonl
```
This file was initialized with an immutable Genesis Block and provides prospective out-of-sample forward proof.

---

## 5. Operator Runbook

### 5.1 Starting the 24/7 Paper-Shadow Worker (Ubuntu)
```bash
# Navigate to repository root
cd /home/user/CBT

# Ensure active virtual environment
source .venv/bin/activate

# Launch paper-shadow worker in background with systemd or nohup
nohup python app.py --mode=paper-shadow --symbols=BTCUSDT,ETHUSDT > logs/paper_shadow.log 2>&1 &
```

### 5.2 Checking Worker Health & Status
```bash
# View live tail of paper shadow logs
tail -f logs/paper_shadow.log

# Check recent prospective trade events
tail -n 20 research/live_paper_practice_manifest.jsonl | jq .

# Verify guardian heartbeat
python scripts/system_preflight.py
```

### 5.3 Graceful Shutdown
```bash
# Gracefully signal worker process
kill -TERM $(pgrep -f "app.py --mode=paper-shadow")
```

### 5.4 Emergency Kill Switch & Disable
If any abnormal behavior or anomaly is detected:
```bash
# Immediate emergency kill switch (fails closed, clears pending paper orders)
python -c "from core.execution.risk_guardian import trigger_emergency_kill_switch; trigger_emergency_kill_switch('OPERATOR_MANUAL_HALT')"
```
This forces all paper activity into `HARD_FREEZE`. No simulated orders can be submitted until cleared by explicit operator reset.
