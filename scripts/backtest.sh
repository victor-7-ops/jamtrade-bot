#!/usr/bin/env bash
# Run a backtest over a defined period.
# Usage: bash scripts/backtest.sh [TIMERANGE]
#   e.g. bash scripts/backtest.sh 20240101-20250101
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

CONFIG="${JAMTRADE_CONFIG:-user_data/config-backtest.json}"
STRATEGY="MultiConfirmationStrategy"
TIMERANGE="${1:-20240101-20250101}"

echo "▶ Backtesting $STRATEGY over $TIMERANGE"
"$FREQTRADE" backtesting \
  --config "$CONFIG" \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" \
  --timeframe 4h \
  --breakdown day

echo ""
echo "✓ Backtest complete."
echo "⚠  REMINDER: run 'bash scripts/validate.sh' to check for lookahead bias"
echo "   before trusting these numbers. Good-looking results mean nothing if"
echo "   the strategy is secretly using future data."
