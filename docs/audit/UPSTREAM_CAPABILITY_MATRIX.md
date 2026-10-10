# UPSTREAM CAPABILITY & GOVERNANCE MATRIX
**Project:** SKY / Crypto Brain Terminal (CBT)  
**Governance Level:** Quantitative Systems Architecture & Security Governance  
**Classification:** Class D/F Evaluation Matrix  
**Companion Document:** [`UPSTREAM_REPOSITORY_AUDIT.md`](file:///c:/Users/azims/CBT/docs/audit/UPSTREAM_REPOSITORY_AUDIT.md)  

---

## 1. Technical Evaluation Matrix

| Repository | Primary Tech Stack | License | Runtime Impact | Security Risk | Reusable Pattern / Component | Banned / Prohibited Elements | Governance Disposition |
|:---|:---|:---|:---|:---:|:---|:---|:---:|
| **`stock-market-signal-automation`** | Python, Selenium, Webhooks | MIT | Low | **Medium** (Lookahead leakage, unverified execution) | Webhook dispatch schemas, structured alert formatting | Direct trade execution, technical indicator signals without CPCV | **BENCHMARK ONLY** |
| **`AutoHedge`** | Python, Web3, DeFi SDKs | MIT | Moderate | **High** (Autonomous wallet authority, private keys) | AMM impermanent loss equations, delta hedging math | Wallet management, automated transaction signing, router bypass | **ADAPT ISOLATED COMPONENT (Math Only)** |
| **`Vibe-Trading`** | Python, LLM APIs, Backtrader/Custom | MIT / Apache-2.0 | Low | **High** (P-hacking, multiple testing hazard) | Alpha hypothesis DSL, parameter extraction from natural text | Unconstrained LLM trading decisions, in-sample overfitted alphas | **ADAPT ISOLATED COMPONENT (DSL Only)** |
| **`FinceptTerminal`** | Python/FastAPI, Node.js/React | AGPL-3.0 / MIT | Heavy | **Medium** (Licensing contamination, dependency bloat) | Dockable multi-panel layout, symbol command line | Monolithic backend, viral copyleft code, shallow data adapters | **BENCHMARK ONLY / ADOPT UI PATTERN** |
| **`LibreChat`** | Node.js, React, MongoDB/PostgreSQL | MIT | Moderate | **Low** (Dynamic tool calling risks) | Multi-model provider routing, streaming response hooks | Chat-as-database architecture, unstructured tool calling | **ADOPT PATTERN** |
| **`Open-Generative-AI`** | TypeScript, React, Python | MIT | Moderate | **Low** (State complexity) | Directed Acyclic Graph (DAG) pipeline orchestration | Visual canvas for trading execution, runtime DAG state race conditions | **ADOPT PATTERN** |
| **`Open-LLM-VTuber`** | Python, WebSockets, Edge TTS, Three.js | MIT | Heavy | **Low** (Resource consumption) | Low-latency voice synthesis, streaming debrief audio | 3D avatar rigging, facial expression modeling, GPU graphics bloat | **DEFER / AUDIO BRIEFING ONLY** |
| **`claude-ads`** | Python, Anthropic SDK, Pydantic | MIT | Minimal | **Low** (Schema-bounded) | Bounded multi-worker agent hierarchy, canonical JSON schemas | Advertising domain copy, non-financial agent prompts | **ADOPT PATTERN (CRITICAL)** |
| **`agentic-inbox`** | TypeScript / Python, SQLite | MIT | Minimal | **Low** (Strict state machine) | Three-tier triage state machine, human approval gate | Direct email protocol handling, automated execution bypass | **ADOPT PATTERN (CRITICAL)** |
| **`camofox-browser`** | Node.js, Chromium, C++ Patches | Proprietary / AGPL-3.0 | Heavy | **Critical** (SSRF, malicious scripts, memory leaks) | Residential TLS spoofing for anti-bot bypass | In-process execution, unsandboxed JavaScript execution | **BENCHMARK / ISOLATED SIDECAR ONLY** |
| **`hyperframes`** | TypeScript, Canvas, WebGL, Node.js | MIT | Moderate | **Low** (Off-screen rendering) | Frame-accurate chart rendering, dossier snapshot export | Video compilation pipeline replacing interactive Trading Terminal | **BENCHMARK ONLY** |

---

## 2. SKY Subsystem Mapping

To prevent architectural drift and maintain clean boundaries, upstream patterns are mapped strictly into SKY's existing modular tree:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                SKY MODULAR SUBSYSTEMS                                  │
├────────────────────────────┬─────────────────────────────┬─────────────────────────────┤
│ 1. RESEARCH & KNOWLEDGE    │ 2. QUANT RESEARCH & ALPHA   │ 3. UI & WORKSTATION DESK    │
│    `core/knowledge_os/`    │    `core/quant/`            │    `frontend/src/`          │
│    • claude-ads (Workers)  │    • Vibe-Trading (DSL)     │    • FinceptTerminal (Grid) │
│    • agentic-inbox (Triage)│    • AutoHedge (Math Only)  │    • LibreChat (Chat/Docs)  │
│    • camofox (Sidecar)     │    • Zero Lookahead Audit   │    • Open-LLM-VTuber (Audio)│
├────────────────────────────┴─────────────────────────────┴─────────────────────────────┤
│ 4. DETERMINISTIC RISK & EXECUTION (MILISTONE 18 FROZEN SURFACE)                        │
│    `core/execution/`, `app.py`                                                         │
│    ⛔ ZERO UPSTREAM CODE PERMITTED. ZERO EXECUTION BYPASS.                             │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Functional Mapping
1. **Research & Knowledge Engine (`core/knowledge_os/`):**
   - **`claude-ads` Pattern:** Decomposes the monolithic search process into 5 decoupled, single-responsibility workers (`QueryPlannerWorker`, `SecureFetchWorker`, `ExtractionWorker`, `ClaimExtractionWorker`, `ResearchCriticWorker`).
   - **`agentic-inbox` Pattern:** Powers the new **Research Wikipedia Triage Queue** (`IntelligenceReviewInbox`), ensuring new web claims remain in `STAGING` until validated or approved.
   - **`camofox-browser` Pattern:** Isolated containerized sidecar evaluated solely as a fallback proxy for Cloudflare-blocked financial data portals.

2. **Quantitative Alpha & Hypothesis Engine (`core/quant/`, `ThesisEngine`):**
   - **`Vibe-Trading` Pattern:** Supplies the structured specification format for converting qualitative research articles into testable algorithmic hypotheses (`HypothesisSchema`).
   - **`AutoHedge` Pattern:** Ingests non-execution mathematical formulas for LP impermanent loss and basis risk modeling.

3. **User Workstation & Terminal UI (`frontend/src/`):**
   - **`FinceptTerminal` Pattern:** Informs the multi-panel layout, keyboard-driven command bar, and unified ticker synchronization across Research Wikipedia and Trading Charts.
   - **`LibreChat` Pattern:** Guides multi-model LLM streaming responses, interactive inline citations, and markdown wiki infoboxes.
   - **`Open-LLM-VTuber` Pattern:** Deferred utility for generating 60-second synthesized audio debriefs of overnight research updates.

4. **Execution & Risk Desk (`core/execution/`):**
   - **ABSOLUTE BAN:** No upstream components are permitted to enter this layer. Milestone 18 execution kernel remains frozen.

---

## 3. License Compatibility & Quarantining Rules

| License Type | Upstream Candidates | Risk Level | Architectural Rule in SKY |
|:---|:---|:---:|:---|
| **MIT / Apache-2.0** | `claude-ads`, `agentic-inbox`, `LibreChat`, `Vibe-Trading`, `AutoHedge` | **Permissible** | Re-implement patterns natively or adapt isolated mathematical functions. Ensure attribution in headers. |
| **AGPL-3.0 / Copyleft** | `FinceptTerminal` (partial), `camofox-browser` (variants) | **Hazardous** | **STRICT QUARANTINE.** Never link, import, or copy code directly into CBT codebase. Study UI and functional concepts only as a black-box benchmark. |
| **Proprietary / Custom** | Various web scrapers | **Prohibited** | Zero code inclusion. Re-implement strictly using native Python stdlib / existing licensed dependencies. |

---

## 4. Architectural Invariants Enforced

1. **No Parallel Databases:** All ingested sources, claims, and articles must write directly to `data/research_wiki.db` via `core/knowledge_os/universal_ingestor.py`.
2. **Deterministic Risk Primacy:** Position sizing is exclusively governed by Half-Kelly and Hard Risk Gates. Upstream algorithmic logic cannot calculate position sizes.
3. **Causal Firewall Isolation:** Every research discovery must be timestamped with strict $t_{event} \le t_{decision}$ causality to prevent retrospective bias.
