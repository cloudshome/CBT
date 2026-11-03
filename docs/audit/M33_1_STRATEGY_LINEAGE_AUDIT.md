# SKY / CBT — Milestone 33.1: Strategy Lineage & Quarantine Inheritance Audit

**Document ID:** `docs/audit/M33_1_STRATEGY_LINEAGE_AUDIT.md`  
**Execution Timestamp:** 2026-11-03T18:25:00Z  
**Auditor:** Independent Quantitative Systems Auditor & Portfolio Risk Engineer  
**Module Audited:** `core/risk/strategy_lineage_registry.py` & `core/risk/portfolio_risk_guardian.py`  
**Audit Verdict:** **PRODUCTION PASS (LINEAGE INHERITANCE CONFIRMED)**

---

## 1. Executive Summary & Audit Context

Following Milestone 31, the 52-trade historical shadow strategy was quarantined due to a verified peak-to-trough drawdown of $13.57\%$. However, an adversarial code audit discovered an evasive loophole:
- **Strategy Renaming Loophole:** If an author merely created a new strategy identifier (e.g. changing `strategy_id` from `SHADOW_ORDER` $\to$ `SHADOW_ORDER_V2`), the risk guardian would treat it as a brand-new strategy, erasing the failure history and bypassing quarantine restrictions even if the signal logic was identical.
- **Superficial Parameter Tweak Loophole:** If an author slightly adjusted an ATR stop multiplier (e.g. from $1.50 \to 1.55$) while running the same toxic regime-fragile logic, the system lacked a metric to detect cosmetic mutations.

Milestone 33.1 resolved this vulnerability by deploying the **`StrategyLineageRegistry`** ([`core/risk/strategy_lineage_registry.py`](file:///c:/Users/azims/CBT/core/risk/strategy_lineage_registry.py)), establishing cryptographic genome tracking, parameter fingerprinting, and automated quarantine inheritance.

---

## 2. Lineage Architecture & Inheritance Engine

```
                             ┌──────────────────────────────┐
                             │       Proposed Strategy      │
                             │  - strategy_id               │
                             │  - genome_content (code/AST) │
                             │  - parameters (dict)         │
                             └──────────────┬───────────────┘
                                            │
                                            ▼
                             ┌──────────────────────────────┐
                             │  Gate 1: Direct ID Check     │
                             │  Is strategy_id quarantined? │
                             └──────────────┬───────────────┘
                                            │ NO
                                            ▼
                             ┌──────────────────────────────┐
                             │  Gate 2: Genome Hash Match   │
                             │  Does SHA-256(genome) match  │
                             │  ANY quarantined strategy?   │
                             └──────────────┬───────────────┘
                                            │ NO
                                            ▼
                             ┌──────────────────────────────┐
                             │  Gate 3: Parameter Divergence│
                             │  Is parameter divergence     │
                             │  delta < 15% against family? │
                             └──────────────┬───────────────┘
                                            │ NO
                                            ▼
                             ┌──────────────────────────────┐
                             │    LINEAGE_AUTHORIZED        │
                             │ (Genuinely Distinct Strategy)│
                             └──────────────────────────────┘
```

---

## 3. Mathematical Divergence & Fingerprinting Formulations

### A. Strategy Genome Hash
Normalized source code or signal rules are stripped of superficial whitespace and case-folded to produce an invariant cryptographic digest:
$$\mathcal{G} = \text{SHA256}\left(\text{Normalize}(\text{SignalLogicCode})\right)$$

### B. Parameter Divergence Metric
For any proposed strategy parameters $P_{\text{target}}$ evaluated against quarantined parameters $P_{\text{quarantined}}$, the normalized relative parameter divergence is calculated across all common numerical keys $\mathcal{K}$:
$$\mathcal{D}\left(P_1, P_2\right) = \frac{1}{|\mathcal{K}|} \sum_{k \in \mathcal{K}} \frac{\left|v_{1,k} - v_{2,k}\right|}{\max\left(|v_{1,k}|, |v_{2,k}|, 10^{-6}\right)}$$
- If $\mathcal{D} < 0.15$ (i.e. less than $15\%$ average parameter variation), the strategy is classified as a **superficial cosmetic tweak** and inherits the quarantine restriction (`QUARANTINE_INHERITED_PARAM_TWEAK`).
- If $\mathcal{D} \ge 0.15$ with distinct signal logic, the strategy is classified as genuinely distinct and authorized for evaluation (`LINEAGE_AUTHORIZED`).

---

## 4. Verification Evidence Matrix

| Adversarial Evasion Scenario | Injected Vector | Evaluated Verdict | Test Reference |
|:---|:---|:---:|:---:|
| **Direct Renaming of Quarantined ID** | `strategy_id="LEGACY_TOXIC_SMC_V1"` | Blocked with `DIRECT_STRATEGY_QUARANTINE` | `test_m33_1_identical_genome_evasion_blocked` |
| **Identical Code under New Name** | `ALPHA_GOD_V1` with identical SMC logic | Blocked with `QUARANTINE_INHERITED_IDENTICAL_GENOME` | `test_m33_1_identical_genome_evasion_blocked` |
| **Minor ATR Tweak (5% Shift)** | `NEW_MOMENTUM_B` with ATR 2.0 $\to$ 2.1 | Blocked with `QUARANTINE_INHERITED_PARAM_TWEAK` | `test_m33_1_superficial_parameter_tweak_evasion_blocked` |
| **Genuinely Independent Strategy** | Cointegration Stat-Arb vs SMC | Approved with `LINEAGE_AUTHORIZED` | `test_m33_1_genuinely_distinct_strategy_permitted` |

---

## 5. False-Positive Over-Quarantine Prevention

The audit confirmed that the lineage inheritance logic does **not** over-penalize unrelated strategies:
- Strategies that operate on different genomes (e.g. mean-reversion cointegration pairs vs momentum breakout) produce distinct $\mathcal{G}$ hashes and are evaluated independently.
- Parameter divergence checks are scoped to strategies sharing lineage families or genome templates, preventing unrelated strategies sharing standard risk parameters (such as $0.25\%$ risk) from cross-contaminating quarantine records.
