#!/usr/bin/env bash
# =============================================================================
#  ubuntu-setup.sh  —  CBT Ubuntu 24H Server — One-Shot Setup
#
#  Run this ONCE on your Ubuntu PC as a user with sudo.
#  It will:
#    1. Create a dedicated 'cbt' system user
#    2. Install system dependencies (python3, node, npm, git)
#    3. Clone the repo
#    4. Create .env from .env.example (prompts you to fill in secrets)
#    5. Set up Python venv + pip install
#    6. Build Express backend + frontend
#    7. Set up Prisma DB
#    8. Install systemd services + auto-sync timer
#    9. Enable auto-start on boot
#   10. Start everything now
#
#  Usage:
#    chmod +x ubuntu-setup.sh
#    sudo bash ubuntu-setup.sh
# =============================================================================
set -euo pipefail

# --------------------------------------------------------------------------- #
# CONFIG — change these if needed
# --------------------------------------------------------------------------- #
CBT_USER="cbt"
CBT_HOME="/home/cbt"
REPO_URL="https://github.com/cloudshome/CTB.git"
REPO_DIR="$CBT_HOME/CBT"
SYNC_SCRIPT="/usr/local/bin/cbt-sync.sh"
NODE_MAJOR=20    # Node.js LTS version
PYTHON_MIN="3.11"

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()     { echo -e "${CYAN}[SETUP]${NC} $*"; }
ok()      { echo -e "${GREEN}[  OK  ]${NC} $*"; }
warn()    { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
die()     { echo -e "${RED}[FATAL ]${NC} $*" >&2; exit 1; }

# Must be root
[ "$(id -u)" -eq 0 ] || die "Run this script with sudo: sudo bash ubuntu-setup.sh"

# --------------------------------------------------------------------------- #
# STEP 1 — System dependencies
# --------------------------------------------------------------------------- #
log "Installing system dependencies ..."
apt-get update -qq
apt-get install -y -qq git curl build-essential python3 python3-pip python3-venv python3-full

# Node.js via NodeSource
if ! command -v node &>/dev/null || [ "$(node -e 'process.stdout.write(process.versions.node.split(".")[0])')" -lt "$NODE_MAJOR" ]; then
    log "Installing Node.js $NODE_MAJOR LTS ..."
    curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - 2>/dev/null
    apt-get install -y -qq nodejs
fi
ok "Node $(node --version) | npm $(npm --version)"

# --------------------------------------------------------------------------- #
# STEP 2 — Create 'cbt' system user
# --------------------------------------------------------------------------- #
if ! id "$CBT_USER" &>/dev/null; then
    log "Creating system user '$CBT_USER' ..."
    useradd -r -m -d "$CBT_HOME" -s /bin/bash "$CBT_USER"
    ok "User '$CBT_USER' created at $CBT_HOME"
else
    ok "User '$CBT_USER' already exists."
fi

# --------------------------------------------------------------------------- #
# STEP 3 — Clone repo
# --------------------------------------------------------------------------- #
if [ -d "$REPO_DIR/.git" ]; then
    warn "Repo already exists at $REPO_DIR — skipping clone."
else
    log "Cloning $REPO_URL ..."
    sudo -u "$CBT_USER" git clone "$REPO_URL" "$REPO_DIR"
    ok "Repo cloned to $REPO_DIR"
fi

# --------------------------------------------------------------------------- #
# STEP 4 — .env setup
# --------------------------------------------------------------------------- #
if [ ! -f "$REPO_DIR/.env" ]; then
    log "Creating .env from .env.example ..."
    sudo -u "$CBT_USER" cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    warn "⚠️  YOU MUST EDIT $REPO_DIR/.env and fill in your secrets!"
    warn "   Required: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, SECRET_KEY, API_KEY"
    warn "   After editing, re-run: sudo systemctl restart cbt-fastapi cbt-express cbt-frontend"
    echo ""
    read -rp "   Press ENTER to continue (you can edit .env now or later) ..."
else
    ok ".env already exists — skipping."
fi

# --------------------------------------------------------------------------- #
# STEP 5 — Python virtualenv + install deps
# --------------------------------------------------------------------------- #
log "Setting up Python virtual environment ..."
sudo -u "$CBT_USER" python3 -m venv "$REPO_DIR/.venv"
sudo -u "$CBT_USER" "$REPO_DIR/.venv/bin/pip" install --upgrade pip --quiet
sudo -u "$CBT_USER" "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt" --quiet
ok "Python venv ready at $REPO_DIR/.venv"

# --------------------------------------------------------------------------- #
# STEP 6 — Node deps + build
# --------------------------------------------------------------------------- #
log "Installing Node dependencies ..."
sudo -u "$CBT_USER" bash -c "cd $REPO_DIR && npm ci --silent"
sudo -u "$CBT_USER" bash -c "cd $REPO_DIR && npm --prefix frontend ci --silent"
ok "Node deps installed"

log "Building Express TypeScript backend ..."
sudo -u "$CBT_USER" bash -c "cd $REPO_DIR && npm run build:backend --silent"
ok "Express backend built → dist/"

log "Building Vite frontend (production) ..."
sudo -u "$CBT_USER" bash -c "cd $REPO_DIR && npm run frontend:build --silent"
ok "Frontend built → frontend/dist/"

# --------------------------------------------------------------------------- #
# STEP 7 — Prisma DB
# --------------------------------------------------------------------------- #
log "Applying Prisma migrations ..."
sudo -u "$CBT_USER" bash -c "cd $REPO_DIR && npx prisma migrate deploy" || \
    warn "Prisma migrate failed — run manually: cd $REPO_DIR && npx prisma migrate deploy"
ok "Prisma DB ready"

# --------------------------------------------------------------------------- #
# STEP 8 — Install sync script
# --------------------------------------------------------------------------- #
log "Installing cbt-sync.sh ..."
cp "$REPO_DIR/deploy/ubuntu/cbt-sync.sh" "$SYNC_SCRIPT"
chmod +x "$SYNC_SCRIPT"
ok "Sync script → $SYNC_SCRIPT"

# --------------------------------------------------------------------------- #
# STEP 9 — Install systemd units
# --------------------------------------------------------------------------- #
log "Installing systemd service units ..."
UNITS=("cbt-fastapi.service" "cbt-express.service" "cbt-frontend.service" "cbt-sync.service" "cbt-sync.timer")
for unit in "${UNITS[@]}"; do
    cp "$REPO_DIR/deploy/ubuntu/$unit" "/etc/systemd/system/$unit"
    ok "  Installed /etc/systemd/system/$unit"
done

systemctl daemon-reload

# --------------------------------------------------------------------------- #
# STEP 10 — Enable + start
# --------------------------------------------------------------------------- #
log "Enabling services to start on boot ..."
systemctl enable cbt-fastapi cbt-express cbt-frontend cbt-sync.timer
ok "Auto-start enabled"

log "Starting services now ..."
systemctl start cbt-fastapi
sleep 3
systemctl start cbt-express
sleep 2
systemctl start cbt-frontend
sleep 2
systemctl start cbt-sync.timer

# --------------------------------------------------------------------------- #
# Final status report
# --------------------------------------------------------------------------- #
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}   CBT Ubuntu Server Setup Complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  Service status:"
for svc in cbt-fastapi cbt-express cbt-frontend cbt-sync.timer; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "active" ]; then
        echo -e "    ${GREEN}●${NC} $svc — ${GREEN}$STATUS${NC}"
    else
        echo -e "    ${RED}●${NC} $svc — ${RED}$STATUS${NC}"
    fi
done
echo ""
echo "  Access:"
echo "    Frontend  → http://localhost:5173"
echo "    Express   → http://localhost:3000"
echo "    FastAPI   → http://localhost:8000"
echo ""
echo "  Useful commands:"
echo "    sudo journalctl -fu cbt-fastapi      # FastAPI logs"
echo "    sudo journalctl -fu cbt-express      # Express logs"
echo "    sudo journalctl -fu cbt-frontend     # Frontend logs"
echo "    sudo journalctl -fu cbt-sync         # Sync logs"
echo "    sudo systemctl list-timers cbt-sync  # Check timer"
echo ""
echo "  ⚠️  Remember to fill in $REPO_DIR/.env with your real secrets!"
echo ""
