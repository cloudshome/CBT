# SKY INTEGRATION ROADMAP & EXECUTION PLAN
**Project:** SKY / Crypto Brain Terminal (CBT)  
**Governance Level:** Senior Systems Architect & Engineering Lead  
**Classification:** Class D Implementation Roadmap  
**Status:** ARCHITECTURAL SPECIFICATION & PHASE-GATED ROADMAP  
**Binding Invariants:** M18 Execution Kernel Frozen (`c9cc1cad`), `REAL_CAPITAL_ENABLED = False`  

---

## 1. Executive Implementation Phasing

To implement the institutional research intelligence layer without destabilizing production systems, development is divided into five strictly verified, sequential phases. Each phase is protected by mandatory quality gates and zero-lookahead audits.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FIVE-PHASE INTEGRATION ROADMAP                                  │
├───────────────────┬───────────────────┬───────────────────┬────────────────────────────┤
│ PHASE 1           │ PHASE 2           │ PHASE 3           │ PHASE 4 & 5                │
│ Security & Ledger │ Bounded Workers   │ Knowledge Graph   │ Triage & Terminal UX       │
│ Foundations       │ & Search Fleet    │ & Wiki Infoboxes  │ & Quant Backtest Bridge    │
└───────────────────┴───────────────────┴───────────────────┴────────────────────────────┘
```

---

## 2. Phase-by-Phase Work Packages

### Phase 1: Security & Source Provenance Foundation
*Focus: Bulletproof network security, immutable hash ledger, epistemic data schemas.*
- **Work Package 1.1: SSRF & Network Security Hardening**
  - Implement full socket-level DNS pinning and redirect validation in `core/knowledge_os/web_search_agent.py`.
  - Enforce RFC 1918, link-local metadata (`169.254.169.254`), and port whitelisting.
- **Work Package 1.2: Relational Ledger Schema Expansion**
  - Execute schema migration on `data/research_wiki.db` for `wiki_articles`, `wiki_article_versions`, `wiki_links`, `wiki_source_citations`, and `wiki_contradictions`.
  - Maintain foreign key integrity with existing `research_sources` and `research_claims` tables.
- **Work Package 1.3: Epistemic Validation Primitives**
  - Integrate Pydantic/dataclass validation enforcing epistemic levels (`[FACT]`, `[HYPOTHESIS]`, etc.).
- **Phase 1 Acceptance Gate:**
  - 100% passing tests on SSRF validation suite (including IPv6, hex-encoded IPs, and DNS rebinding mocks).
  - Clean SQLite schema verification with zero lock contention.

---

### Phase 2: Autonomous Research Worker Fleet
*Focus: Bounded multi-worker agent orchestration inspired by `claude-ads`.*
- **Work Package 2.1: Multi-Worker Hierarchy Implementation**
  - Decouple research flow into 5 discrete workers: `QueryPlannerWorker`, `SecureFetchWorker`, `ExtractionWorker`, `ClaimExtractionWorker`, `ResearchCriticWorker`.
  - Implement canonical JSON contracts and partial-failure handling.
- **Work Package 2.2: Multi-Provider Search Adapters**
  - Implement provider abstraction for DuckDuckGo, SearXNG, ArXiv, and Macro RSS.
  - Implement rate limiting, exponential backoff, and domain circuit breakers.
- **Work Package 2.3: Untrusted Data Firewall**
  - Standardize defensive prompting wrappers that isolate untrusted crawled content.
  - Implement regex-based stripping of prompt injection vectors (`SYSTEM:`, `OVERRIDE:`, etc.).
- **Phase 2 Acceptance Gate:**
  - End-to-end execution of a 5-worker research cycle returning structured claims within $\le 10$ seconds.
  - Verified immunity to prompt injection strings injected in mock web pages.

---

### Phase 3: Research Wikipedia Knowledge Graph & Infoboxes
*Focus: Institutional Wikipedia presentation, bidirectional linking, and contradiction tracking.*
- **Work Package 3.1: Bidirectional WikiLink Engine**
  - Implement parser for `[[Article Title|Anchor]]` in `research_wikipedia.py` and `ResearchWikipediaDesk.tsx`.
  - Build automatic bidirectional graph indexing in SQLite (`wiki_links`).
- **Work Package 3.2: Structured Category Infoboxes**
  - Implement specialized infobox schemas for `Market Regime`, `Alpha Factor`, `Protocol`, and `Execution Venue`.
  - Integrate interactive hover previews (`WikiLinkHover.tsx`) with instant cache lookup.
- **Work Package 3.3: Dialectical Contradiction Tracker**
  - Implement automated contradiction detection between opposing claims.
  - Render visual contradiction alerts and regime-conditioning prompts in the UI.
- **Phase 3 Acceptance Gate:**
  - Fast page navigation with zero DOM flickering (UI Stability Principle).
  - Hover previews render in $< 50\text{ms}$ with full source citations.

---

### Phase 4: Human-in-the-Loop Triage & Strategy Bridge
*Focus: Review state machines (`agentic-inbox` pattern) and alpha hypothesis extraction (`Vibe-Trading` pattern).*
- **Work Package 4.1: Research Triage Inbox Desk**
  - Implement interactive review queue in `ResearchWikipediaDesk.tsx` (`STAGING` $\to$ `APPROVED` $\to$ `MERGED`).
  - Researcher can inspect diffs, edit generated summaries, and approve article updates.
- **Work Package 4.2: Falsifiable Hypothesis Extraction**
  - Build hypothesis compiler translating Wikipedia claims into formal `ThesisEngine` objects (`market`, `timeframe`, `entry_rule`, `invalidation_rule`).
- **Work Package 4.3: Backtest Queue Integration**
  - Bridge approved hypotheses to `core/knowledge_os/backtest_queue.py` for scheduled walk-forward combinatorial cross-validation (CPCV).
- **Phase 4 Acceptance Gate:**
  - Zero execution leakage: Hypotheses cannot trigger trade orders or modify live parameters.
  - Full audit trail of researcher approvals recorded in `wiki_article_versions`.

---

### Phase 5: Terminal Workstation UX & Production Polish
*Focus: Institutional layout, persistent charts, and audio debriefs.*
- **Work Package 5.1: Synchronized Workstation Command Bar**
  - Emulate institutional command line (inspired by `FinceptTerminal`): typing `/wiki BTC-REGIME` or `/chart SOLUSDT` seamlessly switches context without re-rendering components.
- **Work Package 5.2: Frame-Accurate Visual Export**
  - Automated generation of backtest summary cards and research visual dossiers.
- **Work Package 5.3: Optional Audio Research Briefings**
  - 60-second synthesized audio debriefs generated for Telegram bot or terminal audio player.
- **Phase 5 Acceptance Gate:**
  - System Preflight Script (`scripts/system_preflight.py`) runs green.
  - Production Vite build and Python test suite 100% green.

---

## 3. Rollback & Emergency Contingencies

| Failure Mode | Trigger Condition | Automated Action | Manual Recovery Procedure |
|:---|:---|:---|:---|
| **SSRF Gate Breach Attempt** | External URL targets loopback or private subnet | Immediately drop connection; log security event | Review domain blocklist; ensure DNS resolver is healthy. |
| **Prompt Injection Detected** | Crawled content attempts instruction hijack | Drop raw payload; flag domain as untrusted | Inspect extraction logs; tighten parser tag filtering. |
| **SQLite Lock Contention** | Concurrent worker writes to `research_wiki.db` | Exponential retry with WAL mode; fallback to memory queue | Verify WAL mode is enabled: `PRAGMA journal_mode=WAL;` |
| **M18 Certification Invalidation** | Accidental file touch in `core/execution/` | CI/CD immediately blocks build and tests fail | Run `scripts/verify_m18_certification.py`; revert unauthorized changes. |
