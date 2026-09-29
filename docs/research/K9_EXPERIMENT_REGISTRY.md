# Milestone K9: Research Experiment Registry & Ledger Reference

**Ledger Database:** `data/kronos/research_experiments.db`  
**Storage Engine:** SQLite (WAL Mode, synchronous NORMAL)  
**Access Model:** Append-Only (Mutations and In-Place Updates Prohibited)  
**Governance Protocol:** Level 1 Constitution (`.specify/memory/constitution.md`)  

---

## 1. Experiment Ledger Schema

```sql
CREATE TABLE research_experiments (
    experiment_id TEXT PRIMARY KEY,
    parent_hypothesis_id TEXT NOT NULL,
    research_config_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_hash TEXT NOT NULL,
    feature_schema_hash TEXT NOT NULL,
    model_version TEXT NOT NULL,
    git_commit_sha TEXT NOT NULL,
    random_seed INTEGER NOT NULL,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    fold_count INTEGER NOT NULL,
    sample_size INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    statistical_tests_json TEXT NOT NULL,
    friction_results_json TEXT NOT NULL,
    multiple_testing_index INTEGER NOT NULL,
    research_state TEXT NOT NULL, -- 'PROMOTE', 'QUARANTINE', 'REJECT', 'INCONCLUSIVE'
    failure_reason TEXT,
    reproducibility_status TEXT NOT NULL,
    notes_json TEXT,
    created_at_ms INTEGER NOT NULL
);
CREATE INDEX idx_exp_asset_tf ON research_experiments(asset, timeframe, horizon_bars);
CREATE INDEX idx_exp_state ON research_experiments(research_state);
```

---

## 2. Active Logged Experiments

| Experiment ID | Hypothesis | Dataset ID | Asset / TF | Folds | OOS Samples | State | Failure Reason / Verdict |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `K9_EXP_CONFIRMATORY_BTC15M_001` | `H1_PRIMARY_INCREMENTAL_SKILL` | `K9_BTCUSDT_15m_464d2ff4` | `BTC` / `15m` | 3 | 4,317 | **`REJECT`** | Negative net expected value under Tier 2 conservative friction hurdle |

---

## 3. Independent Replay & Numerical Verification

Any experiment logged in the SQLite ledger can be replayed to verify deterministic numerical reproducibility within machine precision ($\varepsilon = 1 \times 10^{-4}$):

```bash
# Verify experiment reproducibility from CLI
.venv\Scripts\python -c "
from core.kronos.research.reproducibility import ReproducibilityReplayEngine
engine = ReproducibilityReplayEngine()
verified, diffs = engine.verify_experiment_reproducibility('K9_EXP_CONFIRMATORY_BTC15M_001')
print(f'Experiment Verified: {verified}')
"
```
