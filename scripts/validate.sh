#!/usr/bin/env bash
# MANDATORY validation after changing entry/exit logic.
# Runs Freqtrade's lookahead-bias and recursion analysis. These catch the
# single most common (and most dangerous) bug in algo trading: a strategy
# that accidentally uses future data, making backtests look great and live
# trading lose money.
set -euo pipefail

CONFIG="user_data/config-dryrun.json"
STRATEGY="MultiConfirmationStrategy"
TIMERANGE="${1:-20240101-20250101}"

echo "▶ [1/2] Lookahead bias analysis..."
echo "   (Does the strategy peek at future candles? It must not.)"
freqtrade lookahead-analysis \
  --config "$CONFIG" \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" || {
    echo "✕ Lookahead analysis reported issues. DO NOT trust backtest results."
    echo "  Inspect populate_indicators / entry / exit for use of future data."
    exit 1
  }

echo ""
echo "▶ [2/2] Recursion analysis..."
echo "   (Do indicators give different values depending on startup window?)"
freqtrade recursive-analysis \
  --config "$CONFIG" \
  --strategy "$STRATEGY" \
  --timerange "$TIMERANGE" || true

echo ""
echo "✓ Validation finished. If both passed cleanly, the backtest is more trustworthy."
echo "  If either flagged problems, fix them before going any further."
