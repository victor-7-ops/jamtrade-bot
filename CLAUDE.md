# CLAUDE.md — JamTrade Bot

This file orients Claude Code when working in this repository. Read it fully before making changes.

> 📌 **Read `docs/HANDOFF-TO-CLAUDE-CODE.md` first.** This project was authored in a
> sandboxed chat assistant with no network, no Freqtrade install, no TA-Lib, and no secrets.
> Everything is syntax-validated but **unproven by execution**. That handoff doc lists every
> such limitation and the exact first-session steps to take it from "written" to "running."

## What this project is

A crypto/stocks/forex trading bot built on **Freqtrade**. It runs a multi-confirmation
strategy (6 signal layers + ADX regime filter + ATR trailing stops). The current phase is
**paper trading and strategy development** — NOT live trading with real money.

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
│   ├── HANDOFF-TO-CLAUDE-CODE.md   # READ FIRST: sandbox limits + first-session steps
│   ├── SETUP-GUIDE.md              # install + run instructions
│   ├── STRATEGY-NOTES.md           # how the strategy works + dev log
│   ├── ROADMAP.md                  # phased plan for improvements
│   ├── TELEGRAM-ALERTS.md          # phone notification setup
│   ├── DEPLOY-FREE.md              # zero-cost 24/7 hosting options
│   ├── ORACLE-DEPLOY.md            # full Oracle Always Free runbook (Claude Code-oriented)
│   └── SENTIMENT.md                # market-mood context module (advisory only)
├── scripts/
│   ├── backtest.sh                 # one-command backtest
│   ├── dryrun.sh                   # one-command paper trade
│   ├── download-data.sh            # fetch historical OHLCV
│   ├── validate.sh                 # lookahead + recursion checks
│   ├── signal_advisor.py           # ADVISORY-ONLY buy/hold/sell Telegram pings
│   ├── sentiment.py                # market-mood CONTEXT (aggregated, never a trigger)
│   └── healthcheck.sh              # deployment health check (pings only on failure)
└── user_data/
    ├── config-dryrun.json          # paper trading config (dry_run=true)
    ├── strategies/
    │   └── MultiConfirmationStrategy.py
    └── notebooks/                  # for analysis experiments
```

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

## Deployment notes (Oracle Cloud Always Free)

- Full runbook: `docs/ORACLE-DEPLOY.md`. It's written for this workflow — the owner does the
  browser/console steps; you (Claude Code) provision and maintain the server.
- The advisor runs via a **systemd timer** every 4h (one-shot), not a long-running loop.
- Secrets live in a VM-only `.env` (chmod 600), loaded via systemd `EnvironmentFile`. Never
  commit `.env`; never echo the token into logs.
- On the ARM (Ampere) shape, the TA-Lib **C library** must be built from source before the
  Python binding installs — see the runbook. Flag ARM-specific gotchas when they arise.
- No inbound ports for the advisor. If the owner wants the Freqtrade web UI, require auth and
  prefer an SSH tunnel — never expose it casually.
- Keep everything reproducible from git so the VM can be rebuilt in minutes if Oracle ever
  reclaims the instance.
