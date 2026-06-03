# JamTrade Bot 📡

A multi-confirmation trading bot built on [Freqtrade](https://www.freqtrade.io).
Currently in the **paper-trading / development** phase.

> ⚠️ **This is not a money printer.** It's a structured, honest framework for learning
> algorithmic trading and developing a real strategy. Backtest and paper-trade results
> demonstrate that the *logic works* — they do not predict future profit. Only ever risk
> money you can afford to lose entirely.

## The Strategy

A long-only multi-confirmation system. An entry requires **at least 3 of 6** signal layers
to agree, AND two gating filters to pass.

**Signal layers**
1. Price above EMA50 (trend)
2. RSI < 38 (oversold momentum)
3. MACD histogram > 0 (momentum turning up)
4. Close below lower Bollinger Band (price at value)
5. Volume > 1.4× its 20-period average (conviction)
6. Bullish RSI divergence (bonus reversal signal)

**Gating filters (both required)**
- ADX ≥ 22 (only trade when a real trend exists — skips choppy markets)
- Daily-timeframe uptrend (higher-timeframe agreement)

**Exits**
- ATR-based trailing stop (2.5× ATR) — locks in profit, adapts to volatility
- Indicator exit (RSI > 68 + MACD down + above upper BB; ≥2 must agree)

See `docs/STRATEGY-NOTES.md` for the full breakdown and development log.

## Quick Start

```bash
# 1. Set up environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Download historical data
bash scripts/download-data.sh

# 3. Backtest
bash scripts/backtest.sh 20240101-20250101

# 4. Validate (MANDATORY — catches future-data leakage)
bash scripts/validate.sh

# 5. Paper trade on the live feed (fake money)
bash scripts/dryrun.sh
```

Full instructions: `docs/SETUP-GUIDE.md`

### Deploy it free, 24/7
- `docs/DEPLOY-FREE.md` — the honest 2026 zero-cost hosting options
- `docs/ORACLE-DEPLOY.md` — full Oracle Always Free runbook (written for the Claude Code workflow)
- `docs/TELEGRAM-ALERTS.md` — get buy/hold/sell pings on your phone
- `docs/SENTIMENT.md` — optional market-mood context in your alerts (advisory only, no guru-chasing)

## Working With Claude Code

This repo includes a `CLAUDE.md` that orients Claude Code on conventions, safety rules,
and the development workflow.

> ⚠️ **Start with `docs/HANDOFF-TO-CLAUDE-CODE.md`.** The project was authored in a sandbox
> with no network/Freqtrade/TA-Lib/secrets — so it's syntax-valid but not yet run. That doc
> lists every limitation and the exact steps to get it executing.

A good first prompt:

> "Read docs/HANDOFF-TO-CLAUDE-CODE.md and CLAUDE.md, then walk me through the first-session
> checklist: set up the venv, install deps (incl. TA-Lib), and run a 2024 backtest. Fix any
> API mismatches as we go and flag overfitting concerns."

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Backtesting + understanding the strategy | ▶ current |
| 2 | Paper trading on live feed (weeks–months) | next |
| 3 | Tuning per-market (hyperopt, validation) | later |
| 4 | Tiny real capital (only if 1–3 hold up) | gated |

Details in `docs/ROADMAP.md`.

## License / Disclaimer

For educational use. The authors assume no responsibility for trading results. This is not
financial advice. Trading involves substantial risk of loss.
