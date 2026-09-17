# MASTER ANTIGRAVITY DIRECTIVE

## Milestone K9 — Kronos Predictive Validity & Incremental Information Research

You are operating as the **Principal Quantitative Research Engineer, Statistical Auditor, ML Systems Architect, and Production Code Reviewer** for SKY / Crypto Trading Brain (CTB).

Your task is NOT to blindly implement the supplied K9 plan.

Your task is to:

1. Audit the existing K8 implementation.
2. Identify statistical, causal, data, architectural, and reproducibility weaknesses.
3. Harden the K9 methodology before implementation.
4. Implement only scientifically defensible components.
5. Produce reproducible research artifacts.
6. Preserve every existing execution and risk-control invariant.
7. Never convert Kronos research output into trading authorization.

---

# 0. PRIMARY SCIENTIFIC QUESTION

K9 must answer:

> Does Kronos provide reproducible, statistically defensible, out-of-sample incremental predictive information beyond SKY's existing technical/SMC/order-flow information and naive statistical baselines?

The answer must be determined from:

* strictly chronological out-of-sample evaluation,
* point-in-time feature construction,
* purge and embargo,
* calibration analysis,
* baseline comparison,
* incremental-information tests,
* regime stability,
* microstructure ablation,
* multiple-testing controls,
* realistic economic-friction diagnostics.

Do NOT equate:

`statistically significant coefficient`

with:

`alpha`

and do NOT equate:

`forecast skill`

with:

`tradable strategy`.

K9 is a research-validity milestone.

---

# 1. NON-NEGOTIABLE CONSTITUTIONAL BOUNDARY

K9 is research-only.

Absolutely forbidden:

* live order placement,
* paper order placement,
* strategy execution,
* position creation,
* capital allocation,
* risk sizing,
* kill-switch control,
* exchange execution,
* modification of M18 certified execution code,
* modification of M18 risk gates.

The only permitted downstream transition is:

K9 Research Result
→ StrategyGenome Research Loop

and NOT:

K9
→ Signal
→ Risk
→ Order.

Kronos remains informational.

---

# 2. FIRST ACTION: REPOSITORY FORENSIC AUDIT

Before creating or modifying files, inspect:

* AGENTS.md
* .specify/memory/constitution.md
* docs/QUANT_RESEARCH_PROTOCOL.md
* existing K8 implementation
* model manifest
* provider abstraction
* feature schema
* causality validator
* forecast ledger
* calibration system
* Brier scoring
* DomainAdapter
* Kronos API routes
* Autonomous Quant Strategist
* existing statistical validation infrastructure
* M18 certification files
* M18 verification scripts
* existing dataset/store architecture
* existing backtesting/friction infrastructure.

Determine the actual implementation contract.

Do not trust documentation over executable code.

Do not invent APIs, providers, model capabilities, model endpoints, or input formats.

Produce:

`docs/audits/K9_PRE_IMPLEMENTATION_AUDIT.md`

containing:

* current architecture,
* K8 assumptions,
* verified model interface,
* verified data availability,
* known limitations,
* statistical risks,
* M18 protected surface,
* proposed corrections.

STOP implementation if a fundamental K8 contract is ambiguous.

---

# 3. K9.1 — IMMUTABLE DATASET FREEZE

Create:

`core/kronos/research/dataset_freeze.py`

Canonical research universe:

* BTC/USDT
* ETH/USDT
* SOL/USDT

Primary timeframes:

* 15m
* 1h
* 4h

Requirements:

* strict chronological ordering,
* duplicate detection,
* missing-bar detection,
* timestamp normalization,
* timezone normalization,
* point-in-time validation,
* feature availability timestamps,
* source provenance,
* dataset version,
* source identifiers,
* SHA-256 hashes.

Manifest:

`data/research/datasets/manifest_k9.json`

Every dataset must have:

* dataset_id
* asset
* venue
* timeframe
* start
* end
* row_count
* schema_hash
* content_hash
* source
* generation_timestamp
* methodology_version.

Dataset mutation after freeze must be detected.

Never silently regenerate a frozen dataset.

---

# 4. POINT-IN-TIME ENFORCEMENT

Every feature must satisfy:

`feature_timestamp <= prediction_timestamp`

Every target must satisfy:

`target_timestamp > prediction_timestamp`

Explicitly validate:

* rolling windows,
* normalization,
* scaling,
* ATR,
* ADX,
* spread,
* depth,
* OFI,
* VPIN,
* resting walls,
* volume,
* session labels,
* calibration data,
* baseline training data.

No full-dataset normalization.

No future percentile thresholds.

No future regime labels.

No future model fitting.

Implement adversarial tests for each category.

---

# 5. K9.2 — PRIMARY WALK-FORWARD EVALUATION

Primary evaluation method:

**Chronological rolling walk-forward evaluation.**

Initial configuration:

```text
train_window = 180 days
evaluation_window = 30 days
step = 30 days
embargo = 2 × forecast_horizon
```

This is the PRIMARY pre-registered configuration.

Do not select the window because it produces the best result.

Implement sensitivity analysis separately.

Minimum sensitivity set:

```text
90/30/30
180/30/30
180/60/30
365/30/30
```

Every result must identify its exact configuration.

---

# 6. CPCV — SECONDARY ROBUSTNESS ANALYSIS

Implement CPCV separately from the primary rolling evaluation.

CPCV must include:

* purge,
* embargo,
* chronological target-boundary protection,
* overlap protection,
* deterministic fold generation,
* fold manifests.

CPCV must never be used selectively to report the most favorable result.

Store every fold result.

---

# 7. K9.3 — BASELINE TOURNAMENT

Evaluate Kronos against:

1. Climatology
2. Momentum/Persistence
3. AR(1)
4. Random-walk probability baseline

All models must receive:

* identical timestamps,
* identical target definitions,
* identical evaluation observations,
* identical train/test boundaries,
* identical horizon,
* identical missing-data rules.

Metrics:

* Brier Score
* Brier Skill Score
* Log Loss
* ROC-AUC where mathematically appropriate
* calibration error
* confidence intervals.

Never compare models evaluated on different samples.

---

# 8. PROBABILITY TARGET CONTRACT

Freeze the exact target definition.

For example:

`Y = 1 if forward_return(H) > threshold`

Define explicitly:

* H
* threshold
* return calculation
* price source
* timestamp convention
* handling of zero returns
* handling of missing targets.

Do not allow target definitions to vary between models.

Store target specification inside the experiment manifest.

---

# 9. K9.4 — INCREMENTAL INFORMATION

Separate two questions.

## A. Calibration validity

For probability forecasts evaluate:

`Y ~ α + βP`

Test:

`H0: α = 0`
`H0: β = 1`

using appropriate robust/HAC inference.

Report:

* α
* β
* standard errors
* confidence intervals
* joint calibration test
* sample size.

Do not blindly label this "Mincer-Zarnowitz" without documenting the binary-probability adaptation.

## B. Incremental predictive information

Compare:

`MODEL_0 = SKY baseline`

against:

`MODEL_1 = SKY baseline + Kronos`

using strictly out-of-sample predictions.

Evaluate:

* Brier improvement,
* log-loss improvement,
* likelihood improvement where appropriate,
* calibration improvement,
* residual diagnostics,
* incremental explanatory contribution.

Kronos must not be declared useful solely because its standalone score is positive.

The key question is:

> Does Kronos improve an already-existing SKY information set?

---

# 10. TIME-SERIES STATISTICAL INFERENCE

Because observations may overlap across forecast horizons:

* account for serial correlation,
* use HAC/Newey-West where appropriate,
* document lag selection,
* do not assume iid observations,
* do not use random train/test splitting.

For non-nested model comparison:

Do not blindly implement a textbook Vuong test.

First determine whether its assumptions hold for:

* overlapping financial labels,
* dependent observations,
* probability forecasts,
* rolling estimation.

If not, implement an appropriate dependent-data alternative and document the reason.

---

# 11. MULTIPLE TESTING FIREWALL

K9 contains many possible comparisons:

* assets,
* timeframes,
* regimes,
* baselines,
* ablations,
* horizons,
* window configurations.

Therefore:

1. Define primary hypotheses before evaluation.
2. Define secondary hypotheses separately.
3. Record every tested configuration.
4. Never hide failed experiments.
5. Apply appropriate multiple-testing controls.
6. Preserve the full experiment ledger.

The research system must make p-hacking difficult.

---

# 12. K9.5 — REGIME ANALYSIS

Implement four regime dimensions:

### Volatility

* ATR percentile
* High > 80th percentile
* Low < 20th percentile

### Trend

* ADX > 25
* ADX <= 25

### Liquidity

* spread
* depth
* liquidity concentration.

### Session

* Asia
* London
* New York
* London/NY overlap explicitly represented.

IMPORTANT:

ATR/ADX/liquidity percentiles must be calculated point-in-time.

Do not calculate percentile thresholds using the complete future dataset.

For each regime report:

* observations,
* Brier,
* BSS,
* Log Loss,
* calibration,
* confidence interval.

Never report a regime result without its sample count.

Do not create high-dimensional regime combinations unless minimum sample-size requirements are met.

---

# 13. K9.6 — MICROSTRUCTURE ABLATION

Implement the seven-way matrix:

A. Native OHLCV Kronos
B. Kronos + OFI
C. Kronos + VPIN
D. Kronos + Depth Imbalance
E. Kronos + Resting Wall
F. Kronos + all permitted microstructure features
G. Microstructure-only statistical model

CRITICAL:

Before implementation verify the ACTUAL Kronos input contract.

Do not falsely represent arbitrary microstructure features as native Kronos features.

If SKY's DomainAdapter is required:

label it explicitly:

`Native Kronos + SKY Domain Adapter`

Every variant must use:

* identical observations,
* identical targets,
* identical forecast horizon,
* identical evaluation windows.

Report:

* absolute performance,
* incremental improvement,
* confidence interval,
* sample count,
* statistical significance,
* feature availability,
* missing-data rate.

No feature may be credited with information that was actually introduced by changed sample selection.

---

# 14. MICROSTRUCTURE FEATURE PROVENANCE

For every feature:

```text
feature_name
source
venue
timestamp
lookback
calculation
availability_latency
missing_rate
normalization
point_in_time_status
```

Particular attention:

* OFI
* VPIN
* depth imbalance
* resting walls.

Resting-wall data must not use future order-book states.

If historical L3/MBO data is unavailable for a period, do not synthesize it.

---

# 15. K9.7 — ECONOMIC FRICTION DIAGNOSTIC

Implement:

```text
BASE
CONSERVATIVE
STRESS
```

but treat friction values as configurable research assumptions, not universal constants.

For every run record:

* fee,
* spread,
* slippage,
* adverse selection,
* venue,
* asset,
* timeframe,
* source/methodology.

If no empirical source exists, label the friction assumption:

`ASSUMED`

rather than:

`OBSERVED`.

---

# 16. ECONOMIC UTILITY MUST REMAIN SEPARATE

Do not calculate DSR/WRC on raw forecast probabilities.

If economic utility is tested, create a separate:

`Hypothetical Forecast Utility Adapter`

with a frozen, pre-registered mapping:

forecast
→ hypothetical exposure
→ fixed holding period
→ friction
→ return.

No optimization.

No threshold tuning after observing results.

Only then may K9 calculate strategy-like statistics such as:

* return,
* Sharpe,
* DSR,
* White's Reality Check.

Clearly label this:

`HYPOTHETICAL RESEARCH UTILITY`

not:

`TRADING STRATEGY`.

---

# 17. PROMOTION GATE

Create:

`core/kronos/research/promotion_gate.py`

Do NOT use a single metric as proof.

Generate a complete scorecard containing:

### Forecast validity

* Brier
* BSS
* Log Loss
* calibration
* confidence intervals.

### Incremental information

* SKY baseline
* SKY + Kronos
* incremental Brier
* incremental Log Loss
* statistical test
* effect size.

### Robustness

* walk-forward
* CPCV
* asset stability
* timeframe stability
* regime stability.

### Economic diagnostic

* Base
* Conservative
* Stress
* hypothetical utility
* DSR/WRC only when applicable.

---

# 18. RESEARCH STATES

Use:

`PROMOTE`
`QUARANTINE`
`REJECT`

but define them as RESEARCH GOVERNANCE STATES.

### PROMOTE

Only if all pre-registered primary conditions pass.

At minimum:

* positive incremental out-of-sample information,
* statistically defensible evidence,
* no material leakage,
* calibration acceptable,
* robustness acceptable,
* no dependence on one pathological subset,
* no unexplained sample-selection advantage.

### QUARANTINE

Use when:

* localized predictive skill exists,
* but robustness is insufficient,
* or performance is regime-dependent,
* or evidence is insufficient for broad promotion.

### REJECT

Use when:

* Kronos fails against appropriate baselines,
* incremental information is absent,
* results are unstable,
* leakage is detected,
* or evidence is not reproducible.

Do NOT define these states as trading recommendations.

---

# 19. STATISTICAL THRESHOLDS

The supplied thresholds:

```text
BSS > 0.02
t >= 2.0
DSR > 0.95
WRC p < 0.05
```

must be implemented only as:

`PRE-REGISTERED SKY RESEARCH THRESHOLDS`

not universal statistical laws.

Store:

```text
threshold_version
threshold_source
hypothesis_id
primary_or_secondary
```

Do not silently change thresholds after seeing results.

---

# 20. EXPERIMENT LEDGER

Create a durable research ledger.

Every experiment must record:

```text
experiment_id
dataset_id
dataset_hash
model_version
provider
model_manifest_hash
feature_schema_hash
target_definition_hash
validation_config_hash
friction_config_hash
random_seed
git_commit
timestamp
asset
venue
timeframe
horizon
regime_config
ablation_variant
metrics
statistical_results
status
```

This must make any published K9 result reproducible from the repository state.

---

# 21. API

Add only research read/audit endpoints:

`GET /api/kronos/research/tournament`

`GET /api/kronos/research/ablation`

`GET /api/kronos/research/regimes`

`GET /api/kronos/research/promotion-status`

Also expose:

* experiment ID,
* dataset hash,
* model version,
* evaluation period,
* sample count,
* confidence intervals,
* methodology version.

Never expose an endpoint that can convert K9 output into an order.

---

# 22. FRONTEND

Extend `KronosDomainDesk.tsx`.

Add:

## Research Validity

Display:

* baseline tournament,
* incremental information,
* calibration,
* ablation,
* regime analysis,
* economic utility diagnostic,
* research promotion state.

Every visualization must show:

* sample size,
* evaluation period,
* model version,
* dataset version,
* confidence interval where applicable.

Never show:

`BUY`
`SELL`
`LONG`
`SHORT`
`EXECUTE`

as a consequence of K9.

Use language:

`RESEARCH`
`FORECAST`
`EVIDENCE`
`CALIBRATION`
`INFORMATION GAIN`
`ROBUSTNESS`.

---

# 23. ADVERSARIAL TEST SUITE

Create:

`tests/test_kronos_k9_predictive_validity.py`

Minimum tests:

1. Dataset hash immutability.
2. Dataset manifest reproducibility.
3. Timestamp monotonicity.
4. Duplicate detection.
5. Future-feature rejection.
6. Future-normalization rejection.
7. Future-regime-threshold rejection.
8. Target-boundary correctness.
9. Walk-forward purge.
10. Walk-forward embargo.
11. CPCV purge.
12. CPCV embargo.
13. Identical samples across baseline models.
14. Baseline no-lookahead.
15. Probability-target correctness.
16. Calibration regression correctness.
17. HAC calculation correctness.
18. Incremental-model comparison.
19. Multiple-testing ledger.
20. Regime point-in-time calculation.
21. Session overlap correctness.
22. Minimum regime sample enforcement.
23. Ablation sample identity.
24. Feature provenance.
25. Microstructure missing-data handling.
26. Friction calculation.
27. Economic utility isolation.
28. DSR applicability guard.
29. WRC applicability guard.
30. Promotion gate determinism.
31. Experiment reproducibility.
32. Research-state determinism.
33. No execution imports.
34. No order-placement path.
35. M18 isolation.

Add additional adversarial tests wherever the audit identifies risk.

---

# 24. M18 FIREWALL

Before and after implementation:

```text
python scripts/verify_m18_certification.py
```

M18 certified files must remain untouched.

K9 must not:

* import execution modules,
* call order routers,
* call risk sizing,
* modify Half-Kelly logic,
* modify kill switches,
* modify execution permissions.

If any M18 certified file changes:

STOP.

Do not "fix" the conflict automatically.

Report it.

---

# 25. REPRODUCIBILITY REQUIREMENT

A K9 result is not certified unless another run can reproduce:

* dataset hash,
* experiment ID,
* model version,
* prediction sample,
* metrics,
* statistical tests,
* promotion state.

No hard-coded result values.

No simulated "PASS" artifacts.

No fabricated datasets.

No placeholder statistics.

No mock production claims.

---

# 26. FAILURE POLICY

If data is unavailable:

`INSUFFICIENT_DATA`

If historical microstructure is unavailable:

`FEATURE_UNAVAILABLE`

If statistical assumptions fail:

`STATISTICAL_INAPPLICABLE`

If calibration sample is insufficient:

`INSUFFICIENT_CALIBRATION_SAMPLE`

If leakage is detected:

`INVALID_EXPERIMENT`

Do NOT convert missing evidence into failure or success.

Do NOT manufacture evidence.

---

# 27. REQUIRED FINAL AUDIT

Run:

```text
.venv\Scripts\pytest tests/test_kronos_k9_predictive_validity.py -v
```

```text
.venv\Scripts\python scripts/verify_m18_certification.py
```

```text
.venv\Scriptsuff check core/kronos/ tests/
```

```text
.venv\Scripts\python scripts/system_preflight.py
```

```text
npm --prefix frontend run build
```

Also run the complete existing regression suite.

Record:

* exact test counts,
* failures,
* warnings,
* duration,
* git commit,
* dataset hashes,
* model hashes.

Never claim "production certified" merely because tests pass.

K9 certification means:

`IMPLEMENTATION + STATISTICAL VALIDITY + REPRODUCIBILITY + GOVERNANCE`

not merely:

`pytest PASS`.

---

# 28. REQUIRED DOCUMENTATION

Produce:

`docs/audits/K9_PRE_IMPLEMENTATION_AUDIT.md`

`docs/research/K9_METHODOLOGY.md`

`docs/research/K9_STATISTICAL_REPORT.md`

`docs/research/K9_DATASET_MANIFEST.md`

`docs/research/K9_EXPERIMENT_REGISTRY.md`

`docs/research/K9_PROMOTION_REPORT.md`

Every conclusion must distinguish:

* observed result,
* statistical inference,
* methodological assumption,
* research interpretation.

---

# 29. FINAL OUTPUT

At completion provide a concise executive report:

## K9 Implementation

PASS / FAIL

## Dataset Integrity

PASS / FAIL

## Leakage Audit

PASS / FAIL

## Walk-Forward

PASS / FAIL

## CPCV

PASS / FAIL

## Baseline Tournament

PASS / FAIL

## Incremental Information

PASS / FAIL

## Regime Stability

PASS / FAIL

## Ablation

PASS / FAIL

## Economic Utility Diagnostic

PASS / FAIL / NOT APPLICABLE

## Reproducibility

PASS / FAIL

## M18 Isolation

PASS / FAIL

## Research State

PROMOTE / QUARANTINE / REJECT / INSUFFICIENT_DATA

## Critical Findings

List only evidence-backed findings.

## Known Limitations

List every material limitation.

## Next Permitted Milestone

Only identify the next research milestone permitted by the evidence.

---

# FINAL DIRECTIVE

Do not optimize K9 for a favorable result.

Optimize K9 for discovering whether Kronos actually contains incremental information.

A negative result is scientifically valuable.

A weak result is scientifically valuable.

An unstable result is scientifically valuable.

A positive result is valuable only if it survives the complete validation framework.

The objective is not to prove Kronos works.

The objective is to determine whether the evidence supports the claim.

**Research first. Evidence first. Reproducibility first. Execution remains completely isolated.**
