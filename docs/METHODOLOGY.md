# Methodology — what this project actually produced

The strategy in this repo does not work. Five independent out-of-sample tests say so,
and a benchmark anyone can implement in a brokerage account beats it by roughly 18
percentage points.

That is the *second* most useful output. The first is this document.

Most people who build a trading bot never find out whether it works. They run a
backtest, see a number they like, and either deploy money or lose interest. This
project found out in four months, on fake money, and the only reason it could is the
measurement discipline below. Ten measurement errors were caught along the way — most
of them our own, several of them after they had already produced a confident wrong
conclusion.

Everything here transfers to any project where you are trying to find out whether a
system actually works: ML models, growth experiments, performance optimisation,
anything with a metric and an incentive to like it.

---

## 1. Pick the benchmark before you measure anything

For four months this project had no benchmark, and *"is it working?"* kept producing
contradictory answers because each attempt silently compared against something
different: zero, then buy-and-hold, then nothing at all. **Three wrong strategy
conclusions came out of that.**

A benchmark fixes the question before the measurement. Without one, every result is
"compared to what?" and the answer gets chosen — unconsciously — to make the result
look good.

Rules that followed:

- **Risk-match it.** The chosen benchmark drew down 13.3% against the strategy's
  10.7%. Close enough that the comparison is about skill rather than about who took
  more risk.
- **Make it trivially implementable.** 15% in a basket, 85% in T-bills. Anyone can do
  that. A system that cannot beat something anyone can do has no reason to exist,
  whatever its internal numbers say.
- **Accept that a fair benchmark may be brutal.** Ours was roughly "match Bitcoin on a
  risk-adjusted basis." That is a high bar and it was *supposed* to be. If the honest
  benchmark seems unreasonably hard to beat, the honest conclusion is usually to just
  hold the benchmark.

## 2. Write the decision rule down before the run, and don't touch it while a result is on screen

Every test here declared its pass condition in advance. Example, from the pairlist
test: *"3 pairs must beat 8 in **both** halves, else no change."*

This matters because the moment you see a result you want, you can always find a
reading that justifies it. Pre-committing removes that option.

The harder half of the rule: **when a result exposes a flaw in your decision rule,
fix the rule afterwards, with no run pending.** On 2026-11-04 a config passed because
the rule accepted "higher Sharpe" as sufficient — and the winner had *earned less
money than the benchmark in both halves*, winning only because lower volatility lifts
the ratio. The rule was wrong. It was left alone until the result was fully written
up, then tightened separately. Editing it in the moment would have been
indistinguishable from fitting the rule to the answer.

## 3. Check your units before comparing anything

The single most expensive error here: **summed per-trade percentages were read as an
account return.** They differ by roughly 10× at this position sizing. That one
misreading drove a strategy version to be applied and then reverted, costing two weeks
and contaminating the sample.

Related traps found in the same family:

- A drawdown function returning a **negative** number, compared with `>` against a
  positive threshold. Silent, and always in the flattering direction.
- Two statistics with the same *name* but different definitions (a closed-trade Calmar
  is not a daily-equity Calmar).

If a number seems large, check whether it is the number you think it is before you
believe it.

## 4. Split the sample — full-period numbers hide sign flips

A full-sample comparison said 3 pairs beat 8 pairs. Split in half, 8 pairs won the
first half and 3 pairs won the second. The full-sample ordering was an artifact of
where the two halves happened to cancel.

The same thing killed a Sharpe of 0.90, which collapsed to 0.59 once split.

**A single aggregate number over a long period can hide a complete reversal.** Split
it. If the conclusion flips, you never had a conclusion.

## 5. Measure the benchmark over the *same* window, from the *same* data

A result from one period compared against benchmark figures from a different period is
not a comparison. This was written as a rule early and still violated twice, because
re-measuring is tedious and the headline benchmark number is right there.

The fix was structural rather than disciplinary: the final test script computes the
benchmark *as a special case of the rule being tested*, so it is simulated from the
identical candles over the identical window, automatically. **Make the correct thing
the path of least resistance and you stop relying on remembering.**

## 6. Account for exposure before you call anything an edge

A system holding positions 12% of the time and one holding them 100% of the time
cannot be compared on return alone. Early readings here ignored this and credited the
strategy with "beating a falling market" when it was mostly sitting in cash — that is
drawdown avoided, not alpha.

## 7. Beware the de-risked variant wearing a better ratio

Sharpe, Sortino and Calmar all improve when you simply take less risk. A variant that
earns less money with less volatility will look better on every ratio, and is not an
improvement unless you actually wanted less risk.

If you score with a ratio, **put a floor on the thing the ratio divides**: require
return no worse than the benchmark's before a ratio win counts.

## 8. Robustness checks confirm robustness, not merit

The surviving config here passed a 4× worse fee assumption and 6 of 8
leave-one-out runs. It was robustly *lower-returning*. Robustness tells you an effect
is real and stable; it says nothing about whether the effect is worth having.

Check merit first, then robustness. In that order.

## 9. Distinguish "it ran" from "it worked"

A backtest that completes is evidence the logic executes. It is not evidence of
profit. Stated constantly in this repo, and still needed restating, because a clean
run feels like success.

Related, and specific to this domain but generalisable: **a backtest on a proxy data
source does not predict trade-level behaviour.** Here, one entry condition depended on
trading volume, and volume is venue-specific — so live and backtest took *different
trades*, disagreeing on ~9% of candles. Where they took the same trade they agreed to
~0.2pp. The backtest was valid for distribution-level questions and invalid for
trade-level prediction, and conflating the two produced a wrong diagnosis
("execution quality") that survived for weeks.

## 10. Failure must be loud, and alert delivery must be *tested*, not assumed

Five production incidents in this project. **All five were silent** — green
checkmarks, no signals, nothing obviously wrong. The worst ran for five days: the disk
filled, the process crash-looped 9,918 times, and two positions sat unmanaged. One
exited at −14.06% against a −10% hard stop, because **a stop loss is only enforced
while the process is alive.**

Three lessons, in increasing order of how long they took to learn:

1. **Watch the thing whose absence would hurt.** The healthcheck at the time monitored
   a secondary timer and never looked at the trading process, the disk, or whether
   anything was making progress. It would have reported "healthy" throughout the
   outage. A monitor watching the easy signals is worse than no monitor, because it
   manufactures confidence.
2. **Monitoring can be a risk control, not just ops hygiene.** Any bound your system
   promises — a stop loss, a rate limit, a spend cap — is a promise the code can only
   keep while it is running. Downtime converts a bounded loss into an unbounded one.
3. **Verify the alert path end to end, including delivery.** On 2026-11-04 the
   Telegram credential turned out to be invalid (fast `401`). The healthcheck's send
   ended in `|| true` with stderr discarded, so it would have reported nothing while
   believing it had alerted. Nothing was lost only because it had never needed to
   fire. *An untested alert path should be assumed broken.* Deliberately trip it once.

Corollary for any script: **never swallow an error from the code path that exists to
tell you about errors.**

## 11. Leave one runnable check behind

Non-trivial logic gets one small self-check — not a test suite, not fixtures. The
allocation simulator's selftest asserts that an all-cash portfolio compounds at exactly
the cash rate, that fees reduce return on flat prices, that more weight earns more in a
rally, that drawdown is reported negative, and that the decision rule rejects the
specific de-risked config that fooled it once.

That last one is the pattern worth copying: **when a bug or a bad conclusion gets
through, encode the real failing numbers as an assertion.** It cannot recur silently.

---

## The uncomfortable part

Good methodology mostly produces negative results. That is not a flaw in the
methodology — negative results are the common case, and a process that rarely returns
one is not measuring, it is agreeing with you.

This project's honest scoreboard, same window, same candles:

```
strategy (8 pairs)                       -10.17% total
strategy (3 pairs)                        -0.72% total
best alternative rule tested              +4.8%/yr   (~= T-bills)
15% basket + 85% T-bills (BENCHMARK)      +8.2%/yr   <-- won
```

Four months of work to establish that a simple benchmark wins. Measured against what
the alternative would have cost — the same conclusion reached later, with real money —
that is a cheap answer, and it is the outcome the discipline was *for*.

> No result in this repository justifies deploying capital, and nothing here is
> financial advice. `dry_run` stays `true`.
