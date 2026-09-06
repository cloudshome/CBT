#!/usr/bin/env bash
# =============================================================================
# SKY / CTB — Bare-Metal systemd Installer (single FastAPI tier, port 8000)
#
# Installs ai_quant_sentinel.service with YOUR user and project paths
# substituted into deploy/systemd/ai_quant_sentinel.service.
#
#   bash deploy/install_bare_metal.sh
#
# The script:
#   1. Detects user and project root automatically (any checkout location).
#   2. Guards the Python-version trap: the pinned quantitative stack
#      (numpy<2.2, scipy<1.15, pandas<2.3, pydantic 2.10) ships pre-built
#      wheels ONLY for Python 3.11–3.13. On 3.14+ pip silently compiles for
#      ~1 hour and pydantic-core then fails for lack of Rust — we refuse and
#      print the 2-minute `uv` fix instead.
#   3. Reuses/creates .venv, installs requirements idempotently.
#   4. Creates .env from .env.example when missing.
#   5. Renders + installs the unit to /etc/systemd/system/, enables & starts.
#   6. Health-checks http://localhost:8000/api/health.
#
# Override the interpreter used to build the venv:
#   CBT_PYTHON=python3.13 bash deploy/install_bare_metal.sh
# =============================================================================
set -euo pipefail

CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
UNIT_SRC="${SCRIPT_DIR}/systemd/ai_quant_sentinel.service"
UNIT_DST="/etc/systemd/system/ai_quant_sentinel.service"
SERVICE_NAME="ai_quant_sentinel.service"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

echo "=================================================================="
echo "   🚀 SKY / CTB — BARE-METAL systemd INSTALLER"
echo "=================================================================="
echo "User:        ${CURRENT_USER}"
echo "Project:     ${ROOT_DIR}"
echo "Unit target: ${UNIT_DST}"
echo "=================================================================="

# ---------------------------------------------------------------------------
# 1. Virtualenv: reuse when healthy, otherwise build (with version guard)
# ---------------------------------------------------------------------------
VENV_PY="${ROOT_DIR}/.venv/bin/python"
deps_ready() {
    [ -x "${ROOT_DIR}/.venv/bin/uvicorn" ] \
        && "$VENV_PY" -c 'import fastapi, uvicorn, numpy, pandas, scipy, pydantic' >/dev/null 2>&1
}

if deps_ready; then
    echo "[1/6] ✓ Reusing existing .venv ($( "$VENV_PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' ))"
else
    PYTHON_BIN="${CBT_PYTHON:-python3}"
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        echo "✗ ${PYTHON_BIN} not found." >&2
        exit 1
    fi
    PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    case "$PY_VERSION" in
        3.11|3.12|3.13) echo "[1/6] Python ${PY_VERSION} — supported (pre-built wheels available)." ;;
        *)
            cat >&2 <<WARN

✗ ${PYTHON_BIN} is Python ${PY_VERSION}.
  The pinned stack (numpy<2.2, scipy<1.15, pandas<2.3, pydantic 2.10) has NO
  pre-built wheels for it: pip would compile for ~1h and pydantic-core would
  fail anyway (needs a Rust toolchain).

  Fix — get Python 3.13 in ~2 minutes without touching the system Python:

      curl -LsSf https://astral.sh/uv/install.sh | sh
      cd "${ROOT_DIR}"
      rm -rf .venv
      uv venv --python 3.13 --seed .venv
      source .venv/bin/activate
      uv pip install -r requirements.txt

  Then re-run this installer, or point it at the interpreter directly:
      CBT_PYTHON=python3.13 bash deploy/install_bare_metal.sh

WARN
            exit 1
            ;;
    esac

    echo "[1/6] Creating .venv with ${PYTHON_BIN} and installing requirements…"
    "$PYTHON_BIN" -m venv "${ROOT_DIR}/.venv"
    "${ROOT_DIR}/.venv/bin/pip" install --quiet --upgrade pip
    "${ROOT_DIR}/.venv/bin/pip" install --quiet -r "${ROOT_DIR}/requirements.txt"
fi

# ---------------------------------------------------------------------------
# 2. .env
# ---------------------------------------------------------------------------
if [ ! -f "${ROOT_DIR}/.env" ]; then
    echo "[2/6] Creating .env from .env.example…"
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
else
    echo "[2/6] ✓ .env present"
fi

# ---------------------------------------------------------------------------
# 3. Persistent runtime directories
# ---------------------------------------------------------------------------
echo "[3/6] Initializing data/ directories…"
mkdir -p "${ROOT_DIR}/data/logs" "${ROOT_DIR}/data/backups" "${ROOT_DIR}/data/uploads"

# ---------------------------------------------------------------------------
# 4. Port 8000 conflict guard (Docker stack or a stray manual uvicorn)
# ---------------------------------------------------------------------------
echo "[4/6] Checking port 8000…"
if command -v ss >/dev/null 2>&1 && ss -ltnH "sport = :8000" 2>/dev/null | grep -q .; then
    echo "  ⚠️  Something is ALREADY LISTENING on port 8000."
    echo "     If the Docker stack (cbt-stack@) or a manual `uvicorn --reload` is"
    echo "     running, stop it first — this unit cannot bind while it holds the port."
    echo "     Continuing anyway; the unit will retry (Restart=always)."
else
    echo "  ✓ port 8000 free"
fi

# ---------------------------------------------------------------------------
# 5. Render + install the unit (placeholder substitution — never raw cp)
# ---------------------------------------------------------------------------
echo "[5/6] Installing systemd unit…"
sed -e "s|__CBT_USER__|${CURRENT_USER}|g" \
    -e "s|__CBT_WORKDIR__|${ROOT_DIR}|g" \
    "${UNIT_SRC}" | $SUDO tee "${UNIT_DST}" > /dev/null
$SUDO systemctl daemon-reload
$SUDO systemctl enable "${SERVICE_NAME}"

# ---------------------------------------------------------------------------
# 6. Start + health check
# ---------------------------------------------------------------------------
echo "[6/6] Starting ${SERVICE_NAME}…"
$SUDO systemctl restart "${SERVICE_NAME}"

echo -n "      Waiting for /api/health "
HEALTH="UNKNOWN"
for _ in $(seq 1 20); do
    if curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
        HEALTH="OPERATIONAL"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

if [ "$HEALTH" = "OPERATIONAL" ]; then
    echo "=================================================================="
    echo "   ✅ AI QUANT SENTINEL IS LIVE (systemd-managed, boots on start)"
    echo "=================================================================="
    echo "   📱 Terminal:        http://localhost:8000"
    echo "   💊 Health:          curl -s http://localhost:8000/api/health"
    echo ""
    echo "   🛠 Management:"
    echo "      systemctl status ${SERVICE_NAME}"
    echo "      journalctl -u ai_quant_sentinel -f     # live logs"
    echo "      $SUDO systemctl restart ${SERVICE_NAME}"
    echo "=================================================================="
else
    echo "✗ Service did not become healthy within 40s. Inspect:" >&2
    echo "    systemctl status ${SERVICE_NAME} --no-pager" >&2
    echo "    journalctl -u ai_quant_sentinel -n 50 --no-pager" >&2
    exit 1
fi
