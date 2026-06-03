# StrategyLab → Freqtrade: Paper Trading Setup Guide

This gets your multi-confirmation strategy running on a **live Binance price feed with fake money** (dry-run). No real funds at risk.

---

## What You're Getting

| File | What it is |
|------|-----------|
| `MultiConfirmationStrategy.py` | The strategy (6 layers + ADX filter + ATR trailing stop) |
| `config-dryrun.json` | Config set to paper-trade on live Binance data |
| This guide | Setup + the honest workflow |

---

## Step 1 — Install Freqtrade

**Option A: Docker (easiest, recommended)**
```bash
mkdir ft_userdata && cd ft_userdata
curl https://raw.githubusercontent.com/freqtrade/freqtrade/stable/docker-compose.yml -o docker-compose.yml
docker compose pull
docker compose run --rm freqtrade create-userdir --userdir user_data
```

**Option B: Native (Linux/macOS)**
```bash
git clone https://github.com/freqtrade/freqtrade.git
cd freqtrade
./setup.sh -i
```

Requires Python 3.10+.

---

## Step 2 — Drop in the strategy and config

```bash
# Copy the strategy into Freqtrade's strategies folder
cp MultiConfirmationStrategy.py user_data/strategies/

# Copy the config to the root
cp config-dryrun.json user_data/config.json
```

---

## Step 3 — Download historical data (for backtesting first)

```bash
freqtrade download-data \
  --exchange binance \
  --pairs BTC/USDT ETH/USDT SOL/USDT BNB/USDT \
  --timeframe 4h 1d \
  --timerange 20230101-
```

> Note: we download both 4h (trading timeframe) and 1d (the higher-timeframe trend filter the strategy uses).

---

## Step 4 — Backtest on real historical data

```bash
freqtrade backtesting \
  --strategy MultiConfirmationStrategy \
  --config user_data/config.json \
  --timerange 20240101-20250101 \
  --timeframe 4h
```

You'll get a real report: win rate, profit, drawdown, profit factor.

### CRITICAL: Run the lookahead-bias check
This is the single most important command. It catches strategies that secretly cheat by using future data:
```bash
freqtrade lookahead-analysis \
  --strategy MultiConfirmationStrategy \
  --config user_data/config.json \
  --timerange 20240101-20250101
```
If this flags problems, **the backtest is lying** — fix before trusting any numbers.

---

## Step 5 — Paper trade on the LIVE feed (the main event)

This is "trying it in the real market" safely. Real prices, real-time, fake money:

```bash
freqtrade trade \
  --strategy MultiConfirmationStrategy \
  --config user_data/config.json
```

Because `dry_run: true` is set in the config, this:
- Connects to the **real Binance feed**
- Watches **live prices** every candle
- Simulates trades against a **$1000 fake wallet**
- Logs everything exactly as if it were real

Leave it running. Check back over **days and weeks**, not minutes.

---

## Step 6 — The honest evaluation

After a few weeks of dry-run, ask:

1. **Does live match backtest?** If backtest said 55% win rate and dry-run gives 38%, your backtest was overfit. Trust the dry-run.
2. **Is the drawdown survivable?** Could you stomach the worst losing streak with real money?
3. **How many trades?** Too few = not enough data to judge. Be patient.

---

## The Workflow That Separates Winners From Losers

```
Backtest  →  Lookahead check  →  Paper trade (weeks/months)  →  Compare
                                                                    │
                          ┌─────────────────────────────────────────┤
                          ▼                                          ▼
                  Results hold up?                          Results collapse?
                          │                                          │
                  Tiny real capital                        Back to the drawing
                  (lose-it-money only)                     board — no money lost
```

---

## Tuning It For Your Pairs (Optional, Later)

Once you understand the basics, hyperopt finds better parameters for *your* chosen pairs:
```bash
freqtrade hyperopt \
  --strategy MultiConfirmationStrategy \
  --config user_data/config.json \
  --hyperopt-loss SharpeHyperOptLoss \
  --spaces buy sell \
  --timerange 20240101-20250101 \
  --epochs 100
```

⚠️ Warning: hyperopt is where overfitting happens most. Always validate hyperopt results on a **different** time period than you optimized on.

---

## Reality Checks (Please Read)

- **Dry-run ≠ live.** Even dry-run doesn't fully model slippage on large orders or getting filled in fast markets. Live is always a bit worse.
- **Fees matter.** Binance spot fees (~0.1% per trade) add up fast on frequent trades. The backtest includes them; make sure you understand the impact.
- **This strategy is a starting point, not a money printer.** It's a solid, well-structured foundation to learn from and improve — that's its real value.
- **Only risk what you can afford to lose.** Completely. Treat your first 6–12 months as paid education, not income.

---

## Where To Get Help

- Freqtrade docs: https://www.freqtrade.io
- Strategy customization: https://www.freqtrade.io/en/stable/strategy-customization/
- The lookahead/recursion analysis docs (read these): https://www.freqtrade.io/en/stable/lookahead-analysis/

You've got a real, structured strategy and the safe path to test it. Take it slow — the goal right now is learning, not earning.
