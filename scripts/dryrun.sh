#!/usr/bin/env bash
# Paper trade on a LIVE exchange feed with FAKE money.
# Safe: config has dry_run=true, so no real orders are placed.
# This connects to real Binance prices in real time and simulates trades.
set -euo pipefail

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
freqtrade trade \
  --config "$CONFIG" \
  --strategy "$STRATEGY"
