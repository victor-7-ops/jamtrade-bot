#!/usr/bin/env bash
# Walk-forward validation: roll a test window across history and backtest each
# slice independently. Answers the ROADMAP Phase 3 question directly:
# "does a hyperopt result reproduce its edge on data it never saw?" — but
# repeated across many out-of-sample windows instead of just one train/test
# split, so a strategy that happened to get lucky on one holdout period
# can't hide.
#
# This does NOT run hyperopt itself (that stays a deliberate, reviewed,
# one-at-a-time action per CLAUDE.md). It backtests the CURRENT committed
# strategy/params across a sequence of non-overlapping windows and reports
# whether performance holds up over time, or degrades — an early-warning
# signal for curve-fitting or regime drift, independent of live paper trading.
#
# Usage:
#   bash scripts/walk_forward.sh [START] [END] [WINDOW_MONTHS] [STEP_MONTHS]
#   e.g. bash scripts/walk_forward.sh 20230101 20250601 6 3
#
# Defaults: 6-month windows, stepped every 3 months (50% overlap), across
# the same 2023–2025-H1 range used in STRATEGY-NOTES.md, so results are
# directly comparable to the documented full-range backtests.
set -euo pipefail

CONFIG="user_data/config-dryrun.json"
STRATEGY="MultiConfirmationStrategy"
START="${1:-20230101}"
END="${2:-20250601}"
WINDOW_MONTHS="${3:-6}"
STEP_MONTHS="${4:-3}"

RESULTS_DIR="user_data/backtest_results/walk_forward"
mkdir -p "$RESULTS_DIR"
SUMMARY_JSON="$RESULTS_DIR/summary.json"

date_to_epoch() { date -u -d "$1" +%s 2>/dev/null || date -u -j -f "%Y%m%d" "$1" +%s; }
epoch_to_date() { date -u -d "@$1" +%Y%m%d 2>/dev/null || date -u -r "$1" +%Y%m%d; }
add_months_epoch() {
  # $1 = epoch seconds, $2 = months to add
  local d; d=$(epoch_to_date "$1")
  date -u -d "${d} +$2 months" +%s 2>/dev/null || date -u -j -v"+$2"m -f "%Y%m%d" "$d" +%s
}

start_epoch=$(date_to_epoch "$START")
end_epoch=$(date_to_epoch "$END")

echo "▶ Walk-forward: ${WINDOW_MONTHS}mo windows, ${STEP_MONTHS}mo step, ${START}-${END}"
echo "  (each window backtested independently — this is NOT a single cumulative run)"
echo ""

echo "[]" > "$SUMMARY_JSON"
window_num=0
cursor=$start_epoch

while :; do
  win_end=$(add_months_epoch "$cursor" "$WINDOW_MONTHS")
  if [ "$win_end" -gt "$end_epoch" ]; then
    break
  fi
  window_num=$((window_num + 1))
  win_start_str=$(epoch_to_date "$cursor")
  win_end_str=$(epoch_to_date "$win_end")
  timerange="${win_start_str}-${win_end_str}"
  tag="w${window_num}_${timerange}"

  echo "── Window $window_num: $timerange ──"
  export_dir="$RESULTS_DIR/$tag"
  mkdir -p "$export_dir"

  if freqtrade backtesting \
      --config "$CONFIG" \
      --strategy "$STRATEGY" \
      --timerange "$timerange" \
      --timeframe 4h \
      --export trades \
      --export-filename "$export_dir/result.json" \
      > "$export_dir/log.txt" 2>&1; then
    echo "  ✓ backtest complete → $export_dir/result.json"
  else
    echo "  ✕ backtest FAILED for this window — see $export_dir/log.txt"
    echo "    (often means no trades / no data in this slice; check log before worrying)"
  fi

  cursor=$(add_months_epoch "$cursor" "$STEP_MONTHS")
done

echo ""
echo "✓ Walk-forward runs complete: $window_num window(s)."
echo "  Aggregate + drift-across-windows summary:"
echo "  python scripts/walk_forward_report.py --dir $RESULTS_DIR"
