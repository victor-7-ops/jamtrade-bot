#!/usr/bin/env python3
"""
Which gate is actually blocking the trades? (diagnostic — changes nothing)

Why this exists
---------------
As of 2026-11-25 the live bot has taken 2 trades in 43 days. At that rate a
30-trade sample — the minimum this project set before drawing conclusions — takes
about 21 months. A strategy that cannot accumulate a judgeable sample inside two
years cannot be iterated on, whatever its edge. **Trade frequency, not return, is
the binding constraint**, and nothing else can be improved until it is understood.

The entry is a four-way conjunction:

    >= buy_min_score of 5 layers  AND  ADX >= buy_adx_min
                                  AND  daily close > daily EMA50   (uptrend_1d)
                                  AND  daily close > daily EMA200  (above_ema200_1d)

This measures how much each gate costs, so the answer is a number rather than an
intuition. It does NOT change the strategy, and it does not recommend a change.

Fidelity
--------
Indicators come from the strategy's OWN `advise_indicators()` via freqtrade's
resolver, not from a reimplementation here. This project has produced eleven
measurement errors, several from a quantity that looked equivalent and was not; a
hand-rolled copy of the entry logic would be exactly that trap. The only thing
restated below is the boolean combination, which is visible in one place.

THE DECISION RULE (committed before the run)
--------------------------------------------
This diagnostic can justify testing a relaxation only if ONE gate is doing the
overwhelming majority of the blocking. If attrition is spread evenly, the design is
irreducibly narrow and the honest conclusion is that this architecture cannot
produce a judgeable sample — no relaxation to test.

And should a relaxation be tested later, it counts only if it BOTH reaches ~30
trades per 6 months AND does not worsen out-of-sample return versus the current
config, on a train/test split. Frequency alone is trivially bought by deleting
gates; that is just a worse strategy with more data.

Usage
-----
    python scripts/gate_attrition.py                  # all 8 pairs, OKX
    python scripts/gate_attrition.py --by-year
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logging.getLogger("freqtrade").setLevel(logging.ERROR)


def load_backtesting(config_path: str):
    """freqtrade's own Backtesting object: strategy + dataprovider + exchange.

    Built via Backtesting rather than StrategyResolver alone, for two reasons that
    both bit on the first run of this script:

      * StrategyResolver on its own left the CLASS DEFAULTS in place
        (ADX>=22, rsi<38) instead of the hyperopt export in
        MultiConfirmationStrategy.json that actually governs the bot
        (ADX>=25, rsi<32, vol>1.8). Diagnosing the wrong thresholds would have
        been this project's twelfth measurement error. CLAUDE.md warns about
        exactly this file overriding class defaults.
      * @informative("1d") calls dp.market(), which needs an exchange.

    Backtesting wires both the way a real backtest does, so what is measured here
    is what the backtest and the live bot actually evaluate.
    """
    from freqtrade.configuration import Configuration
    from freqtrade.enums import RunMode
    from freqtrade.optimize.backtesting import Backtesting

    config = Configuration.from_files([config_path])
    config["strategy"] = "MultiConfirmationStrategy"
    config["runmode"] = RunMode.BACKTEST
    config.setdefault("timeframe", "4h")
    config["export"] = "none"

    bt = Backtesting(config)
    # Backtesting only sets .strategy inside its own run loop; _set_strategy is what
    # it calls there, and it also wires the dataprovider onto the strategy.
    bt._set_strategy(bt.strategylist[0])
    return bt, config


def gates_for(strategy, df: pd.DataFrame) -> dict[str, pd.Series]:
    """The four entry gates, each as a boolean Series.

    This mirrors populate_entry_trend(). Keep it in step with the strategy: if the
    conjunction there changes, this is the one place to update.
    """
    score = (
        (df["close"] > df["ema50"]).astype(int)
        + (df["rsi"] < strategy.buy_rsi.value).astype(int)
        + (df["macdhist"] > 0).astype(int)
        + (df["close"] < df["bb_lowerband"]).astype(int)
        + (df["volume"] > df["volume_sma"] * float(strategy.buy_vol_mult.value)).astype(int)
    )
    missing = [c for c in ("uptrend_1d", "above_ema200_1d") if c not in df.columns]
    if missing:
        sys.exit(f"1d informative columns missing ({missing}) — 1d candles not downloaded?")

    return {
        "_L1_above_ema50": df["close"] > df["ema50"],
        "_L2_rsi_oversold": df["rsi"] < strategy.buy_rsi.value,
        "_L3_macd_up": df["macdhist"] > 0,
        "_L4_below_bb": df["close"] < df["bb_lowerband"],
        "_L5_volume_spike": df["volume"] > df["volume_sma"] * float(strategy.buy_vol_mult.value),
        f"score>={strategy.buy_min_score.value}": score >= strategy.buy_min_score.value,
        f"ADX>={strategy.buy_adx_min.value}": df["adx"] >= strategy.buy_adx_min.value,
        "daily>EMA50": df["uptrend_1d"] == 1,
        "daily>EMA200": df["above_ema200_1d"] == 1,
    }


def analyse(bt, config, timeframe: str = "4h") -> pd.DataFrame:
    """Per-candle gate states, over the same candles a backtest would see."""
    strategy = bt.strategy
    warmup = int(getattr(strategy, "startup_candle_count", 400))
    data, _ = bt.load_bt_data()
    frames = []

    for pair, raw in data.items():
        if raw.empty:
            print(f"  ! no {timeframe} data for {pair} — skipped", file=sys.stderr)
            continue

        df = strategy.advise_indicators(raw.copy(), {"pair": pair})
        # Drop the warmup window: daily EMA200 is nan there, so the macro gate reads
        # False and would be scored as "blocking" when it is merely unwarmed.
        df = df.iloc[warmup:].reset_index(drop=True)
        if df.empty:
            continue

        g = gates_for(strategy, df)
        rows = {"pair": pair, "date": df["date"]}
        rows.update({k: v.fillna(False) for k, v in g.items()})
        frames.append(pd.DataFrame(rows))

    if not frames:
        sys.exit("No data loaded. Run scripts/download-data.sh first.")
    return pd.concat(frames, ignore_index=True)


def layer_report(data: pd.DataFrame, layer_names: list[str]) -> None:
    """Why the score gate is tight: how often each layer fires, and whether the
    layers can physically fire together."""
    print("\n── Why the score gate is the bottleneck ──")
    print("\n  Each layer alone")
    for l in layer_names:
        print(f"    {l[1:]:<20} {100 * data[l].mean():>6.1f}%")

    print("\n  Pairwise co-occurrence (how often BOTH fire on the same candle)")
    print("                        " + "".join(f"{l[1:4]:>7}" for l in layer_names))
    for a in layer_names:
        row = f"    {a[1:]:<20}"
        for b in layer_names:
            row += f"{100 * (data[a] & data[b]).mean():>7.1f}" if a != b else f"{'--':>7}"
        print(row)

    counts = sum(data[l].astype(int) for l in layer_names)
    print("\n  Score distribution (how many layers fire at once)")
    for k in range(6):
        pct = 100.0 * (counts == k).mean()
        print(f"    {k} of 5   {pct:>6.2f}%   {'#' * int(pct / 2)}")


def report(data: pd.DataFrame, gate_names: list[str], label: str) -> None:
    n = len(data)
    if n == 0:
        return
    print(f"\n── {label} ── ({n:,} 4h candles across {data['pair'].nunique()} pairs)")

    print("\n  Each gate ALONE (what fraction of candles it lets through)")
    for g in gate_names:
        print(f"    {g:<16} {100 * data[g].mean():>6.1f}%")

    # Marginal cost: the gate's own contribution given the other three already hold.
    # This is the number that matters -- a gate that blocks a lot in isolation but
    # only blocks candles the others already blocked costs nothing in practice.
    print("\n  MARGINAL cost (candles passing the other three, that this one kills)")
    all_pass = data[gate_names].all(axis=1)
    for g in gate_names:
        others = [x for x in gate_names if x != g]
        others_ok = data[others].all(axis=1)
        denom = int(others_ok.sum())
        kept = int((others_ok & data[g]).sum())
        killed = denom - kept
        pct = 100.0 * killed / denom if denom else 0.0
        print(f"    {g:<16} kills {killed:>6,} of {denom:>6,} ({pct:>5.1f}%)"
              f"   → removing it alone: {kept:,} → {denom:,} signals")

    total = int(all_pass.sum())
    span_days = (data["date"].max() - data["date"].min()).days or 1
    print(f"\n  ALL FOUR: {total:,} signal candles "
          f"({100 * total / n:.2f}% of candles · ~{total / (span_days / 182.5):.0f} per 6 months "
          f"across {data['pair'].nunique()} pairs, before max_open_trades caps them)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="user_data/config-backtest.json")
    ap.add_argument("--by-year", action="store_true", help="also break the table down per year")
    args = ap.parse_args()

    bt, config = load_backtesting(args.config)
    strategy = bt.strategy
    print(f"Params in force (from the hyperopt JSON, not class defaults): "
          f"score>={strategy.buy_min_score.value}, ADX>={strategy.buy_adx_min.value}, "
          f"rsi<{strategy.buy_rsi.value}, vol>{strategy.buy_vol_mult.value}x")

    data = analyse(bt, config)
    gate_names = [c for c in data.columns if c not in ("pair", "date") and not c.startswith("_L")]
    layer_names = [c for c in data.columns if c.startswith("_L")]

    report(data, gate_names, "FULL HISTORY")
    layer_report(data, layer_names)
    if args.by_year:
        for year, chunk in data.groupby(data["date"].dt.year):
            report(chunk, gate_names, f"{year}")

    print("\n" + "=" * 70)
    print("READ THIS AGAINST THE PRE-COMMITTED RULE (see docstring)")
    print("=" * 70)
    print("A relaxation is only worth testing if ONE gate dominates the marginal")
    print("column. Evenly spread attrition means the design is irreducibly narrow,")
    print("and the honest conclusion is that it cannot produce a judgeable sample.")
    print("Raising frequency by deleting a gate is not an improvement on its own.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
