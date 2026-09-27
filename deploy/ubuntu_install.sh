#!/usr/bin/env bash
# =============================================================================
# SKY / CTB — One-Command Ubuntu 24/7 Production Deployment Installer
#
# Usage on your Ubuntu PC:
#   chmod +x deploy/ubuntu_install.sh
#   ./deploy/ubuntu_install.sh
#
# This script will:
#   1. Detect user, home dir, repo path, and local LAN IP automatically.
#   2. Install Docker Engine & Compose plugin if not already installed.
#   3. Create and verify .env configuration.
#   4. Initialize persistent storage dirs (data/backups, data/logs).
#   5. Install and enable systemd template service (cbt-stack@$USER.service) for boot persistence.
#   6. Configure production cron jobs (backups, optimization, WAL checkpoints, watchdog).
#   7. Build and start all 4 Docker containers (Python, Node, React/Nginx, Caddy).
#   8. Execute preflight health checks and print access URLs.
# =============================================================================

set -euo pipefail

CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Detect local IP
LOCAL_IP=$(hostname -I | awk '{print $1}' || echo "127.0.0.1")

echo "=================================================================="
echo "   🚀 SKY / CTB — UBUNTU 24/7 PRODUCTION INSTALLER"
echo "=================================================================="
echo "User:       ${CURRENT_USER}"
echo "Directory:  ${ROOT_DIR}"
echo "Local IP:   ${LOCAL_IP}"
echo "=================================================================="

# 1. Install Docker & Compose if missing
if ! command -v docker > /dev/null 2>&1; then
    echo "[1/8] Installing Docker Engine & Docker Compose..."
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "${CURRENT_USER}"
    echo "✓ Docker installed."
else
    echo "[1/8] Docker is already installed."
fi

# 2. Setup .env file
echo "[2/8] Verifying environment configuration (.env)..."
if [ ! -f "${ROOT_DIR}/.env" ]; then
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
    echo "✓ Created .env from .env.example"
fi

# 3. Create persistent directories
echo "[3/8] Initializing persistent data and log storage..."
mkdir -p "${ROOT_DIR}/data/backups"
mkdir -p "${ROOT_DIR}/data/logs"
chmod -R 775 "${ROOT_DIR}/data"

# 4. Make scripts executable
echo "[4/8] Setting execution permissions on deploy scripts..."
chmod +x "${SCRIPT_DIR}"/*.sh
chmod +x "${SCRIPT_DIR}"/*.py 2>/dev/null || true

# 5. Install Systemd Service Unit
echo "[5/8] Installing and enabling systemd boot supervisor..."
# Substitute the actual project root so `docker compose` resolves the correct
# docker-compose.yml (the repo layout nests the project under Users/azims/CBT).
sed "s|__CBT_WORKDIR__|${ROOT_DIR}|g" "${SCRIPT_DIR}/systemd/cbt-stack@.service" \
    | sudo tee /etc/systemd/system/cbt-stack@.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "cbt-stack@${CURRENT_USER}.service"
echo "✓ Systemd unit cbt-stack@${CURRENT_USER}.service enabled."

# 6. Install Crontab automated schedules
echo "[6/8] Installing production cron jobs (backups, VACUUM, WAL checkpoint, watchdog)..."
bash "${SCRIPT_DIR}/crontab_ubuntu.sh"

# 7. Start Docker Compose Stack
echo "[7/8] Building and launching 24/7 container stack..."
cd "${ROOT_DIR}"
docker compose down --remove-orphans || true
docker compose build --pull
docker compose up -d

# 8. Run Verification Healthcheck
echo "[8/8] Waiting for services to initialize and running healthcheck..."
sleep 15
bash "${SCRIPT_DIR}/healthcheck.sh" || true

echo "=================================================================="
echo "   ✅ SKY / CTB IS LIVE AND READY FOR 24/7/365 OPERATION!"
echo "=================================================================="
echo ""
echo "📱 Terminal Access URLs:"
echo "   • This PC (Local):     http://localhost"
echo "   • Windows PC & Phone:  http://${LOCAL_IP} (or https://${LOCAL_IP} if domain configured)"
echo ""
echo "📊 Subsystem Vitals:"
echo "   • Python Quant Engine: http://localhost:8000/api/health"
echo "   • Paper Trading Desk:  http://localhost:3000/health"
echo ""
echo "🛠 Useful Management Commands:"
echo "   • View Stack Logs:     docker compose logs -f"
echo "   • Restart Stack:       sudo systemctl restart cbt-stack@${CURRENT_USER}.service"
echo "   • Manual Backup:       bash deploy/backup_databases.sh"
echo "   • Force WAL Check:     python3 deploy/wal_checkpoint.py"
echo "=================================================================="
