# Roadmap

A phased plan. The phases are ordered for a reason — don't jump ahead. Each gate exists to
protect you from the most common (and expensive) mistakes.

---

## THE BENCHMARK (set 2026-10-14 — read this before any other section)

**Every result in this project is scored against: 15% of the 8-pair basket + 85% T-bills.**

For four months this project had no benchmark, and "is it working?" kept producing
contradictory answers because each attempt silently compared against something different —
zero, then buy-and-hold, then nothing at all. Three wrong strategy conclusions came out of
that. A benchmark fixes the question before the measurement.

Measured over 2023-03-01 → 2026-10-01 (a +254% bull followed by a −43% bear):

```
benchmark                   total     CAGR    maxDD   Sharpe  Sortino  Calmar
BTC only                  +259.2%   +42.8%   -53.0%    0.83     1.28    0.81
Basket (8, equal-weight)   +92.1%   +20.0%   -74.4%    0.50     0.75    0.27
50% basket + 50% cash      +81.6%   +18.1%   -44.4%    0.56     0.84    0.41
25% basket + 75% cash      +53.2%   +12.6%   -23.3%    0.67     1.01    0.54
15% basket + 85% cash      +39.4%    +9.7%   -13.3%    0.83     1.24    0.73   <-- BENCHMARK
100% cash @ 4.5%           +17.5%    +4.6%     0.00%     --       --      --
--------------------------------------------------------------------------------
strategy (atr 3.9)          +9.6%    +2.6%   -10.7%    0.36     0.36    0.24
```

### The bar

**CAGR > 9.7% with maxDD < 13%, or Sharpe > 0.83.**

### Why this one

- **Risk-matched.** 13.3% drawdown against the strategy's 10.7% — close enough that the
  comparison is about skill, not about who took more risk.
- **Trivially implementable.** Anyone can hold 15% in a basket and 85% in T-bills. A
  strategy that cannot beat that has no reason to exist, whatever its backtest says.
- **It is currently winning.** The strategy returns +2.6%/yr against 4.6% risk-free — it
  **underperforms plain cash** while carrying a 10.7% drawdown cash does not have.

Note the bar is roughly BTC-only's risk-adjusted profile (Sharpe 0.83). That is deliberate
and it is high: you are asking a strategy to match holding Bitcoin on a risk-adjusted
basis. If that seems unreasonable, the honest conclusion is to hold Bitcoin.

### Rules

1. **Never report a return without the benchmark beside it.** An absolute number alone has
   repeatedly produced the wrong conclusion here — see the CORRECTION entries in
   STRATEGY-NOTES.
2. **Check units before comparing.** Summed per-trade ratios are not account returns (they
   differ ~10x at current stake sizing). freqtrade's closed-trade Calmar is not the same
   statistic as the Calmar above. Both mistakes have already been made.
3. **Re-measure the benchmark over the same window** as whatever you are scoring. The table
   above covers one full cycle; a two-week live sample must be compared against the
   benchmark over those same two weeks, not against these headline figures.

## Phase 1 — Understand & Backtest ✅ (cleared)

**Goal:** know exactly how the strategy behaves on historical data.

- [x] Install Freqtrade, download data (`scripts/download-data.sh`) — freqtrade 2026.5, talib 0.6.8, BTC/ETH/BNB/SOL 4h+1d
- [x] Run a backtest across multiple years (20230101–20250601, 106 trades)
- [x] Run `scripts/validate.sh` — lookahead PASS (no bias), recursion stable
- [ ] Read `docs/STRATEGY-NOTES.md` until each layer makes sense to you (owner task)
- [x] Backtest across different market conditions: 2023 bull +5.64%, 2024 mixed +9.30%, 2025-H1 bear +2.90% (v1.7)

**Exit criteria:** you can explain why every trade was taken, and the lookahead check passes.

## Phase 2 — Paper Trade on Live Feed ▶ (current)

**Goal:** see if backtest behavior survives contact with the real, live market.

> **Status (2026-06-17):** a dry-run has been live on the Binance feed since
> 2026-06-04 (`tradesv3.dryrun.sqlite`). It was started on pre-v1.3 code, so its
> paper history does **not** reflect the current strategy (v1.7). To make Phase 2
> meaningful it must be restarted on v1.7 — ideally with a fresh paper DB so the
> baseline is clean. Clock the "weeks to months" from that restart, not from 6/04.

- [~] Run `scripts/dryrun.sh` (dry-run, fake money, real prices) — running, but on stale code; restart on v1.7
- [ ] Let it run for **weeks to months** — resist the urge to judge it in days
- [ ] Optionally enable Telegram alerts to monitor without watching a terminal
- [ ] Compare live dry-run stats against the backtest for the same period
- [ ] Keep a journal: does it behave as expected? Surprises?

**Exit criteria:** live dry-run results are *roughly consistent* with the backtest. If they
diverge badly, return to Phase 1 — you learned something valuable and lost nothing.

## Phase 3 — Tune Per Market (later)

**Goal:** adapt parameters to the specific pairs you want to trade.

- [ ] Use `freqtrade hyperopt` on a training period
- [ ] **Validate on a different period than you optimized on** (out-of-sample)
- [ ] Set up per-market configs (crypto vs stocks vs forex behave differently)
- [ ] Re-run the full validate + paper-trade loop on the tuned version

**⚠️ The overfitting trap lives here.** Hyperopt will happily produce parameters that look
spectacular in-sample and fail live. The defense is always out-of-sample validation. If a
hyperopt result can't reproduce its edge on data it never saw, throw it out.

## Phase 4 — Tiny Real Capital (gated)

**Do not enter this phase unless Phases 1–3 all held up.**

### Go-live readiness checklist (every box must be checked)

- [ ] **BEATS THE BENCHMARK.** CAGR > 9.7% with maxDD < 13%, or Sharpe > 0.83, measured
      against 15% basket + 85% T-bills **over the same window**. This is the first box for
      a reason: as of 2026-10-14 the strategy returns +2.6%/yr against 4.6% risk-free, so
      it currently loses to cash. Real capital in a strategy that loses to its benchmark is
      strictly worse than doing nothing, and "it might improve" is not evidence.
- [ ] Paper trading ran for a meaningful period (months, ideally across conditions)
- [ ] Live dry-run results matched backtest expectations — **note this is weaker than it
      sounds here:** L5 is a volume condition and volume is venue-specific, so a backtest on
      any proxy venue takes different trades than live (~9% disagreement on the L5 gate).
      Backtests are valid for distribution-level questions, not trade-level prediction
- [ ] You understand and can stomach the worst drawdown the strategy produced
- [ ] Lookahead and recursion checks pass on the current code
- [ ] Fees and slippage are accounted for in your expectations (not just gross returns)
- [ ] The capital is money you can lose **entirely** without affecting your life
- [ ] You've decided your max loss limit *in advance* and how you'll stop
- [ ] You're treating this as paid education, not as income
- [ ] **Uptime monitoring is live and you have tested that it actually pages you.**
      Not ops hygiene — a *risk control*. `stoploss = -0.10` is only enforced while
      the process is alive: the ATR trailing stop is evaluated when the bot processes
      a candle, so a dead bot enforces no stop at all. The 2026-09-09 outage exited a
      position at **-14.06%** on a strategy whose hard floor is -10%, purely because
      nothing was running for five days. With real capital, a silent death converts
      your bounded max loss into an unbounded one. Verify: `jamtrade-healthcheck.timer`
      active, and deliberately trip it once to confirm the Telegram message arrives.
- [ ] You know how you'll be alerted if the VM dies entirely (the healthcheck runs
      *on* the box, so it cannot report its own host being down)

### When you do go live

- Start with the **smallest** amount that's still worth it (dinner money, not savings).
- Create a **separate** config with real keys — never commit it (`.gitignore` covers this).
- Use a dedicated exchange API key with **trading-only** permissions (no withdrawal rights).
- Keep paper trading the next version in parallel — never stop developing on fake money.

## Beyond — Ideas Backlog

Loose ideas to explore later, once the foundation is solid:

- Short-side logic for bear markets (significant added risk — research carefully)
- ~~A small web dashboard (ties into your JamSpace / .NET interests) to monitor trades~~ —
  done (static-HTML version): `scripts/dashboard.py`. No server, regenerate any time.
  A live .NET version remains open if you want something richer later.
- Portfolio-level position sizing instead of fixed stake
- Alternative regime detection (e.g. volatility regimes, not just ADX)
- ~~Walk-forward automation to continuously re-validate as new data arrives~~ — done:
  `scripts/walk_forward.sh` + `scripts/walk_forward_report.py` (rolling out-of-sample
  windows, decay/instability flags)

---

**The meta-point:** the goal of this whole roadmap is to make sure that by the time real
money is involved, you've removed as much self-deception as possible. Most people lose money
by skipping straight to Phase 4. You're not going to be most people.
