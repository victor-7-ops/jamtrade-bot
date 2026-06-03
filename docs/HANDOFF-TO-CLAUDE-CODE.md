# Handoff to Claude Code — Limitations & Open Work

This file exists because the project was started in a **sandboxed chat assistant** with
restrictions that Claude Code (running on your own machine/server) does **not** have. It
records exactly what couldn't be done here, what's untested as a result, and the concrete
next steps. Read this first when you open the project in Claude Code.

---

## TL;DR for Claude Code

Everything in this repo is **code-complete and syntax-validated**, but most of it has **never
actually executed against the network, a real install, or live data** — because the
environment it was authored in had no internet, no Freqtrade installed, and no secrets. Your
job is to take it from "written and validated" to "running and verified." Start with the
"First session checklist" at the bottom.

---

## What the authoring sandbox could NOT do

These are limitations of the chat environment this was built in — NOT limitations of the
code or of Claude Code:

### 1. No network access
- Could not `pip install` anything, so no dependency ever ran.
- Could not call Binance, CoinGecko, alternative.me, Google Trends, or Telegram.
- Could not `git clone`, `git push`, or reach GitHub.
- **Consequence:** the data-fetching paths (`ccxt`, `requests`, `pytrends`) are written to a
  correct API shape but have **not** been confirmed against the live APIs. Field names,
  rate limits, and response structures should be verified on first run.

### 2. No Freqtrade installed
- The strategy (`MultiConfirmationStrategy.py`) was validated only for **Python syntax**
  (via `ast.parse`), not by Freqtrade's loader.
- **Never backtested. Never dry-run.** No numbers exist yet — any performance is unknown.
- `custom_stoploss`, the `@informative("1d")` merge, and the hyperopt params are written to
  the documented Freqtrade v3 interface but are **unverified at runtime**.
- **Consequence:** expect to fix small API mismatches the first time you run
  `freqtrade backtesting`. This is normal.

### 3. No TA-Lib (C library or Python binding)
- The indicator math in both `MultiConfirmationStrategy.py` and `scripts/sentiment.py` uses
  `talib`, which was not installed.
- The standalone advisor's indicator logic (`signal_advisor.py`) was **not** executed end to
  end. Only the message-formatting and the sentiment dataclass logic were unit-tested with
  mock values.
- **Consequence:** install TA-Lib (C lib first, then the binding) and run the advisor `--once`
  to confirm the indicators compute on real data.

### 4. No secrets / credentials
- No Telegram bot token, no chat id, no exchange keys (and none are needed for dry-run/advisor).
- **Consequence:** Telegram delivery has **never been tested**. The send function is written
  correctly but unverified. First real test: configure `.env`, run advisor `--once`, confirm a
  message arrives.

### 5. No long-running processes / no real OS services
- Could not start a persistent service, a systemd timer, or a cron job.
- The systemd unit files in `docs/ORACLE-DEPLOY.md` and the timer schedule are **written from
  spec, not tested on a live VM.**
- **Consequence:** when you deploy, verify with `systemctl status` / `journalctl` and adjust
  paths/user as needed for the actual machine.

### 6. No Oracle Cloud account or VM
- The entire `docs/ORACLE-DEPLOY.md` runbook is **authored from documentation and best
  practice**, not from a real deployment. Console UIs and exact menu labels change over time.
- **Consequence:** treat the runbook as a strong guide, but expect minor UI drift in the
  Oracle console. The ARM/TA-Lib build steps especially should be confirmed on first run.

### 7. Could not verify dependency versions resolve together
- `requirements.txt` pins are reasonable but were never resolved by `pip`.
- **Consequence:** you may need to adjust a version constraint if pip reports a conflict
  (notably around `freqtrade` + its pinned `pandas`/`numpy`, and `TA-Lib`).

---

## What WAS verified in the sandbox

So you know where the floor is:

- ✅ All Python files pass `ast.parse` (valid syntax, no typos that break parsing).
- ✅ `config-dryrun.json` is valid JSON and has `"dry_run": true`.
- ✅ All shell scripts pass `bash -n` (syntax check).
- ✅ `sentiment.py` logic unit-tested with mock data: rendering, the contrarian flag at
  greed≥75 and fear≤25, and fail-soft when sources are missing all behaved correctly.
- ✅ Project structure, docs, and the `.gitignore` (excludes `.env`, data, the trade DB) are
  in place.

---

## Known-unknowns to check first (most-likely friction points)

Ranked by how likely they are to need a fix:

1. **TA-Lib install on ARM** — the C library usually needs building from source on Ampere.
   See the runbook; confirm `python -c "import talib"` works before anything else.
2. **CoinGecko / alternative.me response fields** — confirm `sentiment.py` reads the live
   JSON correctly (e.g. `price_change_percentage_24h`, `sentiment_votes_up_percentage`,
   `value_classification`). Free APIs occasionally rename or rate-limit.
3. **Freqtrade interface drift** — if you're on a newer Freqtrade than the v3 spec assumed,
   `custom_stoploss`/informative signatures may need a tweak. Run a backtest early to surface it.
4. **Telegram chat_id format** — group vs. user ids differ (groups are negative numbers).
   Verify with a single `--once` run.
5. **Google Trends (pytrends)** — frequently rate-limited / flaky; it's optional and off by
   default (`ADVISOR_SENTIMENT_TRENDS=0`). Don't let it block you.

---

## Open work / roadmap pickup

Nothing below was possible to do in the sandbox; all of it is appropriate for Claude Code:

- [ ] `pip install -r requirements.txt` in a venv; resolve any version conflicts.
- [ ] Build/install TA-Lib; confirm import.
- [ ] Run `bash scripts/download-data.sh`, then `bash scripts/backtest.sh` — get the FIRST
      real numbers. Expect to fix minor API mismatches.
- [ ] Run `bash scripts/validate.sh` (lookahead + recursion) — **mandatory** before trusting
      any backtest. (See CLAUDE.md golden rule #3.)
- [ ] Configure `.env` (Telegram token + chat id); run `python scripts/signal_advisor.py --once`
      and confirm a message arrives, including the sentiment block.
- [ ] `git init`, commit, push to a private GitHub repo (so the Oracle VM can pull it).
- [ ] Follow `docs/ORACLE-DEPLOY.md` to provision the VM and the systemd timer.
- [ ] Run `scripts/healthcheck.sh` on the VM; wire it to its own daily timer.
- [ ] Only after weeks of consistent dry-run/advisor behavior, consider the Phase 4 gate in
      `docs/ROADMAP.md`. Do not shortcut it.

---

## What stays true regardless of environment (carry these into Claude Code)

These are in `CLAUDE.md` already, but they bear repeating because they're about safety, not
sandboxing — Claude Code should honor them just as strictly:

- **Keep `dry_run: true`.** No live trading without explicit, in-session confirmation from you,
  and never commit real API keys.
- **The advisor is advisory-only.** Don't let it be extended to place real orders.
- **Sentiment is context, never a trigger, and never tracks individual traders.**
- **Never claim profitability.** Backtest/paper results show the logic runs, not future profit.
- **Always run the lookahead check after changing entry/exit logic.**
- **Only risk money you can afford to lose**, and treat the early months as education.

---

## A note on what "done" means here

The sandbox could get this to *correct-by-construction* — valid code, sound structure, honest
docs. It could not get it to *proven-by-execution*. That last mile (install, run, verify on
real data and a real server) is exactly what Claude Code is for, and it's where you'll also
learn the most. Take it one verified step at a time.
