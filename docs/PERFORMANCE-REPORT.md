# Performance Report — paper-trading scoreboard + drift check

`scripts/performance_report.py` is the Phase 2 measurement tool. It reads the
dry-run sqlite DB and answers the two questions that decide whether Phase 2
passes:

1. **Which confirmation combos actually earn on the live feed?**
   Every entry is tagged with its layer bitmap (`L1+L3+L5`, ...). The report
   aggregates closed paper trades per tag: count, win rate, avg profit,
   cumulative profit, worst trade, avg hold time. This is the same attribution
   analysis that removed L6 in v1.5 — running continuously instead of
   once-per-backtest-review.

2. **Is live behavior drifting from the backtest?**
   ROADMAP Phase 2 exit criterion: "live dry-run results are roughly consistent
   with the backtest." The drift section compares live win rate and avg
   profit-per-trade against a committed baseline and flags divergence beyond
   loose thresholds (±15pp win rate, ±1pp avg profit). Below 10 closed trades
   it refuses to judge — small samples are noise.

It also breaks results down by **exit_reason**, so you can see whether the ATR
trailing stop, the indicator exit, or the -10% hard stop is where profit leaks.

**It is reporting only.** It opens the DB read-only, places no orders, and
changes no strategy logic. Same contract as the signal advisor.

## Running it

On the box hosting the dry-run (the DB lives there):

```bash
cd ~/jamtrade-bot
.venv/bin/python scripts/performance_report.py
# custom DB path:
.venv/bin/python scripts/performance_report.py --db user_data/tradesv3.dryrun.sqlite
```

No extra dependencies — stdlib only. If `TG_TOKEN` / `TG_CHAT_ID` are set
(same vars the advisor uses), the report is also sent to Telegram.

## Creating the baseline (enables the drift check)

Run a backtest on the current strategy version with export enabled, then
distill it:

```bash
freqtrade backtesting --config user_data/config-dryrun.json \
  --strategy MultiConfirmationStrategy \
  --timerange 20230101-20250601 --export trades

python scripts/performance_report.py \
  --make-baseline user_data/backtest_results/backtest-result-<date>.json \
  --out user_data/backtest_baseline.json

git add user_data/backtest_baseline.json && git commit -m "chore: baseline from v1.7 backtest"
```

**Regenerate the baseline whenever the strategy version changes.** Comparing
v1.7 live results against a v1.5 backtest baseline is meaningless — same
reason the ROADMAP says the paper DB must be restarted on v1.7.

## Weekly systemd timer (EC2 / Oracle)

Mirrors the advisor timer pattern (`docs/ORACLE-DEPLOY.md`). Every Monday
07:00 UTC:

```ini
# /etc/systemd/system/jamtrade-report.service
[Unit]
Description=JamTrade weekly paper-trading report (advisory only)
After=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/jamtrade-bot
EnvironmentFile=/home/ubuntu/jamtrade-bot/.env
ExecStart=/home/ubuntu/jamtrade-bot/.venv/bin/python scripts/performance_report.py
```

```ini
# /etc/systemd/system/jamtrade-report.timer
[Unit]
Description=Run JamTrade performance report weekly

[Timer]
OnCalendar=Mon 07:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jamtrade-report.timer
# smoke test:
sudo systemctl start jamtrade-report.service && journalctl -u jamtrade-report -n 30
```

## Reading the report

- **Tag scoreboard sorted by avg profit** — best combos on top. Groups with
  fewer than `--min-trades` (default 2) closed trades are hidden; a combo
  needs a real sample before it deserves a judgment. Resist acting on 3
  trades of data — the v1.5→v1.7 L6 removal had 2.5 years of backtest
  behind it.
- **Exit breakdown** — if `trailing_stop_loss` exits show high win rate but
  low avg profit, the trail may be too tight; if `stoploss` (-10% hard stop)
  dominates losses, that's the flash-crash tail the v1.6 vol haircut targets.
  Evidence for future tuning, not a trigger for immediate change.
- **Drift flag** — a ⚠️ means investigate, not panic. Check: did fees/slippage
  assumptions hold? Different market regime than the backtest window? Real
  divergence sends you back to Phase 1 per the ROADMAP — that is the system
  working, not failing.

## What this deliberately does not do

- No auto-tuning, no auto-disabling of layers. Humans read reports; changes go
  through the normal one-change-at-a-time → backtest → validate.sh loop.
- No judgment below minimum sample sizes. It says "too few trades" instead.
- No live-trading awareness whatsoever. It reads whatever DB you point it at.
