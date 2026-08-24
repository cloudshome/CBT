# Crypto Brain Terminal (CTB) Backend

Crypto Brain Terminal (CTB) is an institutional-grade paper trading and research platform for quantitative crypto markets, integrating multi-timeframe confluence, Smart Money Concepts (SMC) scanning, and market intelligence.

## Features

- **Market Candles Endpoint (`/api/candles`)**:
  - Fetches normalized OHLCV candlestick arrays (`[timestamp, open, high, low, close, volume]`) directly from Binance public REST API.
  - Automatically caches responses in local SQLite (`candles_cache` table) via Prisma.
  - Provides instant fallback serving cached candles when Binance API is offline, rate-limited, or unreachable.
  - Strict input validation for symbols, supported timeframes, and limits.

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

#### Example Request

```bash
curl "http://localhost:3000/api/candles?symbol=BTCUSDT&timeframe=15m&limit=100"
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

#### Caching & Fallback Behavior

- When fresh data is fetched from Binance REST API, all returned candles are upserted into SQLite (`candles_cache`).
- If Binance REST fails (due to network timeout, HTTP error, or rate limiting), the service serves the latest stored candles from SQLite cache and sets the response header `X-Cache: HIT-FALLBACK`.
- If Binance fails and no cached candles exist for the requested pair, the endpoint returns `502 Bad Gateway`.
