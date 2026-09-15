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

### v1.8 experiment — portfolio-level risk cap (2026-07-07) — NOT ENABLED
- **Hypothesis:** v1.6's vol-haircut sizes each trade independently by its own ATR%.
  With `max_open_trades=3` and fixed `stake_amount=100`, three simultaneous
  high-volatility entries could each pass the per-trade check while stacking more
  combined risk than intended — crypto pairs move together in a crash, so per-trade
  independence doesn't guarantee portfolio-level safety.
- **Change tested:** added `custom_stake_amount` second-pass cap — total risk (stake
  x stop-distance, summed across all open trades + the one being sized) capped at
  `portfolio_risk_cap_pct` of total wallet. Behind a disabled-by-default flag
  (`enable_portfolio_risk_cap`), never touches existing trades, never increases stake.
- **Results** (20230101-20250601, same range as v1.6/v1.7):
  - At `portfolio_risk_cap_pct=0.06` (6%, a reasonable-sounding threshold): **complete
    no-op**. Byte-identical results to the flag being off. Math: 3 trades x $100 stake
    x ~4-10% ATR-stop-distance is only ~$12-30 combined risk, well under 6% of a
    $1000 wallet ($60). The scenario it targets doesn't occur at this stake size.
  - Tightened to 1.5% purely to confirm the mechanism binds at all: it does (profit
    19.03% -> 18.43%), but **max drawdown was unchanged** (2.64% -> 2.65%). It
    throttled position size without reducing realized risk for this strategy's
    actual trade pattern — a worse risk/reward trade than just cutting stake size
    directly, not a smarter one.
  - Lookahead check: PASS (no bias) at both settings — the stake-sizing hook doesn't
    touch entry/exit signal logic, so this was expected.
- **Verdict: keep code, disabled.** No backtest evidence this helps at any threshold
  loose enough to matter, and tightening it just becomes a blunt stake cut with no
  demonstrated drawdown benefit. Left in the strategy file (flag off, well-documented)
  as ready-to-test infrastructure in case a future config — bigger stakes, more
  concurrent open trades, a portfolio that actually experiences correlated pile-ups —
  makes the scenario it targets real. Re-test before ever flipping the flag on.
- **Baseline note:** backtested against the actual v1.1-hyperopted params
  (`buy_rsi=32, buy_adx_min=25, buy_vol_mult=1.8, buy_bb_std=1.8, buy_min_score=3,
  sell_rsi=80, atr_stop_mult=3.9`) — 106 trades, +19.03%, PF 1.89, max DD 2.64%.
  Close to but not identical to the documented v1.6 full-range numbers (+17.12%,
  PF 1.75, 107 trades) — plausibly explained by v1.7's L6 removal (one fewer losing
  trade type) plus possible minor data-file differences since those notes were
  written. Recommend re-confirming this baseline independently before treating it as
  the new reference number.

### config fix — BNB pairlist contradiction (2026-06-21)
- Config-only, no strategy logic touched. `BNB/USDT` sat in **both** `pair_whitelist`
  and `pair_blacklist` (`BNB/.*`) in `config-dryrun.json`. Blacklist won every cycle,
  so BNB could never trade — a dead whitelist slot spamming a `Removing it from
  whitelist` WARNING each loop. Dropped `BNB/USDT` from the whitelist (blacklist was
  the clear intent).
- Restarted dry-run; whitelist now resolves cleanly to `['BTC/USDT','ETH/USDT','SOL/USDT']`,
  warning gone. **Paper clock restarts here (2026-06-21).** Note: the bot had also died
  and relaunched ~9× since 6/17 (Windows sleep/reboot), so the 6/17 clock was already
  fragmented — worth fixing power settings before trusting the live sample.

### v1.7 — prune L6 (bullish RSI divergence) (2026-06-17)
- **Hypothesis (from v1.5 attribution):** L6 fired on exactly one entry in 2.5
  years and that single trade hit the full -10% stop. A confirmation layer that
  fires once and loses isn't confirming anything — it's noise that can only ever
  push a borderline 2-layer setup over the `buy_min_score=3` line. Acting now (vs
  v1.5's "n=1, leave it") because the cost is asymmetric: it can add bad entries,
  never good ones, and removing it also deletes ~20 lines of divergence plumbing.
- **Change:** removed the `bull_div` indicator block from `populate_indicators`
  and dropped `l6` from `buy_score` / the attribution `layers` dict in
  `populate_entry_trend`. No thresholds touched; stops, sizing, gates unchanged.
- **Results** (v1.6 → v1.7, 20230101–20250601):
  - Full range: +17.12% → **+19.03%**, trades 107 → **106** (exactly one entry
    removed), win 52.3% → **53.8%**, avg profit 1.52% → **1.71%**, max DD
    3.09% → **2.64%**.
  - The dropped trade was the lone L6 entry, in 2024: 2024 mixed +7.39% → **+9.30%**
    (DD 2.78%). 2023 bull +5.64% and 2025-H1 bear +2.90% **identical** to v1.6 —
    no other entry changed. No regime flipped negative (the v1.4 failure mode).
- Lookahead check: **PASS** (no bias, 0 biased entry/exit/indicators, 20 signals).
  Recursion: `atr` stable at -0.000%; `ema200_1d` shows the pre-existing v1.2
  startup characteristic, unrelated to this change.
- **Verdict: keep.** Strictly removes a known loser; improvement is one trade,
  fully explained, not a suspicious across-the-board lift. Less code, same risk
  controls. L6 logic preserved in git history if ever revisited with real evidence.

### v1.6 — volatility-aware position sizing (2026-06-14)
- **Hypothesis (from v1.5 attribution):** the 6 hard -10% stop exits were the single
  biggest cost bucket (≈ as much as all 65 trailing stops combined), and 5 of 6 were SOL
  flash crashes. v1.5 flagged volatility-aware sizing as the fix — risk fewer *dollars* on
  high-volatility entries rather than touching the stop or the signals.
- **Threshold set from data, not guessed.** Measured ATR% (atr/close) distribution on 4h:
  BTC median 1.28% / p90 2.02%; SOL median 2.49% / p90 4.10% / max 7.27%. SOL runs ~2× BTC
  volatility and owns the flash-crash tail. Picked a 3.5% knee: normal BTC/ETH/BNB and
  typical SOL trades are untouched; only elevated-vol entries get trimmed.
- **Change:** added `custom_stake_amount`. When entry-candle ATR% > 3.5%, stake is scaled
  by `max(0.5, 0.035 / atr_pct)` (inverse-proportional, floored at 50%). Below threshold,
  full size. Risk policy — deliberately NOT hyperopted (can't be overfit). Entry/exit logic
  and stops untouched; trade count stays 107.
- **Results** (v1.5 → v1.6):
  - Full 20230101–20250601: +16.26% → **+17.12%**, PF 1.67 → **1.75**, Sharpe 0.46 → **0.50**,
    max DD 3.20% → **3.09%**.
  - 2023 bull: +5.62% → +5.64% (flat). 2024 mixed: +7.32% → +7.39%, DD 3.37% → 3.26%.
  - 2025 H1 bear: +2.14% → **+2.90%**, DD 1.97% → **1.23%** — biggest gain, exactly where
    tail risk bites. No regime flipped negative (the property v1.4 broke).
- Lookahead check: PASS (no bias, 0 biased signals). Recursion: `atr` stable at -0.000%;
  the ema200_1d figure is the pre-existing v1.2 characteristic, unrelated to this change.
- **Verdict: keep.** Small, mechanistically-expected, risk-adjusted improvement concentrated
  in the bear regime. Strengthens risk management rather than weakening it. Not a suspicious
  result — believable in size and direction.

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

### Dry-run drought diagnosis (2026-07-20/21)
- Zero trades since pairlist expansion (Jul 14, ff2fa1f) despite 8 whitelisted pairs. Investigated
  live: EC2 `jamtrade-dryrun.service` log confirms whitelist loaded correctly (8 pairs), bot
  RUNNING, no errors — just heartbeats, zero "Executing"/enter events.
- Cross-checked with `signal_advisor.py` locally (Binance proxy data, Kraken unreachable from
  this network/timeout — Binance/majors correlate closely enough for diagnosis): all 8 pairs
  ADX 11–21 (below the 22 threshold, all "choppy/no-trade zone"), buy_score capped at 2/6
  (`trend` + `macd_up` fire; `rsi<38`, `below_BB`, `vol_spike` never fire — RSI sitting
  40–64 mid-range, no dip anywhere).
- Root cause: not a pairlist-size problem. Crypto majors are correlated — when the market-wide
  regime is choppy/sideways with no capitulation, ALL pairs fail the same gates simultaneously,
  regardless of whitelist size. The Jul 14 fix (widening from 3→8 pairs) targeted the wrong
  layer; it helps when pairs diverge, not when the whole market sits in one regime.
- Verdict: **not a bug.** Strategy is a regime-selective dip-buyer by design (see v1.5 finding:
  L5/volume fires on 100% of real entries — hard gate, rare). Zero trades in a rangebound,
  non-panicky market is the strategy correctly sitting out, not malfunctioning. No code/config
  change made. Re-check if drought extends multiple weeks with no regime shift.

### Train/test split (2026-09-15) — the edge does not generalise. VERDICT.

Follow-up to the walk-forward decay. Question: was there ever a real edge that later
decayed, or was the 2024-25 performance a fitting artifact? Method: hyperopt on an
earlier slice ONLY, then evaluate on a later slice the optimiser never saw.

- **Train:** 2024-03-01 → 2025-03-01 (12 months). 100 epochs, Optuna/NSGAIII,
  SharpeHyperOptLoss, spaces buy+sell, `--disable-param-export`. 64 epochs completed.
- **Test:** 2025-03-01 → 2026-06-01 (15 months). Never seen by the optimiser.

```
params                                    train                      test
train-fitted (rsi31/adx23/vol1.7/atr3.6)  56tr 53.6% win  +0.73%     46tr 41.3% win  -0.74%
live         (rsi32/adx25/vol1.8/atr3.9)  54tr 48.1% win  +1.41%     38tr 44.7% win  -0.16%
```

**1. The edge is period-specific, not real.** BOTH parameter sets are positive in train
and negative in test. This is not a question of parameter choice — the strategy stops
working after early 2025 regardless of how it is tuned.

**2. Hyperopt actively degraded generalisation.** The fitted params beat the live ones
in-sample on win rate (53.6% vs 48.1%) and were ~4x worse out-of-sample (-0.74% vs
-0.16%). The optimiser bought in-sample fit by selling robustness. This is the textbook
overfitting signature and it is worth internalising: *more hyperopt would make this
worse, not better.*

**3. The backtest infrastructure is honest — and that is the good news.** Live paper
trading avg profit is **-0.14%**. Live params backtested on the out-of-sample window give
**-0.16%**. Agreement to 0.02pp, across a different exchange (Kraken live vs Binance
backtest). Combined with lookahead-analysis reporting zero bias, this says the tooling is
trustworthy and predicted live performance almost exactly. What it measures is real. What
it measures just is not profitable in the current regime.

**Verdict: this strategy does not have a durable edge.** Phase 4 is not appropriate, and
further tuning is the wrong response. Per ROADMAP Phase 3, discard rather than defend.

Secondary finding — **`buy_bb_std` is not actually hyperoptable.** freqtrade warns:
`Parameter 'buy_bb_std' is part of this hyperopt run, but its value is used during
indicator calculation, which only runs once at hyperopt startup. All epochs will be
evaluated with its static start value.` It is consumed in `populate_indicators`, so the
optimiser samples it and the samples do nothing. The `1.8` recorded in the 2026-06-03
export was therefore an arbitrary draw, never an optimised value. Fix would be
`.range` or `--analyze-per-epoch` — but given the verdict above, do not bother tuning it.

### Walk-forward (2026-09-15) — DECAY FLAG. Do not proceed to Phase 4.

8 windows, 6 months each, 3-month step, all fully warmed (2024-03-01 → 2026-06-01,
current code, Binance data):

```
win  range                 n   win%    avg%    PF  maxDD%
 1   2024-03→09           26    50%  +0.28%  1.11   2.89%
 2   2024-06→12           26    62%  +2.67%  2.98   1.32%
 3   2024-09→2025-03      28    46%  +2.47%  2.41   1.17%
 4   2024-12→2025-06      17    47%  +1.53%  1.76   1.22%
 5   2025-03→09           25    48%  +0.29%  1.12   2.86%
 6   2025-06→12           32    44%  -0.33%  0.88   3.91%
 7   2025-09→2026-03      12    42%  -0.83%  0.73   1.99%
 8   2025-12→2026-06       1     0%  -3.32%  0.00  (thin)
```

Profit factor decays monotonically after window 2: **2.98 → 2.41 → 1.76 → 1.12 → 0.88
→ 0.73**. The last three windows are net losing. Slope -0.412pp/window.

**Entry frequency collapses too**: 32 trades in window 6, 12 in window 7, 1 in window 8.
Not merely losing — finding progressively fewer setups.

**The decay is INSIDE the optimisation range.** The hyperopt export
(`MultiConfirmationStrategy.json`) is dated 2026-06-03, so every window here is data the
parameters were fitted on. This is not out-of-sample degradation; the strategy is losing
money in the recent portion of its own training data.

**This reframes the drift check that passed on the same day.** Live avg profit of -0.14%
looked "within thresholds" against the 2.25-year baseline average of +0.76% — but that
average is carried by the strong 2024-25 windows. Against the recent windows (-0.33%,
-0.83%), live is exactly where the backtest says it should be. Live and backtest agree
with each other; they agree that the edge is absent in the current regime. A passing
drift check is not evidence of a working strategy when the reference itself is losing.

Caveats, stated so they are not used to wave this away:
- Windows overlap 50%, so they are not independent; the effective sample is smaller
  than 8 and the slope is less precise than it looks.
- Binance data; live runs on Kraken. Unavoidable — Kraken serves no OHLCV.
- Window 8 (n=1) is noise and should be ignored; the trend holds without it.

**Per ROADMAP Phase 3: an edge that does not hold up should be discarded, not defended.**
Phase 4 (real capital) is not appropriate. Honest options, in order of preference:

1. Accept that this strategy is regime-dependent — it worked in the 2024-25 conditions
   and does not work now — and either sit it out or develop something regime-aware.
2. Re-examine whether the 2024-25 performance was itself an artifact of the hyperopt,
   by hyperopting on an EARLIER slice and testing forward on a later one it never saw.
3. Discard and start over with what was learned.

What NOT to do: re-run hyperopt over the full range until the numbers look good again.
That fits the parameters to the decay and produces a strategy that backtests beautifully
and loses money live. The decay is the finding; hiding it is not a fix.

### Live observations (2026-09-15) — 9 usable trades, NOT yet actionable

First performance report since recovery. **Sample is 11 closed trades, 2 of them outage
artifacts, spanning two different code versions.** Nothing below justifies a change yet;
recorded so it can be tested as the sample grows rather than rediscovered later.

**The drift flag fired and should be ignored.** It compares live Kraken trades on current
code against a Binance backtest of June-era code, at n=11 with 2 corrupted. The reported
`maxDD -31.42%` is likewise dominated by the artifacts. Incomparable, not alarming.

**Hypothesis 1 — the ATR trail may be too wide.** Every loss came from the trailing stop;
every win from the indicator exit:

```
exit_signal          6   83% win   +4.89% avg    47 hrs
trailing_stop_loss   5    0% win   -6.18% avg   160 hrs
```

Excluding the two artifacts still leaves 3 trailing-stop trades, all losers, ~-4% each.
The duration gap is the interesting part: trailing-stop trades run ~3x longer. That is
the shape you would expect if `atr_stop_mult = 3.9` is wide enough that losers drift for
days before the stop catches them. Three clean trades cannot establish this — but it is a
hypothesis with a mechanism, so it is worth watching specifically.
*Test when n >= 30: does the exit_signal / trailing_stop split persist?*

**Hypothesis 2 — CORRECTED, and it is weaker than it first looked.** Live layer fire
rates across the 11 trades:

```
L1 (price > EMA50)   100%      L4 (below lower BB)    9%
L3 (MACD hist > 0)    91%      L2 (RSI < 32)          0%
L5 (volume > 1.8x)   100%
```

The initial read was "L2 never fires, so on tuned parameters this is a momentum entry,
not the dip-buyer the notes describe". **That was overreach from an 11-trade sample.**
The regenerated baseline (92 trades, same code, 2024-03 to 2026-06) shows:

```
63  L1+L3+L5   (momentum: trend + MACD + volume)
26  L2+L4+L5   (dip: oversold + below-BB + volume)   <- 28% of entries
 3  L1+L4+L5
```

So L2 fires regularly on current parameters — roughly 28% of entries are genuine dip
buys. The live sample simply contained none of them. At a 28% base rate, eleven
consecutive non-dip entries is uncommon (~2.5%) but not extraordinary, and it may also
reflect venue or regime rather than anything structural.

What survives: the strategy has **two distinct entry modes**, not one, and the live
sample so far has exercised only the momentum mode. Worth tracking whether the dip mode
shows up as the sample grows, and whether the two modes perform differently — the
backtest tags make that measurable. What does NOT survive is the claim that the dip
layers are dead.
*Do not loosen RSI. The dip condition works in backtest; the live sample is just small.*

### Outage 2026-09-09 → 2026-09-14 — bot dead 5 days, 2 trades corrupted

**Read this before interpreting any trade before 2026-09-14.**

The EC2 root disk filled. freqtrade crash-looped on
`OSError: [Errno 28] No space left on device` (and sqlite `disk I/O error`) for
roughly five days — **9,918 restarts** — with no notification. Recovered 2026-09-14.

Not a leak: the box is a 6.7 GB root carrying a 2 GB swapfile and a 918 MB venv,
leaving ~1 GB of working room, and Ubuntu's own apt/snap housekeeping churns
~150 MB/day. It was always going to tip eventually. Fixed by reclaiming caches,
halving the swapfile (2G→1G) and capping journald; 93% → 78% free.

**Two trades are artifacts of the outage and must be excluded from analysis:**

| id | pair | exit | reason |
|----|------|------|--------|
| 10 | BTC/USDT | -4.92% | trailing_stop_loss |
| 11 | LINK/USDT | **-14.06%** | trailing_stop_loss |

LINK exited **past the -10% hard stoploss**. That is not a strategy result. The ATR
trailing stop is only evaluated when the bot processes a candle, so while the process
was dead no stop existed at all; on restart it exited at whatever price had become.
Usable sample is **9 trades**, not 11.

The general lesson, now in the Phase 4 gate: **uptime monitoring is a risk control
for this project, not ops hygiene.** A dead bot converts a bounded max loss into an
unbounded one. `healthcheck.sh` was rewritten (it had been watching the advisor timer
and never the bot, the disk, or progress) and now runs hourly on a systemd timer.

A second, separate bug surfaced during recovery: ccxt returns `taker=None` for Kraken
per-market fees, so freqtrade died with `TypeError: float * NoneType` on the first
market order — i.e. on the first stoploss exit. Fee is now pinned in the config. Note
the shape: entries are limit orders and worked fine, so the bot appeared healthy right
up until the moment it needed to cut a loss.

**Restart boundary: 2026-09-14 07:40 UTC.** Trades after this run the caught-up
strategy (the box had been stuck at the PR #1 merge since June — it was running
neither v1.7 nor v1.8 — plus startup_candle_count 400 and the fail-closed HTF gates).
Do not compare trades across that line.

### Audit fixes (2026-09-14) — warmup + fail-closed gates

Repo-wide audit. Two changes here affect strategy behaviour; the rest were config/tooling.

**`startup_candle_count` 200 → 400 — VALIDATED, and the old value was over a cliff.**
Freqtrade applies this count to each timeframe in its own units, so 200 gave the 1d
informative only 200 daily candles. `recursive-analysis` (freqtrade 2026.8) shows what
that actually meant:

```
Indicators      |    199 |   399  | 400 (strategy) |   499  |   999   |  1999
ema200_1d       |   nan% | 0.122% |         0.142% | 0.113% | -0.001% | -0.001%
above_ema200_1d |   nan% |    -   |             -  |    -   |    -    |    -
```

At 199 candles the daily EMA200 is **not computable — nan** — which makes the derived
`above_ema200_1d` gate nan as well. A nan comparison evaluates False, so in that state the
macro gate does not "allow by default", it **silently blocks every entry**. The old setting
sat one candle off that edge.

400 is on the defined side with 0.14% residual drift vs a 1999-candle reference. Full
convergence needs ~999 candles, but that demands ~2.7 years of daily history ahead of any
backtest window, and the gate only consumes EMA200 as a binary `close > ema200` test —
0.14% changes the answer only when price is within 0.14% of the line. Not worth the cost.

Validation (2026-09-14, freqtrade 2026.8, Binance data, local venv):
- `lookahead-analysis`: **no bias** — 0 biased entry signals, 0 biased exit, 0 biased
  indicators across 20 signals.
- Backtest 20230101-20250601 reproduces `backtest_baseline.json` **exactly**: 106 trades,
  53.8% win, 1.71% avg profit, 2.64% max drawdown, 19.03% total. No regression from any
  change in this batch.
- Controlled A/B on 20240301-20250601 (a window where 400 candles of warmup genuinely fit),
  startup 200 vs 400, cache disabled: **byte-identical** — 59 trades, 1.43% avg, 9.31%
  total, 2.89% DD. In a strong uptrend price sits far enough above EMA200 that seed bias
  never flips the boolean; the fix removes a latent failure mode rather than changing
  present-day results.

**This reopens the Jul-2026 drought question — and it is now known to be UNRESOLVABLE
with available data.** The 2026-07-20/21 entry below concluded "not a bug — choppy
regime", reasoning from ADX readings taken with `signal_advisor.py`. That tool was
independently broken at the time (see below), and we now know the macro gate can
hard-block on nan rather than degrade gracefully. Settling it needs OHLCV covering July
2026, and no source can provide it:

- **Kraken serves no OHLCV at all.** Verified 2026-09-15 on the EC2 box:
  `ERROR - Historic klines not available for Kraken. Please use --dl-trades instead.`
  Reconstructing candles from raw trades is gigabytes per pair — not practical on a
  t3.micro.
- **Binance** returns 403 from the owner's network and 451 from US AWS IPs.
- The local Binance archive **ends 2026-06-03**, before the drought.

A third exchange (OKX, Bybit, Coinbase) could act as a proxy, but proxying correlated
majors is exactly the reasoning that made the original diagnosis shaky, so it would
produce another unfalsifiable answer rather than a real one. **Leave this open.** The
regime explanation may be correct, incomplete, or wrong — treat all three as live
possibilities rather than citing the July verdict as settled.

**Higher-timeframe gates now fail CLOSED.**
`populate_entry_trend` used `dataframe.get("above_ema200_1d", 1) == 1`, which defaults to
*allow* when the column is absent. A broken informative merge would therefore delete the
macro filter silently and the bot would start buying in exactly the sustained bear markets
the gate exists to avoid — with nothing in the logs. Missing 1d columns now block all
entries for that pair and emit a `logger.warning`. Risk gates must not be able to vanish
quietly (CLAUDE.md rule 4).
- No behaviour change on the normal path: when 1d data merges correctly, the logic is
  identical. This only changes the data-fault path.

**Also relevant to reading older entries:** the advisor (`signal_advisor.py`) had drifted
from the strategy — it still scored the removed L6 divergence layer, omitted both daily
gates entirely, and hardcoded thresholds that no longer matched the hyperopt export
(RSI 38 vs the live 32, ADX 22 vs 25, volume 1.4x vs 1.8x). It now reads
`MultiConfirmationStrategy.json` directly. The Jul-20/21 drought diagnosis above was made
with the drifted tool: its ADX conclusion stands, but the quoted "below the 22 threshold"
was really 25, and the "score capped at 2/6" was on a 6-layer scale the bot no longer uses.

<!-- Add new entries above this line. Template:
### vX.Y — short title (date)
- What changed and why.
- Backtest before → after (win rate, profit, max DD, profit factor).
- Lookahead/recursion check: pass/fail.
- Verdict: keep / revert.
-->
