# Crypto Brain Terminal (CTB)

Crypto Brain Terminal (CTB) is an institutional-grade paper trading and research platform for quantitative crypto markets, integrating multi-timeframe confluence, Smart Money Concepts (SMC) scanning, Gemini desk intelligence, a dark quantitative Trading Desk UI, Progressive Web App (PWA) offline capabilities, a continuous integration (CI) pipeline, and Docker Compose containerization.

---

## Architecture Overview

```
                      +-----------------------------+
                      |         HOST BROWSER        |
                      +--------------+--------------+
                                     |
                                Port 80 (HTTP)
                                     v
                 +---------------------------------------+
                 |          CTB FRONTEND (NGINX)         |
                 |  - Serves static PWA (HTML/CSS/JS)    |
                 |  - Proxies /api/* -> backend:3000     |
                 +-------------------+-------------------+
                                     |
                          Docker Bridge Network
                                     |
                                     v
                 +---------------------------------------+
                 |          CTB BACKEND (EXPRESS)        |
                 |  - Port 3000                          |
                 |  - Quant Engine, Risk Gate, Gemini    |
                 +-------------------+-------------------+
                                     |
                              /app/data/dev.db
                                     v
                        +-------------------------+
                        |  NAMED VOLUME: ctb-data |
                        +-------------------------+
```

- **Frontend**: React 18 + Vite + Tailwind CSS + Lucide Icons + PWA (Service Worker & Web Push)
- **Backend**: Node.js + Express + TypeScript
- **Database**: SQLite via Prisma ORM for paper trading and candle caching
- **AI / ML**: Gemini (`@google/genai`) for desk intelligence and quantitative Q&A
- **Containerization**: Multi-stage Dockerfiles + Nginx Reverse Proxy + Docker Compose
- **CI / CD**: GitHub Actions (`.github/workflows/ci.yml`)

---

## Docker & Docker Compose Deployment

### 1. Prerequisites
- Docker Engine & Docker Compose installed.

### 2. Configure Environment
Create or verify `.env` in the project root:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Build & Start Containers
```bash
# Build images and start services in the background
docker compose up --build -d
```

- **Frontend UI & API Proxy**: `http://localhost` (Port 80)
- **Direct Backend API**: `http://localhost:3000` (Port 3000)
- **Persistent Data**: SQLite database state is persisted in named volume `ctb-sqlite-data`.

### 4. Stop Containers
```bash
docker compose down
```

---

## Local Development (Without Docker)

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

- **Run complete backend test suite**:
  ```bash
  npm test
  ```
- **Run linter**:
  ```bash
  npm run lint
  ```
- **Build both backend and frontend (PWA bundle)**:
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
