# SKY / CBT — Milestone 38: Prospective Shadow Research Protocol

**Date:** 2026-11-05  
**Author:** Institutional Quantitative Research Director & Risk Governance Auditor  
**Status:** ACTIVE GOVERNANCE PROTOCOL  
**Target Candidates:** H3 (`H3_OI_FLUSH_CAPITULATION_LONG_BTC`), H5 (`H5_OI_COMPRESSION_BREAKDOWN_SHORT_ETH`)  
**Ledger Path:** `research/m38_shadow_prediction_ledger.jsonl`  

---

## 1. Governance Charter & Non-Negotiable Boundaries

Under the SKY / CBT Three-Tier Governance Architecture:
1. `REAL_CAPITAL_ENABLED = False` is permanently locked.
2. **Zero Execution Authority:** Neither H3 nor H5 may route orders to any exchange account, API key, paper account, or execution router.
3. **Zero Parameter Tuning:** The mathematical definitions and thresholds defined in `research/m38_hypothesis_manifest.json` are cryptographically frozen. Any parameter adjustment automatically invalidates prospective research data.
4. **Append-Only Immutability:** All signals and prospective outcomes must be recorded to `research/m38_shadow_prediction_ledger.jsonl` in an append-only sequence with cryptographic hash chaining. Deletions or retroactive modifications are strictly prohibited.

---

## 2. Prospective Shadow Methodology

Rather than relying on retroactive backtests—which can suffer from selection bias—the prospective shadow protocol records signals in real time **before** future price bars unfold.

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Live Hourly Bar │ ----> │ Cryptographic   │ ----> │ Bar-by-Bar      │
│ Close Event (t) │       │ Signal Logging  │       │ Shadow Tracking │
└─────────────────┘       └─────────────────┘       └─────────────────┘
                                                             │
                                                             v
                                                    ┌─────────────────┐
                                                    │ Terminal Event  │
                                                    │ SL / TP / Time  │
                                                    └─────────────────┘
                                                             │
                                                             v
                                                    ┌─────────────────┐
                                                    │ Reconciliation  │
                                                    │ & Ledger Commit │
                                                    └─────────────────┘
```

### 2.1 Step 1: Signal Emission Event
When an hourly bar closes at timestamp $t$:
1. The candidate rules evaluate purely on completed historical data up to $t$.
2. If triggered, a `SIGNAL_OPEN` record is appended to the ledger before timestamp $t+1$ opens.
3. The record logs:
   - Unique `trade_id`
   - Strategy ID & Candidate SHA-256
   - Expected entry price (open of bar $t+1$)
   - Stop Loss price ($1.0\text{R}$)
   - Take Profit price ($2.0\text{R}$ for H3, $2.5\text{R}$ for H5)
   - Max Hold limit timestamp ($t + 24\text{h}$ for H3, $t + 72\text{h}$ for H5)

### 2.2 Step 2: Continuous State Tracking
At every subsequent hourly bar close:
- Check whether high/low penetrated stop loss or take profit.
- Deduct institutional friction model:
  - Taker entry: $0.04\%$
  - Maker exit: $0.02\%$
  - Slippage: $0.01\%$
  - Spread: $0.01\%$
  - Funding rate settlement: Accrued every 8 hours (00:00, 08:00, 16:00 UTC).

### 2.3 Step 3: Terminal Event Resolution
When an exit condition triggers:
- Append a `SIGNAL_CLOSE` record containing realized gross return, realized net return in R-multiples, slippage incurred, holding duration, and exit reason (`STOP_LOSS`, `TAKE_PROFIT`, or `TIME_EXIT`).

---

## 3. Shadow Prediction Ledger Schema

Each line in `research/m38_shadow_prediction_ledger.jsonl` follows this strict JSON schema:

```json
{
  "event_type": "SIGNAL_OPEN | SIGNAL_CLOSE",
  "trade_id": "H3_BTC_20261105_120000",
  "strategy_id": "H3_OI_FLUSH_CAPITULATION_LONG_BTC",
  "hypothesis_sha256": "3497bd8b7bbad797c7c34e67be658ad8ba5f4b780cf44b729c81bc9c5cba2a68",
  "timestamp_utc": "2026-11-05T12:00:00Z",
  "asset": "BTCUSDT",
  "direction": "LONG",
  "entry_price": 68450.00,
  "stop_loss": 67320.00,
  "take_profit": 70710.00,
  "risk_unit": 1130.00,
  "max_hold_bars": 24,
  "status": "OPEN | CLOSED",
  "exit_timestamp_utc": null,
  "exit_price": null,
  "exit_reason": null,
  "realized_r_net": null
}
```

---

## 4. Graduation & Kill Gates

To graduate from `RESEARCH_CANDIDATE` to `PAPER_TRADING_INCUBATION`, the candidate must satisfy all three graduation gates during prospective shadow observation:

### 4.1 Prospective Sample Size Gate
- **H3:** Minimum **25 prospective shadow trades** ($N_{\text{OOS, total}} \ge 27$).
- **H5:** Minimum **24 prospective shadow trades** ($N_{\text{OOS, total}} \ge 30$).

### 4.2 Statistical Significance Gate
- Prospective Out-Of-Sample Net Expectancy: $\mathbb{E}[R] \ge \mathbf{+0.20R}$.
- Prospective Win Rate: $\ge 45\%$.
- Prospective Profit Factor: $\ge 1.40$.
- 10,000-Iteration Clustered Block Bootstrap 95% Lower Bound: $\mathbf{> 0.00R}$ (Statistically rejected null hypothesis of zero edge).

### 4.3 Prospective Kill-Switch Gate
If at any point during prospective observation:
- Cumulative shadow drawdown reaches **$-6.0\text{R}$**, OR
- 5 consecutive stop losses occur with zero trend continuation,
the candidate is automatically marked **`DEFUNCT_REJECTED`** and decommissioned from the system without further optimization.

---

## 5. Audit & Oversight Schedule

- **Cadence:** Weekly automated ledger reconciliation.
- **Reporting:** Every Sunday at 23:59 UTC, an automated summary will update `docs/research/M38_SHADOW_STATUS.md`.
- **Integrity Verifier:** `python scripts/verify_m18_certification.py` must run concurrently to guarantee zero cross-contamination with the certified execution engine.
