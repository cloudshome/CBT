# SPECIFICATION — R2: Structured Telemetry & Request Correlation IDs
**Change Class:** Class C (Small Engineering Feature / Telemetry Infrastructure)  
**Governance Authority:** Level 0 (`AGENTS.md`) & Level 1 (`constitution.md`)  
**Target Subsystems:** `core/correlation_context.py`, `core/audit_bus.py`, `core/sky_intelligence/orchestrator.py`, `core/half_kelly_sizer.py`, `core/portfolio_shadow.py`  

---

## 1. OBJECTIVE & PROPAGATION PATH

Establish end-to-end request traceability across the decision, sizing, execution, and audit lifecycle.
The correlation identifier must flow unbroken across all five hops:

$$\text{HTTP Request} \longrightarrow \text{Orchestrator} \longrightarrow \text{Sizer} \longrightarrow \text{Shadow Portfolio} \longrightarrow \text{Audit Bus}$$

---

## 2. FUNCTIONAL REQUIREMENTS

### 2.1 Correlation ID Behavior & Sanitization
- Every request entering the system receives a validated `correlation_id`.
- If an incoming `X-Correlation-ID` header is present, it is evaluated against a strict sanitization policy:
  - Allowed characters: alphanumeric, hyphens, underscores, dots, colons (`[a-zA-Z0-9_\-\.:]`).
  - Length: Between 8 and 64 characters.
  - Malformed, control, space, or script characters are rejected and replaced with a newly generated institutional ID: `CID-<timestamp_ms>-<hex8>`.
- In all outgoing HTTP responses, the sanitized correlation ID is echoed in the `X-Correlation-ID` header.

### 2.2 Asynchronous & Thread-Safe Context Propagation
- Implemented via `contextvars.ContextVar[str | None]` in `core/correlation_context.py`.
- Thread-safe, coroutine-isolated, and inherited across child tasks.
- If any component does not receive an explicit `correlation_id` argument, it automatically falls back to `get_correlation_id()`.

### 2.3 Component Dataclass Extensions
1. **Orchestrator (`core/sky_intelligence/types.py` & `orchestrator.py`):**
   - `DecisionOutput` carries `correlation_id: str | None = None`.
   - `explanation_dossier` includes `"correlation_id": correlation_id`.
2. **Half-Kelly Sizer (`core/half_kelly_sizer.py`):**
   - `HalfKellySizingResult` carries `correlation_id: str | None = None`.
   - `calculate_sizing` accepts `correlation_id: str | None = None`.
3. **Shadow Portfolio (`core/portfolio_shadow.py`):**
   - `ShadowPosition` carries `correlation_id: str | None = None`.
   - `open_position` accepts `correlation_id: str | None = None`.
4. **Audit Bus (`core/audit_bus.py`):**
   - `AuditEvent` carries `correlation_id: str | None = None`.
   - `emit_event` accepts `correlation_id: str | None = None`.
   - In-memory ring buffer and persistent SQLite table `system_audit_events` store `correlation_id`.

---

## 3. INVARIANTS & SAFETY CONSTRAINTS
1. **Zero Modification to Protected M18 Files:** Implemented strictly outside the 14 certified files.
2. **Telemetry Failure Isolation:** If logging or correlation extraction fails, it fails safely without altering position sizing, risk calculations, or trading decisions.
3. **Secret Redaction:** Telemetry records and audit events must never serialize exchange secrets, private keys, or passwords.
4. **Database Isolation:** All tests run strictly in temporary sandboxes via `tests/conftest.py`.
