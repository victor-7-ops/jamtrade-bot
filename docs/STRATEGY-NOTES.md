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

### Drought checked LIVE this time (2026-10-28) — correctly sitting out, confirmed

1 closed trade in the 15 days since the 2026-10-13 revert, against 27 trades in the 29 days
before it. A 13x collapse in activity. Bot itself healthy: active, 0 restarts, disk 38%, no
alerts.

Checked the gates **while the drought was happening** — the thing nobody did in July, which
is why that verdict is still marked unresolvable:

```
pair         >EMA50d  >EMA200d   ADX4h  ADX>=25  ALL GATES
BTC/USDT       False      True    24.8    False      False
ETH/USDT       False     False    28.3     True      False
SOL/USDT       False      True    22.4    False      False
ADA/USDT       False     False    31.6     True      False
XRP/USDT       False     False    18.0    False      False
LINK/USDT      False     False    27.8     True      False
DOT/USDT       False     False    28.1     True      False
AVAX/USDT      False     False    25.3     True      False
```

**All 8 pairs below their daily EMA50.** That gate alone blocks every entry regardless of
anything else. ADX is healthy on 5 of 8 — there is a trend, it points down. **Not wedged,
correctly sitting out.** Confirmed, not inferred.

Two consequences.

**The validation plan has no timeline.** Trade pace swings 13x with regime (0.93/day then
0.07/day). "Wait for 30 trades in one regime" could be two months or over a year, and which
one is unknowable in advance. A strategy that cannot be evaluated on a human timescale is
hard to improve regardless of whether it is any good.

**It sharpens the trend-following comparison.** A trend-follower would be equally flat right
now — everything is below its moving averages, so same position, same safety. The entire
return gap came from participation on the way UP, not from better behaviour in drawdowns.
Both approaches sit out a bear; only one captures the bull.

### Trend-following test (2026-10-28) — 10x better than this strategy, still loses to sizing

**Diagnosis first.** Mean edge vs holding is -72.9pp in rising markets and +21.1pp in
falling ones, at 29% exposure. The losses are not bad trades, they are **absence**: in the
+254% train window the strategy captured +18.6%. Crypto returns are violently right-skewed,
a handful of weeks carry most of the gain, and a dip-buyer is least invested exactly when
price is running. That is the design choosing to miss the fat tail, not a tuning fault.

**Test.** The crudest possible inversion — hold what is above its 200-day MA, else cash at
4.5%. No parameters, no layers, no volume gate. Signals use `shift(1)` (no lookahead),
switching modelled at 0.1% per side. Same window as the benchmark, 2023-03 → 2026-10, OKX
8-pair data.

```
variant                     total    CAGR    maxDD  Sharpe  Sortino  Calmar
buy & hold basket          +98.1%  +21.0%   -74.4%    0.51     0.77    0.28
static 15% + 85% cash      +40.0%   +9.8%   -13.3%    0.84     1.26    0.74
trend: basket >200dMA      +73.9%  +16.7%   -62.0%    0.47     0.45    0.27
trend: per-asset >200dMA  +113.4%  +23.5%   -48.6%    0.60     0.64    0.48
STRATEGY (atr 3.9)          +9.6%   +2.6%   -10.7%    0.36     0.36    0.24

time invested: basket-level 49%, per-asset 45%  (strategy: 29%)
switches: 38 basket / 36 turnover units per-asset
```

**Two findings, and they point opposite ways.**

1. **The diagnosis is confirmed.** A two-line rule returns +113.4% against this strategy's
   +9.6%, at higher Sharpe, beating buy-and-hold on *both* return and drawdown. Four months
   of multi-confirmation layers, hyperopt and ATR tuning are beaten decisively by "hold what
   is trending up". Per-asset beats basket-level (+113.4% vs +73.9%) — diversified signals
   matter more than the rule itself.

2. **It still loses to the static blend risk-adjusted** — Sharpe 0.60 vs 0.84, Calmar 0.48
   vs 0.74. **This gap cannot be closed by sizing**: scaling a strategy up or down leaves
   Sharpe unchanged, so at every position size the static blend returns more per unit of
   risk. Its -48.6% drawdown is also far outside what the current design targets.

**Conclusion: nothing tested beats sizing.** Timing helped enormously relative to the
current strategy and not at all relative to holding less. The benchmark survives everything
thrown at it so far.

**Caveats, stated so this is not over-read.** One cycle (2023-2026), one basket, one
rule. A mostly-cash portfolio gets a flattering Sharpe by construction — low volatility is
most of it. The window contains a once-in-a-cycle bull followed by a crash, which suits a
trend filter's best case and a static blend's best case simultaneously. The trend result is
also a single untuned rule with no out-of-sample split; **treat +113% as a direction, not an
estimate**, and walk-forward it before believing the number.

**If a redesign happens, start from the trend rule, not from this strategy.** It is simpler,
more robust (no venue-specific volume gate, no knife-edge thresholds), participates in the
right tail, and already outperforms by 10x before any tuning. The bar is unchanged: beat
15% basket + 85% T-bills at CAGR > 9.7% / maxDD < 13%, which the trend rule does **not**
currently clear on a risk-adjusted basis.

### SUPERSEDES the decay finding (2026-10-21) — there was no decay, there was never a consistent edge

Re-ran the walk-forward on the OKX 8-pair dataset: **13 windows**, 6 months each, 3-month
step, 2023-03 → 2026-09. The 2026-09-15 analysis that produced the DECAY FLAG used 92
trades / 3 pairs / 8 windows. Every other conclusion was re-checked against the larger
sample; this one had not been.

**The decay does not reproduce.**

```
                      old (92 trades, 3 pairs)   new (285 trades, 8 pairs)
avg-profit slope         -0.412 pp/window           -0.139 pp/window
verdict                  ⚠️ DECAY FLAG              ✅ no meaningful trend
```

Per-window on the new data:

```
win  range                 n   win%    avg%    PF  maxDD%   strat%    hold%   edge_pp  expo%
 1   20230301-20230901    32    47%  +0.50%  1.08   3.31%   +0.55%  -10.97%    +11.5    29%
 2   20230601-20231201    52    56%  +1.75%  1.83   3.01%   +8.56%  +57.94%    -49.4    31%
 3   20230901-20240301    78    53%  +1.39%  1.66   4.37%  +10.52% +204.82%   -194.3    45%
 4   20231201-20240601    64    39%  -0.37%  0.89   7.48%   -2.11%  +56.30%    -58.4    48%
 5   20240301-20240901    42    33%  -2.17%  0.39   9.23%   -8.84%  -28.11%    +19.3    28%
 6   20240601-20241201    47    57%  +2.49%  2.39   4.44%  +11.09%  +66.48%    -55.4    29%
 7   20240901-20250301    56    48%  +2.19%  1.87   3.49%  +12.88%  +58.53%    -45.6    41%
 8   20241201-20250601    37    35%  -1.47%  0.80   5.90%   -2.74%  -26.58%    +23.8    29%
 9   20250301-20250901    41    41%  -1.17%  0.73   5.15%   -3.82%  +30.73%    -34.5    27%
10   20250601-20251201    50    38%  -0.75%  0.77   7.96%   -3.74%  -21.28%    +17.5    30%
11   20250901-20260301    21    29%  -1.59%  0.49   4.11%   -3.34%  -54.59%    +51.3    10%
12   20251201-20260601     1     0%  -3.43%  0.00   0.34%   -0.34%  -31.06%    +30.7     0%  (thin)
13   20260301-20260901     9    67%  +1.16%  2.10   0.56%   +1.11%   -2.21%     +3.3     5%
```

**What replaces decay is arguably worse: instability.** `stdev/mean = 9.5x`. Window
averages swing -2.17% to +2.49% with no direction, and the sign tracks regime almost
perfectly — positive in 2/3/6/7 (bull stretches), negative in 5/8/9/10/11. Mean edge vs
holding is **-72.9pp in rising markets and +21.1pp in falling ones**, at 29% exposure.

**The narrative changes.** "It worked, then the market moved away from what it was tuned
on" is not supported. The honest reading is that **the strategy has no consistent edge in
either direction — it is a bet on regime**, and a full-range backtest number averages over
regimes that behave nothing like each other.

**This does not change the 2026-10-14 decision**, which rested on the full-cycle
risk-adjusted comparison (Sharpe 0.36 vs 0.50, losing to cash), not on decay. If anything
it strengthens it: there is no decayed edge to recover by retuning, so a redesign is the
only route. The standing bar is unchanged — beat 15% basket + 85% T-bills: CAGR > 9.7% at
maxDD < 13%.

**Note for any redesign:** the regime-tracking above is the one exploitable-looking pattern
in this data. Resist it. The 2026-10-13 regime-sizing test found exactly that kind of
signal in-sample and watched the sign reverse out-of-sample on n=4. Something that
correlates with regime after the fact is not the same as something that predicts it.

### Full-cycle verdict (2026-10-14) — a static allocation dominates this strategy

First full-cycle comparison on the 8-pair OKX dataset (285 trades, 2023-03 → 2026-10),
covering a +254% bull and a -43% bear.

**ATR sweep, train 2023-03..2025-01 / test 2025-01..2026-10:**

```
atr    train tot   test tot   full cycle   test DD
2.5      -18.0%     -14.9%      -30.2%      15.45%
3.0       -7.2%     -13.1%      -19.3%      13.65%
3.9      +18.6%     -10.2%       +6.5%      12.62%   <- live
4.5      +19.9%     -10.4%       +7.4%      11.76%
5.5      +28.8%     -10.3%      +15.6%      12.19%
7.0      +27.9%      -6.4%      +19.7%       9.21%
market  +254.2%     -43.1%     +101.5%
```

Wider stops do look better on this larger sample — 7.0 wins test return, test drawdown and
full cycle. **Not applied.** The backtest cannot predict trade-level live behaviour (L5 is
venue-specific, see below) and the last stop change made on weaker evidence cost two weeks
and a contaminated sample. 3.9 stays live; the live record keeps building under one config.

**The decisive numbers — risk-adjusted, full cycle:**

```
                     strategy (3.9)   buy & hold (8 pairs equal-weight)
total                    +9.64%                 +92.11%
CAGR                        n/a                 +19.97%
Sharpe  (daily)            0.36                    0.50
Sortino (daily)            0.36                    0.75
Calmar                     1.18                    0.27
max drawdown             -10.69%                 -74.38%
```

**This is a design problem, not a sizing problem.** If the strategy's Sharpe beat holding,
low absolute return would just mean "size it up". It does not — 0.36 vs 0.50. Leverage
would deliver *worse* volatility-adjusted returns than holding the basket.

The strategy's one real edge is drawdown: 10.7% against 74.4%, hence Calmar 1.18 vs 0.27.
But that can be bought more cheaply. A static ~15% allocation to the same basket, 85% cash:

```
return  ~ 0.15 x 92.11% = +13.8%      strategy: +9.64%
maxDD   ~ 0.15 x 74.38% = -11.2%      strategy: -10.69%
```

**A static fractional allocation roughly matches the drawdown and beats the return**, with
no bot, no VPS, no monitoring, no outages. With the idle 85% in T-bills it is not close.

Caveats, so this is not overstated: one cycle, one basket, cash modelled at 0% yield for the
static case, and a constant-fraction drawdown scales linearly while the strategy's is
path-dependent. The gap is wide enough to survive all three.

**Owner decision 2026-10-14: the profile is not good enough; rethink the approach rather
than tune it.** Recorded here because the next person to look at an ATR table will see 7.0
beating 3.9 and be tempted to tune — the problem is a tier above parameter choice.

What a rethink has to beat, stated concretely so it is falsifiable: **a static 15% basket
allocation returning ~+13.8% at ~11% drawdown over this cycle.** Any redesign that cannot
clear that bar is not worth operating, however good its backtest looks in isolation.

### SOLVED (2026-10-13) — why live diverges from backtest: L5 is venue-specific

The standing open question. Answered now that the OKX 8-pair dataset covers the live period.

**It is not execution quality.** Matched live and backtest trades over 2026-09-14 → 10-13:

```
                entry diff   exit diff   profit gap
mean over 7 matched trades    +0.39%      +0.37%      -0.18pp
```

Where both systems took the same trade, results agree almost exactly:

```
09-15 16:00 XRP    live -7.92%   backtest -7.86%
09-20 04:00 AVAX   live +7.99%   backtest +8.53%
09-28 20:00 LINK   live -7.11%   backtest -7.21%
```

So slippage, fees and fill quality are **not** the problem.

**The two systems take different trades.** Both produced 16 trades in the window — a
coincidence, not agreement. Only 7 matched on pair within 8h. Live took LINK 09-18 20:00,
AVAX 09-21 04:00 and three positions at 09-25 16:00; the backtest took ETH 09-21 04:00,
XRP 09-21 12:00, AVAX 09-23 16:00.

**Cause: L5 depends on volume, and volume is venue-specific.** Comparing Kraken (live) to
OKX (backtest) over the same 4h candles:

```
pair        price diff    Kraken/OKX volume ratio        L5 agreement
XRP/USDT      0.0316%     median 0.042  (0.01 - 0.39)       91.4%
LINK/USDT     0.0872%     median 0.064  (0.00 - 0.28)       90.9%
SOL/USDT      0.0297%     median 0.036  (0.01 - 0.20)       90.4%
```

Prices agree to ~0.03%. Kraken's volume is ~4% of OKX's and the ratio swings two orders of
magnitude. L5 is relative (`volume > 1.8x its own 20-SMA`) so the absolute level does not
matter — but the *shape* differs, because different venues have different participants.
Result: **the L5 condition disagrees on ~9% of candles**, and L5 fires on ~100% of entries.
A 9% disagreement rate on the hard gate across 8 pairs and hundreds of candles is more than
enough to produce completely different trade sets.

**What this means — carefully.**

1. **Backtesting on a proxy venue cannot predict live trade SELECTION for this strategy.**
   It is fine for price-driven logic; L5 is not price-driven. Since Kraken serves no OHLCV
   at all, there is no way to backtest the venue we actually trade on.
2. **The performance gap may be sampling noise, not a systematic penalty.** Per-trade
   returns here range -10.6% to +8.0%; with n=16 the standard error of the mean is roughly
   1.4pp, and the observed live-vs-backtest difference is about 2.75pp/trade — under two
   standard errors. **We cannot conclude live is systematically worse.** It drew a different,
   worse set of trades from a similar distribution.
3. **This retroactively weakens the v1.9 verdict further.** v1.9 "failing live" was measured
   against a backtest that was never taking the same trades. Combined with the units error
   corrected above, very little of the original case survives.
4. The backtest remains useful for **distribution-level** questions — does a change help on
   average across hundreds of trades — and useless for **trade-level** prediction.

**Do not "fix" this by removing or loosening L5.** v1.5 found L5 fires on 100% of entries,
making it a hard gate; changing it alters the strategy's identity, and the evidence here is
about measurement, not about whether L5 is a good filter. The honest response is to lower
confidence in short-window live-vs-backtest comparisons, not to reshape the strategy so it
backtests more conveniently.

### CORRECTION (2026-10-13) — the v1.9 revert rationale was based on a units error

**The headline claim in the v1.9 revert entry below is wrong.** It states v1.9 lost
"-26.64% while the market fell 8.29%", i.e. three times the market. That compared a
**sum of per-trade profit ratios** against an **account-relative** benchmark.

At a 100 USDT stake on a 1000 USDT wallet those differ by 10x. The real figures:

```
                        per-trade avg   summed ratios   ACCOUNT impact
v1.9 live, 6 trades        -4.44%          -26.64%          -2.66%
market over same window                                     -8.29%
```

**v1.9 lost 2.66% of account while the market fell 8.29% — it OUTPERFORMED by ~5.6pp.**
`performance_report.py` now leads with the account figure and labels the summed one.

**What this does and does not change.**

Still true: live underperformed the backtest. With the OKX 8-pair data now covering the
live period, the same windows backtest as:

```
window                      backtest acct   live acct   backtest/trade   live/trade
v1.8  2026-09-14 -> 09-29       +0.70%        -0.89%        +0.96%         -1.11%
v1.9  2026-09-29 -> 10-12       -1.42%        -2.66%        -1.83%         -4.44%
whole 2026-09-14 -> 10-12       -0.15%        -3.55%        +0.05%         -2.54%
```

Trade counts track closely (15 backtest vs 14 live), so **entry logic is firing as
expected — the divergence is in outcomes, not signals**, at roughly **-2.5pp per trade**.
That is a real gap worth chasing (slippage on market-order stop exits, Kraken-vs-OKX fills,
the 0.26% taker fee) but it is an execution-quality problem, not the collapse I described.

No longer supported: that v1.9 was a disaster. On 6 trades it beat its benchmark. The
remaining case against it — 0/6 wins and worse per-trade than backtest — is weak at that
sample size.

**The revert stands anyway**, for reasons that do not depend on the error: 3.9 has far more
live history, the sweep showed 3.9 best on both backtest windows, and v1.4 independently
closed the wider-stop avenue in June. But the *stated* reason was wrong, and a future reader
would otherwise inherit a false fact.

**Third measurement error in this project to produce a wrong strategy conclusion**, after
benchmarking against zero and ignoring exposure. All three came from comparing two numbers
that were not the same kind of thing. The instruments are now fixed in all three places;
the lesson is that a plausible-looking number deserves a unit check before it drives a
decision.

### Regime-aware sizing REJECTED before implementation (2026-10-13) — and why refinement keeps failing

Tested the hypothesis before writing the feature: does regime strength at entry predict
trade outcome? Measured as distance of daily close above the daily EMA200, on the 92-trade
baseline export.

In-sample over the whole period it looked real, and **inverted** the expected direction —
not "weak regime hurts" but "overextension hurts":

```
margin above daily EMA200      n   win%    avg%    cum pp
Q1  -0.9 to 11%               23   43.5   +0.69    +15.8
Q2    11 to 20%               23   56.5   +1.34    +30.9
Q3    20 to 32%               23   52.2   +2.90    +66.8
Q4    32 to 97%               23   34.8   -1.88    -43.3
corr(margin, profit) = -0.156
```

Plausible story: a "dip" when price sits 32-97% above its 200-day EMA is buying euphoria,
with no support beneath — bad for a dip-buyer.

**It does not survive the train/test split:**

```
                      margin >32%                 margin <=32%
TRAIN  2024-03..25-03  n=19  26.3% win  -58.9pp   n=35  60.0% win  +135.3pp
TEST   2025-03..26-06  n= 4  75.0% win  +15.6pp   n=34  41.2% win   -21.7pp
```

The sign **reverses** out-of-sample, on n=4. And 17 of the 23 high-margin trades fall
between 2024-03 and 2025-01 — it is one bull-market episode, not a relationship.
**Not implemented.**

**The pattern worth naming.** Four consecutive refinement attempts have now failed the same
way: hyperopt params (train-fitted, worse out-of-sample), v1.9's wider stop (clean
out-of-sample validation, failed live), the exit-logic variants (fixed one regime, broke
the other), and now regime sizing (sign reversal out-of-sample).

The common cause is sample size. The backtest is **92 trades over 27 months on 3 pairs**.
Any conditioning — by regime, by quartile, by window — splits that into groups of ~20, and
at n=20 noise dominates whatever structure exists. The strategy is not necessarily
unrefinable; **this dataset cannot distinguish a real refinement from a lucky one.**

That reframes the top priority. The blocker is not strategy design, it is **sample size**:

1. `config-backtest.json` runs 3 pairs while live runs 8. Downloading Binance data for the
   other five would roughly double-to-triple the trade count at zero strategy risk. This is
   now the single highest-value piece of work available.
2. Until then, treat any refinement that "works" in backtest as unproven regardless of how
   clean its validation looks — v1.9 passed a textbook train/test split and still cost two
   weeks of live data.
3. Live paper trading continues to accumulate the only sample that is not subject to this
   problem.

### Exit-logic fix attempted and REJECTED (2026-10-13) — it is structural, not a bug

Follow-up to the v1.9 finding below: the indicator exit cannot fire in a downtrend, so the
ATR stop is the only exit there. Tried to fix it by adding a 4th bearish condition `s4`
(threshold stays "2 of N"). Four variants, same window pair as all other tests:

```
variant                          train tot/DD      test tot/DD       full tot/DD
baseline (3 conditions)          +8.52% / 2.89%    -0.60% / 3.88%    +7.92% / 3.59%
A  close < ema50                 +2.71% / 4.74%    +1.21% / 2.08%    +3.93% / 4.74%
B  uptrend_1d == 0               +5.70% / 4.26%    -2.35% / 4.72%    --
C  A AND above_ema200_1d == 0    +8.52% / 2.89%    -1.03% / 3.90%    --
D  A AND ema50 falling 24h       +3.34% / 5.31%    +1.50% / 2.28%    +4.85% / 5.31%
```

(test window market change: -22.68%)

**Verdict: ship none of them.** A and D genuinely fix the bear case — the indicator exit
starts firing (51 of 75 exits under A, 56.9% win, +10.79%) instead of the stop taking
everything. But both cost 5-6pp in the bull window and are net-negative over the full
period with *worse* drawdown.

**Why it cannot be fixed this way — the part worth keeping.** This strategy is a
dip-buyer. L2 is `RSI < 32` and L4 is `close < lower Bollinger`: **price weakness is its
entry signal.** So price weakness cannot also serve as its exit signal. Any condition that
fires in a downtrend also fires on exactly the pullbacks the strategy exists to buy. Under
variant A, dip entries (`L2+L4+L5`, ~28% of trades) enter below the lower band — often
already below ema50 — so `s4` was true at entry and killed them at birth. Trade count fell
92 → 75.

The other two variants close off the remaining obvious routes:
- **C** proves the macro gate cannot help: entry already requires `above_ema200_1d == 1`,
  so it would have to flip mid-trade, and daily EMA200 is far too lagging for that. It
  almost never fired.
- **B** proves the daily uptrend gate cannot help either: same lagging daily signal, fires
  long after the damage.

A time-based exit was considered and dropped without testing: in the backtest losers are
*shorter* than winners (trailing 1d22h vs indicator 2d19h), so holding time does not
discriminate.

**What this means.** The exit asymmetry is not a defect in `populate_exit_trend` — it is
the cost of being a dip-buyer, and it is already priced into the current design. The ATR
stop *is* the bear-market exit, which is why the stop distance matters so much and why
widening it (v1.9) was so damaging. The current 3.9 is the best value tested.

Routes that remain genuinely open, none of them exit-condition tweaks:
1. Regime-aware position sizing — trade smaller when the macro gate is weak, rather than
   trying to exit faster.
2. Entry quality — v1.4 reached this same conclusion from the other direction: *"guide
   future experiments toward entry quality, not exit tuning."* Two independent routes now
   point there.
3. Accept the profile: this is a low-exposure system that gives up bull upside and limits
   bear damage, and the measured edge over buy-and-hold is small.

### v1.9 REVERTED (2026-10-13) — backtest said wider stop, live said no

`atr_stop_mult` 5.5 → **3.9**. Range reverted (3.0, 9.0) → (1.5, 4.0), default → 2.5.
14 days of v1.9 live:

```
6 closed trades · win 0% · avg -4.44%/trade · cum -26.64% · maxDD -26.64% · exposure 68%
exits:  trailing_stop_loss  6/6   (indicator exit NEVER fired)
tags:   L2+L4+L5 x4 (-3.91% avg) · L1+L3+L5 x2 (-5.49% avg)
```

Benchmark, fetched from Kraken over the same window (mean of the 8 whitelist pairs):
**-8.29%**. The strategy returned **-26.64%** at 68% exposure — roughly 18pp WORSE than
simply holding. No regime excuse: it lost three times what the market lost.

**Mechanism — and this is the part worth keeping.** `populate_exit_trend` needs 2 of:

```
rsi > sell_rsi (80)      # requires overbought
macdhist < 0             # fires in a downtrend
close > bb_upperband     # requires overbought
```

In a sustained downtrend only `macdhist < 0` can be true. Score reaches 1, never 2, so
**the indicator exit is structurally incapable of firing in a falling market** and the ATR
stop becomes the only way out. Widening that stop therefore enlarges every single loss in
precisely the regime where nothing else can close a position. 6/6 trailing-stop exits is
exactly this.

The backtest could not see it: its window (2024-03..2026-06) contained enough rallies for
indicator exits to carry the winners, so the wider stop looked like a pure drawdown
improvement (2.52% vs 3.59%).

**Why the range was reverted too, not just the value.** A hyperopt allowed to roam to 9.0
will rediscover 5.5+ every time, because the objective function cannot see this failure
mode. The narrow range is now a guard rail, not an oversight — do not "fix" it again
without first fixing the exit logic.

Validation after revert: `lookahead-analysis` has_bias **No**; baseline regenerated and
reproduces the pre-v1.9 numbers exactly (92 trades, 46.74% win, +0.7636% avg, 3.59% DD),
confirming a clean revert rather than a partial one.

**LIVE BOUNDARY: 2026-10-13.** The DB now holds four regimes. Use `--since`; never pool.

**We already knew this. See v1.4 (2026-06-10), below.** That experiment tested the same
avenue from the same observation — hyperopt pinning `atr_stop_mult` against its ceiling,
the trail producing all the losses, the indicator exit producing all the wins. It also
degraded specifically the bear-market case (2025: +1.03% → -0.70%) and concluded, verbatim:
*"Trailing-stop avenue is now closed with data"* and *"should guide future experiments
toward entry quality, not exit tuning."*

v1.9 reopened it four months later and failed the same way, for the reason v1.4 could see
but not name: the indicator exit cannot fire in a downtrend, so the stop is the only exit
and widening it enlarges every bear-market loss. Two experiments, same defect, one lesson
paid for twice.

**Standing rule: do not tune the exit stop again until `populate_exit_trend` can fire in a
downtrend.** The defect is the exit *condition*, not the stop distance.

**The real finding is not the stop multiple.** v1.9 was recommended on backtest evidence
that was properly validated out-of-sample — train/test split, holdout never touched, both
windows agreeing — and it still made things materially worse live. That means this
strategy's backtest has limited predictive power for its live behaviour. Until that gap is
understood, **further parameter tuning is not justified** regardless of how good the
backtest numbers look. Candidate explanations worth testing: Binance-vs-Kraken execution
differences, the 3-pair backtest config vs 8-pair live whitelist, or the exit asymmetry
above interacting with a regime the backtest window under-represents.

### First clean post-recovery data + ATR sensitivity (2026-09-29)

8 trades opened after the 2026-09-14 restart boundary — the first sample of THIS code on
THIS bot. `--since 2026-09-14`:

```
8 trades · win 38% · avg -1.11%/trade · cum -8.86% · maxDD -15.73% · exposure 47%
exit_signal          3   100% win   +6.09% avg
trailing_stop_loss   4     0% win   -4.14% avg
```

**Exit asymmetry reproduced** — third independent sample (backtest, contaminated live,
clean live) showing every trailing-stop exit losing and every indicator exit winning.

**But the mechanism I proposed for it was wrong.** I claimed losers "drift for days before
the stop catches them" from a 160h-vs-47h duration gap. Clean data shows 60h vs 52h — no
gap. That was an outage artifact. And on reflection the asymmetry is close to tautological:
a trailing stop IS the exit for trades that went against you, so of course those are the
losers. It is not by itself a defect.

**The 47% vs 17% exposure gap is not real** — `config-backtest.json` runs 3 pairs while
live runs 8. My error: I set the backtest config to BTC/ETH/SOL because those were the only
pairs with local data, then compared exposure as if equivalent. Live also trades 0.62/day
vs backtest 0.11/day, same cause. Do not compare trade frequency or exposure across those
two configs until the pair lists match.

**ATR stop sensitivity — the search range was mis-specified.** Swept `atr_stop_mult` on
both windows (3 pairs, current code):

```
atr    TRAIN tot  TRAIN DD   TEST tot  TEST DD    worst trade
2.0      -8.71%       --      -5.13%      --           --
2.5      -7.01%       --      -0.93%      --           --
3.0      -2.32%       --      -1.95%      --           --
3.9      +8.52%    2.89%      -0.60%   3.88%      -10.18%   <- current
4.5      +9.42%       --      -0.30%      --           --
5.5      +6.95%    2.67%      +0.10%   2.70%      -10.18%
7.0      +3.33%       --      +0.59%      --           --
9.0      +2.25%    5.19%      +2.38%   3.38%      -10.18%
```

- Everything below 3.0 is clearly worse on BOTH windows. The lower half of the hyperopt
  range (1.5-4.0) is dead space.
- TRAIN peaks at 4.5; TEST improves monotonically to 9.0 and is still rising. **They
  disagree** — so picking 9.0 because the holdout likes it would be fitting to the holdout
  and destroying the only clean measurement available. Do not do that.
- The **hard stoploss still binds at every multiple** (worst trade -10.18% throughout), so
  widening the trail does not remove risk control; it lets the -10% backstop do the work
  instead of the trail. This matters for CLAUDE.md rule 4: realized per-trade risk is
  unchanged, and drawdown *improves*.
- **5.5 has lower max drawdown than current on both windows** (2.67 vs 2.89, 2.70 vs 3.88)
  and better test return (+0.10% vs -0.60%), at the cost of train return (6.95 vs 8.52).
  It sits mid-region rather than at an edge, so it is not a cherry-picked peak.

**APPLIED 2026-09-29 — v1.9. `atr_stop_mult` 3.9 → 5.5.** Owner-approved. One value
changed; no entry parameters touched.

Also widened the declared range `DecimalParameter(1.5, 4.0)` → `(3.0, 9.0)`, default
2.5 → 5.5. This was *required*, not optional: 5.5 sits outside the old range, and the
range itself was the bug — the 3.9 the optimiser "found" was pinned against its 4.0
ceiling rather than chosen. Upper bound 9.0 is where the ATR distance exceeds the -10%
hard stop on typical crypto ATR%, past which the parameter stops having any effect.

Validation (rule 3, both clean):
- `lookahead-analysis`: has_bias **No** — 0 biased entry, 0 biased exit, 0 biased indicators
- `recursive-analysis`: unchanged; ema200_1d still nan at 199 candles, 0.41% drift at 400

Baseline regenerated on the full fully-warmed window (2024-03-01 → 2026-06-01, 3 pairs):

```
                old (3.9)    new (5.5)
trades              92           81
win rate         46.74%       51.85%
avg profit      +0.7636%     +0.7616%
max drawdown      3.59%        2.52%
total            +7.92%       +7.06%
return / maxDD     2.21         2.80
```

Same avg profit, better win rate, **30% lower drawdown**, slightly lower total return from
11 fewer trades. Risk-adjusted improvement, not a return improvement — which is what the
window-level sweep predicted, so the full-period result corroborates rather than surprises.

**LIVE CHANGE BOUNDARY: 2026-09-29.** Trades before this ran 3.9, after run 5.5. Combined
with the 2026-09-14 restart boundary, there are now three regimes in the trade DB — use
`--since` when scoring, and do not pool across boundaries.

Expect **fewer trades** live (81 vs 92 over 27 months backtest, ~12% fewer). Do not read a
lower trade count as the bot being broken.

Deployed to EC2 2026-09-29 15:47 UTC. Confirmed live: `atr_stop_mult = 5.5`,
`buy_rsi = 32` unchanged, 8 pairs, state RUNNING.

⚠️ **3 trades were open across the restart.** They were ENTERED under 3.9 and will EXIT
under 5.5, so they belong cleanly to neither configuration. The first ~3 closes after
2026-09-29 are therefore hybrids — exclude them when first comparing v1.8 against v1.9,
or the comparison starts with three contaminated rows. `--since` cannot catch this on its
own, because it filters on open date and these opened before the boundary.

**Unexplained and more important than the ATR question:** live is running -1.11%/trade
against a backtest test-window figure of -0.16% at the same parameters. n=8, and there is
no benchmark for the live period (Kraken serves no OHLCV), so this may be noise or regime.
Worth watching specifically as the sample grows.

### CORRECTION (2026-09-15, same day) — the "no edge" verdict below was WRONG

The two entries below conclude "no durable edge, discard rather than defend". That
conclusion was reached by measuring absolute return against zero. Measured against the
alternative — holding the same coins — it inverts:

```
period                    strategy   buy&hold      edge    maxDD
train 2024-03 -> 2025-03    +8.52%     +5.20%    +3.3pp    2.89%
test  2025-03 -> 2026-06    -0.60%    -22.68%   +22.1pp    3.88%
full  2024-03 -> 2026-06    +7.92%    -19.31%   +27.2pp    3.59%
```

Per walk-forward window, strategy minus buy-and-hold:

```
w1 +10.9   w2 -20.2   w3  -7.4   w4 +22.8
w5 -51.6   w6  +6.5   w7 +48.0   w8 +25.8
```

It **underperforms in rallies and strongly outperforms in crashes**. In w7 the market
fell 49% and it lost 1.0%. In w8 the market fell 26% and it lost 0.33%. The
"out-of-sample failure" was -0.60% during a -22.68% market.

This is not a bull-market strategy that stopped working. It is a **low-exposure,
capital-preserving** system: 0.08 trades/day, max 3 concurrent, mostly in cash, with max
drawdown between 1.2% and 3.9% in every window while the market swung +52% and -49%.
The ADX regime gate and daily EMA200 macro gate are doing real work — they keep it out.

**What remains true from the entries below:** absolute return is modest (~3.45%/yr) and
recently slightly negative, and hyperopt still degraded out-of-sample performance
(-0.74% vs -0.16% avg per trade), so more tuning is still the wrong move.

**What is now in question is the benchmark, not the strategy.** A system that sits in
cash most of the time will beat a falling market almost by construction, so buy-and-hold
is too generous a comparison. The honest benchmark for a mostly-cash strategy is CASH:
+7.92% over 27 months is ~3.45%/yr, which is positive but below what T-bills paid over
the same period. So:

- As an absolute-return engine: weak. Does not currently justify the operational risk.
- As a low-beta crypto sleeve / drawdown-avoidance overlay: genuinely doing something,
  and the evidence for it is consistent across all 8 windows.

Which of those you want determines whether this is worth continuing. That is a goals
question, not a backtest question.

**Methodological lesson, and the reason this correction exists:** every metric in the
tooling — avg profit per trade, win rate, the drift check — measures absolute return.
All of them said "failing" during a period when the strategy beat its alternative by
22 percentage points. The measurements were not wrong; they were answering a question
nobody had asked out loud. Benchmark-relative and exposure-adjusted metrics should be
added to `performance_report.py` and `walk_forward_report.py` before any further
strategy work.

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
