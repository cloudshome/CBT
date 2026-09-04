# 📘 SKY / CTB — Production Operations Runbook

> **Target Platform:** Linux Ubuntu 22.04+ / Docker Engine 24+  
> **Classification:** 24/7 Autonomous Quantitative Market Sentinel  
> **Security Level:** Institutional Non-Discretionary Operation  

---

## 1. System Architecture & Port Allocation

| Component | Technology | Internal Port | External Port | Health Probe |
|:---|:---|:---:|:---:|:---|
| **Frontend Terminal** | React 18 + Vite + Nginx | 80 | `80` / `443` | `GET /` |
| **Python Quant Core** | FastAPI + Uvicorn | 8000 | `8000` | `GET /api/health` |
| **Node Paper Desk** | Express + Prisma + SQLite | 3000 | `3000` | `GET /health` |
| **Telemetry & Metrics** | Prometheus Exposition | - | `:8000/metrics`, `:3000/metrics` | `GET /metrics` |

---

## 2. Cold Boot & Service Startup Procedures

### Option A: Production Multi-Container Docker (Recommended)
```bash
# 1. Clone repository and verify environment configuration
cd /opt/cbt
cp .env.example .env # Ensure API_KEY and CORS_ORIGIN are configured

# 2. Build and launch all 3 tiers in background with auto-restart
docker compose up -d --build

# 3. Verify health status of all containers
docker compose ps
```

### Option B: Linux Native Systemd Service
> ⚠️ **Mutually exclusive with Option A.** `orion.service` runs uvicorn directly on
> port 8000, while the Docker stack (`cbt-stack@.service`) also serves that port.
> Enable **exactly one** of the two deployment modes.

```bash
# 1. Install systemd unit definition
sudo cp deploy/systemd/orion.service /etc/systemd/system/
sudo systemctl daemon-reload

# 2. Ensure the Docker stack is stopped (port conflict guard)
sudo systemctl stop cbt-stack@$USER.service || true

# 3. Enable on boot and start service
sudo systemctl enable orion.service
sudo systemctl start orion.service

# 4. Inspect live status
sudo systemctl status orion.service
```

---

## 3. Production Health Probes & Verification

Run the automated production preflight script:
```bash
./deploy/healthcheck.sh
```

Manual endpoint verification:
```bash
# Node.js Readiness & Open Paper Positions
curl -s http://localhost:3000/api/readiness | jq .
curl -s http://localhost:3000/api/metrics/json | jq .

# Python Quantitative Vitals & Audit Bus
curl -s http://localhost:8000/api/health | jq .
curl -s http://localhost:8000/api/telegram/status | jq .

# Prometheus Telemetry Stream
curl -s http://localhost:8000/metrics | head -n 20
curl -s http://localhost:3000/metrics | head -n 20
```

---

## 4. Disaster Recovery & Database Maintenance

### A. Automated Daily Online Backups (Non-Blocking)
Backups use the official SQLite Online Backup API, taking zero table locks and eliminating write contention during active trading.

**Install into root crontab:**
```bash
sudo crontab -e
# Run daily at 02:00 UTC with 14-day automatic retention pruning
0 2 * * * /opt/cbt/deploy/backup_databases.sh >> /var/log/cbt_backup.log 2>&1
```

**Manual Snapshot:**
```bash
python3 deploy/backup_databases.py --retention-days 14
```

### B. Database Growth Management & VACUUM
Reclaims disk space, runs `PRAGMA optimize`, and updates B-Tree table indexes:
```bash
python3 deploy/db_maintenance.py
```

### C. Restoring from a Snapshot Archive
```bash
# 1. Stop trading services
docker compose stop

# 2. Restore using the non-blocking verified restore tool
python3 deploy/restore_databases.py --archive data/backups/cbt_backup_YYYYMMDD_HHMMSSZ.tar.gz

# 3. Restart services
docker compose start
```

---

## 5. Emergency Incident Playbooks

### 🚨 Playbook 1: Exchange Feed Degradation (Circuit Breaker Tripped)
* **Symptom:** `ctb_exchange_circuit_breaker_state` changes from `0 (CLOSED)` to `2 (OPEN)`.
* **Action:** The system automatically fast-fails to Tier 2 (Bybit) or Tier 3 (SQLite Cache) without blocking event loops.
* **Resolution:** Once external API stabilizes, the breaker enters `HALF_OPEN` canary mode and resets to `CLOSED` automatically after 2 successful responses.

### 🚨 Playbook 2: Daily Maximum Drawdown Breaker Hit
* **Symptom:** Account drawdown exceeds `MAX_DAILY_DRAWDOWN_PCT=3.0%`.
* **Action:** Risk Gate automatically rejects all new entry orders with `403 Forbidden` (`RULE_MAX_DAILY_DRAWDOWN_BREACHED`).
* **Resolution:** Positions are managed until natural TP/SL. Circuit automatically resets at 00:00 UTC daily candle close.

### 🚨 Playbook 3: Emergency Kill Switch (Manual Panic Halt)
To immediately close all open shadow and paper positions and reset risk state:
```bash
# 1. Issue authenticated shadow position reset
curl -X POST http://localhost:8000/api/shadow/reset \
  -H "X-API-Key: $API_KEY"

# 2. Stop containers immediately if severe exchange dislocation occurs
docker compose stop
```

---

## 6. Log Inspection & Triage

```bash
# Stream live Python Quantitative telemetry
docker compose logs -f python-backend

# Stream Node Paper Trading logs
docker compose logs -f backend

# Direct disk log files
tail -f data/logs/cbt_terminal.log
```

---

## 7. Production SSL / TLS Reverse-Proxy Setup (Certbot)

To secure the public endpoint with Let's Encrypt TLS:

```bash
# 1. Install Certbot and Nginx plugin
sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx

# 2. Issue TLS certificate for your domain
sudo certbot --nginx -d cbt.yourdomain.com

# 3. Verify automatic certificate renewal cron
sudo certbot renew --dry-run
```

