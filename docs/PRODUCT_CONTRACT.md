# SKY / CBT — Authoritative Product Contract & Operational Safety Boundary

**Document Revision:** 1.0  
**Effective Date:** 2026-11-02  
**Governance Authority:** Level 1 Constitution (`.specify/memory/constitution.md`) & `AGENTS.md`  
**Authoritative Backend:** Python FastAPI (`app.py`)  

---

## 1. Executive Mission & Operating Philosophy

Crypto Brain Terminal (CBT) / SKY is an institutional cryptocurrency quantitative market-intelligence, strategy discovery, and risk-governed decision system.

### The Immutable Constitutional Invariant
> **Risk Primacy & Zero Lookahead:** No trading decision, automated signal, or predictive model may ever bypass deterministic risk gates (Half-Kelly, Max Daily Loss, Single Order Risk Ceiling). Data must always observe causal cutoffs ($t_{\text{available}} \le t_{\text{decision}}$).

---

## 2. Discrete Operating Modes & Safety Boundaries

The system strictly operates within one of five discrete modes. **Live mode is locked by default.**

| Mode | Allowed External I/O | Execution Target | Credential Access | Failure State |
| :--- | :--- | :--- | :--- | :--- |
| **`RESEARCH`** | Historical datasets, research crawlers | Python backtesting engine (`core/backtest/`) | Mock keys only | Fail-closed |
| **`SIMULATION`** | Historical L2/tick replay | Virtual matching engine | Mock keys only | Fail-closed |
| **`PAPER`** (Default) | Live public market data WebSockets | Virtual shadow portfolio (`core/portfolio_shadow.py`) | Read-only market feeds | Fail-closed |
| **`TESTNET`** | Live testnet exchange endpoints | Binance/Bybit Testnet APIs | Testnet API keys (`BINANCE_TESTNET_KEY`) | Circuit break to PAPER |
| **`LIVE_RESTRICTED`** | Production exchange WebSockets & REST | Institutional production venues | Encrypted vault with HMAC ceremony | Immediate Emergency Halt |

### Fail-Closed Mode Boundary Rules
1. **Accidental Live Execution Prevention:** Any order route attempting live venue dispatch without explicit environment flag `ALLOW_LIVE_EXECUTION="true"` and a valid, unexpired operator clearance ceremony token (`execute_operator_clearance_ceremony.py`) immediately raises `ConstitutionalViolationError` and terminates the process.
2. **Deterministic Risk Ceiling:** Regardless of operator settings, no single order may risk more than **1.5% of current equity**, and total daily drawdown exceeding **3.5%** triggers an irrevocable 24-hour cool-down (`core/cooldown_governor.py`).

---

## 3. Authoritative Service & Data Ownership Topology

To eliminate dual-backend divergence, the service responsibilities are frozen as follows:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        REACT VITE TERMINAL UI                          │
│         Served via Nginx / Caddy Proxy (Port 3000 / 80 / 443)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Reverse Proxy
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
       ┌─────────────────────────┐     ┌─────────────────────────┐
       │     PYTHON FASTAPI      │     │      NODE / EXPRESS     │
       │    (AUTHORITATIVE)      │     │   (LEGACY COMPATIBILITY)│
       │   Port 8000 / app.py    │     │   Port 3001 / server.ts │
       └────────────┬────────────┘     └────────────┬────────────┘
                    │                               │
                    │ All Quant, Risk, Orders       │ Legacy metrics & dev
                    ▼                               ▼
       ┌─────────────────────────────────────────────────────────┐
       │             SQLITE PERSISTENCE LEDGERS                  │
       │  - data/trading_logs.db     (Fills, Positions, Audits)  │
       │  - data/market_data.db      (Tick cache, L2 snapshots)  │
       │  - data/experiment_store.db (Immutable research runs)   │
       │  - data/security.db         (Auth, Session security)    │
       └─────────────────────────────────────────────────────────┘
```

1. **Python FastAPI (`app.py`):** The **Sole Authoritative Backend** for:
   - Real-time candle math, SMC structural markers, ATR volatility stops.
   - Setup engine confluence scoring and probability calibration.
   - Smart Order Routing (SOR), Almgren-Chriss optimal slicing, and fill reconciliation.
   - Dynamic portfolio shadow tracking and Half-Kelly sizing.
2. **Node / Express (`src/server.ts`):** 
   - Designated as a **Legacy Compatibility Facade**.
   - Direct database mutation via Prisma in Express is prohibited for trading decisions; Express proxies or mirrors FastAPI endpoints with `X-Backend-Service: CTB-Express-Legacy`.

---

## 4. Verification & Release Evidence Standards

Software test passes do **NOT** constitute proof of quantitative edge. Any production claim requires:
1. **Unit & Integration Verification:** 100% green tests in sandboxed isolation (`tests/conftest.py`).
2. **Milestone 18 Certification:** All 14 gates / 149 adversarial tests passing (`scripts/verify_m18_certification.py`).
3. **Out-of-Sample Empirical Evidence:** Combinatorial Purged Cross-Validation (CPCV) with Deflated Sharpe Ratio ($DSR > 0.95$) and 3-tier fee/slippage friction modeling before capital allocation.
