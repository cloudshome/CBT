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

#### Example Response (`200 OK`)

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "indicators": {
    "ema": [
      { "ts": 1787550300000, "value": 77120.45 },
      { "ts": 1787551200000, "value": 77180.12 }
    ],
    "rsi": [
      { "ts": 1787550300000, "value": 62.45 },
      { "ts": 1787551200000, "value": 65.80 }
    ]
  }
}
```
