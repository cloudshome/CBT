# SKY / CRYPTO BRAIN TERMINAL (CBT) — AUTONOMOUS AGENT CATALOG & ARCHITECTURE SPECIFICATION

**Document Version:** 1.0.0  
**Target Audience:** Autonomous AI Coding Agents (Antigravity, Claude, GPT, Jules, Copilot) & Quantitative Architects  
**Constitutional Rule:** `REAL_CAPITAL_ENABLED = False` permanently locked across all agents.  
**System Invariant:** Risk Primacy. No forecasting model, LLM, or specialist agent has direct execution authority. All orders must pass the Independent Master Risk Gate and Milestone 18 execution invariants.

---

## 1. Architectural Taxonomy Overview

Agents in SKY / CBT operate in a strict multi-tier hierarchy separated by causal firewalls:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER 1: RESEARCH, NARRATIVE & OPPORTUNITY HUNTERS (Non-Executable)          │
│ CausalHypothesisSynthesizer, OpportunityHunter, AgentConceptArena, WebSearch│
├─────────────────────────────────────────────────────────────────────────────┤
│ TIER 2: MASTERMIND SWARM & SPECIALIST COUNCIL (Proposal Generators)         │
│ BtcMacro, Eth, Sol, MemeMomentum, LowCapBreakout, DynamicOpportunity        │
├─────────────────────────────────────────────────────────────────────────────┤
│ TIER 3: ARBITER & INDEPENDENT RISK GOVERNOR (The Veto & Sizing Gate)        │
│ MastermindArbiterCouncil (Guard 1 Primacy) & MasterRiskGate (Half-Kelly)    │
├─────────────────────────────────────────────────────────────────────────────┤
│ TIER 4: MICROSTRUCTURE & FORWARD VALIDATION SENTINELS (Auditors)            │
│ MicrostructureMarkoutEngine, MultiDimensionalDriftDetector, SuspensionCtrl  │
├─────────────────────────────────────────────────────────────────────────────┤
│ TIER 5: DESK AUTONOMOUS RUNNERS & WATCHDOGS (Lifecycle Managers)            │
│ MorningBriefAgent, WatchdogAgent, PaperReviewerAgent, WeeklyReviewAgent     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Tier-by-Tier Agent Specifications

### TIER 1: Research, Narrative & Opportunity Discovery

#### 1. `OpportunityHunter`
* **File:** [`core/opportunity_hunter.py`](file:///c:/Users/azims/CBT/core/opportunity_hunter.py)
* **Job Description:** Continuous multi-venue market screener monitoring 4,000+ spot and futures pairs across Binance and Bybit. Identifies institutional liquidity setups before and after explosive volatility.
* **Core Classification Algorithms:**
  - **Pre-Spike Expansion (Long):** Detects volatility compression ($ATR / Price \le 2.0\%$), dry volume, institutional accumulation, and rising relative volume ($RVOL \ge 2.0$) near resistance. Invalidation set strictly below local range low.
  - **Post-Spike Exhaustion (Short):** Detects parabolic blow-off extensions ($>15\%$ 24h surge), extreme volume climaxes, upper wick rejections, and fading order flow momentum. Invalidation set strictly above swing high.
* **Outputs:** Qualified watchlist records and dynamic triggers dispatched to the Mastermind Swarm.
* **How Other AIs Can Contribute:** Add new market anomaly filters (e.g. open-interest divergences, funding rate extremes) in `_classify_opportunity()`.

#### 2. `CausalHypothesisSynthesizer`
* **File:** [`core/intelligence/causal_synthesizer.py`](file:///c:/Users/azims/CBT/core/intelligence/causal_synthesizer.py)
* **Job Description:** Takes unstructured news, RSS feeds, macro reports, and on-chain event clusters and maps them into point-in-time quantitative hypothesis records.
* **Causal Firewall Invariant:** Enforces Gate 2 zero-lookahead (published timestamp must strictly precede candle open) and Gate 5 failure memory (rejects hypotheses identical to previously quarantined failures).
* **Outputs:** Structured `HypothesisRecord` dispatched to the research replay lab (`ExperimentPlanLedger`).
* **How Other AIs Can Contribute:** Expand the causal mechanisms dictionary in `research_families.py` to support new cross-market transmission channels (e.g. ETF net flows, stablecoin minting spikes).

#### 3. `AgentConceptArena`
* **File:** [`core/research/agent_concept_arena.py`](file:///c:/Users/azims/CBT/core/research/agent_concept_arena.py)
* **Job Description:** Orchestrates evolutionary tournaments between competing trading concepts (pullbacks, breakouts, order blocks, FVG retests). Ranks concepts using out-of-sample Sharpe, Deflated Sharpe Ratio (DSR), and maximum drawdown.
* **Outputs:** Concept ranking leaderboards and auto-demotion tags for underperforming strategy variants.

#### 4. `WebSearchAgent`
* **File:** [`core/knowledge_os/web_search_agent.py`](file:///c:/Users/azims/CBT/core/knowledge_os/web_search_agent.py)
* **Job Description:** Information retrieval agent extracting regulatory filings (SEC, CFTC), protocol releases, and macroeconomic data into the local knowledge vault (`data/research/vault/`).
* **Security Invariant:** Read-only ingestion. Zero access to execution keys or trading orders.

---

### TIER 2: Mastermind Swarm Specialists

All specialists inherit from [`BaseSpecialistAgent`](file:///c:/Users/azims/CBT/core/mastermind/specialist_base.py) and emit `CandidateProposal` objects containing `direction` (`LONG` / `SHORT` / `NO_TRADE`), `confidence_score` (0.0 to 1.0), `expected_value_r`, `target_price`, and `invalidation_price`.

#### 5. `BtcMacroSpecialist`
* **File:** [`core/mastermind/specialists.py`](file:///c:/Users/azims/CBT/core/mastermind/specialists.py)
* **Job:** Evaluates Bitcoin macro regime, multi-timeframe trend (EMA-14/EMA-200), liquidity clusters, and dollar liquidity indices (DXY, US yields). Sets overall market beta context.

#### 6. `EthSpecialist`
* **File:** [`core/mastermind/specialists.py`](file:///c:/Users/azims/CBT/core/mastermind/specialists.py)
* **Job:** Focuses on Ethereum spot/derivative dynamics, ETH/BTC cross ratio, DeFi TVL momentum, and gas velocity.

#### 7. `SolSpecialist`
* **File:** [`core/mastermind/specialists.py`](file:///c:/Users/azims/CBT/core/mastermind/specialists.py)
* **Job:** Monitors Solana ecosystem throughput, DEX volume share, high-beta retail momentum, and validator health.

#### 8. `MemeMomentumSpecialist`
* **File:** [`core/mastermind/specialists.py`](file:///c:/Users/azims/CBT/core/mastermind/specialists.py)
* **Job:** High-velocity momentum specialist for high-beta meme tokens (DOGE, PEPE, SHIB). Tracks social attention spikes, volume acceleration, and liquidity exhaustion wicks.

#### 9. `LowCapBreakoutSpecialist`
* **File:** [`core/mastermind/specialists.py`](file:///c:/Users/azims/CBT/core/mastermind/specialists.py)
* **Job:** Scans lower-market-cap tokens for orderbook imbalances (OBI), spread tightening, and resistance compression. Enforces strict minimum liquidity filters ($15M+ daily volume).

#### 10. `DynamicOpportunitySpecialist`
* **File:** [`core/mastermind/specialists.py`](file:///c:/Users/azims/CBT/core/mastermind/specialists.py)
* **Job:** An ephemeral specialist spawned dynamically by the `OpportunityHunter` when a high-conviction candidate emerges. It anchors to the designated coin until the trade hits take-profit, reaches invalidation, or times out.

---

### TIER 3: Arbiter Council & Independent Risk Governor

#### 11. `MastermindArbiterCouncil`
* **File:** [`core/mastermind/mastermind_arbiter.py`](file:///c:/Users/azims/CBT/core/mastermind/mastermind_arbiter.py)
* **Job:** Synthesizes the specialist proposals into weighted consensus decisions. 
* **Guard 1 Primacy Invariant:** The Arbiter Council evaluates the Master Risk Gate *before* considering any specialist recommendations. If the Risk Gate reports a circuit breaker lockout (e.g. 3.0% daily loss limit reached), 100% of candidate proposals are immediately vetoed.
* **Risk Clamping:** Enforces the 1.5% maximum portfolio equity risk cap on all approved orders.

#### 12. `MasterRiskGate` / `RiskManager`
* **File:** [`core/risk_manager.py`](file:///c:/Users/azims/CBT/core/risk_manager.py) & [`brain/risk_gate.py`](file:///c:/Users/azims/CBT/brain/risk_gate.py)
* **Job:** The deterministic gatekeeper of the platform. Evaluates daily drawdown, portfolio margin capacity, max concurrent open positions, and Half-Kelly position sizing.
* **Constitutional Power:** Absolute veto authority over all trading signals. Cannot be overridden by any prompt or specialist consensus.

---

### TIER 4: Microstructure & Forward Validation Sentinels

#### 13. `MicrostructureMarkoutEngine`
* **File:** [`core/intelligence/forward_validation/markout_engine.py`](file:///c:/Users/azims/CBT/core/intelligence/forward_validation/markout_engine.py)
* **Job:** Post-trade execution auditor. Evaluates every simulated or paper fill across 4 standard horizons ($100\text{ms}, 1000\text{ms}, 5000\text{ms}, 30000\text{ms}$) across three metrics:
  - $M_{\text{mid}}$: Midpoint drift.
  - $M_{\text{exec}}$: Executable opposite-quote movement.
  - $M_{\text{net}}$: Net markout after fees and slippage.
* **Alert Trigger:** Detects toxic flow and adverse selection if $M_{\text{net}}(30\text{s}) < 0$.

#### 14. `MultiDimensionalDriftDetector`
* **File:** [`core/intelligence/forward_validation/drift_detector.py`](file:///c:/Users/azims/CBT/core/intelligence/forward_validation/drift_detector.py)
* **Job:** Statistical auditor comparing live forward paper execution against certified historical backtest distributions across 5 axes:
  1. Return Distribution Drift (Two-sample Kolmogorov-Smirnov test).
  2. Volatility Explosion Ratio ($\sigma_{\text{paper}} / \sigma_{\text{backtest}}$).
  3. Markout Curve Decay Slope.
  4. Execution Spread & Slippage Drift.
  5. Market Regime Transition Discordance.
* **Epistemic Invariant:** Requires sample size $N \ge 30$ before issuing definitive verdicts (`INCONCLUSIVE` otherwise).

#### 15. `SuspensionController`
* **File:** [`core/intelligence/forward_validation/suspension_controller.py`](file:///c:/Users/azims/CBT/core/intelligence/forward_validation/suspension_controller.py)
* **Job:** Governs the lifecycle state machine of strategies (`ACTIVE` $\to$ `WATCH` $\to$ `QUARANTINED` $\to$ `SUSPENDED`).
* **Anti-Survivorship Guarantee:** Failed or suspended strategies are permanently recorded in SQLite with full denominator metrics.

---

### TIER 5: Desk Autonomous Agents & Watchdogs

These agents run periodically on the 24/7 daemon (managed by `brain/agents.py` and `ops/systemd/sky-agent.service`):

#### 16. `MorningBriefAgent`
* **Cadence:** Every 24 hours (UTC session open).
* **Job:** Synthesizes overnight price action, funding rates, open interest shifts, and active Risk Gate state into an executive daily briefing. Dispatches notifications to Telegram.

#### 17. `WatchdogAgent`
* **Cadence:** Every 4 hours.
* **Job:** Audits active paper trades and simulator open orders. Alerts on orphaned trades, connection drops, feed sequence gaps, or pending orders waiting for entry $>48\text{h}$.

#### 18. `PaperReviewerAgent`
* **Cadence:** Every 24 hours (post-session).
* **Job:** Audits closed paper trades, win rate %, realized R:R distribution, and adherence to trade plans. Logs post-trade lessons into SQLite.

#### 19. `WeeklyReviewAgent`
* **Cadence:** Weekly (168 hours / Sunday UTC).
* **Job:** Computes macro business metrics: overall Profit Factor, Sharpe ratio, rule compliance %, and execution slippage breakdown.

---

## 3. Contribution Guide for AI Pair-Programmers

When adding or modifying agents in this repository, any autonomous AI MUST adhere to these rules:

1. **Subclass Properly:**
   - For trading specialists: Subclass `BaseSpecialistAgent` in [`core/mastermind/specialist_base.py`](file:///c:/Users/azims/CBT/core/mastermind/specialist_base.py).
   - For periodic desk workflows: Subclass `BaseAgent` in [`brain/agents.py`](file:///c:/Users/azims/CBT/brain/agents.py).
2. **Never Grant Direct Execution:**
   - Agents emit *proposals* (`CandidateProposal` or `HypothesisRecord`), never live exchange orders.
   - All orders must route through the `MastermindArbiterCouncil` and `MasterRiskGate`.
3. **Database Sandbox Isolation:**
   - Never hardcode production SQLite paths (`data/trading_logs.db`) in tests. Use temporary fixtures (`tmp_path`) or `:memory:`.
4. **Preserve Milestone 18 Surface Area:**
   - Do not modify certified M18 connectors, the kill switch, or smart order routers without re-running `python scripts/verify_m18_certification.py` (149/149 passing tests required).
5. **Epistemic Honesty:**
   - Mark statements using the standard taxonomy: `[FACT]`, `[ASSUMPTION]`, `[HYPOTHESIS]`, or `[UNVERIFIED]`. Never fabricate backtest wins or sample sizes.
