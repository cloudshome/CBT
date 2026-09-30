# Grade-E1 Formal Research Contract & Pre-Registration Protocol

**Document Version:** 1.0.0  
**Certified Date:** 2026-09-19  
**Status:** PRE-REGISTERED (Binding Epistemic & Statistical Protocol)  
**Governance:** Class E/F Quantitative Research Protocol  

---

## 1. Research Objectives & Scope

The objective of **Grade-E1: Institutional Maker Execution Reality Engine** is to determine whether passive limit order execution provides genuine, friction-surviving economic advantage over aggressive taker execution when subjected to:
1. Realistic queue priority constraints.
2. Latency delay in submission, acknowledgement, and cancellation.
3. Adverse selection (post-fill toxic flow).
4. Opportunity cost of unfilled orders during strong market trending.
5. Realistic multi-tier exchange fee schedules (Binance & Bybit VIP0 to VIP4).

---

## 2. Pre-Registered Hypotheses

All statistical tests in Grade-E1 are strictly pre-registered under the following null ($H_0$) and alternative ($H_1$) hypotheses:

### Hypothesis H0-A: Net Maker Edge Non-Negativity
- **$H_0^A$:** Under conservative fill constraints (F1), passive maker execution produces a non-negative net edge after adverse selection and fees:
  $$\mathbb{E}[\text{Net Maker Edge}] \ge 0 \text{ bps}$$
- **$H_1^A$:** Passive maker execution suffers from net negative expectancy due to adverse selection drag and fees:
  $$\mathbb{E}[\text{Net Maker Edge}] < 0 \text{ bps}$$

### Hypothesis H0-B: Absence of Post-Fill Adverse Selection
- **$H_0^B$:** The expected markout at $\tau = 5$ bars post-fill is zero:
  $$\mathbb{E}[\text{Markout}_{\tau=5}] = 0 \text{ bps}$$
- **$H_1^B$:** Passive fills systematically suffer from adverse selection (price drift against position):
  $$\mathbb{E}[\text{Markout}_{\tau=5}] < 0 \text{ bps}$$

### Hypothesis H0-C: Toxicity Independence of Fills
- **$H_0^C$:** The probability of an order getting filled is independent of whether the subsequent $\tau$-bar price movement is adverse:
  $$P(\text{Fill} \mid \text{Adverse Move}) = P(\text{Fill} \mid \text{Favorable Move})$$
- **$H_1^C$:** Fill probability is significantly higher when the subsequent price move is adverse (adverse selection conditioning):
  $$P(\text{Fill} \mid \text{Adverse Move}) > P(\text{Fill} \mid \text{Favorable Move})$$

### Hypothesis H0-D: Maker vs Taker Superiority
- **$H_0^D$:** Calibrated maker execution achieves superior net PnL compared to taker execution across all standard exchange fee tiers (VIP0, VIP2, VIP4):
  $$\text{NetPnL}_{\text{maker}} > \text{NetPnL}_{\text{taker}} \quad \forall \text{ tier} \in \{\text{VIP0}, \text{VIP2}, \text{VIP4}\}$$
- **$H_1^D$:** Maker execution fails to outperform taker execution under standard retail/institutional fee tiers:
  $$\exists \text{ tier}: \text{NetPnL}_{\text{maker}} \le \text{NetPnL}_{\text{taker}}$$

### Hypothesis H0-E: Opportunity Cost Bound
- **$H_0^E$:** The opportunity cost of missed/unfilled maker orders does not exceed the gross fee savings of maker execution:
  $$\mathbb{E}[\text{Opportunity Cost}] \le \text{Fee Savings} = (\text{Fee}_{\text{taker}} - \text{Fee}_{\text{maker}})$$
- **$H_1^E$:** The opportunity cost of missed fills exceeds the fee savings:
  $$\mathbb{E}[\text{Opportunity Cost}] > \text{Fee Savings}$$

### Hypothesis H0-F: Invariance to Queue Penetration Depth
- **$H_0^F$:** Fill rates are invariant to candle penetration depth across varying market volatility regimes.
- **$H_1^F$:** Fill rates depend non-linearly on penetration depth and decay sharply during high-volatility regimes.

---

## 3. Mathematical Definitions & Decomposition

### 3.1. Directional Sign Convention
Let $S \in \{+1, -1\}$ denote order side:
$$S = \begin{cases} +1 & \text{for BUY (Long)} \\ -1 & \text{for SELL (Short)} \end{cases}$$

### 3.2. Post-Fill Markout ($\tau$ bars)
For an order filled at price $P_{\text{fill}}$ at candle index $t$, the post-fill markout at horizon $\tau$ is:
$$\text{Markout}_\tau = S \cdot \left(\frac{P_{t+\tau} - P_{\text{fill}}}{P_{\text{fill}}}\right) \times 10{,}000 \text{ bps}$$

- If $S = +1$ (Buy) and $P_{t+\tau} < P_{\text{fill}}$, $\text{Markout}_\tau < 0$ (adverse movement).
- If $S = -1$ (Sell) and $P_{t+\tau} > P_{\text{fill}}$, $\text{Markout}_\tau < 0$ (adverse movement).

### 3.3. Toxic Fill Ratio
A fill is classified as **toxic** at horizon $\tau = 5$ if $\text{Markout}_5 < 0$:
$$\text{Toxic Fill Ratio} = \frac{1}{N_{\text{fills}}} \sum_{i=1}^{N_{\text{fills}}} \mathbb{I}(\text{Markout}_{5, i} < 0)$$

### 3.4. Spread Capture & Realized Spread
Let $P_{\text{mid}}$ be the prevailing mid-quote at order placement. The gross earned spread is:
$$\text{Gross Spread} = S \cdot \left(\frac{P_{\text{mid}} - P_{\text{fill}}}{P_{\text{mid}}}\right) \times 10{,}000 \text{ bps}$$
The realized spread at horizon $\tau$ is:
$$\text{Realized Spread}_\tau = \text{Gross Spread} + \text{Markout}_\tau$$

### 3.5. Opportunity Cost of Unfilled Orders
For an order that was placed with intended trade signal at time $t$ but remained **UNFILLED** through expiration/cancellation at $t + k$:
$$\text{Opportunity Cost} = \max\left(0, S \cdot \left(\frac{P_{t+k} - P_{\text{limit}}}{P_{\text{limit}}}\right) \times 10{,}000\right) \text{ bps}$$
If the market rallied away from an unfilled Buy limit order, the opportunity cost represents the missed alpha that an aggressive taker fill would have captured.

### 3.6. Net Maker Edge
$$\text{Net Maker Edge} = \text{Gross Spread} - \text{Fee}_{\text{maker}} + \text{Markout}_{\tau} - \left(\frac{N_{\text{unfilled}}}{N_{\text{total}}} \cdot \text{Opportunity Cost}\right)$$

---

## 4. Pre-Registered Decision Thresholds & Research Verdicts

The research verdict is issued strictly deterministically based on empirical test results across the 9 frozen datasets:

| Verdict | Criteria | Operational Impact |
|---|---|---|
| **PROMOTE_FOR_FURTHER_RESEARCH** | $\bullet$ Net Maker Edge $> 0$ at $p < 0.01$ under conservative fill (F1)<br>$\bullet$ Toxic Fill Ratio $< 0.55$<br>$\bullet$ Net Maker outperforms Taker on VIP0/VIP2<br>$\bullet$ DSR $> 1.0$ across all 3 assets | Candidate for next research stage (calibrated L2 data collection). Zero live trading. |
| **QUARANTINE** | $\bullet$ Net Maker Edge $> 0$ under optimistic fill (F3) but $< 0$ under conservative (F1)<br>$\bullet$ Or inconsistent across asset classes (e.g. positive on BTC, negative on SOL) | Retain in research sandbox. Requires regime conditioning and tighter queue filters. |
| **REJECT** | $\bullet$ Net Maker Edge $< 0$ across all fill configurations (F1, F2, F3)<br>$\bullet$ Or Toxic Fill Ratio $> 0.65$<br>$\bullet$ Or Adverse selection completely overwhelms spread capture | Reject maker execution hypothesis for these timeframes. All models revert to conservative taker baseline. |
| **INCONCLUSIVE** | $\bullet$ Statistical power insufficient (bootstrap 95% CI crosses zero with wide dispersion)<br>$\bullet$ Or dataset gaps degrade sample validity | Flag insufficient data; suspend execution assumptions until high-resolution tick archives are available. |

---

## 5. Epistemic Integrity Certification

By this pre-registration:
1. No hypotheses will be modified post-hoc after inspecting backtest results.
2. No data snooping or selective reporting of favorable timeframes will occur.
3. All 9 frozen datasets will be reported without survivorship or cherry-picking.
4. All simulation models remain labeled `GRADE-E1: OHLCV_APPROXIMATION`.
