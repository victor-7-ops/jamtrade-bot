#!/usr/bin/env bash
# healthcheck.sh — verify the JamTrade deployment is healthy.
# Sends a Telegram message ONLY if something is wrong (silence = all good).
# Intended to run on a systemd timer; aws-setup.sh installs one.
#
# Requires TG_TOKEN and TG_CHAT_ID in the environment (load from ~/.env).
#
# ── Why this file was rewritten (2026-09-15) ────────────────────────────
# The original only checked the ADVISOR timer. It never looked at the trading
# bot, the disk, or whether anything was still making progress. On 2026-09-09
# the EC2 box filled its disk, freqtrade began crash-looping, and it stayed
# dead for FIVE DAYS with nobody notified — this script would have reported
# "healthy" the whole time, because the thing that broke was not among the
# things it looked at.
#
# The lesson worth keeping: a healthcheck that monitors the easy signals is
# worse than none, because it manufactures confidence. Check the thing whose
# absence would hurt — here, "is the bot alive and is it making progress".
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BOT_SERVICE="jamtrade-dryrun.service"
DISK_WARN_PCT=85          # alert well before 100% — at 100% freqtrade dies outright
LOG_STALE_HOURS=2         # freqtrade heartbeats ~every 60s, so 2h of silence is wrong
RESTART_WARN=20           # more than this and it is crash-looping, not recovering

# Newline-delimited findings rather than a bash array: under `set -u`, bash older
# than 4.4 (Oracle Linux 7 / RHEL 7 ship 4.2) treats "${#arr[@]}" on an EMPTY
# array as an unbound variable and aborts — so this script would die exactly when
# everything is healthy, and a dead healthcheck reports nothing wrong. A plain
# string plus a counter behaves identically on every bash.
PROBLEMS=""
PROBLEM_COUNT=0

add_problem() {
  PROBLEMS="${PROBLEMS}${1}"$'\n'
  PROBLEM_COUNT=$((PROBLEM_COUNT + 1))
}

if command -v systemctl >/dev/null 2>&1; then
  # 1. THE important one: is the trading bot actually running?
  if systemctl cat "$BOT_SERVICE" >/dev/null 2>&1; then
    STATE="$(systemctl is-active "$BOT_SERVICE" 2>/dev/null || true)"
    if [ "$STATE" != "active" ]; then
      add_problem "⛔ $BOT_SERVICE is NOT running (state: ${STATE:-unknown})"
    fi

    # 2. Running is not the same as healthy — Restart=always can mask a crash
    #    loop as "activating" forever. 9918 restarts is not a hypothetical.
    NRESTARTS="$(systemctl show "$BOT_SERVICE" -p NRestarts --value 2>/dev/null || echo 0)"
    if [ "${NRESTARTS:-0}" -gt "$RESTART_WARN" ]; then
      add_problem "⛔ $BOT_SERVICE has restarted ${NRESTARTS}x — crash-looping, not recovering"
    fi
  else
    add_problem "⛔ $BOT_SERVICE is not installed on this host"
  fi

  # 3. Advisor timer, but only if this host actually runs one. The advisor
  #    moved to GitHub Actions, so its absence here is normal, not a fault.
  if systemctl cat jamtrade-advisor.timer >/dev/null 2>&1; then
    if ! systemctl is-active --quiet jamtrade-advisor.timer; then
      add_problem "⛔ jamtrade-advisor.timer is not active"
    fi
    LAST_RESULT="$(systemctl show -p ExecMainStatus --value jamtrade-advisor.service 2>/dev/null || echo "")"
    if [ -n "$LAST_RESULT" ] && [ "$LAST_RESULT" != "0" ]; then
      add_problem "⛔ Last advisor run exited with code $LAST_RESULT"
    fi
  fi
fi

# 4. Disk. This is what actually killed it: at 100% freqtrade dies with
#    "OSError: [Errno 28] No space left on device" and sqlite throws
#    "disk I/O error". Ubuntu's own apt/snap housekeeping reclaims and
#    regrows ~150MB/day, so warn with days of runway, not hours.
USE_PCT="$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "${USE_PCT:-}" ] && [ "$USE_PCT" -ge "$DISK_WARN_PCT" ]; then
  AVAIL="$(df -h --output=avail / 2>/dev/null | tail -1 | tr -d ' ')"
  add_problem "⛔ Disk ${USE_PCT}% full (${AVAIL} free) — freqtrade dies at 100%"
fi

# 5. Progress, not just liveness. A wedged process still reports "active".
#    freqtrade heartbeats to its logfile roughly every 60s, so a stale log
#    means it is alive but no longer doing anything.
BOT_LOG="$REPO_DIR/user_data/logs/dryrun.log"
if [ -f "$BOT_LOG" ]; then
  LOG_AGE_H=$(( ( $(date +%s) - $(stat -c %Y "$BOT_LOG" 2>/dev/null || echo 0) ) / 3600 ))
  if [ "$LOG_AGE_H" -ge "$LOG_STALE_HOURS" ]; then
    add_problem "⛔ dryrun.log untouched for ${LOG_AGE_H}h — bot is wedged or stopped"
  fi
fi

# 6. Can we reach the exchange API? (public endpoint, no auth)
# Must match exchange.name in the config — checking a different exchange than
# the bot actually trades on makes this test meaningless.
if ! curl -fsS --max-time 15 "https://api.kraken.com/0/public/SystemStatus" >/dev/null 2>&1; then
  add_problem "⛔ Cannot reach Kraken public API"
fi

# 7. Does the venv + key deps still import?
if [ -x "$REPO_DIR/.venv/bin/python" ]; then
  if ! "$REPO_DIR/.venv/bin/python" -c "import ccxt, talib, pandas" >/dev/null 2>&1; then
    add_problem "⛔ Python deps failed to import (ccxt/talib/pandas)"
  fi
else
  add_problem "⛔ venv python not found at .venv/bin/python"
fi

# ── Dead-man's switch ───────────────────────────────────────────────────
# Everything above runs ON the box, so none of it can tell you the box itself
# died — no power, terminated instance, kernel panic, network gone. A silent
# healthcheck is indistinguishable from a healthy one, which is precisely the
# failure mode that hid the 5-day outage.
#
# Inverting it fixes that: ping an external watchdog on SUCCESS, and let the
# watchdog alert when the pings STOP. Set HEALTHCHECK_PING_URL in ~/.env to a
# cron-monitor URL (healthchecks.io has a free tier; any equivalent works).
# Configure the watchdog's period a little above this timer's hourly interval.
# Unset = skipped, so this stays optional.
ping_watchdog() {
  [ -n "${HEALTHCHECK_PING_URL:-}" ] || return 0
  curl -fsS --max-time 10 --retry 2 "${HEALTHCHECK_PING_URL}${1:-}" >/dev/null 2>&1 || true
}

# Report only if there are problems.
if [ "$PROBLEM_COUNT" -eq 0 ]; then
  echo "$(date -u +%FT%TZ) healthcheck OK"
  ping_watchdog
  exit 0
fi

# Signal failure to the watchdog too, so it can alert immediately rather than
# waiting for the ping window to lapse.
ping_watchdog "/fail"

MSG="🩺 JamTrade healthcheck found issues on $(hostname):"$'\n'"${PROBLEMS%$'\n'}"
echo "$MSG"

if [ -n "${TG_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  curl -fsS --max-time 15 \
    -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=${MSG}" >/dev/null 2>&1 || true
fi

exit 1
