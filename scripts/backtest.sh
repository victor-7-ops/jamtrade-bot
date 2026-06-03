#!/usr/bin/env bash
# Run a backtest over a defined period.
# Usage: bash scripts/backtest.sh [TIMERANGE]
#   e.g. bash scripts/backtest.sh 20240101-20250101
set -euo pipefail

CONFIG="user_data/config-dryrun.json"
STRATEGY="MultiConfirmationStrategy"
TIMERANGE="${1:-20240101-20250101}"

echo "▶ Backtesting $STRATEGY over $TIMERANGE"
freqtrade backtesting \
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
