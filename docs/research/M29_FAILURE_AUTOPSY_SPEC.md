# Milestone 29: Failure Autopsy & Negative Knowledge Indexing Specification

## 1. The Value of Negative Knowledge

In quantitative finance, failed hypotheses represent critical institutional capital. Without durable, structured indexing of why a strategy failed, quantitative teams suffer from the "Infinite Loop of Naive Discovery": rediscovering the same falsified concepts every 6 months under new names.

Milestone 29 formalizes negative knowledge capture through the **Failure Autopsy Compiler (`FailureAutopsyCompiler`)** and the **Causal Failure Autopsy (`CausalFailureAutopsy`)**, permanently recorded in `brain_memory.db`.

---

## 2. Structured Failure Categories (`CausalFailureCategory`)

Every falsified or invalidated hypothesis is classified into a precise structural category:

| Category | Description | Primary Diagnostic Trigger |
|:---|:---|:---|
| `COST_FRAGILITY` | Alpha wiped out under realistic fees or slippage | Profitable at Base friction, negative at Conservative/Stress |
| `REGIME_CONFINEMENT` | Alpha confined exclusively to one macro regime | Passes in Bull/High-Vol only, fails in Bear/Ranging |
| `PARAMETER_CLIFF` | Narrow performance peak surrounded by losses | Performance drops $> 25\%$ under $\pm 10\%$ parameter shift |
| `EVENT_CLUSTERING_COLLAPSE` | Degrees of freedom artificially inflated by cluster | Observations collapse when grouped into independent shocks |
| `INSUFFICIENT_SAMPLE` | Too few events or episodes to establish significance | Events $< 30$ or Independent episodes $< 5$ |
| `LOOKAHEAD_CONTAMINATION` | Temporal leakage detected by causal firewall | Feature accesses $t_k > t_i$ or negative time delta |
| `EMPIRICALLY_FALSIFIED` | Negative net expectancy or negative excess alpha | Benchmark Alpha $\le 0$ or Negative total PnL |
| `MULTIPLE_TESTING_EXHAUSTION` | High nominal Sharpe collapses under trial penalty | Bailey DSR $< 0.95$ when adjusted for $N$ trials |

---

## 3. Autopsy Schema & Persistence (`failure_memory` table)

Each autopsy record captures granular forensic evidence:
```python
@dataclass(frozen=True)
class CausalFailureAutopsy:
    autopsy_id: str
    hypothesis_id: str
    contract_id: str
    failure_category: CausalFailureCategory
    root_cause_narrative: str
    observed_metrics: Dict[str, float]
    failing_thresholds: Dict[str, float]
    reusable_lessons_learned: List[str]
    friction_sensitivity: Dict[str, float]
    parameter_fragility_curve: Dict[str, float]
    timestamp: datetime
    execution_authority: str = "NON_EXECUTABLE_RESEARCH_HYPOTHESIS"
    real_capital_enabled: bool = False
```

### 3.1 SQLite Ledger Schema
The autopsies are committed to SQLite table `failure_memory` with indexing on `category`, `hypothesis_id`, and `created_at`:
```sql
CREATE TABLE IF NOT EXISTS failure_memory (
    autopsy_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    category TEXT NOT NULL,
    narrative TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    thresholds_json TEXT NOT NULL,
    lessons_json TEXT NOT NULL,
    friction_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    execution_authority TEXT NOT NULL,
    real_capital_enabled INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fail_cat ON failure_memory(category);
CREATE INDEX IF NOT EXISTS idx_fail_hyp ON failure_memory(hypothesis_id);
```

---

## 4. Upstream Feedback into Hypothesis Synthesizer

When Milestone 28's `CausalSynthesizer` proposes new candidate hypotheses:
1. It queries `failure_memory` for prior mechanisms matching the candidate's family or event triggers.
2. If a structurally identical hypothesis was previously logged with `COST_FRAGILITY` or `REGIME_CONFINEMENT`, the candidate is immediately filtered or pruned before wasting replay computation.
3. This creates a closed-loop empirical learning flywheel where every failure immunizes the system against future iterations of the same mistake.
