#!/usr/bin/env bash
# Download historical OHLCV data for backtesting.
# Pulls both the trading timeframe (4h) and the higher-timeframe trend filter (1d).
set -euo pipefail

CONFIG="user_data/config-dryrun.json"
PAIRS="BTC/USDT ETH/USDT SOL/USDT BNB/USDT"
TIMEFRAMES="4h 1d"
SINCE="20230101-"

echo "▶ Downloading data: $PAIRS [$TIMEFRAMES] since $SINCE"
freqtrade download-data \
  --config "$CONFIG" \
  --exchange binance \
  --pairs $PAIRS \
  --timeframe $TIMEFRAMES \
  --timerange "$SINCE"

echo "✓ Done. Data is in user_data/data/binance/"
