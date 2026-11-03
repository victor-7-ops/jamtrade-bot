#!/usr/bin/env python3
"""
Does a simple ALLOCATION rule beat the benchmark? (research script -- never trades)

Why this exists
---------------
Every out-of-sample test of MultiConfirmationStrategy since 2026-10-13 lost to
cash, while the one finding that replicated was that *how much you hold* mattered
more than *when you trade*. This script tests that directly, with a rule that has
two knobs instead of fifteen:

    hold `w` of an equal-weight basket, rebalance every `n` days,
    optionally dropping any pair trading below its 200-day SMA.

The 15%-basket benchmark from docs/ROADMAP.md is just this rule at w=0.15 with the
gate off, so it is simulated here from the SAME candles over the SAME window as
every candidate. That removes the error ROADMAP rule 3 warns about: comparing a
result to benchmark figures measured over a different period.

Low parameter count is the point. Nine measurement corrections in this project all
came from configurations with enough knobs to fit noise; a two-knob rule cannot
overfit 285 trades the way a fifteen-knob one can.

THE DECISION RULE (committed before you read the output)
--------------------------------------------------------
A config is only interesting if it beats the w=0.15/gate-off benchmark in BOTH
halves, on the ROADMAP bar: higher CAGR at no worse drawdown, or a higher Sharpe.
Winning one half is what killed the ATR sweep, the regime signal, the Sharpe 0.90
reading and the pairlist test. The script marks this for you; it does not let you
pick a winner after the fact.

This is a measurement tool, not a trading path. It places no orders and touches no
config. A passing result is a reason to keep testing, never a reason to deploy
money.

Usage
-----
    python scripts/allocation_test.py                 # defaults: 8 pairs, OKX 1d
    python scripts/allocation_test.py --selftest      # no data needed
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Matches the "100% cash @ 4.5%" row in the ROADMAP benchmark table, so the cash
# leg here is the same cash leg that table priced.
CASH_APY = 0.045
# Kraken taker fee, pinned the same way config-dryrun.json pins it (ccxt reports
# taker=None for Kraken, which once multiplied a live exit into a TypeError).
FEE = 0.0026
TRADING_DAYS = 365  # crypto trades every day; no 252-day convention here

DEFAULT_PAIRS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT",
    "XRP/USDT", "LINK/USDT", "DOT/USDT", "AVAX/USDT",
]
# The same split used for the pairlist test, so results are comparable to it.
DEFAULT_SPLITS = [("train", "20230301", "20250101"), ("test", "20250101", "20261001")]
BENCHMARK = (0.15, False)  # (weight, gate) -- the ROADMAP bar


def simulate(closes: pd.DataFrame, weight: float, rebalance_days: int,
             gate: bool, sma_window: int = 200) -> pd.Series:
    """Daily equity curve for: hold `weight` of an equal-weight basket, rebalanced
    every `rebalance_days`, remainder in cash at CASH_APY.

    With `gate`, a pair below its `sma_window`-day SMA is skipped at rebalance and
    its share of the basket sits in cash. The SMA uses only closes up to and
    including the rebalance day, so there is no lookahead.
    """
    if not 0.0 <= weight <= 1.0:
        raise ValueError(f"weight must be in [0, 1], got {weight}")
    if rebalance_days < 1:
        raise ValueError(f"rebalance_days must be >= 1, got {rebalance_days}")

    sma = closes.rolling(sma_window, min_periods=sma_window).mean() if gate else None
    daily_cash_rate = (1.0 + CASH_APY) ** (1.0 / TRADING_DAYS) - 1.0

    cash = 1000.0
    units = pd.Series(0.0, index=closes.columns)
    equity = []

    for i, (day, price) in enumerate(closes.iterrows()):
        # Interest accrues before any rebalance, so a rebalance day is not paid
        # twice and not skipped.
        cash *= 1.0 + daily_cash_rate
        total = cash + float((units * price).sum())

        if i % rebalance_days == 0:
            if gate:
                eligible = [p for p in closes.columns
                            if np.isfinite(sma.at[day, p]) and price[p] > sma.at[day, p]]
            else:
                eligible = list(closes.columns)

            target_value = pd.Series(0.0, index=closes.columns)
            if eligible:
                target_value[eligible] = total * weight / len(eligible)

            current_value = units * price
            turnover = float((target_value - current_value).abs().sum())
            fee = turnover * FEE
            # Fee is paid out of the basket side, so cash holds exactly the
            # remainder and equity drops by the fee rather than silently
            # absorbing it.
            units = target_value / price
            cash = total - float(target_value.sum()) - fee

        equity.append(cash + float((units * price).sum()))

    return pd.Series(equity, index=closes.index, name="equity")


def metrics(equity: pd.Series) -> dict:
    """Same statistics as the ROADMAP table: computed on the DAILY EQUITY curve,
    not summed per-trade ratios (those differ ~10x and have already misled once).
    """
    days = (equity.index[-1] - equity.index[0]).days
    total = equity.iloc[-1] / equity.iloc[0] - 1.0
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (365.0 / days) - 1.0 if days > 0 else float("nan")
    max_dd = float((equity / equity.cummax() - 1.0).min())  # negative by construction

    ret = equity.pct_change().dropna()
    ann = np.sqrt(TRADING_DAYS)
    sharpe = ret.mean() / ret.std() * ann if ret.std() > 0 else float("nan")
    downside = ret[ret < 0]
    sortino = ret.mean() / downside.std() * ann if len(downside) > 1 and downside.std() > 0 else float("nan")
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("nan")

    return {"total": total, "cagr": cagr, "max_dd": max_dd,
            "sharpe": sharpe, "sortino": sortino, "calmar": calmar}


def beats(cand: dict, bench: dict) -> bool:
    """The ROADMAP bar: higher CAGR at no worse drawdown, or a higher Sharpe."""
    better_return = cand["cagr"] > bench["cagr"] and abs(cand["max_dd"]) <= abs(bench["max_dd"])
    better_risk_adj = cand["sharpe"] > bench["sharpe"]
    return bool(better_return or better_risk_adj)


def load_closes(datadir: Path, pairs: list[str], timeframe: str = "1d") -> pd.DataFrame:
    """Daily closes, via freqtrade's own loader so the on-disk format (feather /
    json / parquet) is whatever freqtrade wrote -- no format guessing here.
    """
    from freqtrade.data.history import load_pair_history

    frames = {}
    for pair in pairs:
        df = load_pair_history(pair=pair, timeframe=timeframe, datadir=datadir)
        if df.empty:
            print(f"  ! no {timeframe} data for {pair} in {datadir} -- skipped", file=sys.stderr)
            continue
        frames[pair] = df.set_index("date")["close"]

    if not frames:
        sys.exit(f"No {timeframe} candles found in {datadir}. Run scripts/download-data.sh first.")

    # inner join: every pair must have a price on a given day, else the basket is
    # silently a different basket on that day.
    closes = pd.DataFrame(frames).dropna()
    if len(frames) < len(pairs):
        print(f"  ! basket is {len(frames)} of {len(pairs)} pairs", file=sys.stderr)
    return closes


def slice_window(closes: pd.DataFrame, start: str, end: str, sma_window: int) -> pd.DataFrame:
    """Window plus `sma_window` days of preceding candles, so the gate is warm on
    day one instead of forcing everything to cash through the first 200 days.
    """
    start_ts, end_ts = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    warm = closes.index[closes.index < start_ts][-sma_window:]
    lead = warm[0] if len(warm) else start_ts
    return closes.loc[(closes.index >= lead) & (closes.index < end_ts)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datadir", default="user_data/data/okx", type=Path)
    ap.add_argument("--pairs", nargs="+", default=DEFAULT_PAIRS)
    ap.add_argument("--weights", nargs="+", type=float, default=[0.15, 0.25, 0.40, 0.60])
    ap.add_argument("--rebalance-days", nargs="+", type=int, default=[30, 90])
    ap.add_argument("--sma-window", type=int, default=200)
    ap.add_argument("--selftest", action="store_true",
                    help="run assertions on synthetic data, no candles needed")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    closes = load_closes(args.datadir, args.pairs)
    print(f"Loaded {len(closes.columns)} pairs, {len(closes)} daily candles "
          f"({closes.index[0]:%Y-%m-%d} to {closes.index[-1]:%Y-%m-%d})\n")

    configs = [BENCHMARK] + [(w, g) for w in args.weights for g in (False, True)
                             if (w, g) != BENCHMARK]
    results: dict[str, dict] = {}

    for name, start, end in DEFAULT_SPLITS:
        window = slice_window(closes, start, end, args.sma_window)
        if window.empty:
            print(f"-- {name} {start}-{end}: no candles in window, skipped --\n")
            continue

        print(f"-- {name}: {start}-{end} ({len(window)} candles incl. SMA warm-up) --")
        for rebal in args.rebalance_days:
            print(f"\n  rebalance every {rebal}d")
            print(f"  {'config':<22}{'total':>9}{'CAGR':>9}{'maxDD':>9}"
                  f"{'Sharpe':>8}{'Sortino':>9}{'Calmar':>8}")
            for weight, gate in configs:
                m = metrics(simulate(window, weight, rebal, gate, args.sma_window))
                label = f"w={weight:.0%} gate={'on' if gate else 'off'}"
                tag = "  <-- BENCHMARK" if (weight, gate) == BENCHMARK else ""
                print(f"  {label:<22}{m['total']:>8.1%}{m['cagr']:>9.1%}{m['max_dd']:>9.1%}"
                      f"{m['sharpe']:>8.2f}{m['sortino']:>9.2f}{m['calmar']:>8.2f}{tag}")
                results[f"{name}|{rebal}|{weight}|{gate}"] = m
        print()

    verdict(results, configs, args.rebalance_days)
    return 0


def verdict(results: dict, configs: list, rebalance_days: list) -> None:
    print("=" * 74)
    print("VERDICT -- a config must beat the benchmark in BOTH halves (see docstring)")
    print("=" * 74)

    halves = [n for n, _, _ in DEFAULT_SPLITS if any(k.startswith(f"{n}|") for k in results)]
    if len(halves) < 2:
        print("Only one half had data -- no verdict. Both halves are required.")
        return

    survivors = []
    for rebal in rebalance_days:
        for weight, gate in configs:
            if (weight, gate) == BENCHMARK:
                continue
            wins = []
            for half in halves:
                cand = results.get(f"{half}|{rebal}|{weight}|{gate}")
                bench = results.get(f"{half}|{rebal}|{BENCHMARK[0]}|{BENCHMARK[1]}")
                if cand is None or bench is None:
                    wins = []
                    break
                wins.append(beats(cand, bench))
            if wins and all(wins):
                survivors.append(f"w={weight:.0%} gate={'on' if gate else 'off'} rebal={rebal}d")

    if not survivors:
        print("\nNothing beat the benchmark in both halves.")
        print("That is the same answer every other variant gave since 2026-10-13, and")
        print("it is a result: the benchmark stands, and holding it needs no bot.")
    else:
        print(f"\n{len(survivors)} config(s) beat the benchmark in BOTH halves:")
        for s in survivors:
            print(f"  - {s}")
        print("\nThis is NOT a green light. Before it means anything:")
        print("  1. Re-run on a third window the rule has never seen.")
        print("  2. Check it is not one lucky pair -- drop the best pair and re-run.")
        print("  3. Confirm the edge survives at a worse fee and with slippage.")
        print("  4. Remember two knobs over two windows can still fit noise.")
    print()


def selftest() -> int:
    """Smallest checks that fail if the simulator is wrong. No candles needed."""
    idx = pd.date_range("2024-01-01", periods=400, freq="D", tz="UTC")

    # 1. All cash (w=0) must compound at exactly CASH_APY and never draw down.
    flat = pd.DataFrame({"A/USDT": np.ones(len(idx)), "B/USDT": np.ones(len(idx))}, index=idx)
    m = metrics(simulate(flat, 0.0, 30, gate=False))
    assert abs(m["cagr"] - CASH_APY) < 1e-3, f"all-cash CAGR {m['cagr']:.4%} != {CASH_APY:.4%}"
    assert m["max_dd"] > -1e-9, f"all-cash drew down {m['max_dd']:.4%}"

    # 2. Flat prices + a basket position: fees must make it LOSE to all-cash.
    held = metrics(simulate(flat, 0.5, 30, gate=False))
    assert held["cagr"] < m["cagr"], "fees did not reduce return on flat prices"

    # 3. Doubling prices: more weight must earn more.
    ramp = pd.DataFrame({"A/USDT": np.linspace(1, 2, len(idx)),
                         "B/USDT": np.linspace(1, 2, len(idx))}, index=idx)
    low = metrics(simulate(ramp, 0.2, 30, gate=False))["total"]
    high = metrics(simulate(ramp, 0.8, 30, gate=False))["total"]
    assert high > low, f"more weight earned less in a rally ({high:.2%} <= {low:.2%})"

    # 4. The gate must sit out a falling market, so it beats holding through it.
    fall = pd.DataFrame({"A/USDT": np.linspace(2, 1, len(idx)),
                         "B/USDT": np.linspace(2, 1, len(idx))}, index=idx)
    gated = metrics(simulate(fall, 0.8, 30, gate=True, sma_window=50))["total"]
    ungated = metrics(simulate(fall, 0.8, 30, gate=False))["total"]
    assert gated > ungated, f"gate did not help in a downtrend ({gated:.2%} <= {ungated:.2%})"

    # 5. maxDD sign convention -- a real crash must report NEGATIVE (was a bug once).
    assert metrics(simulate(fall, 1.0, 30, gate=False))["max_dd"] < 0, "maxDD not negative in a crash"

    # 6. Guard rails reject nonsense input rather than silently simulating it.
    for bad in ({"weight": 1.5}, {"weight": -0.1}, {"rebalance_days": 0}):
        kwargs = {"weight": 0.5, "rebalance_days": 30, "gate": False} | bad
        try:
            simulate(flat, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid input: {bad}")

    print("selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
