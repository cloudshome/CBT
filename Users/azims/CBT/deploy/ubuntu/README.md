# CBT Ubuntu Server — Setup Guide

This folder contains everything needed to run CBT as a 24H auto-syncing
server on your Ubuntu home PC.

---

## ⚠️ Read this first: the repository is nested

The CTB repo does **not** keep the application at the repository root. `git clone`
gives you this:

```
/home/cbt/CBT                      ← repo root (has .git, AGENTS.md, DIRECTION.md)
└── Users/azims/CBT                ← APP ROOT: .env.example, package.json,
                                     requirements.txt, app.py, frontend/, deploy/
```

That nesting is deliberate — GitHub Actions builds from the same path
(`working-directory: Users/azims/CBT` in `.github/workflows/ci.yml`).

**Consequence:** `.env`, `.venv`, `node_modules`, `dist/` and the systemd
`WorkingDirectory` all belong to the **app root**, not the repo root. An older
version of `ubuntu-setup.sh` assumed the two were the same and died with:

```
cp: cannot stat '/home/cbt/CBT/.env.example': No such file or directory
```

The current script **detects** the app root instead of hardcoding it, so it
works for any username, any home directory (`/home/cloudslover/...`,
`/srv/CTB`, …) and for a flattened checkout where app root == repo root.

Detected paths are written to `/etc/cbt/cbt.env`, which `cbt-sync.sh` and
`cbt-health.sh` source — so nothing under `/usr/local/bin` hardcodes a home
directory either:

```ini
CBT_USER=cbt
CBT_HOME=/home/cbt
CBT_REPO_DIR=/home/cbt/CBT
CBT_PROJECT_DIR=/home/cbt/CBT/Users/azims/CBT
CBT_PROJECT_REL=Users/azims/CBT
```

---

## Architecture

```
Windows PC (develop) ──git push──▶ GitHub (CTB) ──git pull──▶ Ubuntu PC (run 24H)
                                                               └─ auto-sync at midnight + 60s after boot
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
| `cbt-sync.service` | systemd oneshot: runs `cbt-sync.sh` (as root) |
| `cbt-sync.timer` | systemd timer: midnight + 60s after boot |
| `cbt-sync.sh` | Sync script: git pull → rebuild → restart services |
| `cbt-health.sh` | Health check: services, ports, git, `.env` presence |
| `cbt-deploy` | Manual "deploy now" wrapper around `cbt-sync.sh` |

The `.service` files contain `__CBT_PROJECT_DIR__` / `__CBT_USER__` /
`__NODE_BIN__` placeholders. **Never copy them into `/etc/systemd/system/` by
hand** — `ubuntu-setup.sh` renders them with your real paths.

---

## One-Time Setup (do this on Ubuntu)

### Step 1 — Get `ubuntu-setup.sh` onto the Ubuntu PC

**Option A: via USB** — copy the entire `CBT/deploy/ubuntu/` folder over.

**Option B: via SCP from Windows (same network)**
```powershell
# Replace UBUNTU_IP with your Ubuntu PC's IP
scp -r C:\Users\azims\CBT\deploy\ubuntu\ ubuntu@UBUNTU_IP:/tmp/cbt-setup/
```

**Option C: raw download** — the script is self-contained; it clones the repo
itself, so only this one file is needed.

### Step 2 — Run it

```bash
chmod +x ubuntu-setup.sh
sudo bash ubuntu-setup.sh
```

Overrides if your layout differs:
```bash
sudo CBT_USER=cbt REPO_DIR=/srv/CTB bash ubuntu-setup.sh
```

The script handles everything:
- Installs Node.js 20 + Python 3 (and refuses Python ≥ 3.14, which has no
  wheels for the pinned quant stack)
- Creates the `cbt` user
- Clones the repo, then **locates the app root inside it**
- Writes `/etc/cbt/cbt.env`
- Verifies git can fetch *without prompting* (see below)
- Creates `.env` from `.env.example` (+ generates a real `SECRET_KEY`)
- Creates `data/` and `credentials/` (both gitignored, so absent after clone)
- Builds Python venv, Express `dist/`, Vite `frontend/dist/`
- Pushes the Prisma schema and initialises the SDCC node identity
- Installs the 5 systemd units with your paths rendered in
- Enables boot auto-start and starts everything

### Step 2b — Private repo: credentials for unattended sync

`cloudshome/CTB` is private, so the clone prompts for a username and password.
A systemd timer has **no keyboard**, so the sync would fail (or hang) unless
credentials are stored. `ubuntu-setup.sh` therefore:

1. sets `credential.helper store` for the `cbt` user *before* cloning, and
2. afterwards runs a `GIT_TERMINAL_PROMPT=0` fetch to prove it works.

When prompted, enter your GitHub username and a **Personal Access Token**
(classic, `repo` scope) — not your account password. It is saved to
`/home/cbt/.git-credentials` (mode 600).

Prefer SSH instead?
```bash
sudo -u cbt ssh-keygen -t ed25519          # add the .pub key to GitHub
sudo -u cbt git -C /home/cbt/CBT remote set-url origin git@github.com:cloudshome/CTB.git
sudo cbt-deploy                            # verify it fetches cleanly
```

### Step 3 — Fill in your `.env` secrets

Note the **app root** path (the setup summary prints the exact one):

```bash
sudo nano /home/cbt/CBT/Users/azims/CBT/.env
```

**Required secrets:**
- `GEMINI_API_KEY=` — your Google Gemini API key
- `TELEGRAM_BOT_TOKEN=` / `TELEGRAM_CHAT_ID=` — Telegram copilot
- `API_KEY=` — protects sensitive endpoints
- `SECRET_KEY=` — already auto-generated by the setup script

Optional, for the SDCC Google Drive mesh: drop
`gdrive_client_secret.json` into `<app root>/credentials/`.

After editing `.env`:
```bash
sudo systemctl restart cbt-fastapi cbt-express cbt-frontend
```

### Step 4 — Verify

```bash
sudo cbt-health
```

---

## Daily Operations

| Task | Command |
|------|---------|
| Full health check | `sudo cbt-health` |
| Deploy now (don't wait for midnight) | `sudo cbt-deploy` |
| FastAPI logs | `sudo journalctl -fu cbt-fastapi` |
| Express logs | `sudo journalctl -fu cbt-express` |
| Frontend logs | `sudo journalctl -fu cbt-frontend` |
| Sync history | `sudo journalctl -fu cbt-sync` |
| Next auto-sync | `systemctl list-timers cbt-sync.timer` |
| Restart after `.env` change | `sudo systemctl restart cbt-fastapi cbt-express cbt-frontend` |

---

## After Power Outage / Reboot

Everything recovers automatically — `WantedBy=multi-user.target`,
`Restart=always`, plus `OnBootSec=60` on the sync timer so a missed nightly
sync is caught a minute after boot. Confirm with `sudo cbt-health`.

---

## Updating (from your dev PC)

1. Push: `git push origin main`
2. Ubuntu pulls at midnight (or run `sudo cbt-deploy` to do it now)
3. `cbt-sync.sh` reinstalls only what changed (`requirements*.txt`,
   `package*.json`, `frontend/`, `prisma/`), always rebuilds the Express
   bundle, then restarts the three services

---

## Access URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Express API | http://localhost:3000 |
| FastAPI | http://localhost:8000 |
| FastAPI Docs | http://localhost:8000/docs |

From other devices on your LAN, swap `localhost` for the Ubuntu PC's IP
(`ip addr show | grep 'inet ' | grep -v 127`).

---

## Troubleshooting

**`cp: cannot stat '/home/cbt/CBT/.env.example': No such file or directory`**
You ran an older `ubuntu-setup.sh` that assumed app root == repo root. Pull the
current one and re-run it — it detects the app root. If it already got partway,
just re-run: every step is idempotent (existing clone/user/`.env` are skipped).

**`Could not find the CBT app root ...`**
The clone is incomplete or empty. `sudo rm -rf /home/cbt/CBT` and re-run.

**Services fail with `status=203/EXEC` or "chdir failed"**
The unit still points at an old path. Re-run `sudo bash ubuntu-setup.sh` (it
re-renders the units from `/etc/cbt/cbt.env`), or inspect:
```bash
systemctl cat cbt-fastapi | grep -E 'WorkingDirectory|ExecStart'
```

**`cbt-sync` logs `Access denied` on `systemctl restart`**
Fixed in the current `cbt-sync.service`: it runs as **root** and drops to the
`cbt` user for git/npm/npx, so builds stay user-owned while restarts succeed.

**`cbt-sync` logs `git fetch failed`**
Credential problem — see Step 2b. Confirm with:
```bash
sudo -u cbt env GIT_TERMINAL_PROMPT=0 git -C /home/cbt/CBT fetch origin
```

**`cbt-sync` logs `git pull --ff-only` refused**
Local edits on the server. `cbt-health` now lists them. Either
`sudo -u cbt git -C /home/cbt/CBT checkout -- <file>` or move the change into
a proper commit on your dev PC.

**Moved the checkout / renamed the user**
Re-run `sudo bash <app root>/deploy/ubuntu/ubuntu-setup.sh`. It rewrites
`/etc/cbt/cbt.env` and re-renders every unit — no manual path editing needed.

---

## Uninstall / Clean

```bash
sudo systemctl stop cbt-fastapi cbt-express cbt-frontend cbt-sync.timer
sudo systemctl disable cbt-fastapi cbt-express cbt-frontend cbt-sync.timer
sudo rm /etc/systemd/system/cbt-*.service /etc/systemd/system/cbt-*.timer
sudo rm /usr/local/bin/cbt-sync.sh /usr/local/bin/cbt-health /usr/local/bin/cbt-deploy
sudo rm -rf /etc/cbt
sudo systemctl daemon-reload
# Optional: remove the app itself
# sudo userdel -r cbt
```
