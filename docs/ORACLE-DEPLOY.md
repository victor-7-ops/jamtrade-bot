# Oracle Cloud (Always Free) Deployment — Full Runbook

This is the end-to-end guide to host your signal advisor (and optionally the Freqtrade
dry-run bot) on an Oracle Cloud **Always Free** VM, 24/7, at zero ongoing cost.

It's written to be used **with Claude Code**. You'll do the account/console steps yourself
(those need a human in a browser), then hand the server to Claude Code to provision and
maintain. Prompts for Claude Code are marked **🤖 Claude Code prompt** throughout.

> Reality check: "Always Free" is genuinely free, but you're a guest on Oracle's free tier.
> They *can* reclaim idle resources or change terms. For an advisory bot that's an
> acceptable risk (a missed ping costs nothing). Keep your repo in git so you can redeploy
> anywhere in minutes if that ever happens.

---

## Part 0 — What you're building

```
┌─────────────────────────────────────────────┐
│  Oracle Always Free VM (Ubuntu, ARM)         │
│                                              │
│   systemd timer  ──every 4h──►  advisor.py   │
│                                    │         │
│                                    ▼         │
│                          ccxt (public data)  │
│                                    │         │
│                                    ▼         │
│                          Telegram message →  │ ──► your phone
└─────────────────────────────────────────────┘
```

No inbound ports, no web server, no exposed secrets. The VM just wakes up, computes, pings
you, and sleeps. Minimal attack surface.

---

## Part 1 — Create the Oracle account (browser, ~15 min)

1. Go to **cloud.oracle.com** → "Start for free."
2. Sign up. **A credit/debit card is required for identity verification.** Always Free
   resources are not charged; you'd only be billed if you explicitly upgrade to "Pay As You
   Go" and exceed free limits. To be safe, simply don't upgrade.
3. Pick your **home region** carefully — choose one close to you (e.g. Singapore or Tokyo for
   the Philippines) for lower latency. You can't change it later.
4. Verify email/phone and finish. Account provisioning can take a few minutes.

> 💡 Tip: Always Free ARM (Ampere A1) capacity is popular and sometimes shows "out of
> capacity" in busy regions. If so, try again at off-peak hours, or pick a slightly less
> busy region as home. An AMD "Micro" instance is also Always Free and easier to get,
> though smaller — more than enough for the advisor.

---

## Part 2 — Launch the VM (browser, ~10 min)

1. In the Oracle console: **Menu → Compute → Instances → Create Instance.**
2. **Name:** `jamtrade-advisor`
3. **Image:** Canonical **Ubuntu 22.04** (or 24.04).
4. **Shape:** click "Change shape" →
   - Preferred: **Ampere (ARM) VM.Standard.A1.Flex**, set to **1 OCPU / 6 GB RAM**
     (well within Always Free).
   - Fallback if ARM unavailable: **VM.Standard.E2.1.Micro** (AMD, Always Free).
5. **SSH keys:** choose "Generate a key pair for me" and **download both** the private and
   public keys. Save the private key somewhere safe (e.g. `~/.ssh/oracle_jamtrade`).
   - On macOS/Linux, lock down permissions: `chmod 600 ~/.ssh/oracle_jamtrade`
6. Leave networking at defaults (it creates a VCN with a public IP).
7. **Create.** When it's running, copy the **public IP address**.

### Connect for the first time
```bash
ssh -i ~/.ssh/oracle_jamtrade ubuntu@<YOUR_PUBLIC_IP>
```
If it connects, you're in. Type `exit` to leave for now.

> 🔒 You do NOT need to open any inbound ports for the advisor — it only makes outbound
> connections. Leave the firewall closed. (If you later want the Freqtrade web UI, that's a
> separate, deliberate step with proper auth — don't expose it casually.)

---

## Part 3 — Point Claude Code at the server

Now hand off to Claude Code. You can either:

- **(Simplest)** SSH into the VM yourself, then run Claude Code there, OR
- Use Claude Code on your local machine and have it give you commands to run over SSH.

Either way, get your project onto the VM first.

**🤖 Claude Code prompt:**
> "I have a fresh Ubuntu VM on Oracle Cloud at IP `<IP>`, SSH key at `~/.ssh/oracle_jamtrade`.
> I want to deploy the signal advisor from this repo. Walk me through (and generate commands
> for) cloning my repo onto the VM, installing system dependencies including the TA-Lib C
> library, creating a Python venv, and installing requirements.txt. I'm on the ARM shape, so
> flag anything ARM-specific."

The manual version of those steps, for reference:

```bash
# On the VM:
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git python3-venv python3-pip build-essential wget

# TA-Lib C library (needed before the python binding will install).
# On ARM/Ubuntu, building from source is the reliable route:
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
cd ~

# Clone your repo (replace with your URL)
git clone https://github.com/<you>/jamtrade-bot.git
cd jamtrade-bot

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Quick import check
python -c "import ccxt, talib, pandas; print('deps OK')"
```

---

## Part 4 — Configure secrets safely

Never put your Telegram token in a committed file. Use an environment file that stays on the
VM only.

```bash
# On the VM, in the repo root:
cat > .env <<'EOF'
TG_TOKEN=your_telegram_token_here
TG_CHAT_ID=your_chat_id_here
ADVISOR_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT
ADVISOR_TIMEFRAME=4h
EOF

chmod 600 .env   # readable only by you
```

`.gitignore` already excludes `.env`, so it won't be committed. Good.

**Test a live signal right now:**
```bash
set -a; source .env; set +a          # load env vars
python scripts/signal_advisor.py --once
```
You should get a Telegram message (or, if a pair is HOLD, a console line). 🎉

---

## Part 5 — Make it run forever (systemd timer)

A systemd **timer** is the robust way to run every 4 hours. It survives reboots, logs
cleanly, and uses zero resources between runs.

**🤖 Claude Code prompt:**
> "Generate a systemd service + timer that runs `scripts/signal_advisor.py --once` every 4
> hours from my venv, loading env vars from the repo's `.env` file, running as the `ubuntu`
> user from the repo directory. Give me the exact file contents and the commands to install
> and enable them."

For reference, the two files look like this:

**`/etc/systemd/system/jamtrade-advisor.service`**
```ini
[Unit]
Description=JamTrade signal advisor (one-shot)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/jamtrade-bot
EnvironmentFile=/home/ubuntu/jamtrade-bot/.env
ExecStart=/home/ubuntu/jamtrade-bot/.venv/bin/python scripts/signal_advisor.py --once
```

**`/etc/systemd/system/jamtrade-advisor.timer`**
```ini
[Unit]
Description=Run JamTrade advisor every 4 hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=4h
Persistent=true

[Install]
WantedBy=timers.target
```

**Install and enable:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jamtrade-advisor.timer

# Verify
systemctl list-timers | grep jamtrade        # see next run time
systemctl status jamtrade-advisor.service     # check last run
journalctl -u jamtrade-advisor.service -n 50  # view logs
```

That's it — it now runs every 4 hours, forever, restarting automatically after reboots.

> Want continuous `--loop` mode instead of a timer? Use a plain service with
> `Restart=always` running `signal_advisor.py --loop`. The timer approach is lighter and
> generally preferable for this workload; ask Claude Code if you want the loop variant.

---

## Part 6 — Running the full Freqtrade dry-run bot instead (optional)

If you'd rather run the actual Freqtrade paper-trading bot on the VM (Mode B), it's a
long-running service:

**🤖 Claude Code prompt:**
> "Create a systemd service that runs `bash scripts/dryrun.sh` from my repo as a persistent
> service with `Restart=always`, loading `.env`. Confirm dry_run stays true. Give me install
> + log-tailing commands."

Keep `dry_run: true`. Enable the Telegram block in `config-dryrun.json` (see
`docs/TELEGRAM-ALERTS.md`) so it pings you on simulated entries/exits.

---

## Part 7 — Keeping it healthy (light maintenance)

"Forever" needs a little upkeep. A monthly 5-minute check:

```bash
# Update the system
sudo apt-get update && sudo apt-get upgrade -y

# Pull latest strategy changes you've pushed from Claude Code
cd ~/jamtrade-bot && git pull && source .venv/bin/activate && pip install -r requirements.txt

# Confirm the timer is alive
systemctl list-timers | grep jamtrade
```

**🤖 Claude Code prompt for a health check:**
> "Write a small `scripts/healthcheck.sh` that verifies: the timer is active, the last
> advisor run exited 0, and that we can reach the exchange API. Have it send a Telegram
> message only if something's wrong."

### Optional: dead-man's switch
Since a silent failure on a free VM is possible, consider having the advisor send a brief
"still alive" message once a day even when everything's HOLD (run with `--notify-hold` on a
daily timer, or add a daily heartbeat). That way silence means "check the server," not
"nothing happened."

---

## Part 8 — If Oracle ever reclaims the instance

Because everything is in git + reproducible, recovery is fast:
1. Launch a new Always Free VM (Part 2).
2. Re-run the Part 3–5 setup (Claude Code can do this in one pass from your repo).
3. Recreate `.env` (keep a secure copy of your token offline).

This portability is the whole point of keeping it in version control. You're never locked in.

---

## Quick reference — the whole flow

```
Oracle account  →  Launch Always Free VM  →  SSH in
      │
      ▼
Claude Code: clone repo, install TA-Lib + venv + deps
      │
      ▼
Create .env (secrets, chmod 600)  →  test: advisor --once
      │
      ▼
systemd timer (every 4h)  →  enable --now
      │
      ▼
Runs forever. Monthly: apt upgrade + git pull. Pings your phone on signals.
```

---

## Safety reminders (don't skip)

- **Don't upgrade the Oracle account to Pay-As-You-Go** unless you intend to, and understand
  what leaves the free tier. Always Free resources won't charge you.
- **Keep `dry_run: true`** and remember the advisor is advisory-only. Nothing here trades
  real money. Going live is a separate, gated decision (see `docs/ROADMAP.md` Phase 4).
- **Never commit `.env` or any token.** If one leaks, `/revoke` it via BotFather immediately.
- **Lock the firewall.** The advisor needs no inbound ports. Don't expose the Freqtrade UI
  without proper authentication and, ideally, an SSH tunnel.
- **A missed alert is not a loss.** That tolerance is exactly why a free VM is fine for this.
