# Crypto Brain Terminal (CTB)

Crypto Brain Terminal (CTB) is an institutional-grade paper trading and research platform for quantitative crypto markets, integrating multi-timeframe confluence, Smart Money Concepts (SMC) scanning, Gemini desk intelligence, and a dark quantitative Trading Desk UI.

---

## Architecture Overview

```
+-----------------------------------------------------------------------------------------------+
| CTB QUANT TERMINAL | [Symbol: BTCUSDT v] [TF: 15m v] | Price: $77,350 (+2.4%) | Latency: 18ms |
+-------------------------------------------------------------+---------------------------------+
|                                                             | GEMINI DESK COPILOT             |
| CANDLESTICK CHART & SMC OVERLAYS                            | - Bias: [BULLISH]               |
| - Interactive OHLCV Candles                                 | - Exec Summary: "BTC expansion" |
| - Toggles: [x] FVG Zones  [x] Order Blocks  [x] Swings/BOS  | - Key Levels: Sup/Res/Inval     |
| - Volume Sub-panel                                          | - Risk Assessment               |
|                                                             | - Q&A Interactive Chat Box      |
+-------------------------------------------------------------+---------------------------------+
| MTF INDICATORS & CONFLUENCE                                 | PAPER TRADING DESK              |
| - EMA(14) Trend | RSI(14) Momentum Gauge | Setups Card      | - Order Entry (Buy/Sell, SL, TP)|
|                                                             | - Live Dollar Risk Calculator   |
|                                                             | - Active Open Positions Table   |
+-------------------------------------------------------------+---------------------------------+
```

- **Frontend**: React 18 + Vite + Tailwind CSS + Lucide Icons
- **Backend**: Node.js + Express + TypeScript
- **Database**: SQLite via Prisma ORM for paper trading and candle caching
- **AI / ML**: Gemini (`@google/genai`) for desk intelligence and quantitative Q&A

---

## Features

- **Trading Desk Terminal UI (`frontend/`)**:
  - **Candlestick Chart**: Interactive SVG candlestick chart with volume histogram, hover crosshair, and toggleable visual overlays for Fair Value Gaps (FVGs), Order Blocks (OBs), and EMA(14) lines.
  - **MTF Confluence Panel**: Live EMA trend direction and Wilder's RSI(14) momentum gauge.
  - **SMC Scanner Panel**: Real-time structure detector with 1-click trade setup populate buttons.
  - **Paper Trading Desk**: Simulated order placement with pre-execution dollar risk calculator and live open positions table.
  - **Gemini Desk Copilot**: Real-time executive AI brief with institutional bias badge, key support/resistance levels, and grounded Q&A prompt terminal.
  - **Toast Notifications**: Interactive toasts for Risk Gate rejections (403), rate limits (429), and order execution confirmations (201).
- **Market Candles Endpoint (`/api/candles`)**:
  - Multi-source fallback: `Binance -> Bybit -> SQLite Cache -> 502 Bad Gateway`.
  - Chronological normalization `[timestamp, open, high, low, close, volume]`.
- **Multi-Timeframe Indicators (`/api/mtf`)**:
  - Pure mathematical calculation of EMA and Wilder's Smoothed RSI.
- **Smart Money Concepts (SMC) Scanner (`/api/scan`)**:
  - Algorithmic detection of Fair Value Gaps, Order Blocks, and Break of Structure.
- **Risk Gate & Paper Trading (`/api/paper`)**:
  - Enforces max 3 open positions and max 2% account risk ($2,000 on $100k account).
- **Gemini Desk Intelligence (`/api/desk`)**:
  - Automated market briefs (`/api/desk/ai-brief`) and ad-hoc Q&A (`/api/desk/ask`).

---

## Getting Started

### Prerequisites

- Node.js >= 20.0.0
- npm >= 10.0.0

### Installation

1. Install backend dependencies and sync database:
   ```bash
   npm install
   npx prisma db push
   ```

2. Install frontend dependencies:
   ```bash
   npm run frontend:install
   ```

### Running the Platform

1. **Start Backend Server** (Port 3000):
   ```bash
   npm run dev
   ```

2. **Start Frontend Terminal UI** (Port 5173):
   ```bash
   npm run frontend:dev
   ```

3. Open your browser at `http://localhost:5173`.

### Testing & Verification

- **Run complete test suite**:
  ```bash
  npm test
  ```
- **Run linter**:
  ```bash
  npm run lint
  ```
- **Build both backend and frontend**:
  ```bash
  npm run build
  ```

---

## API Reference

### 1. `GET /api/candles`
`GET /api/candles?symbol=BTCUSDT&timeframe=15m&limit=100`

### 2. `GET /api/mtf`
`GET /api/mtf?symbol=BTCUSDT&timeframe=15m&indicators=ema,rsi`

### 3. `GET /api/scan`
`GET /api/scan?symbol=BTCUSDT&timeframe=15m&limit=100`

### 4. `POST /api/paper/trade`
`POST /api/paper/trade` (Body: `{ symbol, side, entryPrice, sl, tp, size }`)

### 5. `GET /api/paper/positions`
`GET /api/paper/positions`

### 6. `POST /api/desk/ai-brief`
`POST /api/desk/ai-brief` (Body: `{ symbol, timeframe }`)

### 7. `POST /api/desk/ask`
`POST /api/desk/ask` (Body: `{ query, context }`)
