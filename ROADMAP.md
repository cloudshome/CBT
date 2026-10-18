# ROADMAP.md — Project Roadmap & Future Milestones

## Vision
Crypto Brain Terminal (CTB) is evolving from an institutional-grade quantitative research and paper-trading sandbox into a comprehensive, multi-venue algorithmic trading terminal powered by real-time Smart Money Concepts (SMC) scanning and Gemini Desk Intelligence.

---

## Milestone Phases

```mermaid
gantt
    title CTB Engineering Roadmap
    dateFormat  YYYY-MM
    section Phase 1 (Completed)
    Quant SMC & Indicator Primitives       :done, 2026-06, 2026-08
    Multi-Source Redundant Data Pipeline  :done, 2026-07, 2026-08
    Institutional Risk Gate & Paper Desk  :done, 2026-07, 2026-08
    Gemini Desk Copilot & PWA UI          :done, 2026-08, 2026-08
    Dockerization & CI/CD Hardening       :done, 2026-08, 2026-08

    section Phase 2
    Live Exchange Execution (Binance/Bybit):active, 2026-09, 2026-11
    Real-Time WebSocket Streams           :2026-09, 2026-10
    HMAC Auth & Secure Key Vault          :2026-10, 2026-11

    section Phase 3
    Perpetual Futures & Funding Arbitrage :2026-11, 2027-01
    Multi-Asset Support (DeFi / DEX)      :2026-12, 2027-02
    Cross-Collateral Portfolio Ledger     :2027-01, 2027-03

    section Phase 4
    High-Tick Historical Backtesting      :2027-02, 2027-04
    Monte Carlo Risk Simulation           :2027-03, 2027-05
    Gemini Automated Strategy Synthesis   :2027-04, 2027-06

    section Phase 5
    TimescaleDB / PostgreSQL Migration    :2027-05, 2027-07
    Distributed Redis Order Queue         :2027-06, 2027-08
    Kubernetes & Multi-Region HA          :2027-07, 2027-09
```

---

### Phase 1: Institutional Core & Paper Trading Engine *(Completed)*
- [x] Resilient multi-tier market data pipeline (Binance REST -> Bybit V5 Public REST -> SQLite Persistent Cache -> 502 Bad Gateway).
- [x] Mathematical Smart Money Concepts engine (Fair Value Gaps, Order Blocks, Break of Structure, Swing Highs/Lows).
- [x] Multi-Timeframe indicator telemetry (EMA-14 trendline, Wilder's Smoothed RSI-14 momentum).
- [x] Pre-execution institutional Risk Gate (2.0% maximum equity risk, max 3 concurrent open positions).
- [x] Simulated paper trading desk with automated SL/TP position ledger in SQLite via Prisma ORM.
- [x] Google Gemini AI Desk Copilot for automated market briefs and grounded contextual Q&A.
- [x] React 18 + Vite + Tailwind CSS quantitative PWA terminal with custom SVG candlestick chart.
- [x] Service Worker caching and Web Push notifications for Risk Gate events.
- [x] Multi-stage Docker containerization and GitHub Actions automated CI pipeline.

---

### Phase 2: Live Exchange Execution
- [ ] **Live Order Routing**: Integration of Binance REST API v3 and Bybit V5 Private endpoints for live spot order execution.
- [ ] **HMAC-SHA256 & Ed25519 Request Signing**: Hardware-secured and environment-secured API credential manager.
- [ ] **Real-Time WebSocket Streams**: Bidirectional candle, book ticker, and depth stream subscriptions replacing polling.
- [ ] **Live Position Manager**: Real-time stop-loss and take-profit order management directly with exchange matching engines.

---

### Phase 3: Multi-Asset & Derivatives Support
- [ ] **Perpetual Futures & Funding Arbitrage**: Support for linear USDT perpetuals, funding rate history tracking, and basis arbitrage scanning.
- [ ] **Cross-Collateral Margin Ledger**: Unified margin tracking across multiple concurrent assets and collateral currencies.
- [ ] **Decentralized Exchange (DEX) & On-Chain Telemetry**: Integration with Uniswap V3, Raydium, and Hyperliquid APIs for decentralized order flow confluence.

---

### Phase 4: Advanced AI Backtesting & Simulation
- [ ] **High-Resolution Tick Backtesting Engine**: Event-driven backtesting engine with realistic slippage, liquidity depth simulation, and maker/taker fee modeling.
- [ ] **Monte Carlo Risk Stress-Testing**: Quantitative simulation of portfolio drawdowns under volatile and black-swan market conditions.
- [ ] **Gemini Strategy Synthesizer**: AI-assisted parameter tuning and natural language strategy prompt-to-code compiler.

---

### Phase 5: Distributed Scaling & High Availability
- [ ] **Kubernetes Helm Charts**: Production deployment manifests for multi-region container orchestration with automated zero-downtime rolling updates.

---

## Canonical Multi-Platform Roadmap & Progression Phases

### Phase History & Platform Delivery

- **P1–P6**: RAG Library, LLM Reasoning, Autonomous Agents, MCP Server, Immune System, Hidden Alpha & Variance.
- **P7–P9**: Multi-Exchange Price Verification, Cross-Exchange Collector, Data Independence.
- **P10**: Normalised Schema, Partitioned Parquet CandleStore, Backfiller, Storage Invariants.
- **P11**: Real Canonical Paper Trading & Proof of Edge.
- **P12**: Boxed Scorecards, Plateau Testing, Costs & Funding, MC Resampler.
- **P17**: Web Trader & Workstation Architecture.
- **P18**: Authentication and authorization, role gating, and versioned APIs.
- **P19**: **Ubuntu Sky Hub** package — one database (one DB) on the Ubuntu Hub acting as the single trading authority; no live order execution.
- **P20**: **Windows Companion** (`.exe` installer for monitoring and paper approval). Note: Native installers do not exist yet in production checkout (built via packaging recipes).
- **P21**: **Android Companion** (`.apk` package for alerts, daily ritual, and paper approvals). Note: Native APK installers do not exist yet.
- **P22**: Multi-platform signed release engineering and operational hardening.

