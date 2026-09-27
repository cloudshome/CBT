# SKY — SYSTEM CONSTITUTION & GOVERNANCE FOUNDATION

> **Document Identity:** `SKY-CONST-001`  
> **Status:** APPROVED & LOCKED 🔒  
> **Authority:** Supreme System Constitution for all AI Agents & Human Contributors.  
> **Ecosystem:** SKY / Crypto Brain Terminal (CBT)  

---

## ARTICLE I — PRIME CONSTITUTIONAL DIRECTIVES

### 1.1 The Golden Mission
SKY is a professional cryptocurrency market-intelligence, trading decision-support, and quantitative research engine. Its purpose is to discover, validate, and measure genuine statistical expectancy before live capital is ever committed. SKY is not a flashy dashboard or an undisciplined trading bot; it is an evidence-driven quantitative intelligence system.

### 1.2 The Epistemic Invariance (CODE ≠ RESEARCH ≠ LIVE)
1. **Unit test success proves software correctness; it NEVER proves trading alpha.**
2. **Mathematical plausibility is a hypothesis; it NEVER constitutes empirical evidence.**
3. **In-sample backtest profitability is a preliminary trial; it NEVER proves out-of-sample expectancy.**
4. **Research simulation results NEVER guarantee live execution performance.**
5. Every claim of edge must advance through the full Research Maturity Ladder with immutable evidence.

### 1.3 Strict Causal Firewall & Event-Specific Information Cutoff
1. **Zero Lookahead Bias:** Any historical decision must use ONLY information that was verifiably available at the event cutoff time.
2. **Event Cutoff Conventions:** Earliest allowed execution is the first timestamp at which the required information was actually published under the declared execution model:
   - *Bar-Close Strategy:* Information available at close of candle $t$; earliest execution at $t+1$ open. Unfinished higher-timeframe candles are strictly forbidden.
   - *Order-Book / Tick Strategy:* Information available at microsecond tick $t$; earliest execution at $t + \Delta t_{\text{latency}}$.
   - *Funding / Liquidation Event:* Information available at exchange publication timestamp $t$; earliest execution at $t + \Delta t_{\text{network}}$.
3. **Confirmation Time vs. Event Time:** Structural milestones (BOS, CHoCH, FVG, Order Blocks, Liquidity Sweeps) must record both `event_timestamp` (origin) and `confirmation_timestamp` (causal qualification).

### 1.4 The Research Lab Epistemic Firewall
1. **The Research Lab may discover hypotheses; it may NEVER manufacture empirical evidence.**
2. **A source may propose a mechanism. Only the quantitative research engine may establish whether that mechanism has predictive or trading value.**
3. **Zero-Fabrication Performance Firewall:** Qualitative author assertions ("works really well", "100% win rate", "never fails", "holy grail") must NEVER be converted into quantitative assumptions ($W = 80\%$, $PF = 2.5$). All statistical parameters originate strictly from out-of-sample backtest trials.
4. **Temporal Grounding:** Every claim extracted from multimedia sources (YouTube, podcasts, video lessons) must preserve exact temporal anchors (`timestamp_start`, `timestamp_end`) back to the source media.

### 1.5 The Academic & Book Epistemic Firewall
1. **Statistic Isolation:** Author-reported performance statistics (e.g. "70% win rate", "3.0 Sharpe ratio", "10 to 1 payoff") must be stored strictly as `AUTHOR_REPORTED_STATISTIC` with system confidence $0.0$. They must NEVER be accepted as SKY ground truth without deterministic out-of-sample backtest replication.
2. **Hierarchical Spatial Provenance:** Every claim extracted from bound literature (PDF books, whitepapers, monographs) must preserve exact spatial provenance: $\{ \text{isbn}, \text{title}, \text{edition}, \text{chapter}, \text{section}, \text{page\_number}, \text{paragraph\_index} \}$. Unanchored claims are rejected by the research gate.
3. **Epistemic Typology Discrimination:** Literature extracts must be partitioned into strict epistemic types:
   - `DEFINITION` (formal mathematical/conceptual construct)
   - `AUTHOR_REPORTED_STATISTIC` (unverified claim of empirical edge)
   - `PROPOSED_RULE` (prescriptive entry, exit, or sizing directive)
   - `HISTORICAL_OBSERVATION` (descriptive account of historical market events)
   - `REPORTED_RESEARCH` (citations to academic studies)
   - `UNVERIFIED_CLAIM` (qualitative author opinion or hypothesis)
   - `SKY_EMPIRICAL_RESULT` (statistically verified SKY quantitative backtest)
4. **Separation of Source Domain vs. Applicability Domain:** Material derived from non-crypto markets (traditional equities, FX, commodities, macroeconomics) must be tagged with its source domain while evaluated against its crypto applicability domain (`CRYPTO_DIRECT`, `MARKET_GENERAL`, `MACRO`, `RISK`, `PSYCHOLOGY`, etc.).
5. **Raw Immutable Evidence vs. Vault Separation:** Raw book extracts remain immutable evidence artifacts; only concepts and candidates that survive deterministic quantitative backtesting may be promoted into the permanent Knowledge Vault.

---

## ARTICLE II — DATA PROVENANCE & EXPERIMENT IMMUTABILITY

### 2.1 Dataset Versioning & Checksum Integrity
Every dataset used for backtesting, calibration, or machine learning must have an immutable provenance descriptor:
$$\text{Dataset Provenance} = \langle \text{dataset\_id}, \text{version}, \text{source}, \text{retrieval\_timestamp}, \text{coverage}, \text{sha256\_checksum}, \text{schema\_version} \rangle$$
1. **Data Isolation:** Never silently mix spot, perpetual futures, dated futures, index prices, mark prices, funding data, or liquidation prints.
2. **Synthetic Tagging:** All synthetic, interpolated, or backfilled candles must be explicitly tagged (`is_synthetic = 1`) and isolated from empirical calibration datasets.

### 2.2 Experiment Immutability (Append-Only Evidence)
1. Once an experiment, benchmark, or strategy baseline is assigned an identity (`EXP-XXX`), it is **strictly immutable**.
2. **Never overwrite historical results.** Any modification to parameters, fee models, slippage assumptions, or data splits MUST create a new experiment version with explicit differential reasoning.
3. Negative research results and failed hypotheses are first-class assets and must be preserved to prevent survivorship and data-snooping bias.

---

## ARTICLE III — DETERMINISTIC RISK & EXECUTION SAFETY

### 3.1 Risk Engine Primacy & Hierarchy
1. No trading strategy, signal, optimizer, or AI model may bypass or override the deterministic Risk Engine.
2. **System Hierarchy:**
   $$\text{Safety} > \text{Security} > \text{Data Integrity} > \text{Risk Controls} > \text{Statistical Validity} > \text{Signal Quality} > \text{UX Polish}$$
3. Risk limits (Half-Kelly sizing boundaries, maximum portfolio heat, symbol concentration limits, 5% daily loss limits, and 20% max drawdown kill switches) are 100% deterministic Python code.

### 3.2 Live Execution Credential Isolation
1. **Research code must NEVER have direct live order authority.**
2. Live exchange API keys and secrets must NEVER be present in research environments, backtesters, unit test suites, fixtures, logs, git commits, or AI prompts.
3. Transition from Paper/Shadow trading to Live execution requires explicit human authorization, sealed evidence reports, and isolated production key managers.

---

## ARTICLE IV — SPEC KIT ENGINEERING & DEVELOPMENT GOVERNANCE

### 4.1 Development Workflow Hierarchy
All codebase modifications must be governed through GitHub Spec Kit:
```
CONSTITUTION (.specify/memory/constitution.md)
       ↓
SPECIFY (spec.md)
       ↓
CLARIFY (Ambiguities resolved)
       ↓
PLAN (plan.md)
       ↓
TASKS (tasks.md)
       ↓
ANALYZE / CHECKLIST (Quality gates)
       ↓
IMPLEMENT (Code + Unit/Integration Tests)
       ↓
CONVERGE (Verify implementation against spec)
```

### 4.2 Spec Kit Artifact Lifecycle
1. Do not casually delete or overwrite Spec Kit artifacts.
2. When requirements change, update the source specification (`spec.md`) first, regenerate or reconcile downstream plans (`plan.md`) and tasks (`tasks.md`), rerun analysis, and then implement.
