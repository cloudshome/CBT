# Milestone 29: Preregistered Research Contract Specification

## 1. Executive Summary & Epistemic Objective

In accordance with the Level 1 System Constitution (`.specify/memory/constitution.md`) and Level 2 Quantitative Research Protocol (`docs/QUANT_RESEARCH_PROTOCOL.md`), post-hoc hypothesis cherry-picking and parameter fiddling represent the single greatest cause of statistical false positives in quantitative financial systems.

Milestone 29 establishes the **Preregistered Research Contract (`PreregisteredResearchContract`)** as a mandatory, immutable cryptographic lock on every empirical replay and hypothesis evaluation in the SKY / Crypto Brain Terminal research pipeline. 

No research replay, backtest, walk-forward evaluation, or statistical score may be generated without an uncompromised, cryptographically verified `PreregisteredResearchContract`.

---

## 2. Core Architecture & Cryptographic Integrity

### 2.1 The Preregistration Firewall
A research contract freezes all experimental conditions **before** any data is replayed or inspected:
- Target hypothesis ID and synthesis lineage.
- Concrete parameter space and primary optimization metric.
- Evaluation periods: train window, validation window, out-of-sample (OOS) test window.
- Minimum sample size constraints (minimum events, minimum independent episodes).
- Permitted parameter search space and discretization step sizes.
- Friction profile tier (`BASE`, `CONSERVATIVE`, `STRESS`).
- Candidate model count $N$ (for Bailey & López de Prado Deflated Sharpe Ratio correction).
- Statistical significance thresholds ($\alpha = 0.05$, minimum DSR $\ge 0.95$).

### 2.2 SHA-256 Cryptographic Seal
Every contract generates an immutable canonical SHA-256 hash across its frozen parameters:
```python
contract_payload = {
    "contract_id": self.contract_id,
    "hypothesis_id": self.hypothesis_id,
    "primary_metric": self.primary_metric,
    "parameters": sorted(self.parameters.items()),
    "train_start": self.train_start.isoformat(),
    "train_end": self.train_end.isoformat(),
    "val_start": self.val_start.isoformat(),
    "val_end": self.val_end.isoformat(),
    "oos_start": self.oos_start.isoformat(),
    "oos_end": self.oos_end.isoformat(),
    "min_event_count": self.min_event_count,
    "min_independent_episodes": self.min_independent_episodes,
    "friction_profile": self.friction_profile.value,
    "execution_authority": "NON_EXECUTABLE_RESEARCH_HYPOTHESIS",
    "real_capital_enabled": False,
}
self.contract_signature = hashlib.sha256(json.dumps(contract_payload, sort_keys=True).encode()).hexdigest()
```

### 2.3 Anti-Tampering Verification
Prior to any replay execution or statistical metric calculation, the validation engine calls `contract.verify_integrity()`. If any parameter, date range, or threshold has been altered after instantiation, contract verification raises `ContractTamperingError`, aborting the experiment and recording a security violation in failure memory.

---

## 3. Constitutional Execution Isolation Invariant

Every contract hardcodes and asserts the following non-negotiable boundaries:
```python
assert self.execution_authority == "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
assert self.real_capital_enabled is False
```
Under no circumstances can a `PreregisteredResearchContract` emit order router instructions, smart execution routes, or live exchange credentials. It is strictly constrained to the empirical research laboratory.

---

## 4. Contract Schema Definition

| Field | Type | Description |
|:---|:---|:---|
| `contract_id` | `str` | Unique UUID / monotonic identifier (`prc-...`) |
| `hypothesis_id` | `str` | Parent causal hypothesis identifier (`hyp-...`) |
| `mechanism_family` | `str` | Mechanism classification (e.g. `LIQUIDITY_VACUUM`, `FUNDING_BASIS_DISLOCATION`) |
| `primary_metric` | `str` | Target objective function (e.g. `deflated_sharpe_ratio`, `calmar_ratio`) |
| `parameters` | `Dict[str, Any]` | Frozen model parameters |
| `parameter_search_space` | `Dict[str, List[Any]]` | Full universe of explored parameter variants |
| `train_start`, `train_end` | `datetime` | In-sample training interval |
| `val_start`, `val_end` | `datetime` | Purged cross-validation interval |
| `oos_start`, `oos_end` | `datetime` | Strictly held-out out-of-sample testing interval |
| `min_event_count` | `int` | Minimum required macro/micro events ($\ge 30$) |
| `min_independent_episodes` | `int` | Minimum non-overlapping market regimes ($\ge 5$) |
| `friction_tier` | `FrictionTier` | Slippage & fee assumption (`BASE`, `CONSERVATIVE`, `STRESS`) |
| `candidate_model_count` | `int` | Total trials attempted in research family |
| `contract_signature` | `str` | Canonical SHA-256 seal |
| `execution_authority` | `str` | Permanently `"NON_EXECUTABLE_RESEARCH_HYPOTHESIS"` |
| `real_capital_enabled` | `bool` | Permanently `False` |

---

## 5. Contract Lifecycle & SQLite Persistence

1. **Generation:** Synthesized from `SynthesizedExperimentPlan` during research lab dispatch.
2. **Registration:** Committed to SQLite store (`research_contracts` table in `brain_memory.db`).
3. **Execution Gate:** Loaded by `CausalReplayEngine` and verified.
4. **Permanent Association:** Attached to `CausalValidationResult` or `CausalFailureAutopsy` for immutable auditability.
