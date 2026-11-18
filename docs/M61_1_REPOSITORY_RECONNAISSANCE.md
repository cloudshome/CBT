# SKY / CBT — Milestone 61.1 Repository Reconnaissance
## Comprehensive Forensic Mapping of the Autonomous Trading Architecture

- **Date:** 2026-11-18
- **Current HEAD Commit:** `35a3c310c85c2c4bf190eec26f30d0615555e625` (`main`)
- **Remote Synchronization:** Up to date with `origin/main` (`Azimshawon/SKY.git`) and `cloudshome/main` (`cloudshome/CBT.git`)
- **Working Tree:** 100% Clean
- **Operating Mode:** READ-ONLY FORENSICS → ROOT-CAUSE PROOF → AUTHORIZED MINIMAL REPAIR

---

## 1. M18 PROTECTED-FILE INVENTORY & BASELINE
- **Certified Commit:** `c9cc1cad780453b81032f6b1b1b81117d41c060f`
- **Certified Test Identity SHA-256:** `2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b`
- **Certified Gates:** 14 Gates / 149 Tests (100% Green, re-validated in M59/M60)
- **14 Certified Files:**
  1. `app.py`
  2. `core/database.py`
  3. `core/execution/almgren_chriss.py`
  4. `core/execution/connectors/base.py`
  5. `core/execution/connectors/binance_connector.py`
  6. `core/execution/connectors/bybit_connector.py`
  7. `core/execution/idempotency.py`
  8. `core/execution/kill_switch.py`
  9. `core/execution/live_router.py`
  10. `core/execution/reconciliation_ledger.py`
  11. `core/execution/smart_order_router.py`
  12. `tests/test_milestone18_boss_adversarial.py`
  13. `tests/test_milestone18_final_certification.py`
  14. `tests/test_milestone18_sor_and_slicing.py`

---

## 2. COMPONENT RECONNAISSANCE & CODE MAPPING

### A. Autonomous Trader (`core/autonomous_trader.py`)
- **Lines:** 1,094 lines.
- **Primary Loop:** `AutonomousTrader.scan_and_execute_cycle()` (lines 169–838).
- **Signal Source:** Calls `sky_orchestrator.analyze_market(symbol=sym, timeframe=tf_scan, ...)` (lines 240–246).
- **Execution Target:** Creates `TradeProposal` and delegates to `mind.evaluate_and_route(proposal)` (lines 728–747).
- **Evidence Observation [OBSERVED]:** `AutonomousTrader` does NOT import or call `engine.signal_engine` or `engine.rules.build_plans`.

### B. SKY Intelligence Orchestrator (`core/sky_intelligence/orchestrator.py`)
- **Lines:** 417 lines.
- **Key Methods:**
  - `get_bayesian_setup_stats()` (lines 46–110): Queries `shadow_positions` where `opened_at >= 1793469018542` (2026-10-31 UTC).
  - `analyze_market()` (lines 111–413): Runs 12-stage quantitative evaluation, calculates `p_effective`, `r_win_hat`, `c_friction_r`, `net_ev = (p_effective * r_win_hat) - ((1.0 - p_effective) * 1.0) - c_friction_r`.
  - Hurdle: `risk_passed = net_ev >= 0.25` (line 358).
- **Evidence Observation [OBSERVED]:** With 0 closed trades post-epoch, prior forces $p = 0.50, R = 1.45$. Even with high confluence (82), $p_{eff} = 0.528$, yielding $\text{net\_ev} \approx 0.1336R < 0.25R$. Fails closed to `NO_TRADE` unconditionally.

### C. Setup Engine (`core/sky_intelligence/setup_engine.py`)
- **Lines:** 1,084 lines.
- **Key Setups:**
  - `_evaluate_setup_a()`: Range sweep and reclaim (lines 350–450).
  - `_evaluate_setup_b()`: Trend continuation into FVG (lines 453–624).
    - Line 483: `htf_aligned = ("BULL" in mtf.htf_4h_trend and is_bull) or ("BEAR" in mtf.htf_4h_trend and not is_bull)`. Rejects `NEUTRAL` and `RANGING` 4h HTF states.
  - `_evaluate_setup_c()`: Breakout expansion (lines 626–715).
    - Line 703–705: Hardcoded `is_qualified = False` ("Breakouts on hourly candles falsified in Phase 4 multi-year audit").

### D. Central Trading Mind (`core/central_mind.py`)
- **Lines:** 892 lines.
- **Key Method:** `evaluate_and_route(proposal: TradeProposal) -> DecisionVerdict` (lines 415–770).
- **Invariants Checked:**
  - Invariant 2b (lines 439–456): String blacklist rejecting `"BREAKOUT BUY"`, `"SWEEP REVERSAL"`, `"SETUP_C_BREAKOUT"`, `"SMC_ORDER_BLOCK"`, `"SMC LIQUIDITY SWEEP"`.
  - Invariant 2f (lines 528–543): `qualification_mode = os.getenv("QUALIFICATION_MODE", "true").lower() in ("true", "1", "yes")`. Restricts symbols strictly to `{"BTCUSDT", "BTCUSD", "ETHUSDT", "ETHUSD"}`.
  - Line 761: `pos_id = portfolio_shadow.open_position(...)`.

### E. M57/M60 Certified Strategy Engine (`engine/signal_engine.py` & `engine/rules.py`)
- **`engine/rules.py`:** 434 lines.
  - `build_plans()`: Emits `Plan` objects: `"Immediate Buy/Sell"`, `"Buy/Sell Pullback"`, `"Breakout Buy"`, `"Sweep Reversal Sell/Buy"`, `"FVG Retest Buy/Sell"`.
- **`data/backtester.py`:** 1,073 lines.
  - Evaluates `GradedPlan` outcomes under `EXECUTION_MODEL = "impact"`.
  - Produced the certified 848 Sealed OOS trades ($E[R] = +0.3594R, PF = 1.8067$).
