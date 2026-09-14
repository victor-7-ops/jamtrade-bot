# Telegram Alerts — Get Buy/Hold/Sell Pings on Your Phone

This sets up free phone notifications so the bot messages you whenever it sees a signal.
Telegram is completely free and takes ~5 minutes to wire up.

## Two modes — pick what you want

### Mode A: Signal alerts + manual approval (RECOMMENDED to start)
The bot watches the market in dry-run and **messages you** when the strategy fires a
buy/sell signal. *You* decide whether to act. This is the safest "is the trade okay?"
setup — a human (you) is always in the loop, and nothing automated touches money.

### Mode B: Full notifications on a paper-trading bot
The bot paper-trades automatically (fake money) and notifies you of every simulated
entry/exit. Still zero risk because it's dry-run, but trades happen without your tap.

Both use the same Telegram setup below. The difference is just how you run it.

---

## Step 1 — Create your Telegram bot (2 min)

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Pick a name and username (must end in `bot`, e.g. `jamtrade_signals_bot`)
4. BotFather replies with a **token** like `7123456789:AAH...`. Copy it.

## Step 2 — Get your chat ID (1 min)

1. Search for **@userinfobot** in Telegram and start it — it replies with your numeric ID.
   (Alternatively: message your new bot something, then visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find `"chat":{"id":...}`.)
2. Copy the numeric **chat id**.

## Step 3 — Put them in your environment (never in the config file)

`user_data/config-dryrun.json` is **tracked by git**. Never paste a token into it.
Freqtrade also does not expand `${VAR}` placeholders inside the config, so that
trick does not work either — the literal string is read as the token and startup fails.

Instead, override the config from the environment. Freqtrade merges any
`FREQTRADE__`-prefixed variable over the file before validating it, using `__`
as the nesting separator:

```bash
export FREQTRADE__TELEGRAM__ENABLED=true
export FREQTRADE__TELEGRAM__TOKEN="7123456789:AAH..."
export FREQTRADE__TELEGRAM__CHAT_ID="123456789"
```

Keep them in a `.env` that git ignores, and lock it down:

```bash
cp /dev/null .env && chmod 600 .env
# then add the three lines above (without `export`) and load it:
set -a; . ./.env; set +a
```

On the server, point the systemd unit at that file instead of exporting by hand:

```ini
[Service]
EnvironmentFile=/opt/jamtrade-bot/.env
```

Notification verbosity still lives in the config file (no secrets there), under
the same `telegram` block:

```json
"telegram": {
    "enabled": false,
    "token": "",
    "chat_id": "",
    "notification_settings": {
        "status": "on",
        "entry": "on",
        "entry_fill": "on",
        "exit": "on",
        "exit_fill": "on",
        "protection_trigger": "on"
    }
}
```

`enabled: false` is the committed default so a fresh clone starts without secrets;
`FREQTRADE__TELEGRAM__ENABLED=true` turns it on where the token actually exists.

> 🔒 Security: the token is a password for your bot. `.gitignore` covers `.env`, but it
> does **not** cover `user_data/config-dryrun.json` — that file is tracked, so anything
> you type into it gets committed. If a token leaks, send `/revoke` to BotFather and
> generate a new one.

## Step 4 — Run it

```bash
bash scripts/dryrun.sh
```

You'll get a Telegram message that the bot started. From then on it pings you on signals.

## Telegram commands you can send the bot

Once running, message your bot:

| Command | What it does |
|---------|--------------|
| `/status` | Show open (paper) trades |
| `/profit` | Summary of performance so far |
| `/daily` | Daily profit breakdown |
| `/balance` | Show the (dry-run) wallet |
| `/forcebuy PAIR` | Manually trigger a paper buy (if enabled) |
| `/help` | List all commands |

## Making it a pure "signal advisor" (Mode A)

If you want the bot to *only advise* and never even paper-trade on its own, the cleanest way
is to keep `max_open_trades` low and rely on the entry/exit **notifications** as your alerts,
treating each as "the strategy thinks now is a buy/sell — your call." You read the ping, you
check the chart, you decide. The bot becomes a tireless analyst that taps you on the shoulder,
not an autopilot.

For a fully custom advisor (e.g. a message that literally says "SIGNAL: consider BUY on
BTC/USDT — RSI 32, 4/6 layers") you'd write a small companion script. Ask Claude Code to
build `scripts/signal_advisor.py` and it can generate one that reuses the same indicators.
