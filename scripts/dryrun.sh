#!/usr/bin/env bash
# Paper trade on a LIVE exchange feed with FAKE money.
# Safe: config has dry_run=true, so no real orders are placed.
# This connects to real Binance prices in real time and simulates trades.
set -euo pipefail

# Resolve the freqtrade binary. A bare `freqtrade` only works when the venv is
# already activated, which is NOT true under cron, systemd, or a non-interactive
# ssh command — the script then dies with "command not found" having done nothing.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -x "$REPO_DIR/.venv/bin/freqtrade" ]; then
  FREQTRADE="$REPO_DIR/.venv/bin/freqtrade"
elif [ -x "$REPO_DIR/.venv/Scripts/freqtrade.exe" ]; then
  FREQTRADE="$REPO_DIR/.venv/Scripts/freqtrade.exe"
else
  FREQTRADE="freqtrade"
fi

CONFIG="user_data/config-dryrun.json"
STRATEGY="MultiConfirmationStrategy"

# Safety guard: refuse to run if dry_run is not true in the config.
if ! grep -q '"dry_run": true' "$CONFIG"; then
  echo "✕ SAFETY STOP: '\"dry_run\": true' not found in $CONFIG."
  echo "  This script only runs in paper-trading mode. Aborting."
  exit 1
fi

echo "▶ Starting PAPER trading (dry-run) on live Binance feed."
echo "  Fake wallet. No real money. Press Ctrl+C to stop."
echo ""
"$FREQTRADE" trade \
  --config "$CONFIG" \
  --strategy "$STRATEGY"
