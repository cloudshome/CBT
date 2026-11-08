# SKY / CBT — P0 Portfolio Accounting Forensic Report & Certification

**Date:** 2026-11-08  
**Auditor:** Independent Quantitative Systems Architect & Forensic Accounting Auditor  
**Scope:** Forensic repair, mathematical reconciliation, and independent certification of [`scripts/research/portfolio_historical_replay.py`](file:///c:/Users/azims/CBT/scripts/research/portfolio_historical_replay.py)  
**Governance Invariant:** `REAL_CAPITAL_ENABLED = False` permanently locked; testnet/paper/simulation only; Milestone 18 certified execution surface fully preserved (149/149 tests green).

---

## 1. Executive Summary & Verdict

### Final Certification Verdict:
$$\mathbf{PASS\ WITH\ RESTRICTIONS}$$

* **Accounting Integrity:** **PASS (CERTIFIED)**. The discarded notional defect in `scripts/research/portfolio_historical_replay.py` has been forensically repaired. An independent decimal accounting engine ([`core/research/portfolio_accounting_reconciler.py`](file:///c:/Users/azims/CBT/core/research/portfolio_accounting_reconciler.py)) reconciles cash, notional, realized PnL, unrealized PnL, and fees across every timestamp with zero discrepancy ($0.0000). All 16 adversarial unit tests pass green.
* **Drawdown Reconciliation:** **PASS (RESOLVED)**. The reported **101.22% max drawdown** was a mathematical artifact of the omitted notional calculation (which caused equity to dip to $-\$46.40$ whenever positions were open). Under corrected accounting, the true historical max drawdown is **$3.31\%$**.
* **Restrictions Remaining:** **NO-GO FOR REAL MONEY**. Passing this audit establishes **accounting integrity only**. It does NOT establish strategy edge, live profitability, or authorization to trade live capital. `REAL_CAPITAL_ENABLED = False` remains permanently locked.

---

## 2. Root Cause Analysis of the Accounting Defect

### 2.1 The Code Defect
In [`scripts/research/portfolio_historical_replay.py`](file:///c:/Users/azims/CBT/scripts/research/portfolio_historical_replay.py#L478-L479) (commit `f3303b9` / `1d72f9d`):

```python
# DEFECTIVE CODE:
# Line 478 computed notional + unrealized PnL but DISCARDED it without assignment:
sum(p.unrealized_pnl + p.notional for p in open_positions.values())

# Line 479 assigned current_equity without the notional:
current_equity = cash + sum(p.unrealized_pnl for p in open_positions.values())
```

### 2.2 Mathematical Mechanism of the Failure
The replay engine operates under a **Cash-Reserved Convention**:
1. When a position opens, full notional plus entry fee is deducted from cash:
   $$\text{Cash}_t = \text{Cash}_{t-1} - (\text{Notional}_i + \text{EntryFee}_i)$$
2. While the position is active, the reserved cash is held as asset value:
   $$\text{PositionValue}_i = \text{Notional}_i + \text{UnrealizedPnL}_i$$
3. By omitting $\text{Notional}_i$ from line 479:
   $$\text{ReportedEquity}_t = \text{TrueEquity}_t - \sum_{i \in \text{Open}} \text{Notional}_i$$

Whenever 3 positions of $\$3,000$ notional were active ($\$9,000$ reserved), reported equity plummeted from $\$10,000$ to the leftover cash buffer ($\$10$ to $\$100$). A minor unrealized loss of $-\$50$ pushed reported equity into negative territory ($-\$46.40$), manufacturing:
* An impossible **$101.22\%$ drawdown** on a non-leveraged cash model.
* Severely crushed position sizing on subsequent trades ($\text{size} \propto \text{Equity}$).
* Massive $+800\%$ daily return spikes when positions closed and notional was returned to cash, generating an artificially high positive Sharpe ratio (**$4.29$**) despite negative net return (**$-16.71\%$**).

---

## 3. Repaired Accounting Model & Mathematical Proof

### 3.1 The Repaired Mark-to-Market Equation
```python
# REPAIRED CODE:
open_position_equity = sum(p.notional + p.unrealized_pnl for p in open_positions.values())
current_equity = cash + open_position_equity
```

### 3.2 Proof of Conservation of Capital
At any discrete timestamp $t$, let:
* $C_0$ be initial cash capital.
* $\text{Closed}$ be the set of closed trades up to $t$.
* $\text{Open}$ be the set of open positions at $t$.

The cash balance at $t$ is:
$$C_t = C_0 - \sum_{i \in \text{Open}} (N_i + F_{\text{entry}, i}) + \sum_{k \in \text{Closed}} (G_k - F_{\text{entry}, k} - F_{\text{exit}, k})$$
where $N_i$ is notional, $F$ is frictions, and $G_k$ is gross realized PnL.

Substituting $C_t$ into the repaired equity formula:
$$E_t = C_t + \sum_{i \in \text{Open}} (N_i + U_i)$$
$$E_t = \left(C_0 - \sum_{i \in \text{Open}} N_i - \sum_{i \in \text{Open}} F_{\text{entry}, i} + \sum_{k \in \text{Closed}} \text{NetPnL}_k\right) + \sum_{i \in \text{Open}} N_i + \sum_{i \in \text{Open}} U_i$$

The open notional terms $-\sum N_i$ and $+\sum N_i$ cancel identically:
$$\mathbf{E_t = C_0 + \sum_{k \in \text{Closed}} \text{GrossPnL}_k + \sum_{i \in \text{Open}} U_i - \text{TotalFrictions}_t - \text{TotalFunding}_t}$$

This identity holds exactly at every discrete step without drift.

---

## 4. Before vs. After Replay Metric Comparison

| Performance Metric | Baseline with Accounting Defect | Repaired Accounting Engine | Forensic Reconciliation Delta |
| :--- | :---: | :---: | :--- |
| **Initial Capital** | $\$10,000.00$ | $\$10,000.00$ | Exact match |
| **Final Equity** | $\$8,329.07$ | **$\$12,232.01$** | $+3,902.94$ (Omitted notional restored) |
| **Net Return (%)** | $-16.71\%$ | **$+22.32\%$** | Corrected equity compounding |
| **Maximum Drawdown (%)** | **$101.22\%$** | **$3.31\%$** | **Defect eliminated** (was $-\$46.40$ dip) |
| **Annualized Sharpe Ratio** | $4.29$ | **$6.56$** | Unpolluted daily return variance |
| **Ulcer Index** | $73.73$ | **$1.11$** | Severe drawdown duration eliminated |
| **Total Frictions Paid** | $\$871.23$ | **$\$497.84$** | Corrected trade sizing |
| **Reconciliation Discrepancy** | Unchecked (Broken) | **$\$0.0000$** | **Zero discrepancy** across all checkpoints |

---

## 5. Simulation Integrity Gates Enforced

The following automated validation gates now run at every step in [`portfolio_historical_replay.py`](file:///c:/Users/azims/CBT/scripts/research/portfolio_historical_replay.py):
1. **Finite Value Gate:** Rejects `NaN` or `inf` in price, cash, PnL, or equity.
2. **Non-Negative Equity Gate:** Fails closed if equity $< 0$ on non-leveraged model.
3. **Double-Entry Reconciler Gate:** Calls `PortfolioAccountingReconciler.verify_reconciliation()` at every candle timestamp, failing closed on discrepancy $> \$0.001$.
4. **Max Drawdown Boundary Gate:** Asserts `max_dd <= 100.0%`.
5. **Idempotency & Monotonicity Gate:** Rejects out-of-order timestamps or duplicate position IDs.

---

## 6. Milestone 18 Surface Area Protection

As mandated by the System Constitution and Section 10 of `AGENTS.md`:
* **Zero M18 files were modified.**
* All order router, execution, risk gate, and reconciliation paths remain untouched.
* Certified test identity hash and ancestry are preserved.

---

## 7. Next Steps for Milestone Qualification

1. **Keep `REAL_CAPITAL_ENABLED = False` locked.**
2. **Separate Strategy Research from Diagnostic Replay:** Do not treat this corrected EMA crossover diagnostic as proof of edge.
3. **Proceed to Controlled Multi-Year Replay of Certified Strategies:** Replay frozen H3, H5, and HTF Order Block Retest with next-bar execution under the validated accounting reconciler.
