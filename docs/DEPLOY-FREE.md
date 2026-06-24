# Deploy Free — Run It 24/7 at Zero Cost

You want the bot running around the clock, messaging you buy/hold/sell, without paying for
hosting. Here are the genuinely free paths in 2026, ranked by how well they actually work.

> Heads up: the free-hosting landscape changed in 2026. Railway removed its free tier and
> prepaid credits; Fly.io is now a 2-hour trial only. Don't follow older tutorials that
> assume those are free — they'll lead you to a credit card.

---

## 🥇 Option 1: A machine you already own (best for $0)

An old laptop, a spare desktop, or a **Raspberry Pi**. This is the real winner: truly free,
fully under your control, and it never sleeps.

**Why it's best for a signal bot:** the advisor only needs to wake up every 4 hours (one
candle), run a quick calculation, and send a message. That's almost no CPU. A Raspberry Pi
Zero sipping a couple of watts handles it forever for pennies of electricity.

### Setup (Linux / macOS / Pi)
```bash
# clone your repo, set up venv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# set your secrets (add these to ~/.bashrc to persist across reboots)
export TG_TOKEN="your_token"
export TG_CHAT_ID="your_chat_id"

# test once
python scripts/signal_advisor.py --once

# run continuously
python scripts/signal_advisor.py --loop
```

### Keep it running after you close the terminal
Use the host's own scheduler instead of a long-running process — more robust and uses zero
resources between runs.

**cron (runs every 4 hours, on the hour):**
```bash
crontab -e
# add this line (adjust the path):
0 */4 * * * cd /home/you/jamtrade-bot && /home/you/jamtrade-bot/.venv/bin/python scripts/signal_advisor.py --once >> advisor.log 2>&1
```

**Or systemd (for the --loop mode as a background service)** — ask Claude Code to generate a
`jamtrade-advisor.service` unit file; it's a few lines and makes the advisor auto-start on
boot and restart if it crashes.

---

## 🥈 Option 2: AWS EC2 (t3.micro, free-tier credits)

AWS gives $100 in credits (+ $100 more possible) on the new Free Plan, expiring 22 Dec 2026.
A t3.micro running 24/7 costs ~$7.50/mo — the credits cover 6+ months, then you decide
whether to keep paying (~$8/mo) or migrate to Oracle Always Free.

**Pros:** real Linux VM, x86 (TA-Lib builds without ARM pain), widely documented.
**Cons:** credits expire; after 22 Dec 2026 it bills automatically at ~$8/mo.

**Non-negotiable setup step — set a billing alarm before launching anything:**
1. AWS Console → CloudWatch → Alarms → Create Alarm
2. Metric: `Billing > Total Estimated Charge > USD`
3. Threshold: `> 1.00`
4. Action: send email to yourself
This catches any accidental paid-service usage immediately.

**Do NOT enable AWS Organizations** — the free-plan email explicitly warns this auto-upgrades
to a paid plan.

See `docs/AWS-DEPLOY.md` for the full runbook.

---

## 🥉 Option 3: Oracle Cloud "Always Free" (best free cloud forever)

Oracle's Always Free tier gives you small VMs that genuinely don't expire. It's the closest
thing to a free always-on cloud server in 2026.

- **Pros:** truly always-on, real Linux VM, generous for this workload.
- **Cons:** requires a credit card to verify identity (not charged on Always Free), and the
  signup/setup has more friction than push-to-deploy platforms.

Once you have the VM, setup is identical to Option 1 (it's just a Linux box). Use cron or
systemd the same way.

---

## 🥉 Option 3: GitHub Actions on a schedule (clever + free)

GitHub Actions gives free minutes on public repos. You can schedule a workflow to run the
advisor every few hours — no server at all.

**Tradeoffs:** scheduled actions can be delayed under load, and you must keep secrets in
GitHub Actions secrets (never in code). Good for low-frequency signal checks; not for a
continuously-running bot.

Ask Claude Code to generate `.github/workflows/advisor.yml` — it'll wire up a cron schedule
that runs `signal_advisor.py --once` and reads `TG_TOKEN` / `TG_CHAT_ID` from repo secrets.

---

## ⚠️ Option 4: Render free tier (works, with caveats)

Render still has a real free tier, but: free web services <b>spin down after ~15 minutes</b>
of inactivity and take 30-50s to wake. A background worker that sleeps isn't reliable for
timely alerts. If you use Render free, the scheduled-cron approach (Option 3 style) fits
better than a persistent worker. For always-on, Render's paid tier starts around $7/month —
which is no longer zero cost.

---

## Which should you pick?

| Your situation | Best option |
|----------------|-------------|
| Have any spare computer or a Pi | **Option 1** — done, free forever |
| No spare hardware, want always-on | **Option 2** (Oracle Always Free) |
| Just want periodic checks, no server | **Option 3** (GitHub Actions) |
| Already use Render, low urgency | Option 4 with cron |

For your case — a buy/hold/sell advisor that checks every 4h — **Option 1 on a Raspberry Pi
or old laptop is the cleanest zero-cost answer**, with Oracle Always Free as the no-hardware
backup.

---

## Important reminders

- **The advisor is advisory only.** It messages you a suggestion; you decide. Nothing here
  places trades or touches money.
- **Keep secrets in environment variables**, never in committed files. `.gitignore` already
  excludes `.env`.
- **Free uptime isn't guaranteed uptime.** Any free host can hiccup. For an advisory tool
  that's fine — a missed ping isn't a financial loss. (This is exactly why starting with
  *advisory*, not *automated live trading*, is the smart move.)
- **Electricity ≠ literally zero**, but running a Pi for this is a few cents a month — the
  closest thing to free that's also reliable.
