#!/usr/bin/env python3
"""
walk_forward_report.py — aggregate walk-forward backtest windows and flag
performance decay or instability across time.

Reads the per-window backtest exports produced by scripts/walk_forward.sh
(user_data/backtest_results/walk_forward/w*_*/result.json) and reports, per
window: trade count, win rate, avg profit, profit factor, max drawdown.

Then flags two things a single full-range backtest can hide:

  1. TREND — is performance declining across successive windows? (linear
     trend on avg-profit-per-window). A strategy curve-fit to its original
     backtest range often looks fine in aggregate but decays window by
     window as the market moves away from what it was tuned on.

  2. INSTABILITY — is variance across windows unusually high relative to
     the average? High swing between adjacent windows suggests the strategy
     is regime-sensitive in a way the full-range number smooths over.

This is a REPORTING tool. It runs no backtests itself, places no orders, and
recommends no parameter changes — it surfaces evidence for the human-reviewed,
one-change-at-a-time tuning loop described in CLAUDE.md.

Usage:
    python scripts/walk_forward_report.py --dir user_data/backtest_results/walk_forward

Stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import sys


def load_windows(base_dir: str) -> list[dict]:
    pattern = os.path.join(base_dir, "w*_*", "result.json")
    paths = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"w(\d+)_", p).group(1)))
    if not paths:
        # freqtrade may append a timestamp to the filename despite --export-filename
        pattern = os.path.join(base_dir, "w*_*", "result*.json")
        paths = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"w(\d+)_", p).group(1)))
    if not paths:
        sys.exit(f"No window results found under {base_dir} — run scripts/walk_forward.sh first")

    windows = []
    for path in paths:
        m = re.search(r"w(\d+)_(\d{8})-(\d{8})", path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        strat = next(iter(data["strategy"].values()))
        total_trades = strat.get("total_trades", 0)
        wins = strat.get("wins", 0)
        windows.append(
            {
                "window": int(m.group(1)) if m else len(windows) + 1,
                "timerange": f"{m.group(2)}-{m.group(3)}" if m else "?",
                "trades": total_trades,
                "win_rate_pct": 100.0 * wins / total_trades if total_trades else 0.0,
                "avg_profit_pct": 100.0 * strat.get("profit_mean", 0.0),
                "profit_factor": strat.get("profit_factor", 0.0),
                "max_dd_pct": 100.0 * strat.get("max_drawdown_account", strat.get("max_drawdown", 0.0)),
            }
        )
    return windows


def trend_slope(values: list[float]) -> float:
    """Simple least-squares slope of values against window index (1, 2, 3, ...)."""
    n = len(values)
    if n < 3:
        return 0.0
    xs = list(range(1, n + 1))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    den = sum((x - x_mean) ** 2 for x in xs)
    return num / den if den else 0.0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(description="Walk-forward window aggregation + decay/instability flags")
    ap.add_argument("--dir", default="user_data/backtest_results/walk_forward",
                    help="directory containing w<N>_<range>/result.json window exports")
    ap.add_argument("--min-trades", type=int, default=5,
                    help="windows with fewer trades than this are shown but excluded from trend/instability math")
    args = ap.parse_args()

    windows = load_windows(args.dir)

    print(f"── Walk-forward results: {len(windows)} window(s) ──")
    print(f"{'win':>3} {'range':<19} {'n':>4} {'win%':>6} {'avg%':>7} {'PF':>5} {'maxDD%':>7}")
    for w in windows:
        flag = "" if w["trades"] >= args.min_trades else "  (thin sample)"
        print(
            f"{w['window']:>3} {w['timerange']:<19} {w['trades']:>4} {w['win_rate_pct']:>5.0f}% "
            f"{w['avg_profit_pct']:>+6.2f}% {w['profit_factor']:>5.2f} {w['max_dd_pct']:>6.2f}%{flag}"
        )

    usable = [w for w in windows if w["trades"] >= args.min_trades]
    print()
    if len(usable) < 3:
        print(f"Only {len(usable)} window(s) with >= {args.min_trades} trades — need at least 3 "
              f"for trend/instability analysis. Widen the range or shrink the window size.")
        return

    profits = [w["avg_profit_pct"] for w in usable]
    slope = trend_slope(profits)
    mean_profit = statistics.mean(profits)
    stdev_profit = statistics.pstdev(profits)

    print("── Decay check ──")
    print(f"avg-profit-per-window slope: {slope:+.3f} pp/window (mean {mean_profit:+.2f}%, stdev {stdev_profit:.2f}%)")
    if slope < -0.15:
        print("⚠️ DECAY FLAG: avg profit trending down across successive windows. Possible curve-fit to "
              "the original backtest range, or a strategy losing its edge as the market evolves. "
              "Per ROADMAP Phase 3: an edge that doesn't hold out-of-sample should be discarded, not defended.")
    else:
        print("✅ No meaningful downward trend across windows.")

    print()
    print("── Instability check ──")
    if mean_profit != 0 and abs(stdev_profit / mean_profit) > 2.0:
        print(f"⚠️ INSTABILITY FLAG: window-to-window profit variance is large relative to the mean "
              f"(stdev/mean = {stdev_profit / mean_profit:.1f}x). The full-range backtest number may be "
              f"averaging over a few very different regimes rather than one consistent edge.")
    else:
        print("✅ Window-to-window variance looks reasonable relative to the mean.")

    print()
    print("Reporting only — no backtests run, no params changed, no trades placed.")


if __name__ == "__main__":
    main()
