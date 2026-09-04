# 🔐 SKY / CTB — Environment Configuration Reference

This document provides the canonical reference for all environment variables used across the Python Quantitative Core, Node.js Paper Trading Engine, and React Frontend.

---

## Core Security & Network Configuration

| Variable | Type | Default | Required | Description |
|:---|:---:|:---:|:---:|:---|
| `API_KEY` | `string` | *(empty)* | Recommended | Shared secret key for administrative and mutating endpoints (`X-API-Key` or `Authorization: Bearer <key>`). In dev, passthrough if unset. |
| `CORS_ORIGIN` | `string` | `*` | Production | Comma-separated list of allowed origins (e.g. `https://trading.mypropfirm.com`). |
| `TRUST_PROXY_XFF` | `bool` | `false` | Behind proxy | Set `true` ONLY when the service is reachable exclusively behind Caddy/nginx, which overwrites `X-Forwarded-For`. When unset/`false`, the rate limiter ignores `X-Forwarded-For` to prevent client spoofing of per-IP quotas. |
| `TELEGRAM_WEBHOOK_SECRET` | `string` | *(empty)* | Production | Shared secret Telegram sends as `X-Telegram-Bot-Api-Secret-Token` on webhooks. When set, `/api/telegram/webhook` rejects requests with a missing/mismatched token. |
| `PORT` | `number` | `3000` | No | Listening port for the Node.js Express server. |
| `PYTHON_PORT` | `number` | `8000` | No | Listening port for the Python FastAPI server. |
| `NODE_ENV` | `string` | `development` | No | Application lifecycle environment (`development`, `test`, `production`). |

---

## Market Data & External APIs

| Variable | Type | Default | Required | Description |
|:---|:---:|:---:|:---:|:---|
| `GEMINI_API_KEY` | `string` | *(empty)* | Optional | Google Gemini API key for natural language executive briefs and Ask Desk assistant. (Fallback to deterministic SMC rules if unset). |
| `BINANCE_BASE_URL` | `string` | `https://api.binance.com` | No | Base URL for Binance REST market candle queries. |
| `BYBIT_BASE_URL` | `string` | `https://api.bybit.com` | No | Base URL for Bybit V5 fallback REST queries. |

---

## Database & Persistence Configuration

| Variable | Type | Default | Required | Description |
|:---|:---:|:---:|:---:|:---|
| `DATABASE_URL` | `string` | `file:./dev.db` | Yes | SQLite connection URI for Prisma / Node.js Paper Desk. |
| `DATA_DIR` | `string` | `data` | No | Storage directory path for Python SQLite databases (`market.db`, `brain.db`, `experiments.db`). |
| `BACKUP_DIR` | `string` | `data/backups` | No | Destination folder for automated `.tar.gz` SQLite snapshots. |

---

## Quantitative Risk & Execution Limits

| Variable | Type | Default | Description |
|:---|:---:|:---:|:---|
| `MAX_DAILY_DRAWDOWN_PCT` | `number` | `3.0` | Circuit breaker trip threshold. All entries blocked if breached. |
| `MAX_LEVERAGE` | `number` | `5.0` | Maximum allowable gross leverage on any single trading setup. |
| `KELLY_FRACTION` | `number` | `0.5` | Fractional Kelly multiplier for optimal mathematical capital sizing. |
| `SLIPPAGE_TOLERANCE_BPS` | `number` | `15.0` | Maximum acceptable execution slippage in basis points. |
| `MAX_PAPER_OPEN_POSITIONS` | `number` | `3` | FastAPI paper-trading risk gate: maximum concurrent open positions. |
| `MAX_PAPER_ACCOUNT_BALANCE` | `number` | `100000` | FastAPI paper-trading risk gate: notional account balance used for risk-per-trade %. |
| `MAX_PAPER_RISK_PCT` | `number` | `0.02` | FastAPI paper-trading risk gate: maximum risk per trade as a fraction of account balance (2%). |

---

## Production Security Best Practices

1. **Never commit `.env` files** to version control. Keep `.env` in `.gitignore`.
2. **Always set a high-entropy `API_KEY`** (>= 32 characters) on public VPS instances:
   ```bash
   openssl rand -hex 32
   ```
3. **Restrict `CORS_ORIGIN`** strictly to your frontend domain in production.
