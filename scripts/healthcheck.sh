#!/usr/bin/env bash
# healthcheck.sh — verify the advisor deployment is healthy.
# Sends a Telegram message ONLY if something is wrong (silence = all good).
# Intended to be run on its own daily systemd timer on the Oracle VM.
#
# Requires TG_TOKEN and TG_CHAT_ID in the environment (load from .env).
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROBLEMS=()

# 1. Is the advisor timer active?
if command -v systemctl >/dev/null 2>&1; then
  if ! systemctl is-active --quiet jamtrade-advisor.timer; then
    PROBLEMS+=("⛔ jamtrade-advisor.timer is not active")
  fi
  # 2. Did the last advisor run fail?
  LAST_RESULT="$(systemctl show -p ExecMainStatus --value jamtrade-advisor.service 2>/dev/null || echo "")"
  if [ -n "$LAST_RESULT" ] && [ "$LAST_RESULT" != "0" ]; then
    PROBLEMS+=("⛔ Last advisor run exited with code $LAST_RESULT")
  fi
fi

# 3. Can we reach the exchange API? (public endpoint, no auth)
if ! curl -fsS --max-time 15 "https://api.binance.com/api/v3/ping" >/dev/null 2>&1; then
  PROBLEMS+=("⛔ Cannot reach Binance public API")
fi

# 4. Does the venv + key deps still import?
if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  if ! "$REPO_DIR/.venv/bin/python" -c "import ccxt, talib, pandas" >/dev/null 2>&1; then
    PROBLEMS+=("⛔ Python deps failed to import (ccxt/talib/pandas)")
  fi
else
  PROBLEMS+=("⛔ venv python not found at .venv/bin/python")
fi

# Report only if there are problems.
if [ ${#PROBLEMS[@]} -eq 0 ]; then
  echo "$(date -u +%FT%TZ) healthcheck OK"
  exit 0
fi

MSG="🩺 JamTrade healthcheck found issues on $(hostname):"$'\n'"$(printf '%s\n' "${PROBLEMS[@]}")"
echo "$MSG"

if [ -n "${TG_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  curl -fsS --max-time 15 \
    -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=${MSG}" >/dev/null 2>&1 || true
fi

exit 1
