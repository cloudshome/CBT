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
  - **Rate Limiting**: Server-side IP rate limiter (60 requests per minute per IP) with standard `RateLimit-*` and `Retry-After` headers.
  - **Automatic Caching**: Any successful fetch (Binance or Bybit) automatically upserts candles to SQLite.
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

### `GET /api/candles`

Fetches candlestick data for a given cryptocurrency trading pair.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `symbol` | `string` | **Yes** | — | Uppercase alphanumeric ticker (e.g., `BTCUSDT`, `BTC`, `ETHUSDT`). If USDT suffix is omitted, it is automatically appended. |
| `timeframe` | `string` | No | `15m` | Candle interval. Supported: `5m`, `15m`, `1h`, `4h`, `1d`. |
| `limit` | `integer`| No | `100` | Number of candles to return (between `1` and `1000`). |

#### Response Headers

- `X-Data-Source`: `BINANCE` | `BYBIT` | `SQLITE_CACHE`
- `X-Cache`: `BYBIT-FALLBACK` (when served by Bybit) | `HIT-FALLBACK` (when served from local cache)
- `RateLimit-Limit`: Maximum requests permitted per window (`60`)
- `RateLimit-Remaining`: Remaining request quota in current window
- `RateLimit-Reset`: Seconds until rate limit quota resets

#### Example Request

```bash
curl -i "http://localhost:3000/api/candles?symbol=BTCUSDT&timeframe=15m&limit=100"
```

#### Example Response (`200 OK`)

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "candles": [
    [1700000000000, 65120.5, 65400.0, 65050.0, 65350.2, 145.892],
    [1700000900000, 65350.2, 65600.0, 65300.0, 65520.0, 198.341]
  ]
}
```
