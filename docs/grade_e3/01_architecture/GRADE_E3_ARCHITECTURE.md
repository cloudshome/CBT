# Grade-E3: High-Frequency Level 2 Reality Engine — Architectural Design Specification

> **Document Identity:** `GRADE_E3_ARCH_001`  
> **Classification:** Class H Quantitative Architecture & Security Design  
> **Status:** APPROVED & BINDING 📐  
> **Directive Reference:** Master Antigravity Directive (Phase 2)  
> **Governing Constitution:** `.specify/memory/constitution.md` | `AGENTS.md`  
> **Preceding Audit:** [`docs/grade_e3/00_audit/GRADE_E3_PREIMPLEMENTATION_AUDIT.md`](file:///c:/Users/azims/CBT/docs/grade_e3/00_audit/GRADE_E3_PREIMPLEMENTATION_AUDIT.md)  
> **Date:** 2026-09-20  

---

## 1. Architectural Mission & Non-Negotiable Invariants

The Grade-E3 architecture transitions SKY / CTB from candle-bar heuristic approximations to deterministic, high-resolution Level 2 order book and trade tick reality simulation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ CONSTITUTIONAL INVARIANT 1: PERMANENT CAPITAL FIREWALL                     │
│ real_capital_enabled is immutably False. Zero live execution paths.         │
├─────────────────────────────────────────────────────────────────────────────┤
│ CONSTITUTIONAL INVARIANT 2: CERTIFIED SURFACE PROTECTION                   │
│ Milestone 18 (14 files at commit c9cc1cad) remains untouched and locked.    │
├─────────────────────────────────────────────────────────────────────────────┤
│ CONSTITUTIONAL INVARIANT 3: TEMPORAL INTEGRITY DUALITY                     │
│ 1 µs internal event-loop precision != 100 ms empirical snapshot certainty.  │
├─────────────────────────────────────────────────────────────────────────────┤
│ CONSTITUTIONAL INVARIANT 4: DECOUPLED AUTHORIZATION GATEWAY                │
│ is_viable != is_validated != is_tradeable. is_tradeable is strictly False. │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Specification of the 13 Core Interfaces

### Interface 1: Dataset Integrity Auditor
- **Purpose:** Ingests raw packet payloads, verifies payload digests, monitors sequence continuity, detects duplicate or out-of-order packets, audits timestamp regressions, and produces a tamper-evident audit report.
- **Inputs:** `raw_bytes: bytes`, `diff_dicts: list[dict]`, `trade_dicts: list[dict]`, `clock_drift_tolerance_ms: float = 100.0`.
- **Outputs:** `FidelityAuditReport`, `EvidenceStatus` (`RAW_CAPTURED` $\to$ `PARSED` $\to$ `SEQUENCE_VALIDATED`).
- **Invariants:**
  - `pu == prev_u` or $U \le \text{prev\_u} + 1 \le u$ across all sequential diffs.
  - No negative prices or quantities ($P > 0, Q \ge 0$).
  - Monotonic trade timestamps ($t_{i+1} \ge t_i - \Delta_{\text{drift}}$).
- **Failure Behavior:** Gaps, regressions, or corrupted packets transition to `FAILED` or raise `SequenceIntegrityError` / `ClockRegressionError` when `fail_on_gap=True`.
- **Provenance Requirements:** SHA-256 digest calculated over raw payload bytes before parsing.
- **Determinism Requirements:** 100% bitwise deterministic given identical payload bytes.
- **Test Strategy:** Replay synthetic sequence breaks, timestamp reversals, duplicate packet packets, and verify state transitions.

---

### Interface 2: Snapshot and Diff Reconstructor
- **Purpose:** Maintains a sorted Level 2 limit order book ladder, buffers early diffs until snapshot receipt, prunes zeroed levels, detects crossed markets, and computes microstructural state metrics.
- **Inputs:** Snapshot `last_update_id: int`, `bids: list[tuple[float, float]]`, `asks: list[tuple[float, float]]`, sequential `L2DiffUpdate` stream.
- **Outputs:** Reconstructed order book state, `OrderBookTop` (best bid, best ask, mid-price, micro-price, spread bps, OBI), book state hash.
- **Invariants:**
  - Bids strictly sorted descending: $P_{\text{bid}, i} > P_{\text{bid}, i+1}$.
  - Asks strictly sorted ascending: $P_{\text{ask}, i} < P_{\text{ask}, i+1}$.
  - Strictly uncrossed: $P_{\text{best\_bid}} < P_{\text{best\_ask}}$. If $P_{\text{best\_bid}} \ge P_{\text{best\_ask}}$, raise `CrossedBookError`.
- **Failure Behavior:** Fails closed if snapshot update ID is beyond buffered diff range (`SnapshotSyncError`).
- **Provenance Requirements:** Computes state SHA-256 digest over sorted ladder JSON representation.
- **Determinism Requirements:** Identical sequence of snapshots and diffs must produce identical order book state and state hash.
- **Test Strategy:** Test book reconstruction, out-of-order diff buffering, crossed book triggering, and state hash invariance.

---

### Interface 3: Trade Tick Ingestion & Parser
- **Purpose:** Ingests executed market trade prints and normalizes trade direction according to universal exchange rules.
- **Inputs:** `raw_trade_dicts: list[dict]`.
- **Outputs:** `list[TradeTick]` (`trade_id`, `timestamp_ns`, `price`, `size`, `is_buyer_maker`, `symbol`).
- **Invariants:**
  - $P > 0, Q > 0$.
  - Correct aggressor side mapping: `is_buyer_maker=True` $\implies$ passive buyer, aggressive seller; `is_buyer_maker=False` $\implies$ passive seller, aggressive buyer.
- **Failure Behavior:** Malformed trade ticks are rejected and recorded in the integrity report.
- **Provenance Requirements:** Trade tick array bound to raw payload hash.
- **Determinism Requirements:** Deterministic parse order preserving source feed sequence.
- **Test Strategy:** Test trade print parsing across Binance Spot and Bybit Linear Perp payload schemas.

---

### Interface 4: Temporal Normalization Engine
- **Purpose:** Unifies heterogeneous timestamp formats (nanoseconds, microseconds, milliseconds, ISO strings) onto a monotonic nanosecond timeline.
- **Inputs:** `timestamp_raw: int | float | str`, `source_precision: str`.
- **Outputs:** `timestamp_ns: int`.
- **Invariants:** Non-negative nanosecond integer clamped monotonically.
- **Failure Behavior:** Non-convertible timestamp strings or NaN values fail closed with `ValueError`.
- **Provenance Requirements:** Preserves original timestamp in metadata.
- **Determinism Requirements:** Pure deterministic numerical conversion.
- **Test Strategy:** Test unit conversions across ns, us, ms, s, and leap-second clock drift assertions.

---

### Interface 5: Queue Simulation Engine
- **Purpose:** Models passive maker limit order lifecycle, queue position estimation, and queue depletion from competing aggressor trades.
- **Inputs:** Order parameters (`order_id`, `side`, `price`, `quantity`, `timestamp_ns`), `QueueModelType` (Q0, Q1, Q2, Q3), stream of `TradeTick`.
- **Outputs:** `QueuePositionEstimate`, `list[L2FillEvent]`.
- **Invariants:**
  - Fills occur only when cumulative aggressive volume at order price exceeds estimated queue ahead ($V_{\text{aggressor}} \ge Q_{\text{ahead}} + Q_{\text{order}}$) or upon price penetration through limit price.
  - Queue ahead cannot be negative.
  - Fill quantity cannot exceed remaining order quantity.
- **Failure Behavior:** Invalid price/quantity or submission against inverted books raises `ValueError`.
- **Provenance Requirements:** Bound to `QueueModelType`, parameter hash, and random seed.
- **Determinism Requirements:** Deterministic given fixed random seed and trade tick sequence.
- **Test Strategy:** Test Q0, Q1, Q2, Q3 depletion rates, partial fills, price penetration fills, and queue position bounds.

---

### Interface 6: Latency Modeling Engine
- **Purpose:** Simulates realistic network transmission delay, cancel latency racing, and matching-engine in-flight trade races.
- **Inputs:** `CancelLatencyConfig` (distribution, $p50$, $p90$, $p99$), `cancellation_timestamp_ns: int`.
- **Outputs:** `cancel_effective_at_ns: int`, `sampled_latency_ms: float`.
- **Invariants:**
  - $\Delta t_{\text{cancel}} > 0$ (no instantaneous or time-traveling cancellations).
  - An aggressive trade arriving at $t < t_{\text{effective}}$ fills the order even if cancellation was requested at $t_{\text{request}} \le t$.
- **Failure Behavior:** Non-positive latency parameters fall back to conservative default ($25\,\text{ms}$).
- **Provenance Requirements:** Records whether latency was `EMPIRICAL`, `ASSUMED`, `SYNTHETIC`, or `SCENARIO`.
- **Determinism Requirements:** Deterministic pseudo-random variate generation seeded with reproducible PRNG.
- **Test Strategy:** Verify cancel racing: trades before $t_{\text{effective}}$ generate fills; trades after $t_{\text{effective}}$ are ignored.

---

### Interface 7: Markout Calculation Engine
- **Purpose:** Measures ex-post price drift following order execution across standardized institutional horizons.
- **Inputs:** `fill: L2FillEvent`, `trade_history: list[TradeTick]`, horizons $\tau \in \{100\,\text{ms}, 1\,\text{s}, 5\,\text{s}, 30\,\text{s}, 5\,\text{min}\}$.
- **Outputs:** `markouts_bps: dict[str, float]` (directional basis points relative to fill price).
- **Invariants:**
  - Directional sign convention:
    $$\text{Markout}_{\tau} = \begin{cases} \frac{P_{t+\tau} - P_{\text{fill}}}{P_{\text{fill}}} \times 10^4 & \text{for BUY} \\ \frac{P_{\text{fill}} - P_{t+\tau}}{P_{\text{fill}}} \times 10^4 & \text{for SELL} \end{cases}$$
  - No future data leakage: only trades with $t \ge t_{\text{fill}} + \tau$ are queried.
- **Failure Behavior:** If trade history ends before horizon $\tau$, markout for that horizon is recorded as `None` or omitted; never extrapolated.
- **Provenance Requirements:** Bound to fill event ID and trade history digest.
- **Determinism Requirements:** 100% deterministic lookup over immutable trade array.
- **Test Strategy:** Test BUY and SELL markouts across all 5 horizons with known future prices.

---

### Interface 8: Winner's Curse Estimator
- **Purpose:** Quantifies whether passive limit fills suffer from adverse selection relative to the unconditional market drift.
- **Inputs:** `conditional_fill_markouts: list[float]`, `unconditional_market_samples: list[float]`.
- **Outputs:** `winners_curse_bias_bps: float`, `standard_error: float`, `confidence_interval: tuple[float, float]`.
- **Invariants:**
  $$\text{Winner's Curse Bias} = E[\text{Markout}_{\tau} \mid \text{Filled}] - E[\Delta P_{\tau} \mid \text{Unconditional}]$$
  A negative value proves adverse selection (the order filled because the market moved against it).
- **Failure Behavior:** Sample size $< 10$ reports `INSUFFICIENT_SAMPLE_SIZE`.
- **Provenance Requirements:** Bound to experiment run ID.
- **Determinism Requirements:** Deterministic statistical reduction.
- **Test Strategy:** Validate bias calculation against known synthetic drift and fill distributions.

---

### Interface 9: Institutional Fee & Economics Engine
- **Purpose:** Computes net maker expectancy after subtracting venue fees, adverse selection drag, and exchange slippage.
- **Inputs:** `maker_gross_pnl_bps: float`, `adverse_selection_bps: float`, `fee_tier: FeeSchedule` (VIP0, VIP2, VIP4).
- **Outputs:** `net_maker_edge_bps: float`, `is_economically_viable: bool`.
- **Invariants:**
  $$\text{Net Maker Edge} = \text{Gross Spread Capture} - \text{Adverse Selection Drag} - 2 \times \text{Maker Fee}$$
- **Failure Behavior:** Invalid fee tiers fail closed with `KeyError`.
- **Provenance Requirements:** Canonical fee tiers locked in `CANONICAL_FEE_TIERS`.
- **Determinism Requirements:** Exact floating-point arithmetic.
- **Test Strategy:** Test VIP0 (7.5 bps fee), VIP2 (4.0 bps fee), and VIP4 (-0.5 bps rebate) economics.

---

### Interface 10: Evidence Bundle Generator
- **Purpose:** Constructs an immutable, cryptographic audit package binding all inputs, configurations, code commit, and results.
- **Inputs:** `raw_data_hash`, `book_builder_hash`, `queue_model`, `cancel_config`, `code_commit`, `experiment_id`, `result_artifact_hash`.
- **Outputs:** `TamperEvidentEvidenceBundle` (with deterministic SHA-256 `bundle_hash`).
- **Invariants:**
  - Tampering with any field changes `bundle_hash` and invalidates `verify_integrity()`.
- **Failure Behavior:** Fails closed if any required hash field is empty or malformed.
- **Provenance Requirements:** Self-authenticating SHA-256 digest over canonical JSON.
- **Determinism Requirements:** Canonical JSON key ordering (`sort_keys=True`).
- **Test Strategy:** Assert `bundle.verify_integrity() == True`; assert modifying any field causes verification failure.

---

### Interface 11: Provenance Authority Verifier
- **Purpose:** Validates Grade-E3 evidence bundles, checks dataset manifests, detects parameter tampering, and blocks epistemic grade inflation.
- **Inputs:** `profile: MicrostructureDragProfile`, `bundle: TamperEvidentEvidenceBundle | None`.
- **Outputs:** `is_valid: bool`.
- **Invariants:**
  - OHLCV datasets cannot claim `L2_TICK_VERIFIED` (`EpistemicInflationError`).
  - Bundle hash must match recomputed digest (`ProvenanceTamperError`).
- **Failure Behavior:** Raises explicit exception or returns `False` fail-closed.
- **Provenance Requirements:** Manifest verification against `manifest_k9.json`.
- **Determinism Requirements:** Pure deterministic validation function.
- **Test Strategy:** Test valid bundles, tampered digests, and inflated OHLCV profiles.

---

### Interface 12: Research Verdict Synthesizer
- **Purpose:** Synthesizes empirical evidence across all datasets into an institutional verdict (`QUARANTINE`, `CONDITIONALLY_PERMITTED`, or `UNVIABLE`).
- **Inputs:** Multi-asset experiment results (BTC, ETH, SOL), fee tier comparisons, statistical significance tests.
- **Outputs:** Institutional Verdict Document (`GRADE_E3_FINAL_VERDICT.md`), recommendation matrix.
- **Invariants:**
  - Negative net maker edge strictly prevents promotion.
  - Results are never suppressed or smoothed.
- **Failure Behavior:** Missing assets or failed integrity checks yield `INCONCLUSIVE` or `QUARANTINE`.
- **Provenance Requirements:** Signed with experiment run timestamp and code commit.
- **Determinism Requirements:** Deterministic rule evaluation.
- **Test Strategy:** Test verdict logic across profitable, marginal, and negative net edge profiles.

---

### Interface 13: Strategy Reality Bridge Adapter
- **Purpose:** Exposes Grade-E3 empirical microstructure profiles to `StrategyLeague` and `ExecutionAuthorizationGateway`.
- **Inputs:** `strategy_returns: list[float]`, `asset: str`, `timeframe: str`.
- **Outputs:** `CalibratedExecutionResult` (`calibrated_pnl`, `drag_bps`, `is_viable`, `is_tradeable`).
- **Invariants:**
  - `is_tradeable` strictly returns `False` under research governance.
  - Preserves 3-tuple legacy sequence unpacking: `cal_pnl, drag, is_viable = bridge.apply_execution_reality(...)`.
- **Failure Behavior:** Unknown asset returns conservative synthetic fallback.
- **Provenance Requirements:** Profile validated by `ProvenanceAuthority` prior to return.
- **Determinism Requirements:** 100% deterministic calibration.
- **Test Strategy:** Test sequence unpacking, drag application, and authorization gateway gating.

---

## 3. Architecture Signoff & Readiness for Implementation

The 13 interfaces form a closed, internally consistent, and constitutionally compliant system.
Milestone 18 certified surfaces and the Permanent Capital Firewall are completely protected.

**Design Status:** `APPROVED & READY FOR PHASE 3 DATA INTEGRITY IMPLEMENTATION`.
