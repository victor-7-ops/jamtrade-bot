# AWS EC2 Deployment — Full Runbook

JamTrade dry-run bot on a t3.micro (Ubuntu 24.04, x86), running 24/7 via systemd.

> Work split: **You** do the AWS console steps (browser, ~15 min).
> **Claude Code** handles everything on the server over SSH.

---

## Part 0 — What you're building

```
Your PC                          AWS EC2 (t3.micro)
  git push  ──────────────────►  ~/jamtrade-bot/
                                    .venv/
                                    freqtrade trade (dry_run=true)
                                    systemd: jamtrade-dryrun.service
                                    Restart=always
```

- `dry_run: true` — paper trading only, no real money
- systemd `Restart=always` — auto-recovers from crashes
- Only port 22 (SSH from your IP) is open — no web exposure
- Secrets in `~/.env` (chmod 600), never committed

---

## Part 1 — Billing alarm (do this FIRST, before launching anything)

1. AWS Console → top-right region: set to **us-east-1** (billing metrics only exist there)
2. CloudWatch → Alarms → **Create Alarm**
3. Select metric → Billing → Total Estimated Charge → USD → Select metric
4. Threshold: `Greater than 1.00`
5. Action: Send notification → create SNS topic → add your email
6. Name: `jamtrade-billing-guard` → Create alarm
7. Confirm the subscription email that arrives

Do NOT skip this. A misconfigured service (e.g. accidentally enabling NAT Gateway) can rack
up charges fast.

---

## Part 2 — Launch the EC2 instance (browser, ~10 min)

1. EC2 → **Launch instance**
2. Name: `jamtrade-dryrun`
3. AMI: **Ubuntu Server 24.04 LTS (x86_64)** — pick the one marked "Free tier eligible"
4. Instance type: **t3.micro** (1 vCPU, 1GB RAM)
5. Key pair: **Create new key pair**
   - Name: `jamtrade-key`
   - Type: RSA, format: `.pem`
   - Download it → save to `C:\Users\gadia\.ssh\jamtrade-key.pem`
6. Network settings → **Edit**:
   - Security group name: `jamtrade-sg`
   - Inbound rule: SSH (22) → Source: **My IP** (auto-fills your current IP)
   - Delete any other default inbound rules (HTTP/HTTPS not needed)
7. Configure storage: **8 GiB gp3** (default)
8. **Launch instance**
9. Wait ~1 min → EC2 → Instances → copy the **Public IPv4 address**

Then paste Claude Code the SSH string:
```
ssh -i C:\Users\gadia\.ssh\jamtrade-key.pem ubuntu@<YOUR_PUBLIC_IP>
```

---

## Part 3 — First SSH connection (you run this once)

On Windows (PowerShell or Git Bash):
```bash
# Fix permissions on the key (Windows Git Bash)
chmod 600 ~/.ssh/jamtrade-key.pem

# Connect
ssh -i ~/.ssh/jamtrade-key.pem ubuntu@<YOUR_PUBLIC_IP>
```

If you get a fingerprint prompt, type `yes`.

---

## Part 4 — Server provisioning (Claude Code runs this over SSH)

Run `scripts/aws-setup.sh` from the repo — it handles everything:

```bash
# On the server, after first SSH:
curl -fsSL https://raw.githubusercontent.com/victor-7-ops/jamtrade-bot/master/scripts/aws-setup.sh | bash
```

Or clone first then run:
```bash
git clone https://github.com/victor-7-ops/jamtrade-bot.git ~/jamtrade-bot
cd ~/jamtrade-bot
bash scripts/aws-setup.sh
```

What the script does (in order):
1. System update + install build deps
2. Add 2GB swap file (t3.micro only has 1GB RAM — pandas needs headroom)
3. Build TA-Lib C library from source (x86, straightforward)
4. Create Python venv + install requirements
5. Verify `dry_run: true` in config (hard stop if not)
6. Install + enable `jamtrade-dryrun.service` systemd unit
7. Start the service, tail 20 lines of logs

---

## Part 5 — Configure secrets (Telegram, optional but recommended)

Telegram lets you see simulated entries/exits and confirms the server is alive.
Without it, a silent crash looks like "no signals" — you won't know until you SSH in.

```bash
# On the server:
nano ~/.env
```

Add:
```
TG_TOKEN=your_bot_token_from_botfather
TG_CHAT_ID=your_chat_id
```

```bash
chmod 600 ~/.env
```

Then enable Telegram in `user_data/config-dryrun.json`:
```json
"telegram": {
    "enabled": true,
    "token": "",
    "chat_id": ""
}
```

Wait — don't put secrets in the config file. Instead, the systemd service loads `~/.env`
via `EnvironmentFile=`. Update `config-dryrun.json` to read from env:

```json
"telegram": {
    "enabled": true,
    "token": "${TG_TOKEN}",
    "chat_id": "${TG_CHAT_ID}"
}
```

Then restart the service:
```bash
sudo systemctl restart jamtrade-dryrun
sudo systemctl status jamtrade-dryrun
```

---

## Part 6 — Verify it's running

```bash
# Service status
sudo systemctl status jamtrade-dryrun

# Live logs
sudo journalctl -u jamtrade-dryrun -f

# Tail the freqtrade log
tail -f ~/jamtrade-bot/user_data/logs/dryrun.log

# Check trade DB
cd ~/jamtrade-bot
source .venv/bin/activate
python -c "import sqlite3; c=sqlite3.connect('tradesv3.dryrun.sqlite').cursor(); c.execute('SELECT count(*) FROM trades'); print('trades:', c.fetchone())"
```

You should see `Bot heartbeat. PID=... state='RUNNING'` every 60s in the log.

---

## Part 7 — Keeping it updated

When you push strategy changes from Claude Code:

```bash
# On the server:
cd ~/jamtrade-bot
git pull
sudo systemctl restart jamtrade-dryrun
sudo journalctl -u jamtrade-dryrun -f
```

**Important:** freqtrade does NOT hot-reload. Every strategy change needs a service restart.
The old DB is preserved — you don't lose paper trade history.

---

## Part 8 — Monthly health check (5 min)

```bash
# System updates
sudo apt-get update && sudo apt-get upgrade -y

# Service alive?
sudo systemctl is-active jamtrade-dryrun

# Disk usage (8GB is plenty but worth checking)
df -h /

# Swap usage (shouldn't be > 50% regularly; if so, consider upgrading instance)
free -h

# Last 50 log lines
sudo journalctl -u jamtrade-dryrun -n 50
```

---

## Part 9 — If you need to rebuild

Everything is in git. If the instance dies or you need to start over:

1. Terminate the old instance in EC2
2. Launch a new t3.micro (same steps as Part 2)
3. Run `scripts/aws-setup.sh` again
4. Restore `~/.env` (keep a local copy)

The paper trade DB (`tradesv3.dryrun.sqlite`) lives on the VM — back it up before
terminating if you want to preserve the paper history:

```bash
# From your PC:
scp -i ~/.ssh/jamtrade-key.pem ubuntu@<IP>:~/jamtrade-bot/tradesv3.dryrun.sqlite ./dryrun-backup.sqlite
```

---

## Quick reference

| Task | Command |
|------|---------|
| SSH in | `ssh -i ~/.ssh/jamtrade-key.pem ubuntu@<IP>` |
| Check status | `sudo systemctl status jamtrade-dryrun` |
| Start / stop / restart | `sudo systemctl start/stop/restart jamtrade-dryrun` |
| Live logs | `sudo journalctl -u jamtrade-dryrun -f` |
| Pull + restart | `cd ~/jamtrade-bot && git pull && sudo systemctl restart jamtrade-dryrun` |
| Trade count | `python -c "import sqlite3;c=sqlite3.connect('tradesv3.dryrun.sqlite').cursor();c.execute('SELECT count(*) FROM trades');print(c.fetchone())"` |

---

## Safety reminders

- `dry_run: true` stays true. The server changes nothing about this.
- No API keys in any committed file. Secrets live only in `~/.env` on the VM.
- SSH only, no inbound web ports. Freqtrade REST API stays disabled unless you need it
  (and if you enable it, use an SSH tunnel — never expose port 8080 publicly).
- Set the billing alarm before launching (Part 1). Credits expire 22 Dec 2026 → ~$8/mo after.
