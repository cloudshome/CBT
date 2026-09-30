# Milestone 21 Pre-Implementation Audit & Security Specification

**System:** SKY / Crypto Brain Terminal (CBT)  
**Milestone:** 21 — External Exchange Testnet Connectors & Operational Reliability Validation  
**Date:** September 2026  
**Classification:** Class H (Live / Testnet Execution Boundary)  
**Permanent Real Capital Status:** **DISABLED / DENIED** (`REAL_CAPITAL_ENABLED = False`)

---

## 1. Executive Summary & Review Findings

Milestone 21 transitions SKY from local deterministic simulation to real external exchange testnet environments: **Binance Spot Testnet** and **Bybit V5 Testnet**.

The central mandate of Milestone 21 is:
> **Demonstrate that SKY's execution, reconciliation, and governance architecture behaves correctly when connected to real external testnet APIs—with zero production endpoint, credential, or capital leakage.**

This pre-implementation audit addresses the two critical P0 blockers identified during architectural review:

### 1.1. BLOCKER 1 (P0): Structural Endpoint Isolation
- **Vulnerability:** Relying on user configuration or fallback mechanisms could allow production URLs (`api.binance.com`, `api.bybit.com`) to be contacted during testing.
- **Resolution:** Implementation of `EndpointPolicy` with an immutable canonical hostname allowlist per environment (`BINANCE_TESTNET`, `BYBIT_TESTNET`, `DETERMINISTIC`), domain suffix blacklisting, and TLS-only protocol enforcement. Production targets and unencrypted protocols (`http://`, `ws://`) are rejected before network socket creation.

### 1.2. BLOCKER 2 (P0): "Reconnection Is Not Recovery"
- **Vulnerability:** Simply re-establishing a dropped WebSocket stream resumes event flow but silently misses all trades, fills, and order state transitions that occurred during the outage (gap fills).
- **Resolution:** Implementation of `AuthoritativeRecoveryManager`. Every WebSocket reconnection triggers an authoritative recovery flight querying open orders and execution logs, ingesting gap fills through the 4-tier deduplicator, reconciling child order states, resolving residuals, and asserting $Q_{\text{unresolved}} == 0$. Any irreconcilable state trips the FSM to `ANOMALY_HALTED`.

---

## 2. Invariant & Mathematical Architecture

### 2.1. Canonical Hostname Allowlists

| Environment | Canonical Hostname Allowlist | Allowed Schemes |
|---|---|---|
| `BINANCE_TESTNET` | `testnet.binance.vision`<br>`stream.testnet.binance.vision`<br>`ws-api.testnet.binance.vision` | `https://`, `wss://` |
| `BYBIT_TESTNET` | `api-testnet.bybit.com`<br>`stream-testnet.bybit.com` | `https://`, `wss://` |
| `DETERMINISTIC` | `localhost`, `127.0.0.1` | `http://`, `https://`, `ws://`, `wss://` |

All production indicators (`*.binance.com`, `*.bybit.com`, `*.bytick.com`) are permanently blacklisted.

### 2.2. Round-Trip Clock Offset Estimation with Uncertainty Bounds

Local clock time $t$ and exchange server time $s$ are measured via round-trip HTTP timing:
- Dispatch timestamp: $t_0$
- Receive timestamp: $t_1$
- Round-trip time: $\text{RTT} = t_1 - t_0$
- Server timestamp: $s$

Clock offset estimator ($\hat{\theta}$):
$$\hat{\theta} = \frac{t_0 + t_1}{2} - s$$

Measurement uncertainty:
$$\text{Uncertainty} = \frac{\text{RTT}}{2}$$

Exchange timing verification requires $\text{Uncertainty} \le \tau_{\max}$ (default: 25.0 ms).

### 2.3. Bybit V5 Strict Event Separation

Bybit V5 delivers order and execution events on distinct private topics:
- **`ORDER_STATUS_EVENT` (topic: `order`):** Lifecycle progression only (`New`, `PartiallyFilled`, `Filled`, `Cancelled`). Does **not** increment filled quantity or generate economic fill records.
- **`EXECUTION_EVENT` (topic: `execution`):** Authoritative trade execution records (`execId`, `execQty`, `execPrice`). Ingested into the 4-tier deduplication engine for economic accounting.
- **`BALANCE_UPDATE` (topic: `wallet`):** Collateral monitoring and margin equity tracking.

---

## 3. Milestone 18 Surface Area Invariant Protection

All 14 certified Milestone 18 surface area files (`c9cc1cad`) remain completely untouched:
- Zero edits to `core/execution/live_router.py`, `smart_order_router.py`, `reconciliation_ledger.py`, `almgren_chriss.py`, `idempotency.py`, `kill_switch.py`, `connectors/base.py`, `connectors/binance_connector.py`, `connectors/bybit_connector.py`, `database.py`, `app.py`, or M18 test suites.
- M18 cryptographic test identity SHA-256 (`2acbff25f391249cb1881bd40a4440384cecdd7682c6f83b91487d8744d0b57b`) remains 100% frozen.
