# Trading Concept & Strategy Repository Forensic Audit

**Audit Date:** 2026-10-13  
**Branch / Commit Audited:** `main` (`e11251b`)  
**Governance Lock Status:** `REAL_CAPITAL_ENABLED = False` (`VERIFIED`), Milestone 18 Certified Surface (`14/14` files intact, SHA-256 `2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b` `VERIFIED`).

---

## 1. Executive Summary & Architectural Reality

A forensic inspection of the CBT / SKY repository reveals a **dual-stack quantitative architecture** that evolved across two distinct engineering generations:

1. **Stack 1 — The Empirical CLI / Research Engine (`engine/`, `data/`, `brain/`, `research/`, `sky_agent/`):**
   - Built around deterministic bar-by-bar candle slicing (`engine/signal_engine.py::analyze_frame_at`), rule-based conditional `Plan` generation (`engine/rules.py::build_plans`), historical trade grading (`data/backtester.py::run_backtest`), 3-tier execution friction modeling (`data/costs.py::calculate_trade_cost`), and walk-forward validation (`data/validation.py`, `engine/edge_validation.py`).
   - Contains the real historical experiment trail documented in `docs/REAL_DATA_RUN_2026-08-14.md`, `docs/PATH_TO_REAL_MONEY.md`, `docs/HANDOVER_2026-08-15_P12_5.md`, and `docs/HANDOVER_2026-08-15_P12_6.md`.
2. **Stack 2 — The FastAPI v4.0.0 Institutional Core (`app.py`, `core/`):**
   - Powers the production FastAPI server, React/TypeScript terminal (`src/`), Milestone 18 multi-venue execution safety boundary (`core/execution/`), SKY Intelligence 17-module pipeline (`core/sky_intelligence/`), Autonomous Quant Strategist (`core/autonomous_quant_strategist.py`, `core/strategy_league.py`), Autonomous Research Engine (`core/autonomous_research/`), Knowledge OS (`core/knowledge_os/`), Kronos probabilistic forecasting (`core/kronos/`), and Mastermind Arbiter (`core/mastermind/`).

> [!IMPORTANT]
> **Critical Forensic Finding:** While both stacks contain sophisticated structural components, **no unified, machine-readable 60-concept Trading Concept Registry or fair cross-family baseline evaluator previously connected them**. Furthermore, `core/sky_intelligence/setup_engine.py` contains hardcoded prior expectancy figures (`0.38R`, `0.42R`, `0.35R`, `0.31R`, `0.29R`) and sample sizes (`4218`, `2890`, `3450`, `1920`, `2640`) that are static constants rather than dynamically computed outputs from `data/backtester.py`.

---

## 2. Traceable Component Mapping (Source Files, Behavior, Tests, Dependencies)

### 2.1 Stack 1: Empirical Backtesting, Signal Rules & Edge Validation (`engine/`, `data/`, `brain/`, `research/`)

| Component | Source File | Actual Behavior Verified in Code | Existing Tests | Dependencies | Status |
|:---|:---|:---|:---|:---|:---|
| **Point-in-Time Signal Engine** | `engine/signal_engine.py` | `analyze_frame(df)` and causal wrapper `analyze_frame_at(df, decision_idx)` which slices `df.iloc[:decision_idx + 1]` before computing indicators, regime, structure, volume, patterns, confluence, and plans. | `tests/test_no_lookahead.py` | `engine.indicators`, `engine.structure`, `engine.volume`, `engine.patterns`, `engine.regime`, `engine.confluence`, `engine.rules` | `VERIFIED` |
| **Conditional Plan Builder** | `engine/rules.py` | `build_plans()` generates up to 6 plan families (10 directional plan types): `Immediate Buy/Sell`, `Buy/Sell Pullback`, `Breakout Buy/Sell`, `Sweep Reversal Buy/Sell`, and `FVG Retest Buy/Sell`. | `tests/test_no_lookahead.py` | `engine.confluence`, `engine.calibration_hook` | `VERIFIED` |
| **Technical Indicators** | `engine/indicators.py` | Computes EMA (9, 21, 50, 200), RSI (14), MACD, Bollinger Bands, ATR (14), ADX, Stochastic RSI, and VWAP. | `tests/test_no_lookahead.py` | `pandas`, `numpy` | `VERIFIED` |
| **SMC Structure Detector** | `engine/structure.py` | Computes swing highs/lows, BOS (`bos`), CHOCH (`choch`), liquidity sweeps (`sweep`), Fair Value Gaps (`fvg_bull`, `fvg_bear`), and Order Blocks (`ob_bull`, `ob_bear`). | `tests/test_no_lookahead.py` | `pandas`, `numpy` | `VERIFIED` |
| **Regime Classifier (Legacy)** | `engine/regime.py` | Classifies bars into `trending_up`, `trending_down`, `ranging`, `volatile`, or `compressed` using ADX, ATR ratio, and EMA alignment. | `tests/test_no_lookahead.py` | `pandas`, `numpy` | `VERIFIED` |
| **Walk-Forward Backtester** | `data/backtester.py` | `run_backtest()` steps through OHLCV history at `step` intervals, grades triggered vs expired conditional plans over `horizon` bars (`_evaluate`), enforces pessimistic same-bar SL/TP tie-breaking (`ambiguous_same_bar_exit_lost = -1.0R`), and computes net R via `data/costs.py`. | `tests/test_no_lookahead.py`, `tests/test_ExecutionEngine.py` | `engine.signal_engine`, `data.costs`, `data.provenance` | `VERIFIED` |
| **3-Tier Execution Friction** | `data/costs.py` | `calculate_trade_cost()` models round-trip taker/maker fee bps, half-spread bps, ATR-scaled slippage bps, and holding-period funding bps across `optimistic`, `realistic`, and `punitive` models. | `tests/test_ExecutionEngine.py` | Standard library | `VERIFIED` |
| **Edge Validation Gate** | `engine/edge_validation.py` | `edge_verdict()` requires minimum trades (`min_trades=200`), positive net expectancy, `profit_factor >= 1.15`, `max_drawdown_r <= 25.0`, Monte Carlo 95th percentile DD (`monte_carlo_decisive`), and positive walk-forward OOS expectancy. | `tests/test_pipeline_integration.py` | `data.backtester`, `data.scorecard`, `data.validation` | `VERIFIED` |
| **Provenance & Real-Data Gate** | `data/provenance.py` | `check_manifest_for_Side(path, real_only=True)` blocks synthetic datasets (`conftest.py::make_ohlcv`) from being used when `--real-data-only` is active; verifies SHA-256 dataset digests. | `tests/test_pipeline_integration.py` | `hashlib`, `json` | `VERIFIED` |
| **Experiment & Feature Registries** | `research/experiment_registry.py`, `research/feature_registry.py`, `research/strategy_selection_guard.py` | Logs experiment records to `data/experiment_store.db`, validates `v2.1.0` 12-layer state vectors, and computes Bailey & López de Prado Deflated Sharpe Ratio (DSR). | `tests/test_research_firewall.py` | `core.database`, `scipy`, `numpy` | `VERIFIED` |

---

### 2.2 Stack 2: FastAPI v4.0.0 Core (`core/`) — The 23-Module & Subsystem Inventory

In the FastAPI `core/` architecture, intelligence is distributed across **17 modules in `core/sky_intelligence/`** plus **6 core research/forecasting/arbitration subsystems** (totaling the 23-module institutional intelligence inventory):

1. `core/sky_intelligence/market_regime.py` — `MarketRegimeEngine`: 7-state regime classifier (`TRENDING_UP`, `TRENDING_DOWN`, `RANGE_BOUND`, `VOLATILITY_EXPANSION`, `VOLATILITY_COMPRESSION`, `DELEVERAGING_PANIC`, `CHOP_NO_TRADE`) using efficiency ratio, ADX proxy, ATR ratio, and BB width.
2. `core/sky_intelligence/multi_timeframe.py` — `MultiTimeframeEngine`: HTF/MTF/LTF structural alignment and conflict scoring (`veto_counter_trend`).
3. `core/sky_intelligence/market_structure.py` — `MarketStructureEngine`: Verified swing points ($N$-bar causal fractal lag), BOS, MSS/CHoCH, and dealing range premium/discount zones.
4. `core/sky_intelligence/liquidity_engine.py` — `LiquidityEngine`: Equal highs/lows (EQH/EQL), session highs/lows, and sweep-and-reclaim quality scoring.
5. `core/sky_intelligence/fvg_engine.py` — `FVGEngine`: 3-candle Fair Value Gap detection, ATR-normalized size, and mitigation tracking (`UNMITIGATED`, `PARTIALLY_MITIGATED`, `FULLY_MITIGATED`).
6. `core/sky_intelligence/order_block_engine.py` — `OrderBlockEngine`: Institutional Order Block and Breaker Block identification with displacement validation.
7. `core/sky_intelligence/displacement_engine.py` — `DisplacementEngine`: Body-to-range ratio, ATR multiple, and volume-expansion impulse scoring.
8. `core/sky_intelligence/volume_engine.py` — `VolumeMicrostructureEngine`: RVOL, effort-vs-result absorption, and directional delta proxy.
9. `core/sky_intelligence/vwap_engine.py` — `VWAPEngine`: Session VWAP, $\pm 1\sigma / 2\sigma / 3\sigma$ standard deviation bands, and acceptance/reclaim state.
10. `core/sky_intelligence/volatility_engine.py` — `VolatilityEngine`: ATR percent, Bollinger/Keltner squeeze detection, and dynamic stop/target multipliers.
11. `core/sky_intelligence/derivatives_intelligence.py` — `DerivativesIntelligenceEngine`: Funding rate Z-score, Open Interest delta regime (`NEW_LONGS`, `SHORT_COVERING`, etc.), and crowded-positioning veto.
12. `core/sky_intelligence/setup_engine.py` — `SetupQualificationEngine`: Evaluates 5 named setups (`SETUP_A_SWEEP_MSS`, `SETUP_B_PULLBACK_FVG`, `SETUP_C_BREAKOUT_EXPANSION`, `SETUP_D_RANGE_SWEEP_RECLAIM`, `SETUP_E_VWAP_RECLAIM`). **Defect identified:** Hardcodes `historical_expectancy_r`, `historical_win_rate`, and `historical_sample_size`.
13. `core/sky_intelligence/expectancy_engine.py` — `ExpectancyCalibrationEngine`: Computes Bayesian shrinkage between prior expectancy and empirical trade ledger rows; applies Half-Kelly sizing (`0.25%` to `1.00%` risk).
14. `core/sky_intelligence/ablation_framework.py` — `AblationStudyFramework`: Evaluates marginal expectancy contribution of individual signal modules.
15. `core/sky_intelligence/orchestrator.py` — `SkyIntelligenceOrchestrator`: Master pipeline combining modules 1–13 into `SkyDecisionPacket`.
16. `core/sky_intelligence/types.py` — Strongly typed dataclasses and enums for SKY Intelligence packets.
17. `core/sky_intelligence/__init__.py` — Package exports.
18. `core/autonomous_quant_strategist.py` & `core/strategy_league.py` — 4-tier quarantine league (`SANDBOX_CANDIDATE` $\to$ `VALIDATION_LEAGUE` $\to$ `PAPER_SHADOW_LEAGUE` $\to$ `ELITE_ALLOCATION_POOL`) with CPCV (`core/walk_forward_cpcv.py`) and DSR (`core/statistical_defense.py`).
19. `core/autonomous_research/pipeline.py` — 6-stage autonomous research pipeline (Ingestion $\to$ Extraction $\to$ Hypothesis $\to$ Priority $\to$ Empirical Test $\to$ Promotion) backed by `core/autonomous_research/storage/db.py` (`data/autonomous_research.db`).
20. `core/knowledge_os/` — Epistemic knowledge base (`research_wikipedia.py`, `project_brain.py`, `human_brain.py`, `claim_verifier.py`, `strategy_bridge.py`).
21. `core/kronos/probability_engine.py` & `core/kronos/research/baseline_registry.py` — Probabilistic OHLCV return distribution forecaster + 4 statistical baselines (`M_RW`, `M_CLIM`, `M_MOM`, `M_AR1`) with Brier skill score and Platt calibration.
22. `core/mastermind/mastermind_arbiter.py` — Specialist consensus and structural veto arbiter (`RegimeSpecialist`, `StructureSpecialist`, `DerivativesSpecialist`, `MicrostructureSpecialist`, `StatisticalBaselineSpecialist`).
23. `core/execution/` & `core/risk_engine/` — Milestone 18 certified execution isolation (`live_router.py`, `smart_order_router.py`, `reconciliation_ledger.py`, `kill_switch.py`, `almgren_chriss.py`) locked behind `REAL_CAPITAL_ENABLED = False`.

---

## 3. Forensic Audit of Historical CBT / SKY Setups & Recorded Leads (Phase 7)

### 3.1 Audit of Recorded Historical Figures

The prompt requires a forensic verification of the previously recorded figures (`Buy Pullback: +0.657R`, `Sell Pullback: +0.573R`, `Sweep Reversal Buy: +0.017R`, `Sweep Reversal Sell: -0.074R`, `Breakout Buy`, `FVG Retest`, and Kronos forecasts).

Tracing the git commit history and research run logs (`docs/HANDOVER_2026-08-15_P12_5.md`, `docs/HANDOVER_2026-08-15_P12_6.md`, `docs/REAL_DATA_RUN_2026-08-14.md`, and `docs/PATH_TO_REAL_MONEY.md`) establishes the exact provenance of these numbers:

| Setup / Concept | Recorded Synthetic Figure (P12.5) | Real Binance BTCUSDT 15m Figure (P12.6 / 2026-08-14) | Exact Provenance & Forensic Diagnosis | Current Verdict |
|:---|:---|:---|:---|:---|
| **Buy Pullback** (`engine/rules.py:L164-205`) | `+0.657R` (P12.5 synthetic) | `+1.077R gross` (`n=13`, 1,000-bar 24h horizon); `-0.413R net` on 1h horizon | In P12.5, evaluated on `tests/conftest.py::make_ohlcv()` (seeded Gaussian random walk) with `step=3`, `horizon=96` (32x overlapping windows). On real BTCUSDT 15m (`horizon=96`), showed `+1.077R gross` across only 13 overlapping plans ($\approx 2\text{--}3$ independent events). On the pre-registered 1h (`horizon=4`) primary run, lost `-0.413R net`. | `NEEDS_MORE_DATA` (Promising 24h hypothesis, unvalidated $N_{\text{eff}}$) |
| **Sell Pullback** (`engine/rules.py:L207-250`) | `+0.573R` (P12.5 synthetic) | `+1.158R gross / +0.974R net` (`n=19`, 1,000-bar 24h horizon); `-0.395R net` on 1h horizon | Same P12.5 synthetic provenance (`make_ohlcv` random walk + 32x overlap). On real BTCUSDT 15m (`horizon=96`), produced `+0.974R net` on 19 overlapping plans during a bearish sub-window, but failed on the 484-day 1h primary horizon (`-0.395R net`). | `NEEDS_MORE_DATA` (Requires non-overlapping multi-regime OOS test) |
| **Sweep Reversal Buy** (`engine/rules.py:L319-348`) | `+0.017R` (P12.5 synthetic) | `+0.048R gross / -0.448R net` (`n=42`, 24h horizon); `-0.512R net` on 1h horizon | Near-zero gross expectancy (`+0.017R` synthetic, `+0.048R` real gross) collapses to `-0.448R net` once realistic fees, half-spread, and slippage (`data/costs.py`) are deducted. High trigger rate with tight stops suffers severe adverse selection. | `QUARANTINED` (Negative net expectancy after realistic costs) |
| **Sweep Reversal Sell** (`engine/rules.py:L288-318`) | `-0.074R` (P12.5 synthetic) | `-0.112R gross / -0.584R net` | Consistently negative both gross and net across synthetic and real BTCUSDT datasets. Single-bar wick detection without L2 absorption or HTF displacement fades strong breakouts prematurely. | `REJECTED` (Negative gross and net expectancy) |
| **Breakout Buy** (`engine/rules.py:L253-285`) | `+0.180R` (pre-P12.5 optimistic tie-break) | `-0.630R gross / -0.904R net` (`PF=0.225`, `n=27`) | Consistently the worst-performing setup on real BTCUSDT 15m data (`PF=0.225`). Entering on a close near an unconfirmed swing high (`price > swing_high * 0.985`) systematically buys local exhaustion tops and suffers high taker slippage. | `REJECTED` (Severe negative expectancy & PF 0.225 on real data) |
| **FVG Retest Buy / Sell** (`engine/rules.py:L351-404`) | Not separated in P11 | `0` to `<5` triggers in 1,000-bar real sample; uncalibrated | Rule requires `fvg_level < price` at exact bar evaluation (`engine/structure.py` only looks at the single most recent 3-bar gap rather than maintaining an unmitigated FVG zone ledger). Consequently, almost never triggers in `engine/rules.py`, while `core/sky_intelligence/setup_engine.py` (`SETUP_B_PULLBACK_FVG`) hardcodes `0.42R` (`n=2890`) without backtest backing. | `NEEDS_MORE_DATA` (Requires unmitigated zone persistence & fair backtest) |
| **Kronos Probabilistic Forecast** (`core/kronos/probability_engine.py`) | N/A | Brier skill evaluated vs `M_RW`, `M_CLIM`, `M_MOM`, `M_AR1` | `core/kronos/probability_engine.py` is currently a deterministic heuristic regime-conditioned sampler (`numpy.random.default_rng`), **not** a trained neural foundation model weight checkpoint. Properly isolated behind `forecast_only_cannot_execute=True`, with baselines in `core/kronos/research/baseline_registry.py`. | `SPECIFIED` (Valid probabilistic baseline harness; must never bypass risk gates) |

---

### 3.2 Four Structural Flaws Identified in Historical Runs

1. **Synthetic Data Contamination (Pre-P12.6):** Runs prior to `2026-08-14` executed on `tests/conftest.py::make_ohlcv()` (a seeded Gaussian random walk with injected drift) where positive expectancy was an artifact of synthetic drift and an optimistic same-bar TP/SL tie-break bug (`+2.0R` instead of `-1.0R`, fixed in P12.5).
2. **Overlapping Evaluation Horizon Inflation:** Running `data/backtester.py` with `step=3` and `horizon=96` (24 hours on 15m bars) evaluates the same price move up to $96 / 3 = 32$ times. A reported sample of $n = 32$ plans in a persistent trend represents $N_{\text{eff}} \approx 1\text{--}3$ independent trades, inflating $t$-statistics by up to $\sqrt{32} \approx 5.6\times$.
3. **Horizon Mismatch (1h vs 24h):** On real Binance `BTCUSDT` 15m data (`484` days, `2025-01-01` to `2026-04-29`), the sealed 1-hour horizon (`horizon=4`) failed every single walk-forward window (`train -0.452R`, `val -0.251R`, `oos -0.101R`, `recent -0.429R`) because 15m structural setups cannot overcome round-trip taker fees + slippage + spread (`~15–25 bps`) within 4 bars.
4. **Hardcoded Unverified Priors in `core/sky_intelligence/setup_engine.py`:** Lines `118–120`, `184–186`, `245–247`, `306–308`, and `368–370` of `core/sky_intelligence/setup_engine.py` assign fabricated prior sample sizes (`4218`, `2890`, `3450`, `1920`, `2640`) and expectancies (`0.38R` to `0.29R`) to `SETUP_A` through `SETUP_E`. These priors feed `ExpectancyCalibrationEngine` with `prior_weight = 50.0`, dominating real trade feedback until 50+ live/paper trades accumulate.

---

## 4. Audit Conclusions & Remediation Mandate

1. **Quarantine Hardcoded Priors:** All concepts in the new Trading Concept Registry must start at honest, evidence-backed lifecycle states (`RESEARCH`, `SPECIFIED`, `IMPLEMENTED`, `BACKTESTED`, `QUARANTINED`, `REJECTED`, or `NEEDS_MORE_DATA`) — never `PAPER_QUALIFIED` or `PAPER_VALIDATED` without passing strict out-of-sample, cost-adjusted, overlap-penalized ($N_{\text{eff}}$) gates.
2. **Overlap-Adjusted Effective Sample Size ($N_{\text{eff}}$):** Strategy evaluation must compute and enforce $N_{\text{eff}}$ accounting for trade holding-period overlap so overlapping signal bars cannot fake statistical significance.
3. **Preserve M18 Certification & Layer Firewalls:** All new concept registry and evaluation modules must live in `core/research/` (`LAYER_2_QUANT_SIMULATION`) and expose API endpoints via `core/strategist_routes.py` without touching any of the 14 Milestone 18 certified files.

