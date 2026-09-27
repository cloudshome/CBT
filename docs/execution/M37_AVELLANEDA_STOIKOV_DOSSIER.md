# MILESTONE 37 RESEARCH & QUANTITATIVE DOSSIER
## Avellaneda-Stoikov (2008) High-Frequency Market Making & Hawkes Flow Toxicity Reality Engine

**Platform Release:** `v4.0.0`  
**Milestone:** 37  
**Status:** PRODUCTION PASS (8/8 Verified Tests Green)  
**Constitutional Capital Firewall:** `real_capital_enabled = False`  
**Milestone 18 Integrity Status:** PASS (149/149 Certified Tests Locked at `c9cc1cad`)  

---

### 1. Executive Summary & Mathematical Foundation

Milestone 37 expands the SKY/CBT execution layer with an analytical high-frequency market making engine governed by Avellaneda & Stoikov (2008) reservation pricing coupled with a recursive self-exciting Hawkes point process for sub-millisecond adverse-selection defense.

Under traditional naïve market making, quotes placed symmetrically around the mid-price suffer from adverse selection: incoming informed flow fills the market maker precisely before toxic price moves, leading to catastrophic inventory depletion or directional skew. Milestone 37 resolves this via two coupled quantitative mechanisms:
1. **Inventory-Aware Reservation Price Skewing:** Quotes dynamically shift away from accumulated inventory to attract mean-reverting rebalancing flow.
2. **Hawkes Self-Exciting Process for Toxicity Detection:** Incoming trade arrivals trigger intensity spikes $\lambda(t)$ with calibrated exponential decay half-lives, dynamically widening the quoted spread or pulling quotes when trade clusters indicate adverse information cascades.

---

### 2. Theoretical Formulation

#### 2.1 Reservation Price (Indifference Price)
The market maker's utility maximization under constant absolute risk aversion (CARA $\gamma$) yields the indifference reservation price $r(s, q, t)$:
$$r(s, q, t) = s - q \gamma \sigma^2 (T - t)$$
Where:
- $s$: Current mid-market price
- $q$: Current net inventory in base asset units ($q > 0$ for long, $q < 0$ for short)
- $\gamma$: Absolute risk-aversion coefficient ($\gamma > 0$)
- $\sigma$: Asset instantaneous return volatility
- $T - t$: Market maker's terminal inventory holding horizon

**Microstructure Behavior:**
- When $q > 0$ (inventory long), $r < s$: The reservation price shifts below mid, lowering the ask quote to aggressively incentivize external buyers to offload inventory, while retreating the bid quote to prevent further accumulation.
- When $q < 0$ (inventory short), $r > s$: The reservation price shifts above mid, lifting the bid quote to attract sellers, while elevating the ask quote.
- When $q = 0$ (inventory flat), $r = s$: Quotation is purely symmetric around mid.

#### 2.2 Optimal Spread & Half-Spread Asymmetry
The theoretical optimal total spread $s^*$ and optimal half-spreads $\delta^a, \delta^b$ are given by:
$$s^*(s, q, t) = \gamma \sigma^2 (T - t) + \frac{2}{\gamma} \ln\left(1 + \frac{\gamma}{\kappa}\right)$$
$$\delta^a = \frac{r - s}{2} + \frac{1}{\gamma} \ln\left(1 + \frac{\gamma}{\kappa}\right) + \frac{1}{2} \gamma \sigma^2 (T - t)$$
$$\delta^b = \frac{s - r}{2} + \frac{1}{\gamma} \ln\left(1 + \frac{\gamma}{\kappa}\right) + \frac{1}{2} \gamma \sigma^2 (T - t)$$
Where $\kappa$ parameterizes the order flow density decay $A e^{-\kappa \delta}$ as quotes move deeper into the book.

Raw quoting prices:
$$\text{raw\_ask} = s + \delta^a$$
$$\text{raw\_bid} = s - \delta^b$$

#### 2.3 Microstructure Tick Discretization & Spread Floor
Exchange order books enforce discrete tick sizes $\Delta_{\text{tick}}$. To guarantee non-crossing and compliant limit orders:
$$\text{discrete\_ask} = \left\lceil \frac{\text{raw\_ask}}{\Delta_{\text{tick}}} \right\rceil \Delta_{\text{tick}}$$
$$\text{discrete\_bid} = \left\lfloor \frac{\text{raw\_bid}}{\Delta_{\text{tick}}} \right\rfloor \Delta_{\text{tick}}$$
$$\text{discrete\_ask} - \text{discrete\_bid} \ge 2 \cdot \Delta_{\text{tick}}$$

---

### 3. Hawkes Process Flow Toxicity Reality Engine

#### 3.1 Recursive Intensity Dynamics
To detect toxic trade cascades in $\mathcal{O}(1)$ time per fill without re-evaluating historical event buffers, we employ an exponential kernel Hawkes self-exciting point process:
$$\lambda(t) = \mu + \sum_{t_i < t} \alpha e^{-\beta (t - t_i)}$$
Given recursive state $R(t_{k-1})$ at event $k-1$:
$$R(t_k) = e^{-\beta (t_k - t_{k-1})} (1 + R(t_{k-1}))$$
$$\lambda(t_k) = \mu + \alpha R(t_k)$$

Parameters:
- $\mu$: Baseline non-toxic trade arrival rate ($\mathrm{trades/sec}$)
- $\alpha$: Self-excitation jump magnitude per trade
- $\beta$: Exponential decay rate ($\mathrm{sec}^{-1}$), yielding half-life $\tau_{1/2} = \frac{\ln(2)}{\beta}$
- Branching ratio $\eta = \frac{\alpha}{\beta} < 1$ (subcriticality condition for stability)

#### 3.2 Toxicity Tier Classification & Dynamic Spread Widening
| Hawkes Ratio $\lambda(t) / \mu$ | Toxicity Tier | Quoting Multiplier | Tactical Defense Action |
|:---:|:---:|:---:|:---|
| $< 1.5\times$ | `BENIGN_BALANCED` | $1.0\times$ | Standard Avellaneda-Stoikov quoting |
| $1.5\times - 3.0\times$ | `MODERATE_FLOW` | $1.25\times$ | Precautionary spread widening |
| $3.0\times - 6.0\times$ | `ELEVATED_TOXICITY` | $1.75\times$ | Aggressive spread widening |
| $\ge 6.0\times$ | `CRITICAL_TOXIC_SURGE` | $2.50\times$ | Critical toxicity defense: maximum spread & quote retraction |

---

### 4. Constitutional Risk Primacy & Defensive Single-Sided Quoting

Under the System Constitution (`.specify/memory/constitution.md`), trading capital is governed by strict risk invariants:
- Single-asset position allocation is hard-capped at $\le 1.5\%$ total portfolio equity.
- When market making inventory $|q| \cdot s \ge 0.015 \cdot \text{Equity}$:
  - If $q > 0$ (inventory long reaches 1.5% equity cap): Quoting on the bid (accumulating side) is **immediately suspended**. The sentinel quotes exclusively on the ask side (`allowed_sides = ["SELL"]`).
  - If $q < 0$ (inventory short reaches 1.5% equity cap): Quoting on the ask is **immediately suspended**. The sentinel quotes exclusively on the bid side (`allowed_sides = ["BUY"]`).
- `real_capital_enabled = False` is enforced across all structures, models, and outputs.

---

### 5. Empirical Verification Suite (8 Passing Tests)

```
tests/execution/test_milestone37_avellaneda_stoikov.py::test_01_reservation_price_inventory_symmetry PASSED [ 12%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_02_optimal_spreads_and_quote_asymmetry PASSED [ 25%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_03_discrete_quotes_tick_grid_and_non_crossing PASSED [ 37%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_04_hawkes_exponential_decay_and_half_life PASSED [ 50%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_05_hawkes_clustering_triggers_spread_widening PASSED [ 62%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_06_inventory_at_1_5_percent_cap_disables_accumulating_side PASSED [ 75%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_07_permanent_capital_isolation_firewall PASSED [ 87%]
tests/execution/test_milestone37_avellaneda_stoikov.py::test_08_milestone18_execution_surface_untouched PASSED [100%]
```

The certified Milestone 18 execution boundary (149/149 tests) remains 100% active and unmodified.
