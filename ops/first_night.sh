#!/bin/sh
# First-night Hub bootstrap on a home Ubuntu PC. No root. No exchange orders.
# Usage:  bash ops/first_night.sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
PREFIX="${SKY_HUB_PREFIX:-$HOME/.local/sky-hub}"
export SKY_HUB_PREFIX="$PREFIX"
export SKY_NO_AUTO_INSTALL=1
export DEMO_MODE="${DEMO_MODE:-0}"

echo "SKY first night"
echo "  repo   $ROOT"
echo "  data   $PREFIX"
echo "  live exchange execution  NO"

if ! command -v python3 >/dev/null; then
  echo "install python3:  sudo apt install -y python3 python3-venv python3-pip" >&2
  exit 1
fi

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
. "$ROOT/.venv/bin/activate"
python -m pip install -q -r "$ROOT/requirements.txt"

python "$ROOT/main.py" hub setup --mode local --owner "${USER:-operator}"
python "$ROOT/main.py" hub backup
python "$ROOT/main.py" hub doctor
echo
echo "Next:"
echo "  1. python $ROOT/main.py web --host 127.0.0.1 --port 8050"
echo "  2. open http://127.0.0.1:8050  — create the owner password"
echo "  3. morning: python $ROOT/main.py daily && python $ROOT/main.py hub status"
echo "  4. 24h units (sudo): see docs/HOME_HUB_FIRST_NIGHT.md §2"
echo "Do not open port 8050 on the router. Do not add trade keys."
