#!/usr/bin/env bash
# aws-setup.sh — one-shot server provisioning for JamTrade on AWS t3.micro (Ubuntu 24.04 x86)
# Run once after first SSH onto a fresh instance.
# Safe to re-run — most steps are idempotent.
set -euo pipefail

REPO_DIR="$HOME/jamtrade-bot"
VENV_DIR="$REPO_DIR/.venv"
LOG_DIR="$REPO_DIR/user_data/logs"
CONFIG="$REPO_DIR/user_data/config-dryrun.json"
SERVICE_NAME="jamtrade-dryrun"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " JamTrade AWS Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1: system update + build deps ──────────────────────────────────────
echo "[1/9] System update + build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
  build-essential wget curl git \
  python3-dev python3-venv python3-pip \
  libssl-dev libffi-dev pkg-config

# ── Step 2: swap file (2GB) ─────────────────────────────────────────────────
echo "[2/9] Swap file (2GB — pandas needs headroom on 1GB RAM)..."
if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
  echo "  Swap created."
else
  echo "  Swap already exists, skipping."
fi

# ── Step 3: TA-Lib C library from source ────────────────────────────────────
echo "[3/9] TA-Lib C library (build from source)..."
TALIB_VERSION="0.4.0"
TALIB_TAR="ta-lib-${TALIB_VERSION}-src.tar.gz"
if ! ldconfig -p | grep -q libta_lib; then
  cd /tmp
  wget -q "https://sourceforge.net/projects/ta-lib/files/ta-lib/${TALIB_VERSION}/${TALIB_TAR}"
  tar -xzf "$TALIB_TAR"
  cd "ta-lib-${TALIB_VERSION}"
  ./configure --prefix=/usr
  make -j"$(nproc)"
  sudo make install
  sudo ldconfig
  cd ~
  echo "  TA-Lib C library installed."
else
  echo "  TA-Lib C library already installed, skipping."
fi

# ── Step 4: clone repo if needed ────────────────────────────────────────────
echo "[4/9] Repo..."
if [ ! -d "$REPO_DIR" ]; then
  echo "  Cloning repo..."
  git clone https://github.com/victor-7-ops/jamtrade-bot.git "$REPO_DIR"
else
  echo "  Repo exists, pulling latest..."
  cd "$REPO_DIR" && git pull
fi
cd "$REPO_DIR"

# ── Step 5: Python venv + deps ──────────────────────────────────────────────
echo "[5/9] Python venv + dependencies..."
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies installed."

# ── Step 6: safety check — dry_run must be true ─────────────────────────────
echo "[6/9] Safety check: dry_run=true..."
if ! grep -q '"dry_run": true' "$CONFIG"; then
  echo ""
  echo "✕ SAFETY STOP: '\"dry_run\": true' not found in $CONFIG"
  echo "  This script only deploys in paper-trading mode. Fix the config first."
  exit 1
fi
echo "  dry_run: true — OK."

mkdir -p "$LOG_DIR"

# ── Step 7: systemd service ──────────────────────────────────────────────────
echo "[7/9] Installing systemd service: $SERVICE_NAME..."

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=JamTrade Freqtrade Dry-Run Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=-${HOME}/.env
ExecStart=${VENV_DIR}/bin/freqtrade trade \
  --config ${CONFIG} \
  --strategy MultiConfirmationStrategy \
  --logfile ${LOG_DIR}/dryrun.log
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# ── Step 8: cap the journal ─────────────────────────────────────────────────
# journald is uncapped by default. On a 6.7GB root this matters: a crash loop
# writing full Python tracebacks every 30s will grow the journal until the disk
# fills, which then kills freqtrade ("No space left on device"), which produces
# more tracebacks. Capping it breaks that feedback loop.
echo "[8/9] Capping systemd journal at 200M..."
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/99-jamtrade-cap.conf > /dev/null <<'EOF'
[Journal]
SystemMaxUse=200M
SystemKeepFree=500M
MaxRetentionSec=1month
EOF
sudo systemctl restart systemd-journald

# ── Step 9: healthcheck timer ───────────────────────────────────────────────
# Without this, healthcheck.sh is just a script nobody runs. On 2026-09-09 the
# bot died and stayed dead for five days because nothing was watching it.
# Hourly, and it only messages you when something is actually wrong.
echo "[9/9] Installing healthcheck timer..."
sudo tee /etc/systemd/system/jamtrade-healthcheck.service > /dev/null <<EOF
[Unit]
Description=JamTrade deployment healthcheck (alerts via Telegram on failure)

[Service]
Type=oneshot
User=${USER}
WorkingDirectory=${REPO_DIR}
EnvironmentFile=-${HOME}/.env
ExecStart=/bin/bash ${REPO_DIR}/scripts/healthcheck.sh
EOF

sudo tee /etc/systemd/system/jamtrade-healthcheck.timer > /dev/null <<'EOF'
[Unit]
Description=Run JamTrade healthcheck hourly

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now jamtrade-healthcheck.timer

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Setup complete."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " Status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -20
echo ""
echo " Tail logs with:"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo "   tail -f $LOG_DIR/dryrun.log"
echo ""
echo " First heartbeat appears within ~60s of bot startup."
