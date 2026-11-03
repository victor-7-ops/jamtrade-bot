#!/usr/bin/env bash
# Monthly paper-trading scoreboard, pushed to Telegram.
#
# Unlike healthcheck.sh (silent unless something is wrong), this ALWAYS sends:
# it is a scheduled report, not an alarm. The point is that the check-in happens
# whether or not anyone remembers to run it — the 2026-07 and 2026-09 incidents
# were both found late because nothing scheduled was looking.
#
# Requires TG_TOKEN and TG_CHAT_ID in the environment (systemd loads ~/.env).
#
# SINCE defaults to the current regime boundary. Trades before it ran different
# code, and pooling across a boundary is the mistake docs/PERFORMANCE-REPORT.md
# and the hub's "regime boundaries" table both warn about. UPDATE THIS when a new
# boundary is set — a stale value silently reports the wrong window.
set -euo pipefail

SINCE="${SINCE:-2026-10-13}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  PYBIN="$REPO_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYBIN="python3"
else
  PYBIN="python"
fi

# Report to the top of the entry-tag section: headline, benchmark and exposure,
# which is what the monthly read actually needs. The full output is long and
# Telegram caps a message at 4096 characters.
REPORT="$("$PYBIN" scripts/performance_report.py \
            --since "$SINCE" \
            --baseline user_data/backtest_baseline.json 2>&1 \
          | sed -n '1,/Entry-tag scoreboard/p' | sed '$d')" || REPORT="report FAILED to run"

BOT_STATE="$(systemctl is-active jamtrade-dryrun 2>/dev/null || echo unknown)"
DISK="$(df -h / | awk 'NR==2 {print $5" used, "$4" free"}')"

MSG="$(printf '%s\n' \
  "JamTrade monthly scoreboard (since ${SINCE})" \
  "bot: ${BOT_STATE} | disk: ${DISK}" \
  "" \
  "${REPORT}" \
  "" \
  "Benchmark: 15% basket + 85% T-bills, bar = CAGR > 9.7% at maxDD < 13%." \
  "Paper money. No result here justifies real capital.")"

# Telegram rejects anything over 4096 chars outright, which would turn a long
# report into no report at all.
MSG="${MSG:0:4000}"

# Print the report before attempting delivery, so a delivery failure never costs
# the data -- it stays in the journal (`journalctl -u jamtrade-scoreboard`).
printf '%s\n' "$MSG"

if [ -n "${TG_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  curl -fsS --max-time 20 \
    -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=${MSG}" >/dev/null
  echo "scoreboard sent (since ${SINCE})"
else
  # No creds: print instead of failing silently, so a cron/systemd run leaves a
  # trace in the journal rather than looking successful.
  echo "TG_TOKEN / TG_CHAT_ID not set — printing instead of sending:" >&2
  printf '%s\n' "$MSG"
fi
