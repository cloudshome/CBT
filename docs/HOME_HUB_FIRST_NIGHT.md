# First night — home Ubuntu PC as the SKY Hub

One page. Run this **on the PC that stays on**, not in Arena.

This does **not** connect Gmail, banks, or exchange **trade** keys.
Safe tonight: live market (no account) + optional Telegram + optional
Binance **read-only**. You approve every paper trade. No live orders.

---

## 0. PC that can stay up

```bash
# stay awake (Settings → Power, or:)
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Plug the machine in. A cheap UPS is optional but good.

---

## 1. Tonight (no root required)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

git clone https://github.com/Azimshawon/SKY.git ~/SKY
cd ~/SKY
git checkout main    # or the merged P19 branch if main is behind

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# private data next to your home — not world-readable, no sudo
export SKY_HUB_PREFIX="$HOME/.local/sky-hub"
export SKY_NO_AUTO_INSTALL=1
export DEMO_MODE=0

python3 main.py hub setup --mode local --owner "$USER"
python3 main.py hub backup
python3 main.py hub doctor
python3 main.py daily
```

Open the desk **on this PC only**:

```bash
python3 main.py web --host 127.0.0.1 --port 8050
# browser: http://127.0.0.1:8050
# create the owner password in the first-run screen (P18.1)
```

Copy `ops/sky.env.example` into `$HOME/.local/sky-hub/etc/sky/sky.env` if
setup did not already write it. Set:

```bash
DEMO_MODE=0
DASHBOARD_HOST=127.0.0.1
# optional alerts — CONNECT_REAL_WORLD.md steps 2
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_CHAT_ID=
# optional read-only Binance — Enable Reading ONLY, IP-locked
# BINANCE_READ_API_KEY=
# BINANCE_READ_API_SECRET=
```

**Do not** put trade/withdraw keys. **Do not** open port 8050 on the router.

Same steps as a script: `bash ops/first_night.sh`

---

## 2. 24h services (needs sudo, do once)

```bash
cd ~/SKY
sudo mkdir -p /opt/sky /etc/sky /var/lib/sky/store /var/lib/sky/backups
sudo rsync -a --delete --exclude .venv --exclude .git --exclude data/store \
  ./ /opt/sky/
sudo python3 -m venv /opt/sky/.venv
sudo /opt/sky/.venv/bin/pip install -r /opt/sky/requirements.txt
sudo /opt/sky/.venv/bin/pip install gunicorn

# service user
sudo adduser --system --group --home /var/lib/sky --no-create-home sky || true
sudo cp /opt/sky/ops/sky.env.example /etc/sky/sky.env
sudo chmod 0640 /etc/sky/sky.env
sudo chown -R sky:sky /etc/sky /var/lib/sky
sudo chown -R root:sky /opt/sky
sudo chmod 0750 /etc/sky /var/lib/sky

sudo cp /opt/sky/ops/systemd/sky-*.service /opt/sky/ops/systemd/sky-*.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sky-dashboard.service sky-paper.service \
  sky-scan.timer sky-backup.timer sky-agent.service sky-agent.timer
sudo systemctl status sky-dashboard.service sky-agent.service --no-pager
```

Dashboard is still **127.0.0.1:8050**. Phone access = SSH tunnel or Caddy
TLS from `ops/proxy/` — never raw 8050 on the internet.

---

## 3. Morning — what “healthy” looks like

```bash
export SKY_HUB_PREFIX="$HOME/.local/sky-hub"   # skip if you installed /opt
python3 ~/SKY/main.py hub status
python3 ~/SKY/main.py hub doctor
python3 ~/SKY/main.py daily
python3 ~/SKY/main.py health
```

| Check | Healthy |
|---|---|
| `hub doctor` | verdict **ok**; env not world-readable; loopback bind |
| `hub status` | disk not tiny; at least one backup after first night |
| systemd | `sky-dashboard` + `sky-paper` + `sky-agent` **active**, timers **enabled** |
| `daily` | readiness prints; gate may still be **closed** (no edge yet — correct) |
| browser | http://127.0.0.1:8050 opens; Connections ≠ DEMO MODE |
| Telegram (if set) | Connections → Send test alert reaches your phone |

`gate closed` is **not** a failed install. It means the paper book has not
met 100/20 + positive **net** expectancy. Keep journaling. Do not loosen it.

---

## 4. Explicitly not tonight

- Exchange **trade** or withdraw keys
- Gmail / bank / social “let the agent log in”
- Port-forward 8050
- Lowering the graduation bar so the desk feels busy

If something is wrong, `python3 main.py hub logs --unit sky-dashboard.service`.
Full contract: `docs/HANDOVER_2026-08-18_P19.md`. Connections: `CONNECT_REAL_WORLD.md`.
