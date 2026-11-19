# IMPLEMENTATION PLAN — R1: Cross-Service Integration Contracts
**Change Class:** Class C  
**Dependencies:** None (Self-contained test contract verification)  

---

## 1. ARCHITECTURAL APPROACH

We enforce cross-service contracts across two synchronized test suites:
1. **Python Pytest Suite (`tests/test_cross_service_contracts.py`):**
   - Uses `fastapi.testclient.TestClient(app)`
   - Exercises FastAPI authoritative contracts, health vital schemas, error envelopes, and API key protection
   - Validates that primary data schemas match frontend TypeScript expectations (`frontend/src/types.ts`)
2. **Node Jest Suite (`tests/cross_service_contract.test.ts`):**
   - Uses `supertest(createApp())`
   - Exercises Express legacy routing, convergence headers, error propagation, rate limiting, and schema parity
   - Verifies handling when mock upstream or dependencies are degraded

---

## 2. RISK ASSESSMENT & MITIGATION
- **Risk:** Modifying protected M18 files.
  - *Mitigation:* Zero touches to `app.py`, `core/execution/`, or any of the 14 certified files. All contract assertions are externalized in dedicated test suites.
- **Risk:** Flaky network dependencies.
  - *Mitigation:* Uses local in-memory TestClient / supertest with zero outbound network calls.
- **Risk:** Production database contamination.
  - *Mitigation:* Governed by `tests/conftest.py` sandbox and Jest `test.db`.
