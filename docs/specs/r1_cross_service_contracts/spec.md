# SPECIFICATION — R1: Cross-Service Integration Contracts
**Change Class:** Class C (Small Engineering Feature / Integration Contract Test)  
**Governance Authority:** Level 0 (`AGENTS.md`) & Level 1 (`constitution.md`)  
**Target Services:** Python FastAPI (:8000), Node/Express (:3000), React/Vite Frontend (:80)  

---

## 1. OBJECTIVE & SCOPE

Establish comprehensive automated integration contract verification tests spanning:
1. **Python FastAPI (Authoritative Quant Engine, Port 8000):** Verify health contracts, schema serialization, authentication enforcement, error response envelopes, and OpenAPI route completeness.
2. **Node/Express (Legacy Compatibility Facade, Port 3000):** Verify convergence headers, readiness probes, error handling, rate limiting, and fallback behavior.
3. **Frontend API Contracts (Port 80 / Vite Proxy):** Verify that all endpoints invoked by `frontend/src/services/api.ts` have corresponding backend routes and matching response payload structures.

---

## 2. FUNCTIONAL CONTRACT INVARIANTS

### 2.1 Health & Liveness Contracts
- FastAPI `GET /api/health`:
  - Returns HTTP 200 with JSON: `{ "status": "OPERATIONAL", "api_vitals": { ... }, "drift_report": { ... } }`
- Express `GET /health`:
  - Returns HTTP 200 with JSON: `{ "status": "ok", "service": "CTB-Backend" }`
- Express `GET /api/readiness`:
  - Returns HTTP 200 with JSON: `{ "status": "ok", "ready": true, "timestamp": ISO_8601_STRING }`

### 2.2 Convergence & Architectural Separation Headers
All Express responses must emit:
- `X-Backend-Service: CTB-Express-Legacy`
- `X-Authoritative-Backend: Python-FastAPI`
- `X-Convergence-Status: Legacy-Fallback-Route`

### 2.3 Error Envelope & Status Propagation
- 400 Bad Request: Returns JSON error structure with informative description.
- 401 Unauthorized: Triggered when `API_KEY` is configured and request lacks valid `Authorization: Bearer <token>` or `X-API-Key`.
- 404 Not Found: Graceful JSON error envelope, no HTML dump.
- 422 Unprocessable Entity (FastAPI): Structured Pydantic validation failure.
- 429 Too Many Requests: Rate limiter throttling with standard `Retry-After` headers.

### 2.4 Payload Schema Parity
- **Normalized Candles Contract:** Both services must produce OHLCV records satisfying `{ timestamp: number, open: number, high: number, low: number, close: number, volume: number }`.
- **Paper Trade / Shadow Position Contract:** Positions must contain `{ symbol, direction, size, entry_price, stop_loss, take_profit, status }`.
- **Risk Configuration Contract:** Must provide equity limits and maximum open position caps.

---

## 3. NON-FUNCTIONAL REQUIREMENTS & BOUNDARIES
- **M18 Certification Boundary:** Zero modifications permitted to the 14 M18 certified files.
- **Database Isolation:** All tests run strictly in temporary sandbox environments (`tests/conftest.py` / `test.db`).
- **Speed & Reliability:** Tests must execute synchronously in < 10 seconds without external network dependencies.
