# Crypto Brain Terminal (CTB) Backend

Crypto Brain Terminal (CTB) is an institutional-grade paper trading and research platform for quantitative crypto markets, integrating multi-timeframe confluence, Smart Money Concepts (SMC) scanning, and market intelligence.

## Features

- **Market Candles Endpoint (`/api/candles`)**:
  - **Multi-Source Fallback Hierarchy**:
    1. **Primary**: Binance Public REST API (`https://api.binance.com/api/v3/klines`).
    2. **Secondary Fallback**: Bybit V5 Public REST API (`https://api.bybit.com/v5/market/kline`).
    3. **Tertiary Fallback**: Local SQLite Cache (`candles_cache` table via Prisma).
    4. **Final Failure**: HTTP 502 Bad Gateway if all sources are unreachable.
  - **Multi-Source Normalization**: Formats data from all sources into consistent `[timestamp, open, high, low, close, volume]` arrays sorted chronologically (ascending).
  - **Automatic Caching**: Any successful fetch (Binance or Bybit) automatically upserts candles to SQLite.
- **Multi-Timeframe Technical Indicators (`/api/mtf`)**:
  - Computes Exponential Moving Average (EMA) and Wilder's Relative Strength Index (RSI) across supported timeframes.
  - Automatically fetches underlying market data using the unified fallback pipeline.
- **Smart Money Concepts (SMC) Scanner (`/api/scan`)**:
  - Detects Fair Value Gaps (FVGs) and Order Blocks (OBs) with mitigation status.
  - Detects Swing Highs/Lows and Break of Structure (BOS).
  - Generates actionable trade setup suggestions (entry, stop loss, take profit, R:R).
- **Risk Gate & Paper Trading (`/api/paper`)**:
  - **Pre-Execution Risk Gate Middleware**:
    - **Max Open Trades**: Caps concurrent active positions to 3 (rejects with 403 Forbidden).
    - **Max Risk Per Trade**: Caps loss per trade to 2% ($2,000 on a $100k account) calculated as $| \text{entry} - \text{sl} | \times \text{size}$ (rejects with 403 Forbidden).
    - **Directional Level Verification**: Ensures proper alignment between Entry, Stop Loss, and Take Profit.
  - **Position Tracking**: Monitor live open simulated positions.
- **Rate Limiting**: Server-side IP rate limiter (60 requests per minute per IP) with standard `RateLimit-*` and `Retry-After` headers.
- **Strict Input Validation**: Symbol normalization (e.g. `BTC` -> `BTCUSDT`), supported timeframe verification, and limit boundaries.

## Getting Started

### Prerequisites

- Node.js >= 20.0.0
- npm >= 10.0.0

### Installation

1. Install dependencies:
   ```bash
   npm install
   ```

2. Push Prisma database schema to SQLite:
   ```bash
   npx prisma db push
   ```

3. (Optional) Generate Prisma Client:
   ```bash
   npx prisma generate
   ```

### Development & Scripts

- **Run in development mode**:
  ```bash
  npm run dev
  ```
- **Build TypeScript**:
  ```bash
  npm run build
  ```
- **Start production server**:
  ```bash
  npm start
  ```
- **Run linter**:
  ```bash
  npm run lint
  ```
- **Run automated test suite**:
  ```bash
  npm test
  ```

---

## API Reference

### 1. `GET /api/candles`

Fetches candlestick data for a given cryptocurrency trading pair.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `string` | **Yes** | — | Uppercase alphanumeric ticker (e.g., `BTCUSDT`, `BTC`, `ETHUSDT`). If USDT suffix is omitted, it is automatically appended. |
| `timeframe` | `string` | No | `15m` | Candle interval. Supported: `5m`, `15m`, `1h`, `4h`, `1d`. |
| `limit` | `integer`| No | `100` | Number of candles to return (between `1` and `1000`). |

#### Example Request

```bash
curl -i "http://localhost:3000/api/candles?symbol=BTCUSDT&timeframe=15m&limit=100"
```

---

### 2. `GET /api/mtf`

Computes technical indicators (EMA, RSI) on market data close prices for a given symbol and timeframe.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `string` | **Yes** | — | Uppercase alphanumeric ticker (e.g. `BTCUSDT`, `BTC`). |
| `indicators` | `string` | **Yes** | — | Comma-separated list of indicators to compute: `ema`, `rsi`, or `ema,rsi`. |
| `timeframe` | `string` | No | `15m` | Candle interval. Supported: `5m`, `15m`, `1h`, `4h`, `1d`. |
| `limit` | `integer`| No | `100` | Number of underlying candles to fetch (between `1` and `1000`). |
| `emaPeriod` | `integer`| No | `14` | Lookback period for EMA. |
| `rsiPeriod` | `integer`| No | `14` | Lookback period for RSI. |

#### Example Request

```bash
curl -i "http://localhost:3000/api/mtf?symbol=BTCUSDT&timeframe=15m&indicators=ema,rsi"
```

---

### 3. `GET /api/scan`

Runs quantitative Smart Money Concepts (SMC) analysis on candle data, identifying Fair Value Gaps (FVG), Order Blocks (OB), structural shifts (BOS), and actionable trade setups.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `string` | **Yes** | — | Uppercase alphanumeric ticker (e.g., `BTCUSDT`, `BTC`, `ETHUSDT`). |
| `timeframe` | `string` | No | `15m` | Candle interval. Supported: `5m`, `15m`, `1h`, `4h`, `1d`. |
| `limit` | `integer`| No | `100` | Number of candles to scan (between `1` and `1000`). |

#### Example Request

```bash
curl -i "http://localhost:3000/api/scan?symbol=BTCUSDT&timeframe=15m&limit=100"
```

---

### 4. `POST /api/paper/trade`

Routes a simulated trade through the pre-execution Risk Gate.

#### Request Body

```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entryPrice": 65000.0,
  "sl": 64000.0,
  "tp": 68000.0,
  "size": 1.0
}
```

#### Example Response (`201 Created`)

```json
{
  "message": "Paper trade executed successfully.",
  "trade": {
    "id": 1,
    "symbol": "BTCUSDT",
    "side": "BUY",
    "entryPrice": 65000.0,
    "sl": 64000.0,
    "tp": 68000.0,
    "size": 1.0,
    "status": "OPEN",
    "createdAt": "2026-08-24T15:10:00.000Z"
  }
}
```

---

### 5. `GET /api/paper/positions`

Retrieves all currently active open paper trading positions.

#### Example Request

```bash
curl -i "http://localhost:3000/api/paper/positions"
```
