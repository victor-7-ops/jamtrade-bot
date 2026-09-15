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

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Resolve an interpreter for the one-line JSON read below. Ubuntu ships no bare
# `python` — only `python3` — so calling `python` fails on the server while
# working fine in a Windows venv. Prefer the project venv, which definitely has
# what we need, then fall back.
if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  PY="$REPO_DIR/.venv/bin/python"
elif [ -x "$REPO_DIR/.venv/Scripts/python.exe" ]; then
  PY="$REPO_DIR/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "✕ No python interpreter found (looked for .venv, python3, python)." >&2
  exit 1
fi

# Prefer the venv's freqtrade too — a bare `freqtrade` only resolves when the
# venv happens to be activated, which is not true under cron/systemd.
if [ -x "$REPO_DIR/.venv/bin/freqtrade" ]; then
  FREQTRADE="$REPO_DIR/.venv/bin/freqtrade"
elif [ -x "$REPO_DIR/.venv/Scripts/freqtrade.exe" ]; then
  FREQTRADE="$REPO_DIR/.venv/Scripts/freqtrade.exe"
else
  FREQTRADE="freqtrade"
fi

EXCHANGE="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["exchange"]["name"])' "$CONFIG")"

echo "▶ Downloading data from '$EXCHANGE' (config whitelist) [$TIMEFRAMES] since $SINCE"
"$FREQTRADE" download-data \
  --config "$CONFIG" \
  --timeframe $TIMEFRAMES \
  --timerange "$SINCE"

echo "✓ Done. Data is in user_data/data/$EXCHANGE/"
