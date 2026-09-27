# SKY / CTB Institutional Deployment & Promotion Governance Framework

> **Document Version:** 2.0.0  
> **Status:** ACTIVE & MANDATORY 🛡️  
> **Authority:** Institutional Architecture & Governance Desk  
> **Enforcement Module:** [`core/governance/institutional_deployment.py`](file:///c:/Users/azims/CBT/core/governance/institutional_deployment.py)  

---

## 1. Executive Directive: Zero Live Capital Principle

As mandated by institutional governance:
> **Real exchange trading is STRICTLY PROHIBITED.**
> The system state machine initializes exclusively at `RESEARCH_ONLY`.
> `real_capital_enabled` is hardcoded to `False` in Python code and protected by the **Permanent Capital Firewall**.
> Enabling live funds via environment variables, config files, API payloads, or test flags is an uncatchable fatal violation.

---

## 2. The 6 Institutional Deployment Gates

Promotion from research hypotheses to operational testing requires satisfying six independent, sequential, cryptographically bound deployment gates:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ GATE 1: DATA FIDELITY (L2 Depth & Trade Tick Ingestion Integrity)           │
│ Criteria: Monotonic IDs, gapless sequence (pu == prev_u), clock drift <= 100ms│
├─────────────────────────────────────────────────────────────────────────────┤
│ GATE 2: EXECUTION REALITY (Microstructural Queue & Markout Measurement)     │
│ Criteria: Standardized markouts (100ms, 1s, 5s, 30s), queue uncertainty     │
├─────────────────────────────────────────────────────────────────────────────┤
│ GATE 3: NET POSITIVE EXPECTANCY (OOS Deflated Sharpe & Frictions)           │
│ Criteria: Out-of-sample Net EV > 0 under Tier 2/3 frictions, DSR >= 0.85    │
├─────────────────────────────────────────────────────────────────────────────┤
│ GATE 4: ROBUSTNESS & REPRODUCIBILITY (Multi-Regime Walk-Forward & WRC)      │
│ Criteria: Parameter perturbation +/-20%, White's Reality Check p < 0.05     │
├─────────────────────────────────────────────────────────────────────────────┤
│ GATE 5: EXTENDED SANDBOX BURN-IN (Testnet Replay & Reconciliation)          │
│ Criteria: >= 14 days consecutive live feeds, zero unresolved reconciliation │
├─────────────────────────────────────────────────────────────────────────────┤
│ GATE 6: HUMAN CONTROLLED CAPITAL (Hardware WebAuthn Multi-Sig & Limits)     │
│ Criteria: Hardware token signoff, <= $500 micro notional, instant killswitch│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Immutable Evidence Invariant:
A gate is **NEVER** marked passed because a boolean function returns `True`. Every gate requires an immutable `GateEvidence` bundle with:
- `gate_id`: e.g. `GATE_1_DATA_FIDELITY`
- `status`: `PASSED`
- `strategy_id`: canonical identifier
- `dataset_hash`: 64-character SHA-256 digest matching manifest
- `experiment_id`: canonical experiment run reference
- `evidence_hash`: deterministic digest of canonical evidence fields
- `issuer`: recognized governance pipeline authority
- `issued_at` & `valid_until`: explicit validity window (expired evidence fails closed)
- `revocation_status`: false (revoked evidence fails closed)

---

## 3. The 8-Stage System State Machine

State transitions advance sequentially through the sole transition authority:
$$\text{request\_promotion}(\text{target\_stage}, \text{evidence\_bundle}, \text{human\_authorization})$$

```
[1] RESEARCH_ONLY
      ↓ (Requires Gate 1)
[2] RESEARCH_VIABLE
      ↓ (Requires Gate 2)
[3] EXECUTION_MODEL_VALIDATED
      ↓ (Requires Gate 3)
[4] SANDBOX_ELIGIBLE
      ↓ (Requires Gate 4 + Gate 5)
[5] SANDBOX_VERIFIED
      ↓ (Requires Formal Audit Signoff)
[6] HUMAN_LIVE_REVIEW
      ↓ (Requires Gate 6 + Hardware Auth Token)
[7] MICRO_CAPITAL_ELIGIBLE
      ↓ (Requires Multi-Party Quorum Signoff)
[8] LIVE_AUTHORIZED (Capital locked to False in current repository)
```

---

## 4. Decoupled Operational Capability Matrix

Stage advancement does **NOT** automatically grant operational capabilities:

| Operational Capability | `RESEARCH_ONLY` | `RESEARCH_VIABLE` | `EXEC_VALIDATED` | `SANDBOX_ELIGIBLE` | `SANDBOX_VERIFIED` | `HUMAN_REVIEW` | `MICRO_CAPITAL` | `LIVE_AUTH` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `research` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `historical_replay` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `paper_trading` | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `exchange_testnet` | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `live_market_data` | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `funded_account_connection` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `live_order_submission` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `capital_allocation` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 5. Emergency Downgrade Protocol

Any violation of operational invariants (e.g. sequence gap, feed corruption, reconciliation discrepancy, latency spike, crossed order book) immediately triggers:

$$\text{governor.emergency\_downgrade}(\text{reason}, \text{target\_stage}=\text{RESEARCH\_ONLY})$$

All non-research capabilities are instantaneously revoked fail-closed.
