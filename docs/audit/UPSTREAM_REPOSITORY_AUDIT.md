# UPSTREAM REPOSITORY INTELLIGENCE AUDIT
**Project:** SKY / Crypto Brain Terminal (CBT)  
**Governance Level:** Senior Quantitative Systems Architect & Technical Guardian  
**Classification:** Class D/F Research Intelligence & Governance Audit  
**Status:** ARCHITECTURAL SPECIFICATION & EVALUATION AUDIT  
**Binding Invariants:** M18 Execution Kernel Frozen (`c9cc1cad`), `REAL_CAPITAL_ENABLED = False` Permanently Locked  

---

## 1. Executive Summary & Audit Mandate

The objective of this audit is to conduct an institutional-grade, forensic evaluation of eleven (11) open-source repositories to determine their architectural applicability, component reusability, failure modes, and security risks for the **SKY / Crypto Brain Terminal (CBT)** intelligence layer.

SKY is not a generic algorithmic trading script or a retail dashboard. It is a strictly governed, quantitative intelligence operating system combining:
1. **Deterministic Execution & Invariant Risk Desk (Milestone 18):** Frozen under cryptographic manifest (`m18_certification_manifest.json`), zero-bypass Half-Kelly position sizing, and permanent simulation/paper-only locks.
2. **Knowledge OS & Research Wikipedia:** An evidence-backed, immutable epistemological ledger where market assertions, historical regimes, and structural market anomalies are verified, cited, and cross-examined.
3. **Autonomous Research Agents:** Bounded, unprivileged web discovery engines that harvest market research while defending against Server-Side Request Forgery (SSRF), indirect prompt injection, and data poisoning.

### The Five Architectural Dispositions
Every audited repository is assigned one of five strict architectural dispositions:
- **`ADOPT PATTERN`**: The conceptual model, workflow state machine, or data schema is adopted into SKY's native Python/TypeScript codebase without importing external code or binary dependencies.
- **`ADAPT ISOLATED COMPONENT`**: A tightly scoped, non-execution module (e.g., DSL parser, mathematical formulation) is adapted, refactored into SKY's existing clean architecture, and subjected to unit testing and causal firewall verification.
- **`BENCHMARK ONLY`**: Used solely as a UX, performance, or capability baseline to compare institutional workflows; zero code or pattern dependency.
- **`DEFER`**: Technically sound but secondary to core quant intelligence; placed on backlog for future post-production milestones.
- **`REJECT`**: Incompatible with SKY's System Constitution, violates risk gates, introduces severe security vulnerabilities, or carries viral copyleft licensing (e.g., AGPL-3.0) that threatens codebase integrity.

---

## 2. Forensic Repository Evaluations

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               11 REPOSITORIES AUDITED                                  │
├─────────────────────────┬───────────────────────────┬──────────────────────────────────┤
│ 1. stock-market-signal  │ 5. LibreChat              │ 9. agentic-inbox                 │
│ 2. AutoHedge            │ 6. Open-Generative-AI     │ 10. camofox-browser              │
│ 3. Vibe-Trading         │ 7. Open-LLM-VTuber        │ 11. hyperframes                  │
│ 4. FinceptTerminal      │ 8. claude-ads             │                                  │
└─────────────────────────┴───────────────────────────┴──────────────────────────────────┘
```

---

### Repo 1: `stock-market-signal-automation`
- **Primary Function:** Automated scraping of financial portals/screeners and webhook-driven signal dispatching to messaging channels (Telegram, Discord, Slack).
- **Verified Capabilities:**
  - Automated scheduling of headless browser or REST requests against equity/crypto screeners.
  - Basic rule matching (RSI crosses, Moving Average golden crosses) triggering webhook dispatches.
- **Critical Flaws & Red Lines:**
  - *Zero Causal Firewall:* Indicators are computed on incomplete or repainting candle streams, creating severe lookahead bias.
  - *Trivial Signal Generation:* Overfitted indicator heuristics with zero walk-forward combinatorial cross-validation (CPCV) or Deflated Sharpe Ratio (DSR).
  - *Coupled Execution Risks:* Tightly couples signal generation with trigger execution without an independent risk desk or cost friction model.
- **Value for SKY:**
  - Notification payload formatting and multi-channel dispatch schema for informational alerts.
- **Non-Adoption Boundary:**
  - **Zero trading logic or indicator calculations may enter SKY.** Signals must never trigger execution directly; in SKY, any market signal can only be a `[HYPOTHESIS]` entering the `ThesisEngine` and `BacktestQueue`.
- **Verdict:** **`BENCHMARK ONLY / ADAPT NOTIFICATION SCHEMA`**

---

### Repo 2: `AutoHedge`
- **Primary Function:** Autonomous hedging agent designed to manage DeFi liquidity positions, perpetual futures hedges, and automated rebalancing.
- **Verified Capabilities:**
  - Mathematical modeling of impermanent loss (IL) curves for Automated Market Maker (AMM) LP tokens.
  - Real-time delta calculation against synthetic and perpetual order books.
- **Critical Flaws & Red Lines:**
  - *Automated Execution & Private Key Management:* Interacts directly with Web3 wallets and exchange API credentials with autonomous order authority.
  - *Constitutional Violation:* Violates SKY Constitution Level 1 and M18 execution freeze. Autonomous order placement without deterministic Half-Kelly risk gates and human clearance is strictly forbidden.
  - *Fragile Slippage Assumptions:* Assumes constant liquidity depth during violent volatility spills, leading to liquidation cascades.
- **Value for SKY:**
  - Pure mathematical formulas for AMM LP impermanent loss and delta hedging equations.
- **Non-Adoption Boundary:**
  - **TOTAL REJECTION OF WALLET INTEGRATION, SMART CONTRACT ROUTING, AND AUTOMATED EXECUTION PATHWAYS.**
- **Verdict:** **`ADAPT ISOLATED COMPONENT (AMM Math Only) / REJECT EXECUTION`**

---

### Repo 3: `Vibe-Trading`
- **Primary Function:** AI-assisted quantitative research framework where natural language prompts are transformed into algorithmic alpha hypotheses, backtested, and optimized.
- **Verified Capabilities:**
  - LLM prompt orchestration for financial factor generation.
  - Parameter extraction from qualitative trading thesis into machine-executable parameters.
  - Fast feedback loop between market observation and strategy backtest harness.
- **Critical Flaws & Red Lines:**
  - *P-Hacking & Multiple Testing Hazards:* Unbounded LLM strategy generation exponentially inflates backtest overfitting. Without Harvey-Liu Deflated Sharpe Ratio (DSR) or White's Reality Check (WRC), 99% of discovered "alphas" are statistical noise.
  - *Lookahead Leakage:* Often feeds full dataframes to LLMs or evaluation loops without strict chronological masking ($t \le t_{event}$).
- **Value for SKY:**
  - Structured Alpha Hypothesis Specification DSL: Converting narrative trader notes into formal `ThesisEngine` inputs (`market`, `timeframe`, `entry_rule`, `invalidation_rule`, `target_metric`).
- **Non-Adoption Boundary:**
  - Strategy generation must remain strictly bounded by SKY's `docs/QUANT_RESEARCH_PROTOCOL.md` 11-stage maturity ladder. No strategy may be tagged as tradeable without CPCV and out-of-sample testing.
- **Verdict:** **`ADAPT ISOLATED COMPONENT (Alpha Formulation DSL)`**

---

### Repo 4: `FinceptTerminal`
- **Primary Function:** Comprehensive open-source institutional workstation (alternative to Bloomberg/Refinitiv) covering equities, crypto, macroeconomics, SEC filings, prediction markets, and AI co-pilots.
- **Verified Capabilities:**
  - Modular workspace UI: Dockable panels, synchronized symbol tickers, multi-asset data feeds.
  - Broad data integration across diverse financial APIs (FRED, SEC EDGAR, Polymarket, Yahoo Finance, Binance).
  - Workflow separation between macro news, technical charting, and qualitative dossier generation.
- **Critical Flaws & Red Lines:**
  - *Monolithic & Architectural Sprawl:* Massive dependency tree, heavy client footprint, and high maintenance overhead.
  - *Licensing Hazard:* Any viral copyleft code (such as AGPL-3.0) must be aggressively quarantined to avoid contaminating SKY's codebase.
  - *Shallow Quantitative Depth:* Breadth-over-depth terminal; lacks deep L2 microstructure, VPIN toxicity, or institutional fill reconciliation.
- **Value for SKY:**
  - Institutional layout reference: Symbol command line, dockable panel paradigms, and multi-asset overview layout for SKY Trading Terminal and Research Lab.
- **Non-Adoption Boundary:**
  - **No external codebase copying.** Do not adopt monolithic backend frameworks. Emulate panel layout and data aggregation concepts natively in React/Tailwind.
- **Verdict:** **`BENCHMARK ONLY / ADOPT UI WORKSPACE PATTERN`**

---

### Repo 5: `LibreChat`
- **Primary Function:** Institutional-grade, multi-provider conversational AI platform supporting OpenAI, Anthropic, Gemini, local models, artifact rendering, plugins, and persistent tool calling.
- **Verified Capabilities:**
  - Clean separation between LLM provider adapters, conversation state, and plugin/tool execution.
  - Multi-user authentication, token budgeting, and role-based access control.
  - Interactive artifacts and code canvas rendering.
- **Critical Flaws & Red Lines:**
  - *Chat-Centric Knowledge Fallacy:* Epistemic knowledge stored in chat threads decays rapidly, cannot be audited, and lacks relational foreign keys.
  - *Unstructured Tool Execution:* Dynamic tool invocation without deterministic sandboxing creates potential privilege escalation.
- **Value for SKY:**
  - Architectural pattern for multi-model AI routing, fallback chains, streaming response hooks, and generative markdown artifacts.
- **Non-Adoption Boundary:**
  - Chat history must **never** be the system of record for quantitative knowledge. SKY's `research_wiki.db` (SQLite relational schema) remains the sole authoritative knowledge store.
- **Verdict:** **`ADOPT PATTERN (AI Router & Tool Schema) / PRESERVE RELATIONAL LEDGER`**

---

### Repo 6: `Open-Generative-AI`
- **Primary Function:** Visual node-based workflow builder and multi-agent orchestrator for generative AI pipelines.
- **Verified Capabilities:**
  - Directed Acyclic Graph (DAG) orchestration of sequential and parallel LLM tasks.
  - Input/output contract validation between intermediate reasoning steps.
- **Critical Flaws & Red Lines:**
  - *Operational Complexity:* Visual node editors in trading terminals distract from high-velocity execution and data density.
  - *State Synchronization Fragility:* Complex node graphs often suffer from race conditions and unhandled partial failures.
- **Value for SKY:**
  - DAG-based execution pipeline for multi-step research synthesis: Source Fetch $\to$ Safe Extraction $\to$ Claim Decomposition $\to$ Thesis Formulation.
- **Non-Adoption Boundary:**
  - Maintain DAG logic in strict, deterministic Python async pipelines (`core/knowledge_os/research_automation_orchestrator.py`), avoiding runtime visual graph dependencies.
- **Verdict:** **`ADOPT PATTERN (DAG Pipeline Pipeline Orchestration)`**

---

### Repo 7: `Open-LLM-VTuber`
- **Primary Function:** Real-time conversational virtual avatar system integrating speech-to-text (STT), LLM reasoning, text-to-speech (TTS), and visual persona rendering.
- **Verified Capabilities:**
  - Low-latency streaming audio pipelines (WebSockets, edge TTS, VAD).
  - Expressive personality conditioning and conversational memory.
- **Critical Flaws & Red Lines:**
  - *Zero Quantitative Relevance:* Visual avatars, facial rigging, and VTuber animations add zero alpha, consume excessive GPU memory, and bloat trading workstations.
- **Value for SKY:**
  - Real-time streaming voice briefing synthesis: Transforming complex quantitative research dossiers or macro regime shifts into crisp 60-second audio briefs for Telegram or terminal voice notes.
- **Non-Adoption Boundary:**
  - **TOTAL REJECTION OF 3D RIGGING, AVATAR ENGINES, AND GRAPHICS BLOAT.** Audio streaming architecture may be revisited post-production.
- **Verdict:** **`DEFER (Audio Briefing Only) / REJECT 3D AVATAR ENGINE`**

---

### Repo 8: `claude-ads`
- **Primary Function:** Bounded multi-worker agent orchestration framework enforcing strict canonical JSON schemas, isolated task execution, and robust partial-failure handling.
- **Verified Capabilities:**
  - Bounded agent hierarchy: Parent orchestrator delegates to specialized sub-agents with narrow prompt scopes and non-overlapping responsibilities.
  - Canonical JSON I/O schemas with strict validation, preventing malformed responses from propagating down the pipeline.
  - Partial-failure resilience: When worker $i$ fails or times out, the orchestrator gracefully degrades and proceeds with remaining valid outputs.
- **Critical Flaws & Red Lines:**
  - Specific domain logic is tailored to marketing/advertising copy and has no native financial or market structure knowledge.
- **Value for SKY:**
  - **Highest architectural pattern value for autonomous research.** Perfect pattern for decomposing web research into isolated workers:
    1. *Search Worker* (Provider query execution)
    2. *Fetch & Sanitize Worker* (SSRF-guarded HTTP retrieval)
    3. *Claim Extractor Worker* (Atomic claim parsing)
    4. *Critic & Corroborator Worker* (Cross-referencing & epistemic validation)
- **Non-Adoption Boundary:**
  - Adopt only the orchestration, schema validation, and failure-handling design patterns; implement natively within SKY using Pydantic/dataclasses.
- **Verdict:** **`ADOPT PATTERN (Bounded Multi-Worker Research Orchestration)`**

---

### Repo 9: `agentic-inbox`
- **Primary Function:** AI-powered inbox management framework featuring automated triage, classification, and human-in-the-loop review queues.
- **Verified Capabilities:**
  - Three-tier triage state machine: `Auto-Archive` | `Draft & Await Approval` | `Urgent Action`.
  - Immutable audit trail of human confirmations, modifications, and rejections.
  - Strict sandboxing: AI proposes actions; execution is blocked until human explicitly signs off.
- **Critical Flaws & Red Lines:**
  - Mail-protocol specific (IMAP/SMTP/OAuth) abstractions unnecessary for trading terminal operations.
- **Value for SKY:**
  - **Direct model for SKY Research Wikipedia & Hypothesis Review Queue.**
    Incoming web discoveries and atomic claims cannot directly alter accepted Wikipedia articles or enter backtest queues. They land in an **Intelligence Review Inbox** where the quantitative researcher reviews, edits, or approves them.
- **Non-Adoption Boundary:**
  - Implement as a lightweight React/FastAPI review desk within `ResearchWikipediaDesk.tsx` and `ResearchIngestLab.tsx`.
- **Verdict:** **`ADOPT PATTERN (Human-in-the-Loop Triage & State Machine)`**

---

### Repo 10: `camofox-browser`
- **Primary Function:** Anti-detect headless browser framework with advanced TLS fingerprint spoofing, canvas/WebGL noise injection, and bot-detection bypass.
- **Verified Capabilities:**
  - Stealth web scraping capable of extracting data from Cloudflare-, Akamai-, and DataDome-protected financial sites (e.g. specialized macro portals, exchange documentation).
  - Emulates residential browser fingerprints to bypass scraper blocks.
- **Critical Flaws & Red Lines:**
  - *Security & Exploit Hazards:* Anti-detect browsers frequently bundle modified Chromium binaries or native C++ hooks that present security risks.
  - *Heavy Resource Overhead:* Spawning full Chromium instances consumes massive RAM/CPU, endangering terminal real-time performance.
  - *SSRF Vulnerability:* A full browser with JavaScript execution can be tricked into port scanning local networks or fetching internal metadata if not rigidly isolated.
- **Value for SKY:**
  - Fallback scraping adapter for high-value research sources where `urllib`/`trafilatura` gets HTTP 403 Forbidden.
- **Non-Adoption Boundary:**
  - Must **NEVER** run inside the core application process. If adopted, it must run as an isolated, containerized, network-restricted sidecar with strict egress filtering.
- **Verdict:** **`BENCHMARK ONLY / OPTIONAL ISOLATED SIDECAR (Post-Production)`**

---

### Repo 11: `hyperframes`
- **Primary Function:** Frame-accurate, high-performance canvas rendering and programmatic animation engine for data visualization and video generation.
- **Verified Capabilities:**
  - Deterministic frame rendering of complex multi-series time-series charts and order books.
  - Zero-jitter rendering of high-frequency data streams.
- **Critical Flaws & Red Lines:**
  - Focuses on headless video compilation rather than interactive DOM-based trading terminals.
- **Value for SKY:**
  - High-resolution visual snapshots of research hypotheses: Automated generation of standardized backtest summary cards and trade review visual dossiers.
- **Non-Adoption Boundary:**
  - SKY's interactive trading terminal already utilizes Lightweight Charts and high-performance React canvas. Do not replace live charting with video generation pipelines.
- **Verdict:** **`BENCHMARK ONLY / ADAPT DOSSIER VISUAL EXPORT PATTERN`**

---

## 3. Summary of Upstream Dispositions

| Repository | Primary Fit for SKY | Security / Risk Rating | Final Disposition |
|:---|:---|:---:|:---:|
| `stock-market-signal-automation` | Alert notification schema | Medium (Lookahead / Execution Leak) | **BENCHMARK ONLY** |
| `AutoHedge` | AMM IL math & delta equations | High (Private keys / Auto-execution) | **ADAPT MATH / REJECT EXEC** |
| `Vibe-Trading` | Alpha hypothesis DSL | High (P-hacking / Overfitting) | **ADAPT ISOLATED COMPONENT** |
| `FinceptTerminal` | Terminal workspace layout | Medium (License / Bloat) | **BENCHMARK ONLY / ADOPT UI** |
| `LibreChat` | Multi-model routing & artifacts | Low (Tool sandbox required) | **ADOPT PATTERN** |
| `Open-Generative-AI` | DAG pipeline state machines | Low (Complexity) | **ADOPT PATTERN** |
| `Open-LLM-VTuber` | Voice debrief streaming | Low (Avatar bloat) | **DEFER / AUDIO ONLY** |
| `claude-ads` | Bounded multi-worker agent architecture | Low (Strict schemas) | **ADOPT PATTERN (CRITICAL)** |
| `agentic-inbox` | Human-in-the-loop review triage | Low (Safe state machine) | **ADOPT PATTERN (CRITICAL)** |
| `camofox-browser` | Anti-detect scraper fallback | Critical (SSRF / Heavy binaries) | **BENCHMARK / ISOLATED SIDECAR** |
| `hyperframes` | Visual dossier generation | Low (Video generation) | **BENCHMARK ONLY** |

---

## 4. Architectural Boundaries & Non-Negotiables

1. **Milestone 18 Execution Freeze:**  
   Under no circumstances may any component from the 11 audited repositories touch, wrap, modify, or replace any of the 14 certified files in `core/execution/` or the risk gate invariants in `app.py`.
2. **Permanent Capital Isolation:**  
   `REAL_CAPITAL_ENABLED = False` remains immutable. External signals or research discoveries are strictly classified as read-only hypotheses.
3. **Canonical Relational Ledger:**  
   The primary source of truth for all research intelligence is `data/research_wiki.db` managed by `core/knowledge_os/universal_ingestor.py`. No secondary, competing, or parallel databases will be introduced.
4. **Epistemic Firewalls:**  
   All claims ingested from external sources must carry explicit epistemic tags: `[FACT]`, `[HYPOTHESIS]`, `[ASSUMPTION]`, `[INFERENCE]`, or `[UNVERIFIED]`.
