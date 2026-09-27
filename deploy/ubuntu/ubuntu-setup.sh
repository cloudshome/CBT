#!/usr/bin/env bash
# =============================================================================
#  ubuntu-setup.sh  —  CBT Ubuntu 24H Server — One-Shot Setup
#
#  Run this ONCE on your Ubuntu PC as a user with sudo.
#  It will:
#    1. Install system dependencies (python3, node, npm, git)
#    2. Create a dedicated 'cbt' system user
#    3. Clone the repo
#    4. Locate the app root inside the checkout (see note below)
#    5. Create .env from .env.example (prompts you to fill in secrets)
#    6. Set up Python venv + pip install
#    7. Build Express backend + frontend
#    8. Set up Prisma DB + SDCC node identity
#    9. Install systemd services + auto-sync timer (paths rendered for THIS box)
#   10. Enable auto-start on boot and start everything now
#
#  ── WHY STEP 4 EXISTS ───────────────────────────────────────────────────────
#  The CTB repository nests the application below the repo root:
#
#      /home/cbt/CBT                      <- git clone target (repo root)
#      └── Users/azims/CBT                <- the actual app (.env.example,
#                                            package.json, app.py, frontend/)
#
#  That is the same path CI builds from (`working-directory: Users/azims/CBT`).
#  Every path in this script is therefore *detected*, never hardcoded, so it
#  works for any username, any home directory, and for a flattened checkout
#  where the app sits at the repo root.
#
#  Usage:
#    chmod +x ubuntu-setup.sh
#    sudo bash ubuntu-setup.sh
#
#  Overrides (all optional):
#    sudo CBT_USER=cbt REPO_DIR=/srv/CTB bash ubuntu-setup.sh
# =============================================================================
set -euo pipefail

# --------------------------------------------------------------------------- #
# CONFIG — change these if needed (or override via environment)
# --------------------------------------------------------------------------- #
CBT_USER="${CBT_USER:-cbt}"
# Resolve the home dir BEFORE deriving REPO_DIR: if the 'cbt' user already
# exists with a non-default home, /home/cbt would be the wrong guess.
if [ -n "${CBT_HOME:-}" ]; then
    :                                   # explicit override wins
elif id "$CBT_USER" &>/dev/null; then
    CBT_HOME="$(getent passwd "$CBT_USER" | cut -d: -f6)"
else
    CBT_HOME="/home/$CBT_USER"
fi
REPO_URL="${REPO_URL:-https://github.com/cloudshome/CBT.git}"
REPO_DIR="${REPO_DIR:-$CBT_HOME/CBT}"
SYNC_SCRIPT="/usr/local/bin/cbt-sync.sh"
HEALTH_SCRIPT="/usr/local/bin/cbt-health"
DEPLOY_SCRIPT="/usr/local/bin/cbt-deploy"
CBT_CONFIG_DIR="/etc/cbt"
CBT_CONFIG="$CBT_CONFIG_DIR/cbt.env"
NODE_MAJOR=20    # Node.js LTS version
PYTHON_MIN_MINOR=11   # oldest supported python3 minor (wheel availability)
PYTHON_MAX_MINOR=13   # newest supported python3 minor (see deploy/install_bare_metal.sh)

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
NODE_BIN="$(command -v node)"
NPX_BIN="$(command -v npx)"

# Python version guard — the pinned quant stack (numpy<2.2, scipy<1.15,
# pandas<2.3, pydantic 2.10) only ships wheels for 3.11–3.13. On 3.14+ pip
# silently compiles from source for ~1 hour and then fails on pydantic-core.
PY_MINOR="$(python3 -c 'import sys;print(sys.version_info[1])')"
if [ "$PY_MINOR" -gt "$PYTHON_MAX_MINOR" ]; then
    die "python3 is 3.${PY_MINOR} — too new for the pinned quant stack (needs 3.${PYTHON_MIN_MINOR}–3.${PYTHON_MAX_MINOR}).
        Install a supported interpreter and re-run, e.g.:
          sudo apt-get install -y python3.13 python3.13-venv
          sudo CBT_PYTHON=python3.13 bash ubuntu-setup.sh
        (or use the 2-minute uv route documented in deploy/install_bare_metal.sh)"
elif [ "$PY_MINOR" -lt "$PYTHON_MIN_MINOR" ]; then
    warn "python3 is 3.${PY_MINOR} — older than the tested 3.${PYTHON_MIN_MINOR}+ range; venv build may fail."
else
    ok "Python $(python3 --version 2>&1)"
fi
PYTHON_BIN="${CBT_PYTHON:-python3}"

# --------------------------------------------------------------------------- #
# STEP 2 — Create 'cbt' system user
# --------------------------------------------------------------------------- #
if ! id "$CBT_USER" &>/dev/null; then
    log "Creating system user '$CBT_USER' ..."
    useradd -r -m -d "$CBT_HOME" -s /bin/bash "$CBT_USER"
    ok "User '$CBT_USER' created at $CBT_HOME"
else
    ok "User '$CBT_USER' already exists (home: $CBT_HOME)."
fi

# The repo is private, so the nightly auto-sync must authenticate WITHOUT a
# terminal. Persist whatever is typed once into ~/.git-credentials.
case "$REPO_URL" in
    git@*|ssh://*) IS_SSH=1 ;;
    *)             IS_SSH=0 ;;
esac
if [ "$IS_SSH" -eq 0 ]; then
    sudo -u "$CBT_USER" -H git config --global credential.helper store
fi

# --------------------------------------------------------------------------- #
# STEP 3 — Clone repo
# --------------------------------------------------------------------------- #
if [ -d "$REPO_DIR/.git" ]; then
    warn "Repo already exists at $REPO_DIR — skipping clone."
else
    log "Cloning $REPO_URL ..."
    log "(private repo: enter your GitHub username + a Personal Access Token,"
    log " NOT your password — it is saved so auto-sync works unattended)"
    sudo -u "$CBT_USER" -H git clone "$REPO_URL" "$REPO_DIR"
    ok "Repo cloned to $REPO_DIR"
fi

# --------------------------------------------------------------------------- #
# STEP 4 — Locate the application root inside the checkout
# --------------------------------------------------------------------------- #
# Returns the shallowest directory under $1 that holds both .env.example and
# package.json — i.e. the app root, whether the checkout is nested
# (repo/Users/<name>/CBT) or flattened (repo root).
detect_project_dir() {
    local repo="$1" entry dir
    if [ -f "$repo/.env.example" ] && [ -f "$repo/package.json" ]; then
        printf '%s\n' "$repo"
        return 0
    fi
    while read -r entry; do
        [ -n "$entry" ] || continue
        dir="${entry#* }"
        if [ -f "$dir/package.json" ]; then
            printf '%s\n' "$dir"
            return 0
        fi
    done < <(find "$repo" -mindepth 2 -maxdepth 5 -type f -name '.env.example' \
                 -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
                 -printf '%d %h\n' 2>/dev/null | sort -n)
    return 1
}

log "Locating application root inside $REPO_DIR ..."
PROJECT_DIR="$(detect_project_dir "$REPO_DIR")" \
    || die "Could not find the CBT app root (a folder with .env.example + package.json) under $REPO_DIR.
       Is the clone complete? Try: sudo rm -rf $REPO_DIR && sudo bash ubuntu-setup.sh"
if [ "$PROJECT_DIR" = "$REPO_DIR" ]; then
    PROJECT_REL="."
else
    PROJECT_REL="${PROJECT_DIR#"$REPO_DIR"/}"
fi
ok "App root → $PROJECT_DIR   (nested at: $PROJECT_REL)"

# Everything below operates on the APP ROOT, not the repo root.
DEPLOY_DIR="$PROJECT_DIR/deploy/ubuntu"
[ -d "$DEPLOY_DIR" ] || die "Expected deploy helpers at $DEPLOY_DIR — clone looks incomplete."

# --------------------------------------------------------------------------- #
# STEP 4b — Persist discovered paths for the sync/health helpers + units
# --------------------------------------------------------------------------- #
log "Writing path config → $CBT_CONFIG ..."
mkdir -p "$CBT_CONFIG_DIR"
cat > "$CBT_CONFIG" <<EOF
# Generated by ubuntu-setup.sh on $(date '+%Y-%m-%d %H:%M:%S').
# Sourced by cbt-sync.sh / cbt-health.sh so no script hardcodes a home dir.
# Re-generate any time you move the checkout: sudo bash $DEPLOY_DIR/ubuntu-setup.sh
CBT_USER=$CBT_USER
CBT_HOME=$CBT_HOME
CBT_REPO_DIR=$REPO_DIR
CBT_PROJECT_DIR=$PROJECT_DIR
CBT_PROJECT_REL=$PROJECT_REL
EOF
chmod 644 "$CBT_CONFIG"
ok "Config written"

# --------------------------------------------------------------------------- #
# STEP 4c — Verify unattended git auth (the sync timer has no keyboard)
# --------------------------------------------------------------------------- #
log "Verifying git can fetch without prompting ..."
if sudo -u "$CBT_USER" -H env GIT_TERMINAL_PROMPT=0 git -C "$REPO_DIR" fetch origin --quiet 2>/dev/null; then
    ok "Unattended git auth works — auto-sync will not hang."
else
    warn "Git could NOT authenticate non-interactively (private repo)."
    warn "The nightly auto-sync would fail until this is fixed. Two options:"
    warn "  A) Store a Personal Access Token (repo scope) now — enter it below."
    warn "  B) Switch the remote to SSH:  sudo -u $CBT_USER -H git -C $REPO_DIR remote set-url origin git@github.com:cloudshome/CBT.git"
    echo ""
    read -rp "   Press ENTER to enter credentials now (Ctrl-C to skip and fix later) ..." || true
    sudo -u "$CBT_USER" -H git -C "$REPO_DIR" fetch origin \
        && ok "Credentials stored in $CBT_HOME/.git-credentials" \
        || warn "Still failing — auto-sync disabled until fixed. See $DEPLOY_DIR/README.md"
fi

# --------------------------------------------------------------------------- #
# STEP 5 — .env setup
# --------------------------------------------------------------------------- #
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log "Creating .env from .env.example ..."
    sudo -u "$CBT_USER" -H cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"

    # Replace the shipped dev placeholder with a real random secret.
    if grep -q '^SECRET_KEY=CHANGE_ME_DEV_PLACEHOLDER_NOT_FOR_PRODUCTION$' "$PROJECT_DIR/.env"; then
        NEW_SECRET="$("$PYTHON_BIN" -c 'import secrets;print(secrets.token_urlsafe(48))')"
        sudo -u "$CBT_USER" -H sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${NEW_SECRET}|" "$PROJECT_DIR/.env"
        ok "Generated a random SECRET_KEY"
    fi

    warn "⚠️  YOU MUST EDIT $PROJECT_DIR/.env and fill in your secrets!"
    warn "   Required: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, API_KEY"
    warn "   Edit with:  sudo nano $PROJECT_DIR/.env"
    warn "   After editing, re-run: sudo systemctl restart cbt-fastapi cbt-express cbt-frontend"
    echo ""
    read -rp "   Press ENTER to continue (you can edit .env now or later) ..." || true
else
    ok ".env already exists — skipping."
fi

# App-owned runtime dirs (data/ and credentials/ are gitignored, so absent
# after a fresh clone; the app and Prisma expect them to exist).
log "Creating runtime directories ..."
sudo -u "$CBT_USER" -H mkdir -p "$PROJECT_DIR/data/logs" "$PROJECT_DIR/data/backups" \
                             "$PROJECT_DIR/data/collective/node" "$PROJECT_DIR/credentials"
ok "data/ + credentials/ ready"

# --------------------------------------------------------------------------- #
# STEP 6 — Python virtualenv + install deps
# --------------------------------------------------------------------------- #
log "Setting up Python virtual environment ..."
sudo -u "$CBT_USER" -H "$PYTHON_BIN" -m venv "$PROJECT_DIR/.venv"
sudo -u "$CBT_USER" -H "$PROJECT_DIR/.venv/bin/pip" install --upgrade pip --quiet
sudo -u "$CBT_USER" -H "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet
ok "Python venv ready at $PROJECT_DIR/.venv"

# --------------------------------------------------------------------------- #
# STEP 7 — Node deps + build
# --------------------------------------------------------------------------- #
log "Installing Node dependencies ..."
sudo -u "$CBT_USER" -H bash -c "cd '$PROJECT_DIR' && npm ci --silent"
sudo -u "$CBT_USER" -H bash -c "cd '$PROJECT_DIR' && npm --prefix frontend ci --silent"
ok "Node deps installed"

log "Building Express TypeScript backend ..."
sudo -u "$CBT_USER" -H bash -c "cd '$PROJECT_DIR' && npm run build:backend --silent"
ok "Express backend built → $PROJECT_DIR/dist/"

log "Building Vite frontend (production) ..."
sudo -u "$CBT_USER" -H bash -c "cd '$PROJECT_DIR' && npm run frontend:build --silent"
ok "Frontend built → $PROJECT_DIR/frontend/dist/"

# --------------------------------------------------------------------------- #
# STEP 8 — Prisma DB & SDCC Identity
# --------------------------------------------------------------------------- #
log "Setting up Prisma DB schema ..."
sudo -u "$CBT_USER" -H bash -c "cd '$PROJECT_DIR' && npx prisma generate && npx prisma db push --skip-generate" || \
    warn "Prisma db push failed — run manually: cd '$PROJECT_DIR' && npx prisma db push"
ok "Prisma DB ready"

if [ ! -f "$PROJECT_DIR/data/collective/node/node_identity.json" ]; then
    log "Initializing SDCC Cluster Node Identity (UBUNTU-01) ..."
    sudo -u "$CBT_USER" -H bash -c "cd '$PROJECT_DIR' && .venv/bin/python scripts/sky_cluster_sync.py --init --node-id UBUNTU-01 --role RESEARCH_WORKER" || \
        warn "SDCC node init skipped — run manually: cd '$PROJECT_DIR' && .venv/bin/python scripts/sky_cluster_sync.py --init --node-id UBUNTU-01"
    ok "SDCC Node Identity initialized"
fi

# --------------------------------------------------------------------------- #
# STEP 9 — Install sync / health / deploy commands
# --------------------------------------------------------------------------- #
log "Installing helper commands ..."
install -m 0755 "$DEPLOY_DIR/cbt-sync.sh"   "$SYNC_SCRIPT"
install -m 0755 "$DEPLOY_DIR/cbt-health.sh" "$HEALTH_SCRIPT"
install -m 0755 "$DEPLOY_DIR/cbt-deploy"    "$DEPLOY_SCRIPT"
ok "cbt-sync.sh → $SYNC_SCRIPT"
ok "cbt-health  → $HEALTH_SCRIPT   (usage: sudo cbt-health)"
ok "cbt-deploy  → $DEPLOY_SCRIPT   (usage: sudo cbt-deploy)"

# --------------------------------------------------------------------------- #
# STEP 10 — Install systemd units (render placeholders for THIS machine)
# --------------------------------------------------------------------------- #
log "Installing systemd service units ..."
UNITS=("cbt-fastapi.service" "cbt-express.service" "cbt-frontend.service" "cbt-sync.service" "cbt-sync.timer")
for unit in "${UNITS[@]}"; do
    sed -e "s|__CBT_USER__|$CBT_USER|g" \
        -e "s|__CBT_PROJECT_DIR__|$PROJECT_DIR|g" \
        -e "s|__CBT_REPO_DIR__|$REPO_DIR|g" \
        -e "s|__NODE_BIN__|$NODE_BIN|g" \
        -e "s|__NPX_BIN__|$NPX_BIN|g" \
        "$DEPLOY_DIR/$unit" > "/etc/systemd/system/$unit"
    ok "  Installed /etc/systemd/system/$unit"
done

# Safety net: a unit that still contains a placeholder token would fail with a
# confusing 203/EXEC or "chdir failed" at start-up — catch it here instead.
if grep -l '__[A-Z_]*__' /etc/systemd/system/cbt-*.service /etc/systemd/system/cbt-*.timer 2>/dev/null; then
    die "Rendered units still contain placeholders (listed above). Aborting before daemon-reload."
fi
ok "All unit paths rendered (no placeholders left)"

systemctl daemon-reload

# --------------------------------------------------------------------------- #
# STEP 11 — Enable + start
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
echo "  Paths:"
echo "    Repo root   → $REPO_DIR"
echo "    App root    → $PROJECT_DIR"
echo "    Env file    → $PROJECT_DIR/.env"
echo "    Path config → $CBT_CONFIG"
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
echo "    sudo cbt-deploy                      # ← Deploy now after a git push"
echo "    sudo cbt-health                      # ← Full health check"
echo "    sudo journalctl -fu cbt-fastapi      # FastAPI live logs"
echo "    sudo journalctl -fu cbt-express      # Express live logs"
echo "    sudo journalctl -fu cbt-sync         # Sync history"
echo ""
echo "  Auto-sync: daily at midnight + 60s after boot (manual: sudo cbt-deploy)"
echo ""
echo "  ⚠️  Remember to fill in $PROJECT_DIR/.env with your real secrets!"
echo ""
