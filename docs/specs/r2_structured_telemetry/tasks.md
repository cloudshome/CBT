# TASKS — R2: Structured Telemetry & Correlation IDs
**Change Class:** Class C  

---

- [x] **Task 1:** Implement `core/correlation_context.py` with ContextVar and `CorrelationIdMiddleware`.
- [x] **Task 2:** Update `core/audit_bus.py` to record `correlation_id` in `AuditEvent`, `emit_event`, and SQLite schema.
- [x] **Task 3:** Update `core/sky_intelligence/types.py` & `core/sky_intelligence/orchestrator.py` to propagate `correlation_id`.
- [x] **Task 4:** Update `core/half_kelly_sizer.py` to propagate `correlation_id` in `HalfKellySizingResult`.
- [x] **Task 5:** Update `core/portfolio_shadow.py` to propagate `correlation_id` in `ShadowPosition` and audit events.
- [x] **Task 6:** Create comprehensive test suite `tests/test_structured_telemetry.py` proving full 5-hop trace.
- [x] **Task 7:** Run pytest and ruff, verify all tests pass (6/6 passed in 0.40s).
- [x] **Task 8:** Execute 3-tier self-criticism reviews (Reviews A, B, C).
- [x] **Task 9:** Verify Milestone 18 certification remains valid (149/149 green, zero certified files modified).
- [x] **Task 10:** Update `docs/engineering/INSTITUTIONAL_STABILITY_MASTER_REPORT.md` with verified evidence.
