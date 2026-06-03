# First Session Log — JamTrade Bot Setup

**Date:** 2026-06-03  
**Duration:** ~3 hours  
**Status:** Paper trading live ✅

---

## What was accomplished

The project went from two markdown files (CLAUDE.md + HANDOFF) to a fully running paper trading bot in one session. Every step was verified before moving to the next.

---

## Environment setup

| Step | Result |
|---|---|
| Python 3.12.13 installed via `uv` | ✅ |
| `.venv` created with Python 3.12 | ✅ |
| All 156 packages installed from `requirements.txt` | ✅ |
| TA-Lib 0.6.8 installed (bundled C lib, no OS build needed on Windows) | ✅ |
| `import talib` + `talib.SMA()` smoke-test | ✅ |
| Config fixed: `jwt_secret_key` length, `price_side` → `"other"` | ✅ |
| DNS fix: removed `aiodns`/`pycares` (Windows incompatibility with c-ares) | ✅ |

---

## Data & backtesting

| Step | Result |
|---|---|
| Historical data downloaded (BTC/ETH/SOL/BNB, 4h + 1d, Jan 2023–now) | ✅ |
| First backtest run: 2024 full year | ✅ |
| Lookahead bias check | ✅ PASS — `has_bias: No` |
| Recursive analysis | ✅ PASS — all indicators 0.000% variance |

### Baseline backtest (default params, 2024)

| Metric | Value |
|---|---|
| Total profit | **-10.29%** |
| Win rate | 47.6% |
| Profit factor | 0.68 |
| Sharpe | -1.48 |
| Max drawdown | 13.09% (295 days) |
| Market change | +84.67% |

Honest read: default parameters lost money in a strong bull year. Expected — params were never tuned.

---

## Hyperopt

Ran `SharpeHyperOptLoss`, 200 epochs, `buy` + `sell` spaces, 2024 in-sample.

### Optimised parameters

```python
buy_params = {
    "buy_adx_min": 25,
    "buy_bb_std": 1.8,
    "buy_min_score": 3,
    "buy_rsi": 32,
    "buy_vol_mult": 1.8,
}
sell_params = {
    "atr_stop_mult": 3.9,
    "sell_rsi": 80,
}
```

### Results across all periods

| Period | Profit | Sharpe | Profit factor | Market |
|---|---|---|---|---|
| 2023 (OOS) | +5.30% | 0.62 | 1.43 | +146% |
| 2024 (in-sample) | +1.09% | 0.13 | 1.07 | +84.67% |
| 2025 Jan–Jun (OOS) | -5.28% | -0.43 | 0.72 | -44.37% |

---

## EMA200 macro gate (v1.2)

Added `above_ema200` column to the 1d informative pair. When BTC daily close is below its 200-period EMA, no new longs are entered — strategy sits on cash.

**Two lines changed:**
- `populate_indicators_1d`: added `ema200` + `above_ema200`  
- `populate_entry_trend`: added `macro_ok` gate

### Impact

| Period | Before | After |
|---|---|---|
| 2024 | +1.09% / Sharpe 0.13 | **+1.98% / Sharpe 0.24** |
| 2025 (bear, -44% market) | -5.28% / Sharpe -0.43 | **-0.98% / Sharpe -0.08** |

Lookahead check after change: **PASS**.

---

## Telegram signal advisor

- `.env` created with `TG_TOKEN` and `TG_CHAT_ID` (gitignored)
- Fixed HTML parse error: `rsi<38` → `rsi&lt;38` in message formatter
- `python scripts/signal_advisor.py --once --notify-hold` confirmed:
  - Live Binance data fetched ✅
  - Indicators computed ✅
  - Message with sentiment block delivered to phone ✅

---

## Paper trading

- `freqtrade trade` running against live Binance feed, fake wallet (1000 USDT)
- Registered as Windows Task Scheduler job (`\JamTrade\JamTrade-DryRun`)
- Starts automatically on login, restarts up to 3× on crash
- Logs: `user_data/logs/dryrun.log`
- Active pairs: BTC/USDT, ETH/USDT, SOL/USDT (BNB auto-removed by blacklist)

---

## Paper trading phase — what to watch for

**Purpose:** Verify live fill quality, signal timing, and stability. Backtests use static data; paper trading uses real-time prices and real exchange responses.

**Duration:** Minimum 30 trades (~4 months at current pace of 0.25 trades/day). Ideally 50–100 trades across different market conditions.

**Green flags:** Live win rate ~69%, avg trade duration ~1.3 days, losses roughly matching backtest size.  
**Red flags:** Win rate significantly below backtest, losses larger than backtest (slippage problem), or results *better* than backtest (lucky regime, not edge).

**Useful commands:**
```powershell
# Check logs
Get-Content user_data\logs\dryrun.log -Tail 30

# Run signal advisor manually
.venv\Scripts\python.exe scripts/signal_advisor.py --once --notify-hold

# Stop the bot
Stop-Process -Name freqtrade

# Restart via scheduler
schtasks /run /tn "\JamTrade\JamTrade-DryRun"
```

---

## Issues fixed this session

| Issue | Fix |
|---|---|
| Python 3.14 not supported by Freqtrade | Installed Python 3.12.13 via `uv python install 3.12` |
| `jwt_secret_key` too short in config | Replaced placeholder with 48-char random key |
| `price_side: "same"` incompatible with market orders (lookahead tool) | Changed entry + exit `price_side` to `"other"` |
| `aiodns`/`pycares` DNS failure on Windows | Removed both; `aiohttp` falls back to asyncio resolver |
| Hyperopt missing `filelock` | Installed `freqtrade[hyperopt]` extras |
| `aiodns` reinstalled as transitive dep of hyperopt extras | Re-removed after each install |
| Telegram 400: `rsi<38` unescaped HTML | Changed to `rsi&lt;38` in `signal_advisor.py` |

---

## Next steps (from ROADMAP.md)

1. Let paper trading accumulate 30+ trades over ~4 months
2. Compare live win rate / avg duration / loss size to backtest
3. Run `validate.sh` again after any future strategy changes
4. When ready: follow Phase 4 gate in `docs/ROADMAP.md` before going live
5. Consider Oracle Cloud Always Free VM for 24/7 operation (`docs/ORACLE-DEPLOY.md`)
