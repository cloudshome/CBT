# IMPLEMENTATION PLAN — R2: Structured Telemetry & Correlation IDs
**Change Class:** Class C  

---

## 1. ARCHITECTURAL APPROACH

1. **`core/correlation_context.py`:**
   - Define `_CORRELATION_ID: ContextVar[str | None]`
   - Implement `get_correlation_id()`, `set_correlation_id()`, `sanitize_correlation_id()`, `generate_correlation_id()`
   - Implement `CorrelationScope` context manager
   - Implement Starlette/FastAPI `CorrelationIdMiddleware`
2. **`core/audit_bus.py`:**
   - Add `correlation_id: str | None = None` to `AuditEvent` dataclass
   - In `emit_event()`, extract `correlation_id = correlation_id or get_correlation_id()`
   - In `_ensure_table_exists()`, ensure `correlation_id TEXT` column exists via backward-compatible `ALTER TABLE`
   - Store and index `correlation_id`
3. **`core/sky_intelligence/types.py` & `orchestrator.py`:**
   - Add `correlation_id: str | None = None` to `DecisionOutput`
   - In `analyze_market()`, accept `correlation_id: str | None = None` (fallback to context)
4. **`core/half_kelly_sizer.py`:**
   - Add `correlation_id: str | None = None` to `HalfKellySizingResult`
   - In `calculate_sizing()`, accept `correlation_id: str | None = None` (fallback to context)
5. **`core/portfolio_shadow.py`:**
   - Add `correlation_id: str | None = None` to `ShadowPosition`
   - In `open_position()`, accept `correlation_id: str | None = None` (fallback to context) and pass it when emitting audit events
6. **`tests/test_structured_telemetry.py`:**
   - End-to-end test verifying consistent correlation ID across all 5 hops:
     `HTTP -> Orchestrator -> Sizer -> Shadow Portfolio -> Audit Bus`
   - Sanitization tests (valid header preserved, invalid header sanitized, missing header generated)
   - Redaction & safety tests
