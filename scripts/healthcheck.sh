#!/usr/bin/env bash
# healthcheck.sh — verify the advisor deployment is healthy.
# Sends a Telegram message ONLY if something is wrong (silence = all good).
# Intended to be run on its own daily systemd timer on the Oracle VM.
#
# Requires TG_TOKEN and TG_CHAT_ID in the environment (load from .env).
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Newline-delimited findings rather than a bash array: under `set -u`, bash older
# than 4.4 (Oracle Linux 7 / RHEL 7 ship 4.2) treats "${#arr[@]}" on an EMPTY
# array as an unbound variable and aborts — so this script would die exactly when
# everything is healthy, and a dead healthcheck reports nothing wrong. A plain
# string plus a counter behaves identically on every bash.
PROBLEMS=""
PROBLEM_COUNT=0

add_problem() {
  PROBLEMS="${PROBLEMS}${1}"$'\n'
  PROBLEM_COUNT=$((PROBLEM_COUNT + 1))
}

# 1. Is the advisor timer active?
if command -v systemctl >/dev/null 2>&1; then
  if ! systemctl is-active --quiet jamtrade-advisor.timer; then
    add_problem "⛔ jamtrade-advisor.timer is not active"
  fi
  # 2. Did the last advisor run fail?
  LAST_RESULT="$(systemctl show -p ExecMainStatus --value jamtrade-advisor.service 2>/dev/null || echo "")"
  if [ -n "$LAST_RESULT" ] && [ "$LAST_RESULT" != "0" ]; then
    add_problem "⛔ Last advisor run exited with code $LAST_RESULT"
  fi
fi

# 3. Can we reach the exchange API? (public endpoint, no auth)
# Must match exchange.name in the config — checking a different exchange than
# the bot actually trades on makes this test meaningless.
if ! curl -fsS --max-time 15 "https://api.kraken.com/0/public/SystemStatus" >/dev/null 2>&1; then
  add_problem "⛔ Cannot reach Kraken public API"
fi

# 4. Does the venv + key deps still import?
if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  if ! "$REPO_DIR/.venv/bin/python" -c "import ccxt, talib, pandas" >/dev/null 2>&1; then
    add_problem "⛔ Python deps failed to import (ccxt/talib/pandas)"
  fi
else
  add_problem "⛔ venv python not found at .venv/bin/python"
fi

# Report only if there are problems.
if [ "$PROBLEM_COUNT" -eq 0 ]; then
  echo "$(date -u +%FT%TZ) healthcheck OK"
  exit 0
fi

MSG="🩺 JamTrade healthcheck found issues on $(hostname):"$'\n'"${PROBLEMS%$'\n'}"
echo "$MSG"

if [ -n "${TG_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  curl -fsS --max-time 15 \
    -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=${MSG}" >/dev/null 2>&1 || true
fi

exit 1
