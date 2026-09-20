# Milestone 21 Technical Architecture & Component Contracts

**System:** SKY / Crypto Brain Terminal (CBT)  
**Milestone:** 21 — External Exchange Testnet Connectors & Operational Reliability Validation  
**Date:** September 2026  
**Module Path:** `core/execution/testnet/`  
**Test Path:** `tests/execution/`

---

## 1. Architectural Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SKY STRATEGY ENGINE                               │
│                   (Paper Rehearsal & Simulated Capital)                     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Orders & Cancels
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ENDPOINT SAFETY FIREWALL                           │
│     EndpointPolicy (REAL_CAPITAL_ENABLED = False, Canonical Allowlist)      │
│      CredentialPolicy (Zero Withdrawal / Zero Transfer Permissions)         │
└───────────────────┬─────────────────────────────────────┬───────────────────┘
                    │                                     │
                    ▼ REST                                ▼ WebSocket
┌──────────────────────────────────────┐┌─────────────────────────────────────┐
│            RestTransport             ││         WebSocketTransport          │
│ - TLS-only enforcement              ││ - Heartbeat watchdog (Bybit ping)   │
│ - Exact timing (t0, t1, RTT)         ││ - 24-hour planned rotation (Binance)│
│ - Structured error mapping (429/5xx) ││ - Reconnect hook -> Recovery Flight │
└───────────────────┬──────────────────┘└─────────────────┬───────────────────┘
                    │                                     │
                    ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONCRETE TESTNET CONNECTORS                           │
│  - BinanceSpotTestnetAdapter (HMAC query signing, listenKey keepalive)     │
│  - BybitV5TestnetAdapter (HMAC header signing, strict event separation)     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Trades & Status
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTHORITATIVE RECOVERY MANAGER                           │
│ - Post-reconnect reconciliation flight                                      │
│ - 4-tier fill deduplication (transport -> economic -> lifecycle)           │
│ - Resolves gap fills and canceled residuals                                 │
│ - Fails closed to ANOMALY_HALTED on irreconcilable discrepancies            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 EVIDENCE GENERATOR & FORENSIC VERDICT                       │
│ - 11 technical engineering gates: PASS                                      │
│ - Production market validity: NOT_ESTABLISHED                               │
│ - Real capital authorization: strictly DENIED                               │
│ - Canonical JSON SHA-256 digest                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Specifications

### 2.1. `EndpointPolicy` & `_ImmutablePolicyMeta`
- **Path:** `core/execution/testnet/endpoint_policy.py`
- **Class:** `EndpointPolicy(metaclass=_ImmutablePolicyMeta)`
- **Responsibilities:**
  - Enforces `REAL_CAPITAL_ENABLED = False` via metaclass property preventing mutation.
  - Maintains strict canonical hostnames: `testnet.binance.vision`, `stream.testnet.binance.vision`, `api-testnet.bybit.com`, `stream-testnet.bybit.com`.
  - Rejects production hosts (`*.binance.com`, `*.bybit.com`, `*.bytick.com`), arbitrary hosts, spoofed domains, and unencrypted URI schemes (`http://`, `ws://`).

### 2.2. `CredentialPolicy` & `TestnetCredentials`
- **Path:** `core/execution/testnet/credential_policy.py`
- **Responsibilities:**
  - `TestnetCredentials`: Dataclass asserting `can_withdraw=False` and `can_transfer=False`.
  - `mask_secret()`: Masks keys in telemetry/logs (`abcd...ijkl` or `***`).
  - `validate_account_permissions()`: Audits live REST account query payloads to verify zero withdrawal capabilities.

### 2.3. `RestTransport` & `WebSocketTransport`
- **Paths:** `core/execution/testnet/rest_transport.py`, `core/execution/testnet/websocket_transport.py`
- **Responsibilities:**
  - Pre-flight `EndpointPolicy.validate_url()` execution before any network socket creation.
  - Sub-millisecond monotonic and wall clock measurement ($t_0, t_1$).
  - Mapping HTTP response codes to domain errors (`RateLimitError`, `RestAuthenticationError`, `BadRequestError`, `ExchangeServerError`).
  - WebSocket lifecycle management: Keepalive ping watchdog (20-second interval for Bybit) and 24-hour planned connection rotation sentinel for Binance.

### 2.4. `AuthoritativeRecoveryManager`
- **Path:** `core/execution/testnet/recovery.py`
- **Responsibilities:**
  - Executes authoritative recovery flight after every WebSocket reconnect or restart.
  - Reconciles open orders against exchange state.
  - Absorbs missing gap fills via 4-tier deduplicator without double counting.
  - Automatically resolves canceled residuals when active children disappear from open orders.
  - Enforces quantity conservation and fails closed to `ANOMALY_HALTED` if state uncertainty exists.

### 2.5. `BinanceSpotTestnetAdapter` & `BybitV5TestnetAdapter`
- **Paths:** `core/execution/testnet/binance_spot.py`, `core/execution/testnet/bybit_v5.py`
- **Responsibilities:**
  - HMAC-SHA256 signature generation matching exact venue requirements.
  - Exchange server time query with round-trip clock offset and uncertainty estimation ($\hat{\theta} = \frac{t_0 + t_1}{2} - s$, $\text{uncertainty} = \text{RTT} / 2$).
  - REST order placement, cancellation, open orders, and trade list queries.
  - Bybit event separation: `order` topic for status only, `execution` topic for fills, `wallet` topic for balances.

### 2.6. `EvidenceGenerator` & `Milestone21Verdict`
- **Path:** `core/execution/testnet/evidence.py`
- **Responsibilities:**
  - Evaluates multi-axis qualification scorecard.
  - Preserves epistemically sound separation: technical compliance is `PASS`, live validity is `NOT_ESTABLISHED`, real capital authorization is `DENIED`.
  - Produces signed JSON bundles with canonical SHA-256 digests.
