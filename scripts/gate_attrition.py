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


def load_strategy(config_path: str):
    """The real strategy object, with hyperopt params applied, in backtest runmode.

    Backtest runmode matters: DataProvider then serves the 1d informative from disk
    (user_data/data/<exchange>/) instead of needing a live exchange, so
    @informative("1d") merges exactly as it does in a backtest.
    """
    from freqtrade.configuration import Configuration
    from freqtrade.data.dataprovider import DataProvider
    from freqtrade.enums import RunMode
    from freqtrade.resolvers import StrategyResolver

    config = Configuration.from_files([config_path])
    config["strategy"] = "MultiConfirmationStrategy"
    config["runmode"] = RunMode.BACKTEST

    strategy = StrategyResolver.load_strategy(config)
    strategy.dp = DataProvider(config, None, None)
    return strategy, config


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
        f"score>={strategy.buy_min_score.value}": score >= strategy.buy_min_score.value,
        f"ADX>={strategy.buy_adx_min.value}": df["adx"] >= strategy.buy_adx_min.value,
        "daily>EMA50": df["uptrend_1d"] == 1,
        "daily>EMA200": df["above_ema200_1d"] == 1,
    }


def analyse(strategy, config, pairs: list[str], timeframe: str = "4h") -> pd.DataFrame:
    from freqtrade.data.history import load_pair_history

    datadir = Path(config["datadir"])
    warmup = int(getattr(strategy, "startup_candle_count", 400))
    frames = []

    for pair in pairs:
        raw = load_pair_history(pair=pair, timeframe=timeframe, datadir=datadir)
        if raw.empty:
            print(f"  ! no {timeframe} data for {pair} — skipped", file=sys.stderr)
            continue

        df = strategy.advise_indicators(raw.copy(), {"pair": pair})
        # Drop the warmup window: EMA200-on-daily is nan there, so the macro gate
        # reads False and would be scored as "blocking" when it is merely unwarmed.
        df = df.iloc[warmup:].reset_index(drop=True)
        if df.empty:
            continue

        g = gates_for(strategy, df)
        rows = {"pair": pair, "candles": len(df), "date": df["date"]}
        rows.update({k: v.fillna(False) for k, v in g.items()})
        frames.append(pd.DataFrame(rows))

    if not frames:
        sys.exit("No data loaded. Run scripts/download-data.sh first.")
    return pd.concat(frames, ignore_index=True)


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

    strategy, config = load_strategy(args.config)
    pairs = config["exchange"]["pair_whitelist"]
    print(f"Strategy params in force: score>={strategy.buy_min_score.value}, "
          f"ADX>={strategy.buy_adx_min.value}, rsi<{strategy.buy_rsi.value}, "
          f"vol>{strategy.buy_vol_mult.value}x")

    data = analyse(strategy, config, pairs)
    gate_names = [c for c in data.columns if c not in ("pair", "candles", "date")]

    report(data, gate_names, "FULL HISTORY")
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
