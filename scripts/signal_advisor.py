#!/usr/bin/env python3
"""
signal_advisor.py — Zero-cost buy/hold/sell advisor over Telegram.
====================================================================

This is a STANDALONE, ADVISORY-ONLY companion to the Freqtrade strategy.
It does NOT place trades and never touches money. It pulls live public
market data, runs the same 6-layer multi-confirmation logic, and sends you
a Telegram message saying BUY / HOLD / SELL with the reasoning.

You read the message, look at the chart yourself, and decide. A human is
always in the loop. That's the safest version of "tell me if the trade is okay."

Cost: $0. Uses:
  - ccxt          → free public price data (no API key, no account needed)
  - requests      → to send Telegram messages (Telegram is free)
  - pandas, ta-lib → indicators (installed via requirements.txt)

------------------------------------------------------------------------
SETUP
------------------------------------------------------------------------
1. Create a Telegram bot + get your chat id (see docs/TELEGRAM-ALERTS.md).
2. Set two environment variables (never hard-code secrets):

     export TG_TOKEN="7123456789:AAH..."
     export TG_CHAT_ID="123456789"

3. Run once to test:        python scripts/signal_advisor.py --once
4. Run on a schedule:       python scripts/signal_advisor.py --loop
   (or trigger via cron / the host's scheduler — see docs/DEPLOY-FREE.md)

------------------------------------------------------------------------
"""

import argparse
import os
import time
from datetime import datetime, timezone

import requests

try:
    import ccxt
    import pandas as pd
    import talib
except ImportError as e:
    raise SystemExit(
        f"Missing dependency: {e}. Run: pip install -r requirements.txt"
    )

# Optional sentiment context module (fails soft if absent).
try:
    from sentiment import get_sentiment
    _HAS_SENTIMENT = True
except Exception:
    _HAS_SENTIMENT = False

# ── Config (override via env or edit here) ─────────────────────────────
PAIRS = os.getenv("ADVISOR_PAIRS", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT").split(",")
TIMEFRAME = os.getenv("ADVISOR_TIMEFRAME", "4h")
EXCHANGE_ID = os.getenv("ADVISOR_EXCHANGE", "binance")
LOOP_MINUTES = int(os.getenv("ADVISOR_LOOP_MINUTES", "60"))
CANDLE_LIMIT = 300
# Toggle the sentiment context block in alerts (default on if module present).
SHOW_SENTIMENT = os.getenv("ADVISOR_SHOW_SENTIMENT", "1") == "1"
# Google Trends adds latency and can be flaky; off by default.
SENTIMENT_USE_TRENDS = os.getenv("ADVISOR_SENTIMENT_TRENDS", "0") == "1"

# Strategy params (mirror the Freqtrade strategy defaults)
RSI_BUY = 38
RSI_SELL = 68
ADX_MIN = 22
VOL_MULT = 1.4
BB_STD = 2.1
MIN_BUY_SCORE = 3

TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")


def send_telegram(text: str) -> None:
    """Send a message to your Telegram. No-op (prints) if not configured."""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[telegram not configured] would send:\n" + text + "\n")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[telegram error {resp.status_code}] {resp.text}")
    except requests.RequestException as e:
        print(f"[telegram request failed] {e}")


def fetch_ohlcv(exchange, pair: str) -> pd.DataFrame:
    """Fetch recent candles as a DataFrame. Public data, no auth."""
    raw = exchange.fetch_ohlcv(pair, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
    df = pd.DataFrame(
        raw, columns=["time", "open", "high", "low", "close", "volume"]
    )
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df


def analyze(df: pd.DataFrame) -> dict:
    """Run the multi-confirmation logic on the latest candle."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    ema50 = talib.EMA(close, timeperiod=50)
    rsi = talib.RSI(close, timeperiod=14)
    macd, macdsignal, macdhist = talib.MACD(
        close, fastperiod=12, slowperiod=26, signalperiod=9
    )
    bb_upper, bb_mid, bb_lower = talib.BBANDS(
        close, timeperiod=20, nbdevup=BB_STD, nbdevdn=BB_STD, matype=0
    )
    adx = talib.ADX(high, low, close, timeperiod=14)
    vol_sma = volume.rolling(20).mean()

    i = len(df) - 1  # latest candle
    price = float(close.iloc[i])

    # Bullish RSI divergence over a 10-bar lookback
    lookback = 10
    div = False
    if i > lookback + 3:
        recent_low = close.iloc[i - lookback : i + 1].min()
        prior_low = close.iloc[i - 2 * lookback : i - lookback].min()
        rsi_recent = rsi.iloc[i - lookback : i + 1].min()
        rsi_prior = rsi.iloc[i - 2 * lookback : i - lookback].min()
        div = (recent_low < prior_low) and (rsi_recent > rsi_prior)

    # Confirmation layers
    l1 = price > float(ema50.iloc[i])
    l2 = float(rsi.iloc[i]) < RSI_BUY
    l3 = float(macdhist.iloc[i]) > 0
    l4 = price < float(bb_lower.iloc[i])
    l5 = float(volume.iloc[i]) > float(vol_sma.iloc[i]) * VOL_MULT
    l6 = bool(div)
    buy_score = sum([l1, l2, l3, l4, l5, l6])

    regime_ok = float(adx.iloc[i]) >= ADX_MIN

    # Sell layers
    s1 = float(rsi.iloc[i]) > RSI_SELL
    s2 = float(macdhist.iloc[i]) < 0
    s3 = price > float(bb_upper.iloc[i])
    sell_score = sum([s1, s2, s3])

    # Decision
    if regime_ok and buy_score >= MIN_BUY_SCORE:
        decision = "BUY"
    elif sell_score >= 2:
        decision = "SELL"
    else:
        decision = "HOLD"

    return {
        "decision": decision,
        "price": price,
        "rsi": round(float(rsi.iloc[i]), 1),
        "adx": round(float(adx.iloc[i]), 1),
        "macdhist": round(float(macdhist.iloc[i]), 4),
        "buy_score": buy_score,
        "sell_score": sell_score,
        "regime_ok": regime_ok,
        "layers": {
            "trend(EMA50)": l1,
            "rsi&lt;38": l2,
            "macd_up": l3,
            "below_BB": l4,
            "vol_spike": l5,
            "divergence": l6,
        },
    }


def format_message(pair: str, r: dict) -> str:
    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}[r["decision"]]
    layers_str = "\n".join(
        f"  {'✅' if v else '▫️'} {k}" for k, v in r["layers"].items()
    )
    regime = "✅ trend present" if r["regime_ok"] else "⚠️ choppy (no-trade zone)"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    msg = (
        f"{emoji} <b>{r['decision']}</b> — {pair} ({TIMEFRAME})\n"
        f"Price: {r['price']}\n"
        f"RSI: {r['rsi']} | ADX: {r['adx']} | MACD hist: {r['macdhist']}\n"
        f"Buy score: {r['buy_score']}/6 | Sell score: {r['sell_score']}/3\n"
        f"Regime: {regime}\n"
        f"Layers:\n{layers_str}\n"
    )

    # Optional sentiment CONTEXT block (never affects the decision above).
    if SHOW_SENTIMENT and _HAS_SENTIMENT:
        try:
            symbol = pair.split("/")[0]
            snap = get_sentiment(symbol, use_trends=SENTIMENT_USE_TRENDS)
            msg += snap.as_message_block() + "\n"
        except Exception as e:  # never let context break the alert
            print(f"[sentiment unavailable for {pair}] {e}")

    msg += (
        f"<i>{ts}</i>\n"
        f"⚠️ Advisory only. Check the chart yourself before acting."
    )
    return msg


def run_once(notify_hold: bool = False) -> None:
    exchange = getattr(ccxt, EXCHANGE_ID)({"enableRateLimit": True})
    for pair in PAIRS:
        pair = pair.strip()
        try:
            df = fetch_ohlcv(exchange, pair)
            r = analyze(df)
            # By default only ping on actionable signals to avoid noise.
            if r["decision"] != "HOLD" or notify_hold:
                send_telegram(format_message(pair, r))
            else:
                print(f"{pair}: HOLD (score {r['buy_score']}/6) — no alert sent")
        except Exception as e:  # noqa: BLE001 — advisory tool, keep running
            print(f"[error analyzing {pair}] {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram buy/hold/sell advisor")
    parser.add_argument("--once", action="store_true", help="run a single scan")
    parser.add_argument("--loop", action="store_true", help="run forever on a timer")
    parser.add_argument(
        "--notify-hold",
        action="store_true",
        help="also send messages for HOLD (default: only BUY/SELL)",
    )
    args = parser.parse_args()

    if not args.once and not args.loop:
        args.once = True  # sensible default

    if args.once:
        run_once(notify_hold=args.notify_hold)
        return

    # loop mode
    send_telegram(
        f"📡 Signal advisor started. Watching {', '.join(PAIRS)} on {TIMEFRAME}, "
        f"every {LOOP_MINUTES} min. Advisory only — no trades placed."
    )
    while True:
        run_once(notify_hold=args.notify_hold)
        time.sleep(LOOP_MINUTES * 60)


if __name__ == "__main__":
    main()
