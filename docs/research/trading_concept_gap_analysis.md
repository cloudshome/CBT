# Trading Concept Intelligence System — Gap Analysis

**Date:** 2026-10-13  
**Baseline Commit:** `e11251b`  
**Target Architecture:** CBT / SKY Institutional Trading Concept Intelligence & Strategy Discovery System

---

## 1. Overview of Existing vs. Target Capabilities

| Capability Domain | Current State in Repository (`e11251b`) | Identified Gap | Target Remediation |
|:---|:---|:---|:---|
| **Master Concept Taxonomy (15 Families, 60 Concepts)** | Scattered across `engine/rules.py` (6 plan types), `core/sky_intelligence/setup_engine.py` (5 setups), `core/autonomous_quant_strategist.py` (5 gene types), and domain modules (`core/arbitrage/`, `core/volatility/`, `core/mbo/`). | No unified, versioned, machine-readable registry of the 60 global quantitative and discretionary trading concepts across 15 families. | Implement `core/research/concept_registry.py` containing all 60 canonical concepts across 15 families with SQLite persistence, search/filter/compare, overlap detection, and experiment history. |
| **Evidence-Gated Lifecycle State Machine** | `core/strategy_league.py` has 4 tiers (`SANDBOX_CANDIDATE`, `VALIDATION_LEAGUE`, `PAPER_SHADOW_LEAGUE`, `ELITE_ALLOCATION_POOL`), and `research/experiment_registry.py` has 3 states (`PROMOTED`, `REJECTED`, `QUARANTINED`). | Missing the 11-state institutional concept lifecycle (`RESEARCH` $\to$ `SPECIFIED` $\to$ `IMPLEMENTED` $\to$ `BACKTESTED` $\to$ `OUT_OF_SAMPLE_VALIDATED` $\to$ `PAPER_QUALIFIED` $\to$ `PAPER_VALIDATED`, plus `REJECTED`, `QUARANTINED`, `NEEDS_MORE_DATA`, `DEMOTED`) with fail-closed transition gates. | Implement `ConceptLifecycleStatus` and `ConceptEvidenceGate` in `core/research/concept_registry.py` with auditable transition logs and automatic demotion/quarantine on gate failure. |
| **Historical Setup Provenance & Priors** | `core/sky_intelligence/setup_engine.py` hardcodes unverified priors (`0.38R / n=4218`, `0.42R / n=2890`, etc.). Early P12.5 synthetic runs (`+0.657R`, `+0.573R`) suffered from 32x overlapping windows (`step=3`, `horizon=96`). | Setup priors are not grounded in non-overlapping, cost-adjusted real-data backtests; overlapping bars inflate apparent sample size $N$. | Record exact forensic audit verdicts per setup in the Concept Registry (`Buy/Sell Pullback` $\to$ `NEEDS_MORE_DATA`, `Sweep Reversal Buy` $\to$ `QUARANTINED`, `Sweep Reversal Sell` & `Breakout Buy` $\to$ `REJECTED`) and enforce overlap-adjusted $N_{\text{eff}}$ in evaluation. |
| **Fair Multi-Family Strategy Evaluator (Candidates A–F)** | `data/backtester.py` only evaluates `engine/rules.py` `Plan` objects (`Buy Pullback`, `Breakout Buy`, etc.). `core/autonomous_research/empirical_tester.py` only runs simplified keyword dispatch (`trend`, `mean_reversion`, `funding`, `volatility`). | Cannot fairly compare Candidates A–F (TSMOM, Trend Pullback, Range Breakout, Mean Reversion, Funding/Basis Carry, and SMC/ICT Setups) on identical chronological splits, 3-tier costs, and regime decompositions. | Implement `core/research/concept_evaluation.py` with causal point-in-time signal generators for Candidates A–F, chronological Train/Val/Sealed-OOS split, 3-tier cost sensitivity (`optimistic`, `realistic`, `punitive`), $N_{\text{eff}}$ overlap adjustment, DSR, and regime attribution. |
| **Complementary Portfolio & Regime Orchestration (SKY Arbiter)** | `core/mastermind/mastermind_arbiter.py` aggregates 5 specialists (`Regime`, `Structure`, `Derivatives`, `Microstructure`, `StatisticalBaseline`) for a single trade signal, and `core/portfolio_risk_engine.py` checks pairwise correlation $>0.70$. | No concept-level regime suitability matrix, return-stream correlation clustering across the 60 concepts, or marginal diversification scoring to prevent combining 5 correlated trend followers. | Implement `RegimeOrchestrationAdvisor` in `core/research/concept_evaluation.py` to compute cross-concept return & drawdown correlations, regime suitability weights, and concentration caps before passing candidates to the SKY Risk Gate. |

---

## 2. Detailed Gap Analysis by Subsystem

### Gap 1: Fragmented Concept Representations
Currently, trading concepts exist in three disconnected formats:
1. Procedural `if/elif` blocks in [`engine/rules.py`](file:///c:/Users/azims/CBT/engine/rules.py#L120-L405).
2. Hardcoded setup methods (`_eval_setup_a` through `_eval_setup_e`) in [`core/sky_intelligence/setup_engine.py`](file:///c:/Users/azims/CBT/core/sky_intelligence/setup_engine.py#L81-L375).
3. Loose text strings extracted from markdown claims in [`core/autonomous_research/hypothesis_generator.py`](file:///c:/Users/azims/CBT/core/autonomous_research/hypothesis_generator.py).

**Impact:** The system cannot answer basic institutional governance queries such as:
- *"Which concepts in our registry share the same underlying feature dependencies (e.g., Bollinger Band width + ATR percentile)?"*
- *"What is the exact failure mode and historical experiment trail of `Breakout Buy` vs `Volatility-Compression Breakout`?"*
- *"Which concepts are approved for `TRENDING_UP` vs `RANGE_BOUND` vs `DELEVERAGING_PANIC`?"*

### Gap 2: Effective Sample Size ($N_{\text{eff}}$) vs. Nominal Signal Count ($N$)
In [`data/backtester.py`](file:///c:/Users/azims/CBT/data/backtester.py#L196-L240), `run_backtest()` iterates with `for idx in range(warmup, n - horizon, step):`. When `step=3` (45 minutes) and `horizon=96` (24 hours), a single persistent trend or range triggers identical `Buy Pullback` or `Sell Pullback` plans on consecutive steps whose 96-bar evaluation windows overlap by $96.8\%$.
- **Gap:** Standard $t$-statistics and Sharpe ratios assume independent observations, or at minimum non-overlapping return intervals.
- **Solution:** `core/research/concept_evaluation.py` must enforce non-overlapping trade execution per strategy instance (one active position per concept/symbol at a time, or explicit uniqueness weighting $N_{\text{eff}} = N / \bar{k}_{\text{overlap}}$ following López de Prado's average uniqueness method) and report both nominal $N$ and overlap-adjusted $N_{\text{eff}}$.

### Gap 3: Unification of Cost Sensitivity Across Strategy Families
While [`data/costs.py`](file:///c:/Users/azims/CBT/data/costs.py#L46-L95) implements a clean 3-tier cost model (`optimistic`, `realistic`, `punitive`) for `Plan` objects, [`core/autonomous_research/empirical_tester.py`](file:///c:/Users/azims/CBT/core/autonomous_research/empirical_tester.py#L228-L248) uses a flat `cost_bps` deduction (`3.0 / 8.0 / 18.0 bps`) without accounting for holding-period funding drag or ATR volatility slippage scaling.
- **Solution:** Standardize the 3-tier friction model in `core/research/concept_evaluation.py` so every candidate family (trend, pullback, breakout, mean reversion, funding/basis carry, and SMC/ICT) is graded under:
  1. **Base / Realistic Tier:** Maker/taker fee + half-spread + volatility-scaled slippage + holding-period funding rate.
  2. **Conservative Tier ($1.5\times$ friction):** $1.5\times$ slippage/spread + adverse funding skew.
  3. **Stress / Punitive Tier ($2.5\times$ friction):** $2.5\times$ slippage/spread + liquidity vacuum spread widening.

### Gap 4: Strict Architectural & Milestone 18 Boundary Compliance
Per [`core/execution/m18_certification_manifest.json`](file:///c:/Users/azims/CBT/core/execution/m18_certification_manifest.json) and [`core/governance/architecture_registry.py`](file:///c:/Users/azims/CBT/core/governance/architecture_registry.py), `app.py` and `core/database.py` are frozen Milestone 18 certified files, and `core.research` belongs to `LAYER_2_QUANT_SIMULATION` (`ExecutionAuthority.SIMULATION_RESEARCH_ONLY`).
- **Solution:**
  - Place the new concept registry and evaluation engine inside `core/research/` (`core/research/concept_registry.py` and `core/research/concept_evaluation.py`), importing only `core.database` (`LAYER_0_FOUNDATION`) and standard scientific libraries (`numpy`, `pandas`, `scipy`).
  - Expose REST API routes via [`core/strategist_routes.py`](file:///c:/Users/azims/CBT/core/strategist_routes.py) (`LAYER_3_API_FACADE`), which is already mounted in `app.py` under `/api/strategist` and is **not** an M18 certified file.
  - Initialize the SQLite tables (`trading_concepts`, `concept_experiments`, `concept_lifecycle_transitions`) self-contained inside `ConceptRegistry._ensure_tables()` using `db_manager.get_brain_conn()`, requiring **zero edits** to `core/database.py` or `app.py`.

