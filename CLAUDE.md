# CLAUDE.md — JamTrade Bot

This file orients Claude Code when working in this repository. Read it fully before making changes.

> 📌 **Read `docs/HANDOFF-TO-CLAUDE-CODE.md` first.** This project was authored in a
> sandboxed chat assistant with no network, no Freqtrade install, no TA-Lib, and no secrets.
> Everything is syntax-validated but **unproven by execution**. That handoff doc lists every
> such limitation and the exact first-session steps to take it from "written" to "running."

## What this project is

A crypto/stocks/forex trading bot built on **Freqtrade**. It runs a multi-confirmation
strategy (5 signal layers + ADX regime filter + daily EMA50/EMA200 gates + ATR trailing
stops). The current phase is **paper trading and strategy development** — NOT live
trading with real money.

**Live thresholds live in `user_data/strategies/MultiConfirmationStrategy.json`**, not in
the strategy class. Freqtrade auto-loads that hyperopt export at startup and it overrides
every `IntParameter`/`DecimalParameter` default. Read it before reasoning about behaviour,
and never hardcode a copy of those numbers anywhere else — `scripts/signal_advisor.py`
reads the same file for exactly this reason.

The owner is a developer/musician (also building JamSpace, a .NET SaaS). They are
intermediate at Python, strong at C#. Explain Python-specific idioms when they're non-obvious.

## Golden rules (do not violate)

1. **Never enable live trading without explicit, unambiguous confirmation.**
   `dry_run` stays `true` in configs unless the owner says otherwise in that exact session.
   Never add real API keys to any committed file.

2. **Never claim a strategy is profitable.** Backtests and paper results are evidence the
   *logic runs*, not proof of future profit. Always frame results honestly, including
   drawdown and the gap between in-sample and out-of-sample performance.

3. **Always run `lookahead-analysis` after changing entry/exit logic.** A strategy that
   secretly uses future data will look amazing and fail live. This check is mandatory.

4. **Keep risk management intact.** Don't remove or weaken stoplosses, ATR trailing,
   or the ADX regime filter to make backtest numbers look better. That's curve-fitting.

5. **Money safety language.** When the owner discusses real capital, gently reinforce:
   only risk what they can afford to lose; treat early months as education.

6. **The signal advisor is advisory-only by design.** `scripts/signal_advisor.py` must never
   be extended to place real orders. It pulls public data, computes signals, and sends
   Telegram messages — nothing more. If the owner wants automation, that path goes through
   Freqtrade dry-run first, then the gated Phase 4 checklist — not through this script.

7. **Sentiment is context, never a trigger, and never tracks individuals.**
   `scripts/sentiment.py` summarizes *aggregate* crowd mood from free, ToS-compliant sources
   (Fear & Greed, CoinGecko, optional Google Trends). It must never follow, scrape, or parrot
   a specific trader/influencer's buy-sell calls, and must never auto-act on social media.
   Sentiment may, at most, become a *soft contrarian filter* (e.g. tag a BUY "caution" in
   extreme greed) — always advisory, always clearly labelled, decision still owned by the
   strategy + the human.

## Repo layout

```
jamtrade-bot/
├── CLAUDE.md                       # you are here
├── README.md                       # human-facing overview
├── requirements.txt                # python deps
├── .gitignore                      # keeps secrets/data out of git
├── docs/
│   ├── HANDOFF-TO-CLAUDE-CODE.md   # sandbox limits + first-session steps (historical)
│   ├── FIRST-SESSION-LOG.md        # what the first real session fixed
│   ├── SETUP-GUIDE.md              # install + run instructions
│   ├── STRATEGY-NOTES.md           # how the strategy works + dev log
│   ├── ROADMAP.md                  # phased plan for improvements
│   ├── PERFORMANCE-REPORT.md       # how to read the paper-trading scoreboard
│   ├── TELEGRAM-ALERTS.md          # phone notification setup (env vars, not config)
│   ├── AWS-DEPLOY.md               # ← CURRENT deployment: EC2 t3.micro + systemd
│   ├── ORACLE-DEPLOY.md            # alternative runbook (Oracle Always Free)
│   ├── DEPLOY-FREE.md              # zero-cost 24/7 hosting options
│   └── SENTIMENT.md                # market-mood context module (advisory only)
├── scripts/
│   ├── backtest.sh                 # one-command backtest
│   ├── dryrun.sh                   # one-command paper trade
│   ├── start-dryrun.bat            # Windows launcher for the above
│   ├── download-data.sh            # fetch historical OHLCV (exchange from config)
│   ├── validate.sh                 # lookahead + recursion checks
│   ├── walk_forward.sh             # rolling out-of-sample backtest windows
│   ├── walk_forward_report.py      # summarize walk-forward results
│   ├── performance_report.py       # live-vs-backtest drift scoreboard
│   ├── dashboard.py                # static HTML paper-trading dashboard
│   ├── aws-setup.sh                # EC2 provisioning helper
│   ├── signal_advisor.py           # ADVISORY-ONLY buy/hold/sell Telegram pings
│   ├── sentiment.py                # market-mood CONTEXT (aggregated, never a trigger)
│   └── healthcheck.sh              # deployment health check (pings only on failure)
└── user_data/
    ├── config-dryrun.json          # paper trading config (dry_run=true, no secrets)
    ├── backtest_baseline.json      # reference numbers for drift checks
    ├── strategies/
    │   ├── MultiConfirmationStrategy.py
    │   └── MultiConfirmationStrategy.json   # hyperopt params — OVERRIDES class defaults
    ├── data/                       # downloaded OHLCV (gitignored, re-downloadable)
    └── notebooks/                  # for analysis experiments
```

> Secrets never live in tracked files. Telegram and API-server credentials come from
> `FREQTRADE__*` environment variables (see `docs/TELEGRAM-ALERTS.md`); `config-dryrun.json`
> ships disabled and empty. Never mark that file `--skip-worktree` to hide local edits —
> it desyncs the server from git silently.

## Common commands

```bash
# Install deps (in a venv)
pip install -r requirements.txt

# Download data before backtesting
bash scripts/download-data.sh

# Backtest
bash scripts/backtest.sh

# MANDATORY after logic changes
bash scripts/validate.sh

# Paper trade on live feed (fake money)
bash scripts/dryrun.sh
```

## How to help effectively

- **When tuning the strategy**: change ONE thing at a time, re-backtest, compare. Note the
  before/after in `docs/STRATEGY-NOTES.md`. Resist the urge to stack many changes at once.
- **When results look too good** (e.g. >80% win rate, tiny drawdown): be suspicious, not
  excited. Run the lookahead check and inspect for leakage first.
- **When adding indicators**: more is not better. Redundant indicators that say the same
  thing add noise. Justify each addition.
- **When the owner wants to go live**: walk them through the readiness checklist in
  `docs/ROADMAP.md` Phase 4 before touching any real-money config. Do not shortcut it.

## Tech notes

- Freqtrade strategy interface version: **3**
- Primary timeframe: `4h`, with `1d` as an informative (higher-timeframe trend filter)
- Exchange for paper trading: Binance (public data, no keys needed in dry-run)
- The strategy is hyperopt-ready; buy/sell params are defined as `IntParameter`/`DecimalParameter`

## Deployment notes (AWS EC2 — current)

- **The bot runs on an AWS EC2 t3.micro**, not Oracle. Full runbook: `docs/AWS-DEPLOY.md`.
  `docs/ORACLE-DEPLOY.md` is kept as an alternative, not the live setup — don't follow it
  when debugging production. The owner does the console steps; you (Claude Code) provision
  and maintain the server over SSH.
- **Exchange is Kraken**, not Binance: Binance returns HTTP 451 from US AWS/GitHub IPs.
  `exchange.name` in the config is the single source of truth — `download-data.sh` reads it
  rather than hardcoding, because Freqtrade stores and reads OHLCV under
  `user_data/data/<exchange>/` and a mismatch yields silent empty backtests.
- The advisor runs via a **systemd timer** every 4h (one-shot), not a long-running loop.
- Secrets live in a VM-only `.env` (chmod 600), loaded via systemd `EnvironmentFile`. Never
  commit `.env`; never echo the token into logs.
- The t3.micro is x86, so TA-Lib installs from a normal wheel. (Only the Oracle Ampere
  alternative needs the **C library** built from source first — flag ARM gotchas if that
  path is ever used.)
- No inbound ports for the advisor; only SSH from the owner's IP. If the owner wants the
  Freqtrade web UI, require auth, bind to 127.0.0.1, and use an SSH tunnel — never expose
  it casually, and generate fresh `FREQTRADE__API_SERVER__*` credentials first (the ones
  previously committed to git are burned).
- Keep everything reproducible from git so the VM can be rebuilt in minutes if the instance
  is ever lost.
