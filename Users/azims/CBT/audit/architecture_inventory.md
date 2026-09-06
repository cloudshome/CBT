# Architectural & Subsystem Inventory

## 1. System Process Tree & Deployment Model

SKY / Crypto Brain Terminal operates as a multi-tier hybrid architecture comprising Python services, Node.js background services, and a React / Vite web interface.

```
SKY / CBT Architecture
├── Runtime Processes
│   ├── FastAPI Uvicorn Server (Python 3.13.3, Port 8000)
│   │   ├── REST API endpoints (Execution, Analytics, Market, Research)
│   │   ├── Server-Sent Events (SSE) / WebSocket streams
│   │   └── Asyncio background task loops
│   ├── Dedicated Paper Trading Desk (Node.js v20.12.0, Port 3000)
│   │   ├── WebSocket client to Binance Futures (wss://fstream.binance.com)
│   │   └── In-memory order matching & risk engine
│   └── Vite Frontend Development Server (Node.js v20.12.0, Port 5173)
│       ├── React 18 SPA with Tailwind CSS
│       └── TradingView Lightweight Charts v4.2.1
├── Persistent Storage (SQLite 3.45.1 in WAL Mode)
│   ├── data/market_data.db (OHLCV candles, book depth, trade ticks)
│   ├── data/brain_memory.db (Episodic memory, strategy DNA, knowledge graph)
│   ├── data/trading_logs.db (Audit events, shadow positions, telegram jobs)
│   └── data/experiment_store.db (Backtest experiments, Kronos neural forecasts)
├── File Stores & Ingestion
│   ├── data/vector_store/ (In-memory BoW vector store serialized to vectors.json)
│   ├── data/uploads/ (PDF monographs, books, user uploads)
│   └── data/logs/cbt_terminal.log (Python rotating log bounded at 50 MB)
└── Frontend Concurrency
    ├── Web Worker: src/core/workers/indicatorWorker.ts (EMA, VWAP, multi-sigma bands)
    └── Persistent WebSocket: src/data/providers/wsStateMachine.ts (Binance multiplexer)
```

---

## 2. Subsystem Inventory Matrix

| Subsystem | Source Location | Technology | Persistent? | Memory Risk | Disk Risk | CPU Risk | Concurrency Model |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **FastAPI Backend** | [`app.py`](file:///c:/Users/azims/CBT/app.py) | Python 3.13 / Uvicorn | Process state transient; DB persistent | Low-Medium (64 MB idle, peaks to 135 MB) | Low (writes to SQLite & rotating log) | Medium (asynchronous event loop) | Single process, Asyncio event loop |
| **Paper Trading Desk** | [`server/index.js`](file:///c:/Users/azims/CBT/server/index.js) | Node.js v20 / Express / WS | In-memory orders; periodic log flush | Low (29.6 MB idle) | Low (buffered console output) | Low (sub-millisecond order matching) | Single process, libuv event loop |
| **Vite Dev Server** | [`frontend/`](file:///c:/Users/azims/CBT/frontend) | Node.js v20 / Vite | Ephemeral HMR bundle cache | Medium (103.3 MB idle) | Low (< 5 MB cache in `node_modules`) | Low at idle, spike on HMR edit | Single process, Node thread pool |
| **Market DB** | [`data/market_data.db`](file:///c:/Users/azims/CBT/data/market_data.db) | SQLite 3 WAL mode | Yes (Disk) | Low (SQLite page cache ~2 MB) | **HIGH** (~831 KB/day for 3 syms; ~13.8 MB/day for 50 syms) | Low (batched disk I/O) | Single-writer, multi-reader WAL |
| **Brain Memory DB** | [`data/brain_memory.db`](file:///c:/Users/azims/CBT/data/brain_memory.db) | SQLite 3 WAL mode | Yes (Disk) | Low (~2 MB page cache) | Low-Medium (scales with extracted concepts) | Low | Single-writer, multi-reader WAL |
| **Trading Logs DB** | [`data/trading_logs.db`](file:///c:/Users/azims/CBT/data/trading_logs.db) | SQLite 3 WAL mode | Yes (Disk) | Low (~2 MB page cache) | Medium (audit events scale with orders/ticks) | Low | Single-writer, multi-reader WAL |
| **Experiment DB** | [`data/experiment_store.db`](file:///c:/Users/azims/CBT/data/experiment_store.db) | SQLite 3 WAL mode | Yes (Disk) | Low (~2 MB page cache) | Medium (scales with Monte Carlo backtests) | Low | Single-writer, multi-reader WAL |
| **TTL Cache** | [`core/ttl_cache.py`](file:///c:/Users/azims/CBT/core/ttl_cache.py) | Python In-Memory Dict | No (RAM only) | **HIGH** (Unbounded dictionary; stale keys leak RAM) | Zero | Ultra-low (0.78 µs hit latency) | Thread-safe via Python GIL / Lock |
| **Vector Store** | [`core/memory_vault.py`](file:///c:/Users/azims/CBT/core/memory_vault.py) | In-Memory BoW + JSON disk | Partial (JSON) | **CRITICAL** (Entire index in RAM; $O(N^2)$ write I/O) | **HIGH** (~1.84 KB/vector in indented JSON) | **HIGH** ($O(N)$ linear dot products in Python) | Single-threaded in-memory |
| **PDF Ingestor** | [`core/pdf_extractor.py`](file:///c:/Users/azims/CBT/core/pdf_extractor.py) | pypdf + Gemini Vision | No (Transcripts stored in DB) | Medium (RAM spike during PDF rendering ~120 MB) | **CRITICAL** (Uploads never deleted in `data/uploads/`) | Medium (Vision OCR is external API) | Asyncio worker tasks |
| **YouTube Pipeline** | [`core/youtube/`](file:///c:/Users/azims/CBT/core/youtube) | yt-dlp + transcript API | Transcripts in SQLite; zero media download | Low (text only, < 5 MB RAM per video) | Low (1 video transcript ~35 KB in DB) | Low (flat metadata + subtitle API) | Sequential worker tasks |
| **TradingView Chart** | [`frontend/src/core/engine/TradingViewChart.tsx`](file:///c:/Users/azims/CBT/frontend/src/core/engine/TradingViewChart.tsx) | Lightweight Charts v4.2.1 | Browser RAM | Low-Medium (single mount, RAF updates) | Zero | Low (60 FPS on RAF micro-batching) | Single-mount React lifecycle |
| **Indicator Worker** | [`frontend/src/core/workers/indicatorWorker.ts`](file:///c:/Users/azims/CBT/frontend/src/core/workers/indicatorWorker.ts) | Web Worker (browser) | Browser RAM | Low (< 15 MB heap for 1,000 bars) | Zero | Low (offloaded off main UI thread) | 1 background Web Worker thread |
| **WebSocket Multiplexer** | [`frontend/src/data/providers/wsStateMachine.ts`](file:///c:/Users/azims/CBT/frontend/src/data/providers/wsStateMachine.ts) | Native WebSocket client | Ephemeral | Low (< 5 MB RAM) | Zero | Low (JSON frame parse per 100ms) | Auto-reconnect with watchdog |
| **Logging Subsystem** | [`app.py`](file:///c:/Users/azims/CBT/app.py) | Python `RotatingFileHandler` | Yes (Disk) | Ultra-low (< 1 MB RAM) | **STRICTLY BOUNDED** (Max 50 MB: 5 x 10 MB) | Zero | Synchronous file append |
