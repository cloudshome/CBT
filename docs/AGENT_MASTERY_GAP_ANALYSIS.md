# SKY / CBT — AGENT MASTERY GAP ANALYSIS & MISSION ZERO AUDIT

**Program ID:** SKY-AMP-001 (Agent Mastery Program)  
**Lead Authority:** Principal Quantitative Systems Architect & Project Manager  
**Date:** October 21, 2026  
**Evaluation Status:** MISSION ZERO COMPLETED — BASELINE RECONCILED AGAINST CODE  
**Permanent Firewall:** `REAL_CAPITAL_ENABLED = False`  

---

## 1. Executive Summary & Qualification Verdict

The proposed **SKY Agent Mastery Program** has been formally reviewed, audited, and **ACCEPTED** into the project.

It introduces no architectural drift, preserves all Milestone 18 execution invariants, enforces Guard 1 Risk Gate primacy, and provides a formal engineering framework to transform subjective LLM agents into adversarial, evidence-grounded quantitative specialists.

This document fulfills **Mission Zero**: establishing the definitive, repository-backed inventory of every agent, prompt, scheduler, authority boundary, and test across the codebase, identifying the exact gaps to be upgraded in subsequent phases.

---

## 2. Complete Agent Inventory: Verified Code vs. Catalog

Across the repository, exactly **20 distinct agent and specialist implementations** were discovered across 5 functional tiers.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       RECONCILED AGENT INVENTORY (N=20)                     │
├────┬─────────────────────────────┬────────────────────────────────┬─────────┤
│ Tier│ Canonical Agent Name         │ Source File                    │ Status  │
├────┼─────────────────────────────┼────────────────────────────────┼─────────┤
│ T1 │ OpportunityHunter           │ core/opportunity_hunter.py     │ ACTIVE  │
│ T1 │ CausalHypothesisSynthesizer │ core/causal_synthesizer.py     │ ACTIVE  │
│ T1 │ AgentConceptArena           │ core/research/agent_concept... │ ACTIVE  │
│ T1 │ WebSearchAgent              │ core/knowledge_os/web_search...│ ACTIVE  │
│ T2 │ BtcMacroSpecialist          │ core/mastermind/specialists.py │ ACTIVE  │
│ T2 │ EthSpecialist               │ core/mastermind/specialists.py │ ACTIVE  │
│ T2 │ SolSpecialist               │ core/mastermind/specialists.py │ ACTIVE  │
│ T2 │ MemeMomentumSpecialist      │ core/mastermind/specialists.py │ ACTIVE  │
│ T2 │ LowCapBreakoutSpecialist    │ core/mastermind/specialists.py │ ACTIVE  │
│ T2 │ DynamicOpportunitySpecialist│ core/mastermind/specialists.py │ ACTIVE  │
│ T3 │ MastermindArbiterCouncil    │ core/mastermind_arbiter.py     │ ACTIVE  │
│ T3 │ MasterRiskGate / RiskManager│ core/risk_manager.py           │ ACTIVE  │
│ T4 │ MicrostructureMarkoutEngine │ forward_validation/markout...  │ ACTIVE  │
│ T4 │ MultiDimensionalDriftDet    │ forward_validation/drift...    │ ACTIVE  │
│ T4 │ SuspensionController        │ forward_validation/suspension..│ ACTIVE  │
│ T5 │ MorningBriefAgent           │ brain/agents.py                │ DAEMON  │
│ T5 │ WatchdogAgent               │ brain/agents.py                │ DAEMON  │
│ T5 │ PaperReviewerAgent          │ brain/agents.py                │ DAEMON  │
│ T5 │ WeeklyReviewAgent           │ brain/agents.py                │ DAEMON  │
│ T5 │ TelegramAgentPlanner        │ core/telegram/agent_planner.py │ ACTIVE  │
└────┴─────────────────────────────┴────────────────────────────────┴─────────┘
```

---

## 3. Systematic Gap Analysis by Agent Tier

### Tier 1: Research, Narrative & Opportunity Discovery

#### 1. `OpportunityHunter` ([`core/opportunity_hunter.py`](file:///c:/Users/azims/CBT/core/opportunity_hunter.py))
* **Current Reality:** Scans 4,000+ Binance spot/futures pairs. Correctly classifies Pre-Spike Compression and Blow-Off Exhaustion with deterministic invalidations.
* **Gaps Identified:**
  - Lacks dynamic liquidity-adjusted slippage penalties for low-cap futures candidates.
  - Does not yet track historical candidate decay rates (how many pre-breakouts fail within 60 minutes).
* **Mastery Upgrade Requirement:** Integrate post-selection attrition tracking to score candidate net tradability after 2.5x stress costs.

#### 2. `CausalHypothesisSynthesizer` ([`core/intelligence/causal_synthesizer.py`](file:///c:/Users/azims/CBT/core/intelligence/causal_synthesizer.py))
* **Current Reality:** Point-in-time timestamp contracts and sandbox database isolation are green (15/15 tests passing).
* **Gaps Identified:**
  - Relies heavily on static macro regex matching.
  - Lacks automated negative-control falsification tests (generating randomized pseudo-events to ensure the synthesizer does not produce hypotheses on pure white noise).
* **Mastery Upgrade Requirement:** Add automated white-noise placebo validation and epistemic claim tags (`[FACT]`, `[HYPOTHESIS]`, `[INFERENCE]`).

#### 3. `AgentConceptArena` ([`core/research/agent_concept_arena.py`](file:///c:/Users/azims/CBT/core/research/agent_concept_arena.py))
* **Current Reality:** Evolutionary concept tournament ledger tracks Deflated Sharpe Ratio (DSR) and out-of-sample splits.
* **Gaps Identified:**
  - Tournament winners are judged relative to competitors rather than against a strict non-tradability hurdle.
* **Mastery Upgrade Requirement:** Enforce cost-adjusted hurdle rates (minimum +0.50R net expectancy under 2.5x friction) before any concept can achieve promotion.

#### 4. `WebSearchAgent` ([`core/knowledge_os/web_search_agent.py`](file:///c:/Users/azims/CBT/core/knowledge_os/web_search_agent.py))
* **Current Reality:** Ingests external articles and SEC/CFTC filings into `data/research/vault/`.
* **Gaps Identified:**
  - Lacks strict prompt-injection sandboxing on untrusted external markdown/HTML content.
* **Mastery Upgrade Requirement:** Add explicit prompt-injection sanitization to prevent retrieved web text from manipulating downstream agent instructions.

---

### Tier 2: Mastermind Swarm Specialists

#### Specialists 5–10 (`BtcMacro`, `Eth`, `Sol`, `MemeMomentum`, `LowCapBreakout`, `DynamicOpportunity`)
* **Current Reality:** All subclass `BaseSpecialistAgent` and emit structured `CandidateProposal` records.
* **Gaps Identified:**
  - **Shared Data Illusion:** Multiple specialists often inspect the same underlying BTC or ETH candle feeds, creating an illusion of independent confirmation when errors are actually 100% correlated.
  - **Absence of Disconfirming Search:** Specialists evaluate whether conditions favor their thesis, but do not actively search for contradictory market evidence (e.g. rising spot CVD while futures open interest crashes).
  - **Confidence Calibration:** Confidence scores are rule-of-thumb heuristics (e.g. 0.75, 0.85) rather than calibrated empirical probabilities.
* **Mastery Upgrade Requirement:**
  1. Add mandatory **Adversarial Self-Review** method to `BaseSpecialistAgent` (`find_falsifying_evidence()`).
  2. Implement an **Information Overlap Penalty** in the Arbiter Council to penalize correlated signals.

---

### Tier 3: Arbiter Council & Independent Risk Governor

#### 11. `MastermindArbiterCouncil` ([`core/mastermind/mastermind_arbiter.py`](file:///c:/Users/azims/CBT/core/mastermind/mastermind_arbiter.py))
* **Current Reality:** Enforces Guard 1 Primacy (absolute Risk Gate veto) and 1.5% maximum parent equity risk cap (6/6 tests passing).
* **Gaps Identified:**
  - Consensus weighting treats specialist confidence at face value without discounting for historical false-positive rates.
* **Mastery Upgrade Requirement:** Implement dynamic specialist track-record weighting (Brier score calibration) where poorly calibrated specialists have their vote weight systematically downscaled.

#### 12. `MasterRiskGate` / `RiskManager` ([`core/risk_manager.py`](file:///c:/Users/azims/CBT/core/risk_manager.py))
* **Current Reality:** Deterministic circuit breakers (3.0% daily drawdown, 1.5% per-trade risk cap, kill switch).
* **Gaps Identified:**
  - Operates on static equity values if exchange margin balances fail to refresh.
* **Mastery Upgrade Requirement:** Enforce fail-closed lockout if equity timestamps are stale ($>30\text{s}$) or missing.

---

### Tier 4: Microstructure & Forward Validation Sentinels

#### 13–15. `MicrostructureMarkoutEngine`, `MultiDimensionalDriftDetector`, `SuspensionController`
* **Current Reality:** 3-tier markouts ($100\text{ms}$–$30\text{s}$), 5-axis drift detection, and SQLite failure ledger verified across 94 tests.
* **Gaps Identified:**
  - Drift alerts are currently stored in SQLite and displayed on Cockpit UI, but do not yet automatically trigger an urgent Telegram broadcast to the desk operator.
* **Mastery Upgrade Requirement:** Wire automated high-priority Telegram alerts to `TelegramBot` upon any KS-test return divergence ($p < 0.01$) or toxic markout slope.

---

### Tier 5: Desk Autonomous Runners & Watchdogs

#### 16–20. `MorningBriefAgent`, `WatchdogAgent`, `PaperReviewerAgent`, `WeeklyReviewAgent`, `TelegramAgentPlanner`
* **Current Reality:** Supervised by `sky_agent.daemon` / `ops/systemd/sky-agent.service` running 24/7.
* **Gaps Identified:**
  - The `PaperReviewerAgent` logs post-trade reviews, but does not automatically route systematic execution slip insights back into the `RealisticPaperFillSimulator`.
* **Mastery Upgrade Requirement:** Create a closed feedback loop where realized paper slip feeds back into the simulator's depth-walking friction model.

---

## 4. Prioritized Phased Implementation Plan

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SKY AGENT MASTERY IMPLEMENTATION PHASES                 │
├─────────┬──────────────────────────────────┬────────────────────────────────┤
│ Phase   │ Focus Area                       │ Exit Criteria                  │
├─────────┼──────────────────────────────────┼────────────────────────────────┤
│ Phase 1 │ Shared Contracts & Charters      │ BaseSpecialist Adversarial     │
│         │                                  │ Self-Review & Epistemic Tags   │
├─────────┼──────────────────────────────────┼────────────────────────────────┤
│ Phase 2 │ Arbiter Correlation Penalty      │ Information Overlap Discount   │
│         │ & Dynamic Specialist Weighting   │ & Brier Score Calibration      │
├─────────┼──────────────────────────────────┼────────────────────────────────┤
│ Phase 3 │ Opportunity Hunter Tradability   │ 2.5x Stress Friction Gate &    │
│         │ & Attrition Tracking             │ Historical Decay Funnel        │
├─────────┼──────────────────────────────────┼────────────────────────────────┤
│ Phase 4 │ Drift-to-Telegram Dispatch       │ Real-time Alerts on Markout /  │
│         │ & Closed-Loop Paper Feedback     │ Return Divergence ($p < 0.01$) │
├─────────┼──────────────────────────────────┼────────────────────────────────┤
│ Phase 5 │ Adversarial Qualification Battery│ Red-Team Test Suites A, B, C, D│
│         │ (Individual Agent Challenge)     │ 100% Green across all 20 Agents│
└─────────┴──────────────────────────────────┴────────────────────────────────┘
```

---

## 5. Project Manager Verdict

The SKY Agent Mastery Program is **formally approved**.

It transforms CBT from a collection of promising concepts into an institutional, self-critical, and mathematically audited autonomous quantitative trading intelligence desk.

Mission Zero is complete. Phase 1 implementation begins immediately.

