# 📡 SKY / CTB — Unified API Architecture & Endpoint Reference

The system operates a high-throughput dual-backend architecture:
- **Python FastAPI (`:8000`)**: Real-time quantitative intelligence, Smart Money Concepts (SMC), regime classification, walk-forward validation, provenance hashing, and shadow portfolio execution.
- **Node.js Express (`:3000`)**: Resilient market data fallback orchestration, TradingView charting feeds, Prisma SQLite paper trading ledger, and desk AI briefs.

---

## 1. Observability & Health Probes

| Method | Route | Backend | Auth Required | Description |
|:---|:---|:---:|:---:|:---|
| `GET` | `/health` | Node / Python | Public | Lightweight liveness probe reporting vitals, drift, and database info. |
| `GET` | `/ready` | Python | Public | Readiness probe for container orchestration. |
| `GET` | `/metrics` | Node / Python | Public | Standard Prometheus plaintext format metrics stream. |
| `GET` | `/api/metrics/json` | Node | Public | Diagnostic JSON summary including exchange circuit breaker states. |

---

## 2. Market Data & Multi-Timeframe Streams

| Method | Route | Backend | Auth Required | Description |
|:---|:---|:---:|:---:|:---|
| `GET` | `/api/candles` | Node | Public | Returns OHLCV candles via Binance -> Bybit -> SQLite Cache fallback chain. |
| `GET` | `/api/mtf` | Node | Public | Fetches multi-timeframe candle bundles (5m, 15m, 1h, 4h, 1d) with indicator calculations. |
| `GET` | `/api/scan` | Node | Public | Scans for Fair Value Gaps (FVG) and Order Blocks (OB). |
| `GET` | `/api/tickers` | Node | Public | 24-hour ticker volume, high, low, and price change percentage. |

---

## 3. SKY Quantitative Intelligence & Regimes

| Method | Route | Backend | Auth Required | Description |
|:---|:---|:---:|:---:|:---|
| `GET` | `/api/sky/decision` | Python | Public | Generates comprehensive multi-stage institutional trading decision matrix. |
| `GET` | `/api/prediction` | Python | Public | Quantitative multi-horizon expected price trajectory predictions. |
| `GET` | `/api/scenarios` | Python | Public | Generates stress test simulation paths and scenario analysis. |
| `GET` | `/api/path-simulation`| Python | Public | Real-time Monte Carlo path simulations and probability of target hit. |
| `GET` | `/api/dossier` | Python | Public | Complete 360-degree quantitative asset profile (structure, order flow, liquidity). |

---

## 4. Shadow Portfolio & Execution Desk

| Method | Route | Backend | Auth Required | Description |
|:---|:---|:---:|:---:|:---|
| `GET` | `/api/paper/positions`| Node | `API_KEY` | Lists active SQLite paper trading positions. |
| `POST`| `/api/paper/order` | Node | `API_KEY` | Places new paper order gated by deterministic Risk Gate. |
| `GET` | `/api/shadow/positions`| Python| Public | Lists active Python shadow portfolio positions. |
| `POST`| `/api/shadow/trade` | Python| `API_KEY` | Submits new shadow trade with Half-Kelly risk allocation. |
| `POST`| `/api/shadow/reset` | Python| `API_KEY` | Panic emergency kill switch resetting shadow state. |

---

## 5. Strategy Competition League & Provenance

| Method | Route | Backend | Auth Required | Description |
|:---|:---|:---:|:---:|:---|
| `GET` | `/api/league/leaderboard`| Python| Public | Returns 4-Tier Quarantine League standings and capital weights. |
| `POST`| `/api/strategy/compile` | Python| `API_KEY` | Compiles raw strategy rules into an immutable Strategy Genome. |
| `GET` | `/api/audit/recent` | Python | Public | Streams immutable incident and risk enforcement audit logs. |
| `POST`| `/api/governance/approve`| Python| `API_KEY` | Signs cryptographically verified governance configuration update. |

---

## 6. Real-Time WebSocket Streams

| Protocol | Route | Backend | Description |
|:---|:---|:---:|:---|
| `WSS` | `wss://stream.binance.com/stream?streams=...` | Direct / Proxy | Live sub-second tick, depth, and candlestick stream. |
| `WS` | `ws://localhost:8000/ws/terminal` | Python | Real-time quantitative signal alerts and regime shift broadcast. |
