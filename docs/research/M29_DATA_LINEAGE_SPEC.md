# Milestone 29: Point-in-Time Data Lineage & Causal Integrity Specification

## 1. Principles of Causal Data Integrity

Modern quantitative machine learning and econometric replay frequently suffer from insidious lookahead biases:
1. **Reporting Delay Neglect:** Using economic numbers (CPI, Non-Farm Payrolls, FOMC statements) at their reference period rather than their official public release timestamp.
2. **Post-Hoc Data Revisions:** Backtesting against revised historical series (e.g. GDP revised months later) that were unavailable to a decision-maker at trading time $t$.
3. **Bar Timestamp Confusion:** Using bar close price as though it were available at bar open, or executing on the same tick that formed a breakout.
4. **Information Leakage Across Partitions:** Standard k-fold cross-validation leaking serial correlation and regime structures across time.

Milestone 29 implements deterministic, point-in-time causal data lineage via the **Dataset Manifest (`DatasetManifest`)** and **Causal Replay Engine (`CausalReplayEngine`)**.

---

## 2. Point-in-Time Dataset Manifest Architecture

### 2.1 Schema & Immutability
Each dataset utilized in empirical replay must be cataloged in a `DatasetManifest`:
- `dataset_id`: Unique identifier (e.g. `ds-binance-btc-1m-2023-2024`).
- `asset`: Trading instrument (e.g. `BTC/USDT`).
- `start_time`, `end_time`: Bounding timestamps (UTC).
- `bar_count`: Exact row count.
- `content_sha256`: Cryptographic checksum of normalized bar data.
- `effective_availability_time`: Point-in-time timestamp after which the data may be observed.
- `is_revised_series`: Boolean flag indicating whether revisions exist.
- `revision_history`: List of point-in-time snapshots with publication timestamps.

### 2.2 Strict Temporal Causality Assertions
The dataset manifest enforces strict point-in-time assertions:
$$\forall \text{ observation } i: \quad t_{\text{decision}} \ge t_{\text{effective\_available}}(i) > t_{\text{event}}(i)$$

```python
def assert_causal_soundness(self, query_time: datetime) -> None:
    """Enforces that no data observed after query_time is exposed to the engine."""
    if self.effective_availability_time > query_time:
        raise CausalLeakageDetectedError(
            f"DATA LEAKAGE DETECTED: Dataset {self.dataset_id} availability time "
            f"({self.effective_availability_time.isoformat()}) exceeds query time ({query_time.isoformat()}). "
            f"Temporal margin violation: {(self.effective_availability_time - query_time).total_seconds()}s."
        )
```

---

## 3. Causal Replay Engine Execution Flow

The `CausalReplayEngine` steps through market history strictly bar-by-bar:
```
[Historical Data Storage]
           │
           ▼
[DatasetManifest Verification (SHA-256 + Time Cutoff)]
           │
           ▼
[Bar-by-Bar Replay Loop: t = t_0, t_1, ... t_T]
    ├── 1. Ingest candle at t_i (Close is finalized only at t_i)
    ├── 2. Verify Causal Firewall (assert t_i <= t_wall)
    ├── 3. Evaluate Hypothesis Mechanism on [0 ... t_i] only
    ├── 4. Generate Signal S_i
    ├── 5. Apply Realistic Friction Engine (t_i+1 open / spread / slippage)
    └── 6. Record Fill & Balance State
           │
           ▼
[Bit-Level Deterministic Output Signature (SHA-256)]
```

### 3.1 Zero Lookahead Assertion
During the step loop, any attempt by a feature extractor or indicator to access index $k > i$ or timestamp $t_k > t_i$ raises `CausalLeakageDetectedError`, terminating replay and creating a failure autopsy.

### 3.2 Deterministic Output Signatures
To guarantee scientific reproducibility across different operating environments, the replay engine computes an `output_signature_sha256` encompassing:
- Sorted list of execution fills (timestamps, sizes, prices, fees).
- Sorted equity curve series.
- Final gross and net PnL.

Identical inputs (contract + dataset manifest) are guaranteed to produce bit-for-bit identical output signatures.
