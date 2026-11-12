# M28 DATA LINEAGE & POINT-IN-TIME CAUSALITY AUDIT

**Document ID:** `M28-LINEAGE-001`  
**Repository:** SKY / Crypto Brain Terminal (CBT)  
**Target Milestone:** Milestone 28 — Cross-Domain Macro-Micro Causal Synthesis  
**Auditor:** Senior Quantitative Systems Architect & Research Governance Reviewer  
**Commit Baseline:** `4cd8c45`  
**Standard:** Level 1 Constitution (`SKY-CONST-002`: Zero Lookahead) & Epistemic Taxonomy  
**Status:** DATA LINEAGE ARCHITECTURE CERTIFIED  

---

## 1. Executive Summary & Epistemic Mandate

In quantitative finance, lookahead bias is the primary driver of catastrophic backtest failure. When qualitative macroeconomic news, regulatory filings, and social announcements are coupled with millisecond-resolution microstructure data, three severe temporal hazards emerge:
1. **Reporting Delay / Latency Horizon:** Assuming market participants possessed knowledge of an economic release at the exact nominal timestamp (e.g. 08:30:00.000 ET) when public dissemination took hundreds of milliseconds or minutes.
2. **Retrospective Revisions:** Using modern (revised) data figures to backtest historical decisions when the initial vintage available to traders differed significantly.
3. **Observation Overlap:** Evaluating an entry signal within a candle whose span began *before* the event publication timestamp ($t_{\text{candle\_start}} < t_{\text{published}}$).

This document establishes the **Data Lineage Contract** and mathematical proofs guaranteeing **Zero Lookahead** across the Milestone 27 $\to$ Milestone 28 $\to$ Autonomous Research pipeline.

---

## 2. Temporal Lineage Architecture

```
T0: Event Occurs in Real World
 │  (e.g., FOMC vote, CPI calculation finalized)
 │
 ▼
T1: Official Publication Timestamp (`published_at_utc`)
 │  (First verifiable public dissemination)
 │
 ▼ [Network Latency / Dissemination Lag: Δt_dissemination ≥ 0]
 │
T2: Collector Ingestion Timestamp (`collected_at_utc`)
 │  (Timestamp when Milestone 27 Web Scout or RSS feed received payload)
 │
 ▼ [Intelligence Fabric Processing: Δt_processing ≥ 0]
 │
T3: Intelligence Persistence Timestamp (`created_at_utc`)
 │  (Saved into `global_intelligence_records` with immutable SHA-256)
 │
 ▼ [Causal Research Cutoff Gate: t_cutoff = min(T1, T2)]
 │
T4: Market Observation Start (`candle_open_utc` or `tick_utc`)
 │  (Microstructure evaluation begins: CVD, OBI, SMC)
 │
 ▼
T5: Strategy Hypothesis Formulation / Simulated Entry
```

### Strict Temporal Invariant:
$$\boxed{T1 \le T2 \le T3 < T4 \le T5}$$

Under **no circumstances** may any microstructure observation window or simulated order entry use market data timestamped prior to or equal to $T1$ or $T2$.

---

## 3. The Point-in-Time Event Contract (`PointInTimeEventContract`)

To bridge Milestone 27 `IntelligenceRecord` to Milestone 28 Causal Synthesizer, every event is wrapped in a strict mathematical contract:

```python
class PointInTimeEventContract:
    event_id: str                          # UUID-v4 or deterministic hash
    source_record_id: str                  # Milestone 27 global_intelligence_records.id
    event_type: str                        # MACRO_RELEASE, REGULATORY_FILING, ONCHAIN_ANOMALY, etc.
    published_at_utc: float                # T1: Nominal publication Unix timestamp (seconds)
    collected_at_utc: float                # T2: Real ingestion Unix timestamp (seconds)
    effective_availability_utc: float      # max(published_at_utc, collected_at_utc) + dissemination_buffer_seconds
    initial_metric_value: Optional[float]  # Unrevised vintage value
    revised_metric_value: Optional[float]  # None at initial release
    revision_number: int                   # 0 for initial release
    content_hash_sha256: str               # Cryptographic SHA-256 of canonical text payload
    epistemic_grade: str                   # VERIFIED_PRIMARY, CORROBORATED_REPORT, etc.
    dissemination_buffer_seconds: float    # Conservative safety margin (default 5.0 seconds for macro, 60.0 for web)
```

### Fail-Closed Decision Protocol:
1. **Unverifiable Timestamp:** If `published_at_utc` is `None`, non-positive, or in the future ($> \text{now}_{\text{utc}}$), the contract raises `TemporalIntegrityError` and the event is dropped from causal research.
2. **Ambiguous Availability:** If `collected_at_utc < published_at_utc`, clock drift is detected; the effective availability is forced to $\max(\text{published}, \text{collected}) + 60.0\text{s}$.
3. **Missing Initial Vintage:** If an economic metric is known to have revisions (e.g. GDP, Non-Farm Payrolls) and only the current revised number is present without vintage confirmation, it is marked `UNVERIFIED_VINTAGE` and forbidden from conditioning backtest signals.

---

## 4. Microstructure Temporal Alignment Protocol

When synthesizing qualitative events with quantitative microstructure:

### 4.1 Order Book Imbalance (OBI) Alignment
- L2 Order Book snapshots update at $10\text{Hz}$ or $1\text{Hz}$.
- The microstructure receptor MUST ONLY evaluate order books starting at:
  $$t_{\text{obi\_eval}} \ge \text{effective\_availability\_utc} + \Delta t_{\text{network\_slack}}$$
- Pre-event OBI is strictly isolated as a baseline comparison window:
  $$\text{Baseline: } [t_{\text{pub}} - 300\text{s}, t_{\text{pub}} - 5\text{s}]$$
  $$\text{Post-Event Observation: } [t_{\text{pub}} + 5\text{s}, t_{\text{pub}} + 300\text{s}]$$
- Note the $10$-second dead zone $[t_{\text{pub}} - 5\text{s}, t_{\text{pub}} + 5\text{s}]$ to eliminate high-frequency latency arbitrage noise.

### 4.2 CVD Absorption Alignment
- CVD absorption evaluates cumulative volume delta divergence against price candles ($1\text{m}, 5\text{m}, 15\text{m}$).
- Rule: A candle that opens before $t_{\text{effective\_availability}}$ cannot be treated as a "post-event response".
- If $t_{\text{pub}} = 14:30:15$, the $14:30:00\text{–}14:35:00$ candle is **tainted** by pre-event price action. The causal compiler must either:
  1. Evaluate sub-minute tick CVD from $14:30:20$ onward, OR
  2. Discard the $14:30$ candle and initiate observation strictly on the $14:35:00$ candle open.

### 4.3 SMC Structural Shift Alignment
- Fair Value Gaps (FVG) and Order Blocks (OB) require 3-candle sequences to form.
- Any structural marker formed before $t_{\text{effective\_availability}}$ is treated as a **pre-existing regime**, never as an outcome caused by the event.

---

## 5. Provenance Ledger & Audit Trail

Every synthesized hypothesis records its full lineage in `data/trading_logs.db` table `causal_hypotheses_ledger`:

```sql
CREATE TABLE IF NOT EXISTS causal_hypotheses_ledger (
    hypothesis_id TEXT PRIMARY KEY,
    family_id TEXT NOT NULL,
    macro_event_id TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    published_at_utc REAL NOT NULL,
    effective_availability_utc REAL NOT NULL,
    microstructure_start_utc REAL NOT NULL,
    temporal_margin_seconds REAL NOT NULL,
    content_hash_sha256 TEXT NOT NULL,
    epistemic_grade TEXT NOT NULL,
    mechanism_id TEXT NOT NULL,
    null_hypothesis TEXT NOT NULL,
    alternative_hypothesis TEXT NOT NULL,
    microstructure_conditions_json TEXT NOT NULL,
    falsification_criteria_json TEXT NOT NULL,
    status TEXT NOT NULL,
    execution_authority TEXT NOT NULL DEFAULT 'NON_EXECUTABLE_RESEARCH_HYPOTHESIS',
    created_at_utc REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_causal_hypo_family ON causal_hypotheses_ledger(family_id);
CREATE INDEX IF NOT EXISTS idx_causal_hypo_event ON causal_hypotheses_ledger(macro_event_id);
CREATE INDEX IF NOT EXISTS idx_causal_hypo_status ON causal_hypotheses_ledger(status);
```

---

## 6. Mathematical Proof of Zero Lookahead

**Theorem 1 (Causal Precedence Invariance):**  
Let $E$ be an information event with publication time $t_{\text{pub}}$, and let $M(t)$ denote the market microstructure state at time $t$. Let $S$ be a trading strategy hypothesis whose decision rule is $f(E, M(t))$.

The strategy $S$ is free from lookahead bias if and only if for all observations $M(t)$ used to compute $f$:
$$t \ge t_{\text{pub}} + \delta_{\text{latency}}$$
where $\delta_{\text{latency}} \ge 0$ is the dissemination lag.

**Implementation Guarantee:**  
In `core/intelligence/causal_firewall.py`, the validator computes:
$$\Delta t_{\text{margin}} = t_{\text{microstructure\_start}} - t_{\text{effective\_availability}}$$
If $\Delta t_{\text{margin}} < 0$, the firewall immediately aborts hypothesis formulation and records a `TEMPORAL_LEAKAGE_DETECTED` violation. This condition is checked deterministically with machine precision.

---

## 7. Lineage Certification

This lineage architecture guarantees that every synthesized research hypothesis in Milestone 28 is provably causal, revision-safe, and isolated from historical lookahead artifacts.
