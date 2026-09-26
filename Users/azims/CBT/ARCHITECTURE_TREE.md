# ARCHITECTURE_TREE.md — SKY / Crypto Brain Terminal (CBT)
## Master Project Tree & Modular "Keyboard Key" Topology

> **Authoritative System Topology Guide**  
> For the complete comprehensive specification, see: [`docs/PROJECT_TOPOLOGY_AND_MODULAR_TREE.md`](docs/PROJECT_TOPOLOGY_AND_MODULAR_TREE.md).  
> **Core Guarantee:** Zero-Blast-Radius Decoupling — any branch or leaf can be inspected, refactored, upgraded, or replaced in total isolation without side-effects on the broader system.

---

## 1. THE "KEYBOARD KEY" MODULAR DECOUPLING STANDARD

Every module (leaf) in SKY functions like a hot-swappable mechanical keyboard key switch:
1. **Socket Interface:** Strictly typed input/output DTOs (dataclasses or Pydantic models). Never raw untyped dictionaries.
2. **Directional Flow:** Lower layers never import higher layers. Leaves do not access sibling internal variables.
3. **Diode Fail-Closed Buffer:** Every leaf wraps critical computation in failure sandboxes (`HookSandbox` or fail-closed handlers). If a switch jams, it fails closed without crashing the keyboard.
4. **Capital Firewall:** `real_capital_enabled = False` permanent invariant across all simulation, research, and AMM models.
5. **Causal Firewall:** Zero lookahead bias ($t \le t_{\text{event}}$).
6. **Immutable Backplate:** The 14 Milestone 18 execution files are cryptographically locked and frozen (`c9cc1cad`, 149 tests).

---

## 2. HIGH-LEVEL TOPOLOGY TREE

```
c:\Users\azims\CBT\
├── .specify/                    # Constitutional Memory & Causal Firewalls
├── core/                        # Core Python Quantitative Intelligence & Execution
│   ├── risk_engine/             # [Layer 0] Unbypassable Risk Authority (Half-Kelly, Collateral, LDB)
│   ├── execution/               # [Layer 0 & 2] Smart Execution, Simulation & Arbitrage
│   │   ├── [M18 FROZEN AREA]    # ⚠️ 14 certified files frozen at c9cc1cad (149 tests)
│   │   ├── concentrated_amm/    # [M42] Concentrated Liquidity AMM Engine (Uniswap v3 / v4)
│   │   ├── cross_chain/         # [M41] Cross-Chain Intent Solvers & Bridge Routing
│   │   ├── market_making/       # [M37] Avellaneda-Stoikov & Hawkes Flow Toxicity
│   │   ├── latency_arb/         # [M38] CEX-DEX Latency Arb & MEV Simulator
│   │   ├── rl_execution/        # [M39] Deep RL SAC Execution Slicer
│   │   └── protection/          # [M33] Synthetic Basis & Leg-Risk Fail-Safes
│   ├── collective/              # [M36/M40] HRP & Multi-Strategy Ensemble Allocator
│   ├── sky_intelligence/        # Multi-Agent Debate Committee (Bull, Bear, Neutral, Risk)
│   ├── kronos/                  # Macro Regimes & Correlation Matrices
│   ├── mbo/                     # Market-by-Order L2/L3 Elasticity & VPIN Toxicity
│   ├── research/                # CPCV, DSR, WRC, Experiment Registry
│   ├── auth/                    # FIDO2 Passkeys & EIP-712 AST Validator
│   └── database.py              # SQLite Sandbox Connection Pools
├── src/                         # [Layer 3] Node.js Express REST & Realtime WebSocket Engine
│   ├── server.ts                # HTTP (:3000) and WebSocket Server
│   ├── routes/                  # market, terminal, signals, auth, ai
│   ├── services/                # binanceWsService, bybitWsService, marketDataCache
│   └── middleware/              # rateLimiter, securityHeaders
├── app.py                       # [Layer 3] FastAPI Python Gateway (:8000)
├── frontend/                    # [Layer 4] React 18 + Vite Trading Terminal UI (Zero-Shake)
│   └── src/components/          # Persistent Canvas/SVG chart, L2 Depth, Debate, AMM visualizer
├── electron/                    # [Layer 4] Native Windows Desktop Supervisor
├── tests/                       # Test Sandboxes (Zero Production DB Mutation)
│   ├── conftest.py              # Test sandbox fixture
│   ├── test_milestone18_*.py    # 149 certified execution freeze tests
│   └── execution/               # M31-M42 milestone unit test suites
├── scripts/                     # Preflight verifiers, M18 hash checks, build tools
│   ├── verify_m18_certification.py # Cryptographic gate check
│   └── research/                # M31-R, M41-R, M42-R qualification harnesses
├── docs/                        # Institutional Protocols, Audit Dossiers & Specifications
│   ├── audit/                   # Qualification dossiers & JSON reports
│   └── PROJECT_TOPOLOGY_AND_MODULAR_TREE.md # Comprehensive Master Topology Guide
├── AGENTS.md                    # Permanent Operating Manual & Governance
├── SKY_STATUS.md                # Authoritative Single Source of Milestone Truth
└── ARCHITECTURE.md              # System Architecture Overview
```

---

## 3. HOW TO MODIFY OR ADD ANY COMPONENT SAFELY

To change or add any leaf without risking regressions:
1. **Define Contract First:** Create immutable Input/Output dataclasses in the module.
2. **Anchor Invariants:** Set `real_capital_enabled = False`.
3. **Wrap in Sandbox:** Ensure unhandled exceptions fail closed safely.
4. **Build Isolated Pytest:** Create `tests/<domain>/test_<feature>.py` in sandbox environment.
5. **Verify Certification:** Run `python scripts/verify_m18_certification.py` to ensure the M18 execution path remains 100% untouched.
