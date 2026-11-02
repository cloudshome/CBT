# SKY / CRYPTO BRAIN TERMINAL (CBT)
## Master Milestone, Handover & Architectural Supersession Index

> **Document Identity:** `SKY-INDEX-2026-V1`  
> **Status:** AUTHORITATIVE ARCHIVAL MAP  
> **Authoritative Current Truth:**  
> 1. System Constitution: [`docs/SKY_CONSTITUTION.md`](SKY_CONSTITUTION.md)  
> 2. Operational Manual: [`AGENTS.md`](../AGENTS.md)  
> 3. Product Contract: [`docs/PRODUCT_CONTRACT.md`](PRODUCT_CONTRACT.md)  
> 4. Permanent Roadmap & Memory: [`docs/SYSTEM_MEMORY_AND_ROADMAP_2026.md`](SYSTEM_MEMORY_AND_ROADMAP_2026.md)  
> 5. Backend Route Matrix: [`docs/BACKEND_ROUTE_MATRIX.md`](BACKEND_ROUTE_MATRIX.md)  

---

## 1. Executive Purpose

Over the development history of the Crypto Brain Terminal (CBT / SKY), numerous handover and milestone progress logs were generated across iterative engineering cycles.

To resolve the documentation divergence and cognitive overload identified in **Priority 5** of the Project Inspection Report, this master index:
- Classifies which milestones are **Certified Active Ground Truth**.
- Formally archives historical session logs (`HANDOVER_2026-08-*`).
- Links every historical document to its current authoritative supersession.

> [!IMPORTANT]
> **Supersession Rule:** Any claim, file path, test count, or port assignment in a historical handover document is strictly superseded by the **Authoritative Current Truth** documents listed above.

---

## 2. Certified Active Milestones

| Milestone | Title & Domain | Certification Gate | Current Verified State | Authoritative Reference |
|:---:|:---|:---|:---:|---|
| **M18** | **Multi-Venue Smart Execution & Reconciliation** | 14 adversarial gates / 149 tests | **PRODUCTION PASS** | [`docs/certification/M18_CERTIFICATION_MANIFEST.md`](certification/M18_CERTIFICATION_MANIFEST.md) |
| **M35-R** | **Independent Release & Code Signing Audit** | 15 audit obligations (RFC-3161 timestamps) | **RELEASE CANDIDATE** | [`tests/execution/test_milestone35_r_independent_audit.py`](../tests/execution/test_milestone35_r_independent_audit.py) |
| **Route Contract** | **Backend Route Matrix & Proxy Parity** | 4 contract parity gates (Vite, Nginx, Caddy, FastAPI) | **PASS (100% PARITY)** | [`docs/BACKEND_ROUTE_MATRIX.md`](BACKEND_ROUTE_MATRIX.md) |
| **UI Stream** | **Zero-Shake WebSocket Heartbeat & Lifecycle** | Adaptive staleness watchdog & Vitest suite | **PASS** | [`frontend/src/test/WSStateMachine.test.ts`](../frontend/src/test/WSStateMachine.test.ts) |

---

## 3. Historical Handover Registry (August 2026 Archive)

All documents below represent point-in-time progress logs from August 2026. They are permanently retained for provenance and audit history, but their technical specifications are **SUPERSEDED**.

| Historical Document | Original Snapshot Date | Focus Area | Status | Superseded By |
|---|:---:|---|:---:|---|
| `docs/HANDOVER_2026-08-14.md` | 2026-08-14 | Phase 12 Architecture & Pipeline | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-14_P12_3_2.md` | 2026-08-14 | Phase 12.3.2 Microstructure | ARCHIVED | `core/microstructure_engine.py` |
| `docs/HANDOVER_2026-08-15_P12_3_3.md` | 2026-08-15 | Phase 12.3.3 Order Flow Integration | ARCHIVED | `core/orderbook_imbalance.py` |
| `docs/HANDOVER_2026-08-15_P12_4.md` | 2026-08-15 | Phase 12.4 Regime Transitions | ARCHIVED | `core/regime_transition.py` |
| `docs/HANDOVER_2026-08-15_P12_5.md` | 2026-08-15 | Phase 12.5 Causal Firewall | ARCHIVED | `core/causal_firewall.py` |
| `docs/HANDOVER_2026-08-15_P12_6.md` | 2026-08-15 | Phase 12.6 Empirical Ledger | ARCHIVED | `core/empirical_accumulator.py` |
| `docs/HANDOVER_2026-08-15_P12_8.md` | 2026-08-15 | Phase 12.8 Monte Carlo Stress | ARCHIVED | `core/monte_carlo_stress.py` |
| `docs/HANDOVER_2026-08-16_P12_14.md` | 2026-08-16 | Phase 12.14 Path Simulation | ARCHIVED | `core/path_simulator.py` |
| `docs/HANDOVER_2026-08-16_P12_15.md` | 2026-08-16 | Phase 12.15 Genetic Optimization | ARCHIVED | `core/genetic_optimizer.py` |
| `docs/HANDOVER_2026-08-16_P12_15_1.md` | 2026-08-16 | Phase 12.15.1 Genetic Optimization | ARCHIVED | `core/genetic_optimizer.py` |
| `docs/HANDOVER_2026-08-16_P12_16.md` | 2026-08-16 | Phase 12.16 Probability Calibrator | ARCHIVED | `core/probability_calibrator.py` |
| `docs/HANDOVER_2026-08-16_P12_17.md` | 2026-08-16 | Phase 12.17 Prediction Ladder | ARCHIVED | `core/prediction_ladder.py` |
| `docs/HANDOVER_2026-08-16_P12_18.md` | 2026-08-16 | Phase 12.18 Quant Mentor | ARCHIVED | `core/quant_mentor.py` |
| `docs/HANDOVER_2026-08-16_P13.md` | 2026-08-16 | Phase 13 Setup Engine | ARCHIVED | `core/sky_intelligence/setup_engine.py` |
| `docs/HANDOVER_2026-08-17_P18_2.md` | 2026-08-17 | Phase 18.2 Smart Order Router | ARCHIVED | `core/execution/smart_order_router.py` |
| `docs/HANDOVER_2026-08-17_P18_3.md` | 2026-08-17 | Phase 18.3 TWAP & Almgren-Chriss | ARCHIVED | `core/execution/almgren_chriss.py` |
| `docs/HANDOVER_2026-08-17_W1.md` | 2026-08-17 | Week 1 Execution Progress | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-17_W2.md` | 2026-08-17 | Week 2 Execution Progress | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-17_W2_part2.md` | 2026-08-17 | Week 2 Part 2 Execution | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-18_P18_4.md` | 2026-08-18 | Phase 18.4 Fill Reconciliation | ARCHIVED | `core/execution/reconciliation_ledger.py` |
| `docs/HANDOVER_2026-08-18_P19.md` | 2026-08-18 | Phase 19 Connectors | ARCHIVED | `core/execution/connectors/` |
| `docs/HANDOVER_2026-08-18_P20.md` | 2026-08-18 | Phase 20 Idempotency Locks | ARCHIVED | `core/execution/idempotency.py` |
| `docs/HANDOVER_2026-08-18_P21.md` | 2026-08-18 | Phase 21 Master Kill Switch | ARCHIVED | `core/execution/kill_switch.py` |
| `docs/HANDOVER_2026-08-18_P22_1.md` | 2026-08-18 | Phase 22.1 Risk Gate Integration | ARCHIVED | `core/portfolio_shadow.py` |
| `docs/HANDOVER_2026-08-18_P22_2.md` | 2026-08-18 | Phase 22.2 Sizing Limits | ARCHIVED | `core/half_kelly_sizer.py` |
| `docs/HANDOVER_2026-08-18_P22_3.md` | 2026-08-18 | Phase 22.3 Portfolio Limits | ARCHIVED | `core/portfolio_shadow.py` |
| `docs/HANDOVER_2026-08-19_W3.md` | 2026-08-19 | Week 3 Verification | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-19_W34.md` | 2026-08-19 | Week 34 Hardening | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-19_W35.md` | 2026-08-19 | Week 35 Verification | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-19_W36.md` | 2026-08-19 | Week 36 Release Audit Prep | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-19_W41.md` | 2026-08-19 | Week 41 Integration | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-19_W42.md` | 2026-08-19 | Week 42 Testing | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-19_W4_AGENT.md`| 2026-08-19 | Week 4 Autonomous Agent | ARCHIVED | `core/mastermind/sovereign_master_agent.py` |
| `docs/HANDOVER_2026-08-20_T2.md` | 2026-08-20 | Terminal Session 2 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-20_T3.md` | 2026-08-20 | Terminal Session 3 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-20_T4.md` | 2026-08-20 | Terminal Session 4 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-20_T4_part2.md`| 2026-08-20 | Terminal Session 4 Part 2 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-20_W35_part2.md`| 2026-08-20 | Week 35 Audit Part 2 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-20_v2.47.0.md`| 2026-08-20 | Release v2.47.0 Notes | ARCHIVED | `release/CODE_SIGNING_REPORT.json` |
| `docs/HANDOVER_2026-08-20_v2.48.1.md`| 2026-08-20 | Release v2.48.1 Notes | ARCHIVED | `release/CODE_SIGNING_REPORT.json` |
| `docs/HANDOVER_2026-08-20_v2.49.0.md`| 2026-08-20 | Release v2.49.0 Notes | ARCHIVED | `release/CODE_SIGNING_REPORT.json` |
| `docs/HANDOVER_2026-08-21_T5.md` | 2026-08-21 | Terminal Session 5 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-21_T6.md` | 2026-08-21 | Terminal Session 6 | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-22_EDGE_VALIDATION.md` | 2026-08-22 | Edge Statistical Validation | ARCHIVED | `core/sky_intelligence/orchestrator.py` |
| `docs/HANDOVER_2026-08-22_NEXT_SESSION.md` | 2026-08-22 | Session Planning | ARCHIVED | `SYSTEM_MEMORY_AND_ROADMAP_2026.md` |
| `docs/HANDOVER_2026-08-22_P13_4.md` | 2026-08-22 | Phase 13.4 Setup Qualification | ARCHIVED | `core/sky_intelligence/setup_engine.py` |
| `docs/HANDOVER_2026-08-22_P13_5.md` | 2026-08-22 | Phase 13.5 Confluence Threshold | ARCHIVED | `core/sky_intelligence/setup_engine.py` |
| `docs/HANDOVER_2026-08-22_P13_6.md` | 2026-08-22 | Phase 13.6 Expectancy Validation | ARCHIVED | `core/sky_intelligence/setup_engine.py` |

---

## 4. Operating Manual for AI Agents & Quantitative Engineers

When beginning work on any feature or bug fix:
1. **Never read `HANDOVER_2026-08-*` for current system state.** Always read [`docs/SYSTEM_MEMORY_AND_ROADMAP_2026.md`](SYSTEM_MEMORY_AND_ROADMAP_2026.md) and [`docs/BACKEND_ROUTE_MATRIX.md`](BACKEND_ROUTE_MATRIX.md).
2. **Never modify Milestone 18 execution files without re-running:**  
   `python scripts/verify_m18_certification.py`
3. **Always verify pre-merge scorecard before declaring completion:**  
   `python scripts/system_preflight.py`

