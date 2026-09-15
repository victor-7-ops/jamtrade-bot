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
from datetime import datetime


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
        # Benchmark: what holding the same coins over the same window returned.
        # freqtrade reports this as market_change (mean price change across the
        # whitelist). Without it, "-0.60%" reads as failure even when the market
        # fell 22.68% over the same window -- which is what happened on
        # 2026-09-15 and nearly got a working regime filter discarded.
        market = strat.get("market_change")
        total_pct = 100.0 * strat.get("profit_total", 0.0)

        # Exposure: what fraction of the window capital was actually at risk.
        # A mostly-cash strategy beats a falling market almost by construction,
        # so beating buy-and-hold only means something alongside this number.
        exposure_pct = None
        trades = strat.get("trades") or []
        span_days = None
        if m:
            try:
                start = datetime.strptime(m.group(2), "%Y%m%d")
                end = datetime.strptime(m.group(3), "%Y%m%d")
                span_days = (end - start).total_seconds() / 86400.0
            except ValueError:
                span_days = None
        max_open = strat.get("max_open_trades") or 1
        if trades and span_days and max_open:
            held_days = sum(t.get("trade_duration", 0) for t in trades) / (60.0 * 24.0)
            exposure_pct = 100.0 * held_days / (span_days * max_open)

        windows.append(
            {
                "window": int(m.group(1)) if m else len(windows) + 1,
                "timerange": f"{m.group(2)}-{m.group(3)}" if m else "?",
                "trades": total_trades,
                "win_rate_pct": 100.0 * wins / total_trades if total_trades else 0.0,
                "avg_profit_pct": 100.0 * strat.get("profit_mean", 0.0),
                "profit_factor": strat.get("profit_factor", 0.0),
                "max_dd_pct": 100.0 * strat.get("max_drawdown_account", strat.get("max_drawdown", 0.0)),
                "total_pct": total_pct,
                "market_pct": 100.0 * market if market is not None else None,
                "edge_pp": total_pct - 100.0 * market if market is not None else None,
                "exposure_pct": exposure_pct,
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
    print(
        f"{'win':>3} {'range':<19} {'n':>4} {'win%':>6} {'avg%':>7} {'PF':>5} {'maxDD%':>7} "
        f"{'strat%':>8} {'hold%':>8} {'edge_pp':>8} {'expo%':>6}"
    )
    for w in windows:
        flag = "" if w["trades"] >= args.min_trades else "  (thin)"
        mk = f"{w['market_pct']:>+7.2f}%" if w["market_pct"] is not None else f"{'n/a':>8}"
        ed = f"{w['edge_pp']:>+8.1f}" if w["edge_pp"] is not None else f"{'n/a':>8}"
        ex = f"{w['exposure_pct']:>5.0f}%" if w["exposure_pct"] is not None else f"{'n/a':>6}"
        print(
            f"{w['window']:>3} {w['timerange']:<19} {w['trades']:>4} {w['win_rate_pct']:>5.0f}% "
            f"{w['avg_profit_pct']:>+6.2f}% {w['profit_factor']:>5.2f} {w['max_dd_pct']:>6.2f}% "
            f"{w['total_pct']:>+7.2f}% {mk} {ed} {ex}{flag}"
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

    benched = [w for w in usable if w["edge_pp"] is not None]
    if benched:
        print("── Benchmark check (vs holding the same coins) ──")
        beats = sum(1 for w in benched if w["edge_pp"] > 0)
        mean_edge = statistics.mean(w["edge_pp"] for w in benched)
        exposures = [w["exposure_pct"] for w in benched if w["exposure_pct"] is not None]
        mean_expo = statistics.mean(exposures) if exposures else None

        print(f"beat buy-and-hold in {beats}/{len(benched)} windows · mean edge {mean_edge:+.1f}pp"
              + (f" · mean exposure {mean_expo:.0f}%" if mean_expo is not None else ""))

        up = [w for w in benched if w["market_pct"] > 0]
        down = [w for w in benched if w["market_pct"] <= 0]
        if up:
            print(f"  rising markets ({len(up)}): mean edge {statistics.mean(w['edge_pp'] for w in up):+.1f}pp")
        if down:
            print(f"  falling markets ({len(down)}): mean edge {statistics.mean(w['edge_pp'] for w in down):+.1f}pp")

        # The interpretation guard. On 2026-09-15 this project nearly discarded a
        # working regime filter because every metric measured absolute return: the
        # strategy read "-0.60%, failing" over a window in which the market fell
        # 22.68%. Beating a falling market is only meaningful alongside exposure,
        # because sitting in cash does it for free.
        if mean_expo is not None and mean_expo < 35 and mean_edge > 0:
            print(
                f"  ⓘ Mean exposure is only {mean_expo:.0f}% — capital is in cash most of the time.\n"
                f"    A mostly-cash strategy beats a FALLING market almost by construction, so the\n"
                f"    edge above is not by itself evidence of skill. The honest benchmark for a\n"
                f"    strategy like this is CASH, not buy-and-hold: judge it on absolute return per\n"
                f"    unit of risk, and treat the buy-and-hold column as drawdown avoided, not alpha."
            )
        if up and down:
            up_e = statistics.mean(w["edge_pp"] for w in up)
            down_e = statistics.mean(w["edge_pp"] for w in down)
            if down_e > 0 > up_e:
                print(
                    "  ⓘ Lags in rallies, outperforms in drawdowns — a low-beta / capital-preservation\n"
                    "    profile. Whether that is what you want is a GOALS question, not a backtest one."
                )
        print()

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
