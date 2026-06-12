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

### v1.5 — entry-layer attribution tags + custom_stoploss audit (2026-06-12)
- **Audit (no code change):** investigated suspected lookahead in `custom_stoploss`
  (`dataframe["atr"].iat[-1]` on `get_analyzed_dataframe`). Verified in freqtrade 2026.5
  source that backtesting slices the analyzed dataframe to the current simulated candle
  (`DataProvider._set_dataframe_max_index`), so `.iat[-1]` is the correct current-candle
  ATR. No bug; v1.1–v1.3 backtest numbers stand. 2023/2024 backtests reproduced v1.3 exactly.
- **Change:** added `enter_tag` layer bitmap (e.g. `L1+L3+L5`) in `populate_entry_trend`.
  Tagging only — entry/exit logic untouched; full-range backtest totals unchanged.
- **Attribution findings** (20230101–20250601, 107 trades, +16.26%, PF 1.67):
  - Only 4 layer combos ever fire. Two archetypes dominate: `L1+L3+L5` trend-continuation
    (79 trades, avg +1.8%) and `L2+L4+L5` mean-reversion dip (25 trades, avg +1.3%).
    Both net positive in 2023, 2024, and 2025 — no rotten combo to filter out.
  - L5 (volume) fired on 100% of entries — it behaves as a hard gate, not a confirmation.
  - L6 (RSI divergence) fired once in 2.5 years, and that trade hit the full -10% stop.
    Too rare to justify, but n=1 is not evidence to act on; leave for now.
  - The 6 hard -10% stop_loss exits cost -0.61 total — as much as all 65 trailing stops
    combined. Inspected: 5 of 6 are SOL/USDT (the most volatile pair), most hit -10%
    within 4–24h — flash-crash candles too fast for the 4h trail to ratchet (incl. the
    2025-01-19/20 SOL crash). Future experiment candidate: volatility-aware position
    sizing (smaller stakes when ATR% is extreme) rather than touching the stop itself.
- Lookahead + recursion check: PASS.
- Verdict: keep (instrumentation is free and makes every future experiment measurable).

### v1.4 experiment — armed trailing stop (2026-06-10) — REVERTED
- Hypothesis (from trade export): the always-on ATR trail handles 62% of exits at avg -1.57% (26% win rate) and is the drag; arming it only after +1 ATR of profit should cut that bucket. Supporting evidence: hyperopt pinned `atr_stop_mult` at 3.9 against a 4.0 ceiling, and the indicator exit averages +7.37% at 100% win rate.
- Change tested: `custom_stoploss` returned the static -10% until `current_profit >= 1 ATR`, then trailed at 3.9×ATR.
- Results: 2023 +5.62% → +4.86% (worse), 2024 +7.32% → +9.75% (better), 2025 bear +1.03% → **-0.70%** (flipped negative).
- Verdict: **revert**. Total was a wash but regime robustness — v1.3's best property — degraded; barely-green bear-market trades rode down to the -10% backstop instead of exiting at -1.6%. Trailing-stop avenue is now closed with data.
- Useful residue: the exit-reason breakdown (indicator exit = the moneymaker; trail = defensive cost) should guide future experiments toward entry quality, not exit tuning.

### v1.3 — ROI table disabled (2026-06-10)
- Diagnosis: `minimal_roi` force-took profit at 2% after one day, capping winners while the 3.9× ATR trailing stop was tuned to let them run — the two exits fought each other (avg winner was 0.43%).
- One change: `minimal_roi = {"0": 100}` (never triggers) in both the strategy and the hyperopt JSON (the JSON pins ROI and silently overrides the .py).
- 2023: +5.30% → +5.62%, PF 1.43 → 2.09, drawdown 2.48% → 1.70%.
- 2024: +1.98% → +7.32%, Sharpe 0.24 → 0.50, PF 1.14 → 1.48.
- 2025 bear (market -44%): -0.98% → **+1.03%**, PF 0.92 → 1.08 — first period flipped from loss to gain.
- Trade counts dropped (fewer, longer trades) — consistent with winners running instead of being clipped.
- Lookahead check: PASS.
- Verdict: keep. Exits are now owned entirely by ATR trailing + indicator exit. Still far below buy-and-hold in bulls; that's structural for a dip-buying long-only system.

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
