#!/usr/bin/env bash
# Download historical OHLCV data for backtesting.
# Pulls both the trading timeframe (4h) and the higher-timeframe trend filter (1d).
#
# Exchange and pairs are NOT hardcoded here. They come from the config's
# `exchange.name` and `exchange.pair_whitelist`, so downloaded data always
# lands in the directory the backtest actually reads from. Hardcoding them
# here is what previously left kraken backtests reading an empty data dir.
set -euo pipefail

CONFIG="${JAMTRADE_CONFIG:-user_data/config-backtest.json}"
TIMEFRAMES="4h 1d"
# Starts 2022, not 2023: the strategy's startup_candle_count is 400, so the 1d
# informative needs 400 daily candles BEFORE the first backtest candle. A
# 2023-01-01 start left a 2024 backtest window short of warmup data.
SINCE="20220101-"

EXCHANGE="$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["exchange"]["name"])' "$CONFIG")"

echo "▶ Downloading data from '$EXCHANGE' (config whitelist) [$TIMEFRAMES] since $SINCE"
freqtrade download-data \
  --config "$CONFIG" \
  --timeframe $TIMEFRAMES \
  --timerange "$SINCE"

echo "✓ Done. Data is in user_data/data/$EXCHANGE/"
