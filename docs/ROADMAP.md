# Roadmap

A phased plan. The phases are ordered for a reason — don't jump ahead. Each gate exists to
protect you from the most common (and expensive) mistakes.

## Phase 1 — Understand & Backtest ▶ (current)

**Goal:** know exactly how the strategy behaves on historical data.

- [ ] Install Freqtrade, download data (`scripts/download-data.sh`)
- [ ] Run a backtest across multiple years, not just one good one
- [ ] Run `scripts/validate.sh` — confirm no lookahead bias
- [ ] Read `docs/STRATEGY-NOTES.md` until each layer makes sense to you
- [ ] Backtest across different market conditions (a bull year, a bear year, a flat year)

**Exit criteria:** you can explain why every trade was taken, and the lookahead check passes.

## Phase 2 — Paper Trade on Live Feed (next)

**Goal:** see if backtest behavior survives contact with the real, live market.

- [ ] Run `scripts/dryrun.sh` (dry-run, fake money, real prices)
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

- [ ] Paper trading ran for a meaningful period (months, ideally across conditions)
- [ ] Live dry-run results matched backtest expectations
- [ ] You understand and can stomach the worst drawdown the strategy produced
- [ ] Lookahead and recursion checks pass on the current code
- [ ] Fees and slippage are accounted for in your expectations (not just gross returns)
- [ ] The capital is money you can lose **entirely** without affecting your life
- [ ] You've decided your max loss limit *in advance* and how you'll stop
- [ ] You're treating this as paid education, not as income

### When you do go live

- Start with the **smallest** amount that's still worth it (dinner money, not savings).
- Create a **separate** config with real keys — never commit it (`.gitignore` covers this).
- Use a dedicated exchange API key with **trading-only** permissions (no withdrawal rights).
- Keep paper trading the next version in parallel — never stop developing on fake money.

## Beyond — Ideas Backlog

Loose ideas to explore later, once the foundation is solid:

- Short-side logic for bear markets (significant added risk — research carefully)
- A small web dashboard (ties into your JamSpace / .NET interests) to monitor trades
- Portfolio-level position sizing instead of fixed stake
- Alternative regime detection (e.g. volatility regimes, not just ADX)
- Walk-forward automation to continuously re-validate as new data arrives

---

**The meta-point:** the goal of this whole roadmap is to make sure that by the time real
money is involved, you've removed as much self-deception as possible. Most people lose money
by skipping straight to Phase 4. You're not going to be most people.
