# CBT Ubuntu Server — Setup Guide

This folder contains everything needed to run CBT as a 24H auto-syncing
server on your Ubuntu home PC.

---

## Architecture

```
Windows PC (develop) ──git push──▶ GitHub (CTB) ──git pull──▶ Ubuntu PC (run 24H)
                                                               └─ every 5 min auto-sync
                                                               └─ auto-restart on power outage
```

---

## Files in This Folder

| File | What it does |
|------|-------------|
| `ubuntu-setup.sh` | **One-shot installer** — run this once on Ubuntu |
| `cbt-fastapi.service` | systemd service: FastAPI on port 8000 |
| `cbt-express.service` | systemd service: Express API on port 3000 |
| `cbt-frontend.service` | systemd service: Vite preview on port 5173 |
| `cbt-sync.service` | systemd oneshot: runs cbt-sync.sh |
| `cbt-sync.timer` | systemd timer: triggers sync every 5 minutes |
| `cbt-sync.sh` | Sync script: git pull → rebuild → restart services |
| `cbt-health.sh` | Health check: shows status of all services + ports |

---

## One-Time Setup (do this on Ubuntu)

### Step 1 — Copy files to Ubuntu

**Option A: via USB**
Copy the entire `CBT/deploy/ubuntu/` folder to your Ubuntu PC.

**Option B: via SCP from Windows (if Ubuntu is on same network)**
```bash
# Run this on Windows PowerShell, replace UBUNTU_IP with your Ubuntu PC's IP
scp -r C:\Users\azims\CBT\deploy\ubuntu\ ubuntu@UBUNTU_IP:/tmp/cbt-setup/
```

**Option C: Just clone from GitHub**
```bash
# On Ubuntu, the setup script auto-clones the repo
# Just copy ubuntu-setup.sh alone and run it
```

### Step 2 — Run the setup script on Ubuntu

```bash
# On Ubuntu terminal:
chmod +x ubuntu-setup.sh
sudo bash ubuntu-setup.sh
```

That's it! The script handles everything:
- Creates a `cbt` user
- Installs Node.js 20 + Python 3
- Clones the repo
- Sets up Python venv
- Builds Express + frontend
- Installs all 5 systemd units
- Enables auto-start on boot
- Starts all services immediately

### Step 3 — Fill in your .env secrets

```bash
sudo nano /home/cbt/CBT/.env
```

**Required secrets to fill in:**
- `GEMINI_API_KEY=` — your Google Gemini API key
- `TELEGRAM_BOT_TOKEN=` — your Telegram bot token
- `TELEGRAM_CHAT_ID=` — your Telegram chat ID
- `SECRET_KEY=` — generate with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- `API_KEY=` — your API key for protected endpoints

After editing .env:
```bash
sudo systemctl restart cbt-fastapi cbt-express cbt-frontend
```

### Step 4 — Verify everything is running

```bash
sudo bash /usr/local/bin/cbt-health.sh
# or
sudo bash /home/cbt/CBT/deploy/ubuntu/cbt-health.sh
```

---

## Daily Operations

### Check all service status
```bash
sudo bash cbt-health.sh
```

### View live logs
```bash
sudo journalctl -fu cbt-fastapi      # Python backend
sudo journalctl -fu cbt-express      # Node backend
sudo journalctl -fu cbt-frontend     # Frontend
sudo journalctl -fu cbt-sync         # Git sync log
```

### Force a sync now (don't wait 5 minutes)
```bash
sudo /usr/local/bin/cbt-sync.sh
```

### Check when next auto-sync runs
```bash
sudo systemctl list-timers cbt-sync.timer
```

### Restart after .env changes
```bash
sudo systemctl restart cbt-fastapi cbt-express cbt-frontend
```

---

## After Power Outage / Reboot

Everything recovers **automatically** — no action needed.
Services are configured with `WantedBy=multi-user.target` and `Restart=always`.

To confirm recovery after a reboot:
```bash
sudo bash cbt-health.sh
```

---

## Updating (from Windows)

1. Push your changes from Windows: `git push origin main`
2. Ubuntu auto-pulls within 5 minutes — services restart automatically
3. No manual action needed on Ubuntu

---

## Access URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Express API | http://localhost:3000 |
| FastAPI | http://localhost:8000 |
| FastAPI Docs | http://localhost:8000/docs |

To access from other devices on your home network, replace `localhost`
with your Ubuntu PC's local IP (e.g. `http://192.168.1.x:5173`).

Find your Ubuntu IP: `ip addr show | grep 'inet ' | grep -v 127`

---

## Uninstall / Clean

```bash
sudo systemctl stop cbt-fastapi cbt-express cbt-frontend cbt-sync.timer
sudo systemctl disable cbt-fastapi cbt-express cbt-frontend cbt-sync.timer
sudo rm /etc/systemd/system/cbt-*.service /etc/systemd/system/cbt-*.timer
sudo rm /usr/local/bin/cbt-sync.sh
sudo systemctl daemon-reload
```
