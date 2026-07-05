#!/usr/bin/env python3
"""
performance_report.py — weekly paper-trading scoreboard + backtest drift check.

ADVISORY / REPORTING ONLY. Reads the Freqtrade dry-run sqlite DB, computes:

  1. Per-enter_tag scoreboard — which confirmation-layer combos (L1+L3+L5, ...)
     are winning or losing on the LIVE feed. Same attribution idea that killed
     L6 in v1.5, but running continuously on paper trades instead of backtests.
  2. Per-exit_reason breakdown — is the ATR trail or the indicator exit
     giving back profit?
  3. Overall stats vs a backtest baseline (optional) — early-warning drift
     check for the Phase 2 exit criterion ("live roughly consistent with
     backtest"). Divergence = go back to Phase 1, you learned something.

Never places orders, never touches strategy logic. Prints to stdout and
optionally sends a Telegram digest (TG_TOKEN / TG_CHAT_ID env vars).

Usage:
    python scripts/performance_report.py                       # default DB path
    python scripts/performance_report.py --db path/to/trades.sqlite
    python scripts/performance_report.py --min-trades 3        # hide tiny samples
    python scripts/performance_report.py --baseline user_data/backtest_baseline.json

Generating the baseline from a backtest result export:
    python scripts/performance_report.py \
        --make-baseline user_data/backtest_results/backtest-result-XXXX.json \
        --out user_data/backtest_baseline.json

Stdlib only — no dependencies beyond Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone


DEFAULT_DB = "user_data/tradesv3.dryrun.sqlite"

# Drift thresholds: how far live may drift from the backtest baseline before
# we flag it. Deliberately loose — small live samples are noisy, and a false
# "all is well" is worse than a false alarm you investigate and dismiss.
DRIFT_WIN_RATE_PP = 15.0     # percentage points of win-rate divergence
DRIFT_AVG_PROFIT_PP = 1.0    # percentage points of avg profit-per-trade divergence
MIN_TRADES_FOR_DRIFT = 10    # below this, drift stats are noise — say so instead


@dataclass
class Bucket:
    """Aggregated stats for one group of closed trades (a tag, an exit reason, or all)."""
    profits: list = field(default_factory=list)      # close_profit ratios
    durations_h: list = field(default_factory=list)  # hours

    def add(self, profit_ratio: float, duration_h: float) -> None:
        self.profits.append(profit_ratio)
        self.durations_h.append(duration_h)

    @property
    def n(self) -> int:
        return len(self.profits)

    @property
    def wins(self) -> int:
        return sum(1 for p in self.profits if p > 0)

    @property
    def win_rate(self) -> float:
        return 100.0 * self.wins / self.n if self.n else 0.0

    @property
    def avg_profit_pct(self) -> float:
        return 100.0 * sum(self.profits) / self.n if self.n else 0.0

    @property
    def cum_profit_pct(self) -> float:
        return 100.0 * sum(self.profits)

    @property
    def worst_pct(self) -> float:
        return 100.0 * min(self.profits) if self.profits else 0.0

    @property
    def avg_duration_h(self) -> float:
        return sum(self.durations_h) / self.n if self.n else 0.0


def parse_dt(value) -> datetime | None:
    """Freqtrade stores dates as ISO strings (older versions varied slightly)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):  # very old schemas: epoch
        return datetime.fromtimestamp(value, tz=timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def load_closed_trades(db_path: str) -> list[dict]:
    if not os.path.exists(db_path):
        sys.exit(f"DB not found: {db_path} (pass --db, or run this on the box hosting the dry-run)")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT pair, enter_tag, exit_reason, close_profit,
                   open_date, close_date, is_open
            FROM trades
            WHERE is_open = 0 AND close_profit IS NOT NULL
            ORDER BY close_date
            """
        ).fetchall()
    finally:
        con.close()

    trades = []
    for r in rows:
        od, cd = parse_dt(r["open_date"]), parse_dt(r["close_date"])
        duration_h = (cd - od).total_seconds() / 3600.0 if od and cd else 0.0
        trades.append(
            {
                "pair": r["pair"],
                "enter_tag": r["enter_tag"] or "(untagged)",
                "exit_reason": r["exit_reason"] or "(unknown)",
                "profit": float(r["close_profit"]),
                "duration_h": duration_h,
                "close_date": cd,
            }
        )
    return trades


def bucketize(trades: list[dict], key: str) -> dict[str, Bucket]:
    buckets: dict[str, Bucket] = {}
    for t in trades:
        buckets.setdefault(t[key], Bucket()).add(t["profit"], t["duration_h"])
    return buckets


def max_drawdown_pct(trades: list[dict]) -> float:
    """Max drawdown of the cumulative profit-ratio curve, in percentage points."""
    cum = peak = 0.0
    worst = 0.0
    for t in trades:
        cum += t["profit"]
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    return 100.0 * worst


def fmt_bucket_table(buckets: dict[str, Bucket], min_trades: int, label: str) -> list[str]:
    lines = [f"{label:<22} {'n':>4} {'win%':>6} {'avg%':>7} {'cum%':>7} {'worst%':>7} {'hrs':>6}"]
    shown = {k: b for k, b in buckets.items() if b.n >= min_trades}
    hidden = len(buckets) - len(shown)
    # Sort by expectancy (avg profit) descending — best combos on top.
    for name, b in sorted(shown.items(), key=lambda kv: kv[1].avg_profit_pct, reverse=True):
        lines.append(
            f"{name:<22} {b.n:>4} {b.win_rate:>5.0f}% {b.avg_profit_pct:>+6.2f}% "
            f"{b.cum_profit_pct:>+6.2f}% {b.worst_pct:>+6.2f}% {b.avg_duration_h:>6.0f}"
        )
    if hidden:
        lines.append(f"({hidden} group(s) hidden: fewer than {min_trades} trades — too small to judge)")
    return lines


def drift_report(overall: Bucket, baseline: dict) -> list[str]:
    lines = ["── Drift vs backtest baseline ──"]
    if overall.n < MIN_TRADES_FOR_DRIFT:
        lines.append(
            f"Only {overall.n} closed paper trades — too few for a meaningful comparison "
            f"(need ≥{MIN_TRADES_FOR_DRIFT}). Patience is the Phase 2 exercise."
        )
        return lines

    b_wr = float(baseline.get("win_rate_pct", 0.0))
    b_ap = float(baseline.get("avg_profit_pct", 0.0))
    d_wr = overall.win_rate - b_wr
    d_ap = overall.avg_profit_pct - b_ap

    lines.append(f"win rate:   live {overall.win_rate:.0f}%  vs backtest {b_wr:.0f}%  (Δ {d_wr:+.0f}pp)")
    lines.append(f"avg profit: live {overall.avg_profit_pct:+.2f}% vs backtest {b_ap:+.2f}% (Δ {d_ap:+.2f}pp)")

    flags = []
    if abs(d_wr) > DRIFT_WIN_RATE_PP:
        flags.append(f"win rate drifted {d_wr:+.0f}pp (threshold ±{DRIFT_WIN_RATE_PP:.0f}pp)")
    if abs(d_ap) > DRIFT_AVG_PROFIT_PP:
        flags.append(f"avg profit drifted {d_ap:+.2f}pp (threshold ±{DRIFT_AVG_PROFIT_PP:.1f}pp)")

    if flags:
        lines.append("⚠️ DRIFT FLAG: " + "; ".join(flags))
        lines.append("Per ROADMAP Phase 2: if live diverges badly, return to Phase 1 — "
                     "that is a successful outcome of paper trading, not a failure.")
    else:
        lines.append("✅ Within thresholds — live behavior roughly consistent with backtest so far.")
    return lines


def make_baseline(backtest_json: str, out_path: str) -> None:
    """Distill a freqtrade backtest result export into the small baseline file."""
    with open(backtest_json, encoding="utf-8") as f:
        data = json.load(f)
    # Freqtrade export: {"strategy": {"<StrategyName>": {...stats...}}}
    strat = next(iter(data["strategy"].values()))
    baseline = {
        "source": os.path.basename(backtest_json),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_trades": strat["total_trades"],
        "win_rate_pct": round(100.0 * strat["wins"] / strat["total_trades"], 2) if strat["total_trades"] else 0.0,
        "avg_profit_pct": round(100.0 * strat["profit_mean"], 4),
        "max_drawdown_pct": round(100.0 * strat.get("max_drawdown_account", strat.get("max_drawdown", 0.0)), 2),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)
    print(f"Baseline written to {out_path}:")
    print(json.dumps(baseline, indent=2))


def send_telegram(text: str) -> None:
    token, chat_id = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not token or not chat_id:
        return
    # Telegram hard-caps messages at 4096 chars.
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:  # report failure but never crash the report itself
        print(f"(telegram send failed: {e})", file=sys.stderr)


def main() -> None:
    # Emoji in the report vs legacy Windows consoles (cp1252): degrade, don't crash.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="Paper-trading scoreboard + drift report (advisory only)")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"Freqtrade sqlite DB (default: {DEFAULT_DB})")
    ap.add_argument("--baseline", default="user_data/backtest_baseline.json",
                    help="baseline JSON for drift check (skipped if missing)")
    ap.add_argument("--min-trades", type=int, default=2,
                    help="hide tag/exit groups with fewer trades than this (default: 2)")
    ap.add_argument("--make-baseline", metavar="BACKTEST_JSON",
                    help="generate baseline from a freqtrade backtest result export, then exit")
    ap.add_argument("--out", default="user_data/backtest_baseline.json",
                    help="output path for --make-baseline")
    args = ap.parse_args()

    if args.make_baseline:
        make_baseline(args.make_baseline, args.out)
        return

    trades = load_closed_trades(args.db)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [f"📊 JamTrade paper report — {now}", ""]

    if not trades:
        lines.append("No closed paper trades yet. Nothing to score — let it run.")
    else:
        overall = Bucket()
        for t in trades:
            overall.add(t["profit"], t["duration_h"])
        first = min(t["close_date"] for t in trades if t["close_date"])
        lines.append(
            f"Closed trades: {overall.n} since {first:%Y-%m-%d} · "
            f"win {overall.win_rate:.0f}% · avg {overall.avg_profit_pct:+.2f}%/trade · "
            f"cum {overall.cum_profit_pct:+.2f}% · maxDD {max_drawdown_pct(trades):.2f}%"
        )
        lines.append("")
        lines.append("── Entry-tag scoreboard (which layer combos earn) ──")
        lines.extend(fmt_bucket_table(bucketize(trades, "enter_tag"), args.min_trades, "tag"))
        lines.append("")
        lines.append("── Exit-reason breakdown (where profit leaks) ──")
        lines.extend(fmt_bucket_table(bucketize(trades, "exit_reason"), args.min_trades, "exit"))
        lines.append("")

        if os.path.exists(args.baseline):
            with open(args.baseline, encoding="utf-8") as f:
                lines.extend(drift_report(overall, json.load(f)))
        else:
            lines.append(f"(no baseline at {args.baseline} — run --make-baseline after your "
                         f"next v1.7 backtest to enable the drift check)")

    lines.append("")
    lines.append("Reporting only — reads the dry-run DB, changes nothing, trades nothing.")

    report = "\n".join(lines)
    print(report)
    send_telegram(report)


if __name__ == "__main__":
    main()
