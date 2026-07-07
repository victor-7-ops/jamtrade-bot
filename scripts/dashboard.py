#!/usr/bin/env python3
"""
dashboard.py — static HTML dashboard for paper-trading results.

Renders the same data performance_report.py prints to text/Telegram as a
single self-contained HTML file: no server, no framework, no build step.
Reuses performance_report's DB-reading and aggregation functions directly
(imported, not reimplemented) so the two never drift out of sync.

Optionally pulls in the walk-forward summary table too, if window results
exist under --wf-dir.

This is a REPORTING tool: reads the dry-run DB read-only, writes one HTML
file, does nothing else. No orders, no strategy changes, no server process.

Usage:
    python scripts/dashboard.py
    python scripts/dashboard.py --db user_data/tradesv3.dryrun.sqlite \\
        --baseline user_data/backtest_baseline.json \\
        --wf-dir user_data/backtest_results/walk_forward \\
        --out user_data/dashboard.html

Open the output file directly in a browser (file:// URL) — or serve it with
any static file server if you want it reachable over the network. No live
process required; regenerate by re-running this script (e.g. from the same
systemd timer that runs performance_report.py).

Stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import performance_report as pr  # reuse Bucket, load_closed_trades, bucketize, etc.


def esc(s) -> str:
    return html.escape(str(s))


def render_bucket_table(buckets: dict[str, "pr.Bucket"], min_trades: int, col_label: str) -> str:
    shown = {k: b for k, b in buckets.items() if b.n >= min_trades}
    hidden = len(buckets) - len(shown)
    rows = []
    for name, b in sorted(shown.items(), key=lambda kv: kv[1].avg_profit_pct, reverse=True):
        cls = "pos" if b.avg_profit_pct >= 0 else "neg"
        rows.append(
            f"<tr><td>{esc(name)}</td><td>{b.n}</td><td>{b.win_rate:.0f}%</td>"
            f"<td class='{cls}'>{b.avg_profit_pct:+.2f}%</td>"
            f"<td class='{cls}'>{b.cum_profit_pct:+.2f}%</td>"
            f"<td>{b.worst_pct:+.2f}%</td><td>{b.avg_duration_h:.0f}</td></tr>"
        )
    note = f"<p class='muted'>{hidden} group(s) hidden — fewer than {min_trades} trades.</p>" if hidden else ""
    return (
        f"<table><thead><tr><th>{esc(col_label)}</th><th>n</th><th>win%</th>"
        f"<th>avg%</th><th>cum%</th><th>worst%</th><th>avg hrs</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=7 class=muted>No groups meet the sample threshold.</td></tr>'}</tbody></table>{note}"
    )


def render_layer_table(trades: list[dict], min_trades: int) -> str:
    tagged = [t for t in trades if t["enter_tag"] != "(untagged)"]
    if not tagged:
        return "<p class='muted'>No tagged entries yet.</p>"
    all_layers = sorted({layer for t in tagged for layer in t["enter_tag"].split("+")})
    rows = []
    for layer in all_layers:
        present, absent = pr.Bucket(), pr.Bucket()
        for t in tagged:
            (present if layer in t["enter_tag"].split("+") else absent).add(t["profit"], t["duration_h"])
        fire_pct = 100.0 * present.n / len(tagged)
        out_txt = f"{absent.avg_profit_pct:+.2f}%" if absent.n >= min_trades else "n/a"
        warn = ""
        if fire_pct >= 95.0 and absent.n < min_trades:
            warn = " <span class='warn'>always fires — hard gate, not a discriminator</span>"
        rows.append(
            f"<tr><td>{esc(layer)}</td><td>{fire_pct:.0f}%</td><td>{present.n}</td>"
            f"<td>{present.avg_profit_pct:+.2f}%</td><td>{absent.n}</td><td>{esc(out_txt)}{warn}</td></tr>"
        )
    return (
        "<table><thead><tr><th>layer</th><th>fire%</th><th>n in</th><th>avg% in</th>"
        f"<th>n out</th><th>avg% out</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def render_walk_forward(wf_dir: str) -> str:
    pattern = os.path.join(wf_dir, "w*_*", "result.json")
    paths = sorted(glob.glob(pattern), key=lambda p: int(re.search(r"w(\d+)_", p).group(1) or 0))
    if not paths:
        return "<p class='muted'>No walk-forward results found — run scripts/walk_forward.sh first.</p>"
    rows = []
    for path in paths:
        m = re.search(r"w(\d+)_(\d{8})-(\d{8})", path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        strat = next(iter(data["strategy"].values()))
        trades = strat.get("total_trades", 0)
        wr = 100.0 * strat.get("wins", 0) / trades if trades else 0.0
        avg = 100.0 * strat.get("profit_mean", 0.0)
        pf = strat.get("profit_factor", 0.0)
        dd = 100.0 * strat.get("max_drawdown_account", strat.get("max_drawdown", 0.0))
        cls = "pos" if avg >= 0 else "neg"
        rng = f"{m.group(2)}-{m.group(3)}" if m else "?"
        rows.append(
            f"<tr><td>{m.group(1) if m else '?'}</td><td>{esc(rng)}</td><td>{trades}</td>"
            f"<td>{wr:.0f}%</td><td class='{cls}'>{avg:+.2f}%</td><td>{pf:.2f}</td><td>{dd:.2f}%</td></tr>"
        )
    return (
        "<table><thead><tr><th>window</th><th>range</th><th>n</th><th>win%</th>"
        f"<th>avg%</th><th>PF</th><th>maxDD%</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>JamTrade paper-trading dashboard</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; line-height: 1.4; }}
  h1 {{ font-size: 1.4rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2.2rem; border-bottom: 1px solid #8883; padding-bottom: .3rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
  th, td {{ text-align: right; padding: .35rem .6rem; border-bottom: 1px solid #8882; }}
  th:first-child, td:first-child {{ text-align: left; }}
  .pos {{ color: #1a7f37; }}
  .neg {{ color: #cf222e; }}
  .warn {{ color: #9a6700; font-size: .8em; }}
  .muted {{ color: #6a737d; font-size: .85rem; }}
  .summary {{ display: flex; gap: 1.5rem; flex-wrap: wrap; margin: .8rem 0 1.2rem; }}
  .stat {{ background: #8881; border-radius: 8px; padding: .6rem 1rem; min-width: 120px; }}
  .stat .label {{ font-size: .75rem; color: #6a737d; text-transform: uppercase; }}
  .stat .value {{ font-size: 1.3rem; font-weight: 600; }}
  .footer {{ margin-top: 2.5rem; font-size: .8rem; color: #6a737d; }}
  .flag {{ background: #fff3cd33; border-left: 3px solid #9a6700; padding: .5rem .8rem; margin: .6rem 0; }}
</style>
</head>
<body>
<h1>JamTrade paper-trading dashboard</h1>
<p class="muted">Generated {generated} · reporting only, reads closed dry-run trades, places no orders</p>

<div class="summary">
  <div class="stat"><div class="label">Closed trades</div><div class="value">{n_trades}</div></div>
  <div class="stat"><div class="label">Win rate</div><div class="value">{win_rate:.0f}%</div></div>
  <div class="stat"><div class="label">Avg / trade</div><div class="value">{avg_profit:+.2f}%</div></div>
  <div class="stat"><div class="label">Cumulative</div><div class="value">{cum_profit:+.2f}%</div></div>
  <div class="stat"><div class="label">Max drawdown</div><div class="value">{max_dd:.2f}%</div></div>
</div>

{drift_html}

<h2>Entry-tag scoreboard</h2>
{tag_table}

<h2>Exit-reason breakdown</h2>
{exit_table}

<h2>Layer presence</h2>
{layer_table}

<h2>Walk-forward windows</h2>
{wf_table}

<div class="footer">
  JamTrade Bot &middot; dashboard.py &middot; regenerate any time, no live process required.
</div>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a static HTML dashboard from paper-trading results")
    ap.add_argument("--db", default=pr.DEFAULT_DB)
    ap.add_argument("--baseline", default="user_data/backtest_baseline.json")
    ap.add_argument("--wf-dir", default="user_data/backtest_results/walk_forward")
    ap.add_argument("--min-trades", type=int, default=2)
    ap.add_argument("--out", default="user_data/dashboard.html")
    args = ap.parse_args()

    trades = pr.load_closed_trades(args.db)
    overall = pr.Bucket()
    for t in trades:
        overall.add(t["profit"], t["duration_h"])

    drift_html = ""
    if trades and os.path.exists(args.baseline):
        with open(args.baseline, encoding="utf-8") as f:
            baseline = json.load(f)
        novel_lines = pr.novel_tag_check(trades, baseline)
        drift_lines = pr.drift_report(overall, baseline)
        parts = []
        if novel_lines:
            parts.append(f"<div class='flag'>{'<br>'.join(esc(l) for l in novel_lines)}</div>")
        cls = "flag" if any("DRIFT FLAG" in l for l in drift_lines) else ""
        wrapper = f"<div class='{cls}'>" if cls else "<div>"
        parts.append(f"{wrapper}{'<br>'.join(esc(l) for l in drift_lines)}</div>")
        drift_html = "<h2>Drift vs backtest baseline</h2>" + "".join(parts)

    html_out = PAGE_TEMPLATE.format(
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        n_trades=overall.n,
        win_rate=overall.win_rate,
        avg_profit=overall.avg_profit_pct,
        cum_profit=overall.cum_profit_pct,
        max_dd=pr.max_drawdown_pct(trades) if trades else 0.0,
        drift_html=drift_html,
        tag_table=render_bucket_table(pr.bucketize(trades, "enter_tag"), args.min_trades, "tag")
        if trades else "<p class='muted'>No closed trades yet.</p>",
        exit_table=render_bucket_table(pr.bucketize(trades, "exit_reason"), args.min_trades, "exit")
        if trades else "<p class='muted'>No closed trades yet.</p>",
        layer_table=render_layer_table(trades, args.min_trades),
        wf_table=render_walk_forward(args.wf_dir),
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Dashboard written to {args.out} ({len(html_out)} bytes)")


if __name__ == "__main__":
    main()
