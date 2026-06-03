# Strategy Notes & Development Log

This document explains *why* the strategy is built the way it is, and serves as a running
log of changes. When you tune the strategy, add an entry to the changelog at the bottom.

## Design philosophy

The core idea is **confirmation stacking**: a single indicator generates too many false
signals, so we require several independent signals to agree before risking a trade. Each
layer measures a *different* dimension of the market:

| Dimension | Indicator | Why |
|-----------|-----------|-----|
| Trend | EMA50 | Are we even on the right side of the market? |
| Momentum | RSI + MACD | Is there energy behind a move? |
| Value | Bollinger Bands | Are we buying cheap relative to recent range? |
| Conviction | Volume | Is the market actually participating? |
| Reversal | RSI divergence | Is a turn brewing that price hasn't shown yet? |

Stacking *different* dimensions is the point. Adding three momentum indicators that all say
the same thing doesn't add confirmation — it just adds correlated noise.

## The two gating filters (the most important part)

Most beginner strategies work in trending markets and quietly bleed money in choppy,
sideways ones — which is the majority of the time. Two filters address this:

1. **ADX regime filter.** ADX measures trend *strength* regardless of direction. Below the
   threshold (default 22), the market is directionless and we simply don't trade. This is
   the single biggest defense against death-by-a-thousand-cuts in ranging markets.

2. **Higher-timeframe trend.** A 4h buy signal that fights the daily downtrend is usually a
   trap. Requiring the daily to be in an uptrend filters these out.

## Risk management

- **ATR trailing stop** (`custom_stoploss`): the stop distance scales with volatility.
  Calm market → tight stop. Volatile market → wider stop so normal noise doesn't eject us.
  It only ever ratchets tighter, locking in gains as a trade works.
- **Static stoploss** (`-10%`): a hard backstop if something unexpected happens.
- **minimal_roi**: intentionally permissive. We want the trailing stop and exit signals to
  manage trades, not an arbitrary fixed profit target. Tighten only after paper trading.

## Known limitations (be honest about these)

- **Long-only.** It can't profit from downtrends, only sidestep them. Shorting adds
  complexity and risk; deferred on purpose.
- **No fundamentals or news.** Pure technical analysis. A surprise announcement can blow
  through any technical level instantly.
- **Simulated-data heritage.** The logic was prototyped on synthetic data. Real markets
  have slippage, fees, gaps, and liquidity constraints. Paper trading on the live feed is
  the real test.
- **Parameter sensitivity.** The defaults are reasonable but not optimized for any specific
  pair. Hyperopt can help, but it's also the easiest way to overfit (see ROADMAP Phase 3).

## How to tune responsibly

1. Change **one** parameter or rule at a time.
2. Re-run `scripts/backtest.sh`, then **always** `scripts/validate.sh`.
3. Compare against the previous result. Record both in the changelog below.
4. Watch the gap between in-sample and out-of-sample (walk-forward) performance. A widening
   gap means you're fitting noise, not finding edge.
5. If a change makes backtest results dramatically better, be *more* suspicious, not less.

## Changelog

### v1.2.1 — signal_advisor HTML fix (2026-06-03)
- Fixed Telegram 400 error: `rsi<38` layer label used raw `<` which Telegram's HTML parse_mode rejected. Changed to `rsi&lt;38` in `scripts/signal_advisor.py`.
- Confirmed end-to-end: advisor fetches live Binance data, runs indicators, sends BUY/HOLD/SELL message including sentiment block to Telegram.

### v1.2 — EMA200 1d macro gate (2026-06-03)
- Added `ema200` + `above_ema200` to `populate_indicators_1d`; wired as `macro_ok` gate in `populate_entry_trend`.
- No new hyperopt params — structural logic change only.
- 2024 (in-sample): +1.09% → +1.98%, Sharpe 0.13 → 0.24, PF 1.07 → 1.14, trades 90 → 85.
- 2025 OOS (market -44%): -5.28% → -0.98%, Sharpe -0.43 → -0.08, PF 0.72 → 0.92, trades 84 → 58.
- Lookahead check: PASS.
- Verdict: keep. Cuts bear-market bleed by ~81%. Residual -0.98% in 2025 is structural — EMA200 is lagging and doesn't catch early trend reversals. Acceptable for a long-only strategy.

### v1.1 — first hyperopt run (2026-06-03)
- Ran `freqtrade hyperopt` with `SharpeHyperOptLoss`, 200 epochs, `buy`+`sell` spaces, timerange 20240101-20250101.
- Optimised params: `buy_rsi=32`, `buy_adx_min=25`, `buy_vol_mult=1.8`, `buy_bb_std=1.8`, `buy_min_score=3`, `sell_rsi=80`, `atr_stop_mult=3.9`.
- In-sample 2024: -10.29% → +1.09% profit, Sharpe -1.48 → +0.13, profit factor 0.68 → 1.07, drawdown 13.09% → ~1.5%.
- Out-of-sample 2023: +5.30%, Sharpe 0.62, profit factor 1.43, max drawdown 2.48%. Market was +146%.
- Out-of-sample 2025 (Jan–Jun): -5.28%, Sharpe -0.43. Market was -44% (sustained bear). Long-only strategy losing less than market — risk management working, but still net negative.
- Lookahead/recursion check: PASS (ran before hyperopt on default params; re-validate if logic changes).
- Verdict: keep. Structural gap remains — strategy underperforms in bull markets and loses slowly in bears. Next investigation: add EMA200 1d macro filter to pause trading in sustained downtrends.

### v1.0 — initial port
- Ported the 6-layer logic from the StrategyLab Pro prototype into Freqtrade.
- ADX regime filter (≥22), ATR trailing stop (2.5×), daily higher-timeframe filter.
- Hyperopt parameters defined for buy/sell spaces.
- Status: ready for backtesting + paper trading.

<!-- Add new entries above this line. Template:
### vX.Y — short title (date)
- What changed and why.
- Backtest before → after (win rate, profit, max DD, profit factor).
- Lookahead/recursion check: pass/fail.
- Verdict: keep / revert.
-->
