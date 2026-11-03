# SKY / CBT — M33 Portfolio Accounting & Risk Mathematics Verification

**AUDIT MANDATE:** Mathematical Correctness & Ledger Reconciliation  
**AUDIT ROLE:** Quantitative Risk Engineer & Forensic Auditor  
**EVALUATED SURFACE:** `core/risk/immutable_risk_accounting.py`, `core/risk/portfolio_risk_guardian.py`, `data/trading_logs.db`, `data/historical_ledger_reconstruction_m31.json`.

---

## 1. DETERMINISTIC RISK & ACCOUNTING FORMULAS

### 1. Initial Position Risk ($R_0$) & Immutable Stop

For a trade entered at entry price $P_{\text{entry}}$, with initial protective stop $P_{\text{stop}}$, position size $S$, and contract multiplier $M$:

$$\Delta P_0 = \begin{cases} P_{\text{entry}} - P_{\text{stop}} & \text{if DIRECTION = LONG} \\ P_{\text{stop}} - P_{\text{entry}} & \text{if DIRECTION = SHORT} \end{cases}$$

$$\text{Initial Risk USD } (R_{\text{usd}, 0}) = \Delta P_0 \times S \times M$$

$$\text{Initial Risk Fraction } (r_0) = \frac{\Delta P_0}{P_{\text{entry}}}$$

**Denominator Sanity & Floor Invariants:**
- Strict Geometry: $\Delta P_0 > 0$. If $P_{\text{stop}} \ge P_{\text{entry}}$ on LONG or $P_{\text{stop}} \le P_{\text{entry}}$ on SHORT, status is marked `INVALID_DENOMINATOR` and rejected.
- Plausibility Guard: If $r_0 < 0.0005$ ($0.05\%$) or $R_{\text{usd}, 0} < \$1.00$, marked `IMPLAUSIBLE_DENOMINATOR` (the exact Trade 36 breakeven stop defect).
- Immutability: Once $R_{\text{usd}, 0}$ is recorded in `ImmutableRiskBudget`, trailing stops, breakeven adjustments, and ratchets **NEVER** alter $R_{\text{usd}, 0}$.

---

### 2. Current Stop Risk vs. Initial Risk

When a trailing stop moves from $P_{\text{stop}, 0}$ to $P_{\text{stop}, t}$:
$$\Delta P_t = \begin{cases} P_{\text{current}} - P_{\text{stop}, t} & \text{if LONG} \\ P_{\text{stop}, t} - P_{\text{current}} & \text{if SHORT} \end{cases}$$
$$\text{Current Open Risk USD } (R_{\text{usd}, t}) = \max(0, \Delta P_t \times S_t \times M)$$

**Separation Rule:**
- $R_{\text{usd}, t}$ is used strictly for **real-time portfolio risk aggregation**.
- $R_{\text{usd}, 0}$ is used strictly for **realized trade Net R attribution** ($\text{Net } R = \frac{\text{Net PnL}}{R_{\text{usd}, 0}}$).
- Moving a stop to breakeven ($P_{\text{stop}} = P_{\text{entry}}$) reduces current open risk $R_{\text{usd}, t} \to 0$, but **leaves initial risk $R_{\text{usd}, 0}$ completely unchanged**.

---

### 3. Aggregate Open Risk & Pending Order Reservation

Across $K$ active open positions and $J$ pending unfilled orders:

$$R_{\text{agg}} = \sum_{k=1}^K \max\left(\$25.00, R_{\text{usd}, 0}^{(k)} \times \frac{S_{\text{open}}^{(k)}}{S_{\text{initial}}^{(k)}}\right) + \sum_{j=1}^J R_{\text{reserved}}^{(j)}$$

**Enforcement:**
$$R_{\text{agg}} + R_{\text{proposed}} \le \text{Base Capital} \times \text{Aggregate Open Risk Cap} = \$10,000 \times 0.75\% = \$75.00$$

---

### 4. Gross Notional & Leverage

$$\text{Gross Notional } (N_{\text{gross}}) = \sum_{k=1}^K P_{\text{current}}^{(k)} \times S_k \times M_k$$
$$\text{Net Notional } (N_{\text{net}}) = \sum_{k \in \text{LONG}} P_{\text{current}}^{(k)} S_k M_k - \sum_{k \in \text{SHORT}} P_{\text{current}}^{(k)} S_k M_k$$
$$\text{Effective Leverage } (L) = \frac{N_{\text{gross}}}{\text{MtM Equity}}$$

**Enforcement:**
$$N_{\text{gross}} \le \$30,000.00 \quad \text{and} \quad L \le 3.0\times$$

---

### 5. Mark-to-Market Equity & Continuous Drawdown

$$\text{MtM Equity } (E_t) = \text{Cash Balance}_t + \sum_{k=1}^K \text{Unrealized PnL}_k(t)$$
$$\text{Peak Equity } (E_{\text{peak}, t}) = \max_{0 \le \tau \le t} E_\tau$$
$$\text{Intraday Drawdown } (DD_t) = \frac{E_{\text{peak}, t} - E_t}{E_{\text{peak}, t}} \times 100\%$$

**Enforcement:**
$$DD_t \ge 2.0\% \implies \text{IMMEDIATE HARD\_FREEZE}$$

---

### 6. Daily Loss & Rollover Invariant

$$\text{Intraday Loss USD } (L_{\text{daily}, t}) = \text{Daily Realized Loss}_t + \max\left(0, -\sum_{k=1}^K \text{Unrealized PnL}_k(t)\right)$$
$$\text{Intraday Loss \% } = \frac{L_{\text{daily}, t}}{\text{Base Capital}} \times 100\%$$

**Enforcement:**
- $L_{\text{daily}} \ge 1.0\% \implies \text{WARNING}$
- $L_{\text{daily}} \ge 1.25\% \implies \text{REDUCED\_EXPOSURE}$
- $L_{\text{daily}} \ge 1.5\% \implies \text{HARD\_FREEZE}$

**Rollover Invariant:**
At $00:00:00\text{ UTC}$, `daily_realized_loss` resets to $\$0.00$. However:
$$\text{If State } \in \{\text{HARD\_FREEZE}, \text{INVESTIGATION}\} \implies \text{State remains frozen}.$$

---

### 7. Partial-Fill and Partial-Exit Reconciliation

When a position of initial size $S_0$ closes a partial slice of size $S_{\text{exit}}$:
$$\text{Slice Fraction } (f) = \frac{S_{\text{exit}}}{S_0}$$
$$\text{Attributed Initial Risk } (R_{\text{slice}}) = R_{\text{usd}, 0} \times f$$
$$\text{Slice Net PnL } = \text{Gross PnL}_{\text{slice}} - \text{Fee}_{\text{slice}} - \text{Slippage}_{\text{slice}}$$
$$\text{Slice Realized } R = \frac{\text{Slice Net PnL}}{R_{\text{slice}}}$$
$$\text{Remaining Open Risk } = R_{\text{usd}, 0} \times \left(1 - \sum f_{\text{closed}}\right)$$

---

## 2. RECONCILIATION OF THE 52 HISTORICAL TRADES

The complete chronological ledger of 52 closed trades in `data/trading_logs.db` was independently recomputed from raw executions:

| Category | Metric Value | Exact Calculation / Derivation |
| :--- | :--- | :--- |
| **Total Closed Trades** | **52** | Count of distinct closed positions in `shadow_positions`. |
| **Gross Cumulative Volume** | **$\$780,883.74$** | $\sum_{i=1}^{52} (P_{\text{entry}, i} \times S_i + P_{\text{exit}, i} \times S_i)$. |
| **Winning Trades** | **15** | Win rate = $15 / 52 = 28.85\%$. |
| **Losing Trades** | **37** | Loss rate = $37 / 52 = 71.15\%$. |
| **Gross Winning P&L** | **$+\$1,489.15$** | Sum of positive trade returns. |
| **Gross Losing P&L** | **$-\$2,631.22$** | Sum of negative trade returns. |
| **Nominal Realized P&L** | **$-\$1,142.07$** | $\$1,489.15 - \$2,631.22 = -\$1,142.07$. |
| **Starting Capital** | **$\$10,000.00$** | Initial sandbox cash balance. |
| **Ending Nominal Cash** | **$\$8,857.93$** | $\$10,000.00 - \$1,142.07 = \$8,857.93$. |
| **Modeled Entry Slippage (5 bps)** | **$-\$390.44$** | $0.0005 \times \$780,883.74 = \$390.44$. |
| **Slippage-Adjusted Net Cash** | **$-\$1,532.51$** | $-\$1,142.07 - \$390.44 = -\$1,532.51$. |
| **Historical Equity Peak** | **$\$10,000.00$** | Trade 0 (before initial trade drawdowns). |
| **Historical Equity Trough** | **$\$8,643.46$** | Reached at Trade 45 following consecutive losses. |
| **Peak-to-Trough Drawdown** | **$13.565\% \approx 13.57\%$** | $(\$10,000.00 - \$8,643.46) / \$10,000.00 = 13.565\%$. |

---

## 3. AUDIT CLASSIFICATION OF HISTORICAL R VALUES

In the reconstructed dataset published in `data/historical_ledger_reconstruction_m31.json`:
- **`R_VERIFIED` (36 trades):** Trades with valid initial protective stop-loss geometries and verified risk budgets.
- **`R_ESTIMATED` (15 trades):** Trades where stop distance was clamped to standard institutional volatility bands ($1.5\%$ ATR fallback).
- **`R_UNVERIFIABLE` (1 trade — Trade 36):** The breakeven stop collision where initial risk was overwritten by trailing stop, collapsing denominator to cents. Flagged as unrecoverable ground truth; preserved for historical integrity without fabricating synthetic performance.

