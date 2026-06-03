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

## Step 3 — Put them in your config

Open `user_data/config-dryrun.json` and update the telegram block:

```json
"telegram": {
    "enabled": true,
    "token": "PASTE_YOUR_TOKEN_HERE",
    "chat_id": "PASTE_YOUR_CHAT_ID_HERE",
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

> 🔒 Security: the token is a password for your bot. Because `.gitignore` is set up, your
> real config won't be committed — but double-check before pushing to any public repo.
> If a token leaks, send `/revoke` to BotFather and generate a new one.

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
