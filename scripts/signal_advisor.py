#!/usr/bin/env python3
"""
signal_advisor.py — Zero-cost buy/hold/sell advisor over Telegram.
====================================================================

This is a STANDALONE, ADVISORY-ONLY companion to the Freqtrade strategy.
It does NOT place trades and never touches money. It pulls live public
market data, runs the same multi-confirmation logic, and sends you a
Telegram message saying BUY / HOLD / SELL with the reasoning.

PARITY WITH THE BOT — the whole point of this tool is that its verdict
matches what MultiConfirmationStrategy would do. Three things keep it honest;
break any one and the advisor starts describing a bot that doesn't exist:
  1. Thresholds are READ FROM the hyperopt export the bot itself loads
     (user_data/strategies/MultiConfirmationStrategy.json), never hardcoded.
  2. The layer set is L1-L5 — same as the strategy since v1.7 dropped L6.
  3. The daily gates (EMA50 uptrend + EMA200 macro) are evaluated here too.
     Without them this tool says BUY in exactly the bear markets the bot
     refuses to trade.
Only closed candles are used, matching `process_only_new_candles = True`.

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
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

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
EXCHANGE_ID = os.getenv("ADVISOR_EXCHANGE", "kraken")
LOOP_MINUTES = int(os.getenv("ADVISOR_LOOP_MINUTES", "60"))
# --loop only: consecutive all-pairs-failed scans before sending one outage ping.
OUTAGE_ALERT_AFTER = int(os.getenv("ADVISOR_OUTAGE_ALERT_AFTER", "3"))
CANDLE_LIMIT = 300
# Higher-timeframe gate. EMA200 on daily needs a long warmup to converge —
# 200 candles would put the very first usable value at the last bar.
HTF_TIMEFRAME = "1d"
HTF_CANDLE_LIMIT = 400
# Toggle the sentiment context block in alerts (default on if module present).
SHOW_SENTIMENT = os.getenv("ADVISOR_SHOW_SENTIMENT", "1") == "1"
# Google Trends adds latency and can be flaky; off by default.
SENTIMENT_USE_TRENDS = os.getenv("ADVISOR_SENTIMENT_TRENDS", "0") == "1"

# ── Strategy params ───────────────────────────────────────────────────
# Do NOT hardcode these. Freqtrade auto-loads the hyperopt export
# `user_data/strategies/<StrategyName>.json` at runtime and it OVERRIDES the
# class defaults, so any value copied here by hand silently goes stale the
# next time the strategy is tuned — and the advisor starts describing a bot
# that no longer exists. Read the same file the bot reads.
PARAMS_FILE = (
    Path(__file__).resolve().parent.parent
    / "user_data" / "strategies" / "MultiConfirmationStrategy.json"
)

# Fallbacks = the strategy class defaults, used only if the export is absent
# (i.e. the strategy has never been hyperopted). Mirrors MultiConfirmationStrategy.
_DEFAULTS = {
    "buy_rsi": 38,
    "buy_adx_min": 22,
    "buy_vol_mult": 1.4,
    "buy_bb_std": 2.1,
    "buy_min_score": 3,
    "sell_rsi": 68,
}


def _load_strategy_params() -> dict:
    """Read the hyperopt params Freqtrade will actually run with."""
    params = dict(_DEFAULTS)
    try:
        raw = json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
        spaces = raw.get("params", {})
        for space in ("buy", "sell"):
            for k, v in spaces.get(space, {}).items():
                if k in params:
                    params[k] = v
    except FileNotFoundError:
        print(f"[params] {PARAMS_FILE.name} not found — using strategy class defaults")
    except (ValueError, OSError) as e:
        print(f"[params] could not read {PARAMS_FILE.name} ({e}) — using class defaults")
    return params


_P = _load_strategy_params()
RSI_BUY = _P["buy_rsi"]
RSI_SELL = _P["sell_rsi"]
ADX_MIN = _P["buy_adx_min"]
VOL_MULT = _P["buy_vol_mult"]
BB_STD = _P["buy_bb_std"]
MIN_BUY_SCORE = _P["buy_min_score"]
N_LAYERS = 5  # L1-L5; v1.7 removed L6 (RSI divergence) from the strategy

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


def fetch_ohlcv(exchange, pair: str, timeframe: str, limit: int) -> pd.DataFrame:
    """
    Fetch recent CLOSED candles as a DataFrame. Public data, no auth.

    Exchanges return the currently-forming candle as the last row. Acting on it
    means the signal can flip repeatedly within one bar and won't match the bot,
    which runs with ``process_only_new_candles = True``. Drop it.
    """
    raw = exchange.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        raw, columns=["time", "open", "high", "low", "close", "volume"]
    )
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    if len(df) > 1:
        df = df.iloc[:-1].reset_index(drop=True)
    return df


def analyze_htf(daily: pd.DataFrame) -> dict:
    """
    Daily higher-timeframe gates, mirroring the strategy's @informative("1d")
    block: `uptrend_1d` (close > daily EMA50) and `above_ema200_1d`
    (close > daily EMA200). BOTH must pass for the bot to enter.

    If there isn't enough daily history to evaluate them, this reports
    unknown and the caller blocks the BUY. The strategy defaults these to
    "allow" when the informative columns are missing, but that path only
    triggers on a data fault — and an advisory ping that says BUY when it
    cannot check the macro gate is the expensive direction to be wrong in.
    """
    if daily is None or len(daily) < 200:
        return {"htf_ok": False, "macro_ok": False, "known": False}

    d_close = daily["close"]
    ema50 = talib.EMA(d_close, timeperiod=50)
    ema200 = talib.EMA(d_close, timeperiod=200)
    j = len(daily) - 1
    price, e50, e200 = (
        float(d_close.iloc[j]),
        float(ema50.iloc[j]),
        float(ema200.iloc[j]),
    )
    if math.isnan(e50) or math.isnan(e200):
        return {"htf_ok": False, "macro_ok": False, "known": False}

    return {
        "htf_ok": price > e50,
        "macro_ok": price > e200,
        "known": True,
        "d_close": price,
        "d_ema50": e50,
        "d_ema200": e200,
    }


def analyze(df: pd.DataFrame, htf: dict) -> dict:
    """Run the multi-confirmation logic on the latest CLOSED candle."""
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

    i = len(df) - 1  # latest CLOSED candle
    price = float(close.iloc[i])

    # Confirmation layers L1-L5.
    # (v1.7 removed L6 "bullish RSI divergence" from the strategy — it fired on
    #  one trade in 2.5 years and that trade hit the full stop. Keeping it here
    #  would make the advisor score entries the bot does not score.)
    l1 = price > float(ema50.iloc[i])
    l2 = float(rsi.iloc[i]) < RSI_BUY
    l3 = float(macdhist.iloc[i]) > 0
    l4 = price < float(bb_lower.iloc[i])
    l5 = float(volume.iloc[i]) > float(vol_sma.iloc[i]) * VOL_MULT
    buy_score = sum([l1, l2, l3, l4, l5])

    regime_ok = float(adx.iloc[i]) >= ADX_MIN

    # Sell layers
    s1 = float(rsi.iloc[i]) > RSI_SELL
    s2 = float(macdhist.iloc[i]) < 0
    s3 = price > float(bb_upper.iloc[i])
    sell_score = sum([s1, s2, s3])

    # Decision — mirrors populate_entry_trend: score threshold AND all three
    # gates (ADX regime, daily EMA50 uptrend, daily EMA200 macro).
    gates_ok = regime_ok and htf["htf_ok"] and htf["macro_ok"]
    if gates_ok and buy_score >= MIN_BUY_SCORE:
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
        "htf": htf,
        "layers": {
            "trend(EMA50)": l1,
            f"rsi&lt;{RSI_BUY}": l2,
            "macd_up": l3,
            "below_BB": l4,
            "vol_spike": l5,
        },
    }


def format_message(pair: str, r: dict) -> str:
    emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}[r["decision"]]
    layers_str = "\n".join(
        f"  {'✅' if v else '▫️'} {k}" for k, v in r["layers"].items()
    )
    regime = "✅ trend present" if r["regime_ok"] else "⚠️ choppy (no-trade zone)"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    htf = r["htf"]
    if not htf["known"]:
        gates_str = "  ❔ daily gates: not enough 1d history to check"
    else:
        gates_str = (
            f"  {'✅' if htf['htf_ok'] else '⛔'} daily uptrend (close &gt; EMA50)\n"
            f"  {'✅' if htf['macro_ok'] else '⛔'} macro gate (close &gt; EMA200)"
        )

    msg = (
        f"{emoji} <b>{r['decision']}</b> — {pair} ({TIMEFRAME})\n"
        f"Price: {r['price']}\n"
        f"RSI: {r['rsi']} | ADX: {r['adx']} | MACD hist: {r['macdhist']}\n"
        f"Buy score: {r['buy_score']}/{N_LAYERS} | Sell score: {r['sell_score']}/3\n"
        f"Regime: {regime}\n"
        f"Daily gates:\n{gates_str}\n"
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


def make_exchange():
    """
    Build the ccxt client. An unknown exchange id is a config error that will
    never fix itself, so fail fast here rather than inside the retry loop.
    """
    try:
        klass = getattr(ccxt, EXCHANGE_ID)
    except AttributeError:
        raise SystemExit(
            f"Unknown exchange id '{EXCHANGE_ID}'. Set ADVISOR_EXCHANGE to a ccxt "
            f"exchange (e.g. kraken, binance)."
        )
    return klass({"enableRateLimit": True})


def run_once(notify_hold: bool = False) -> int:
    """
    Scan every pair once. Returns the number of pairs analyzed successfully.

    Never raises on a per-pair or all-pairs failure — the caller decides what a
    total failure means, because it means different things in the two modes:
    a one-shot run under a scheduler should exit non-zero, a long-running loop
    should log it and stay alive.
    """
    exchange = make_exchange()
    ok_count = 0
    for pair in PAIRS:
        pair = pair.strip()
        try:
            df = fetch_ohlcv(exchange, pair, TIMEFRAME, CANDLE_LIMIT)
            daily = fetch_ohlcv(exchange, pair, HTF_TIMEFRAME, HTF_CANDLE_LIMIT)
            r = analyze(df, analyze_htf(daily))
            ok_count += 1
            # By default only ping on actionable signals to avoid noise.
            if r["decision"] != "HOLD" or notify_hold:
                send_telegram(format_message(pair, r))
            else:
                print(
                    f"{pair}: HOLD (score {r['buy_score']}/{N_LAYERS}) — no alert sent"
                )
        except Exception as e:  # noqa: BLE001 — advisory tool, keep running
            print(f"[error analyzing {pair}] {e}")
    return ok_count


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
        if run_once(notify_hold=args.notify_hold) == 0:
            # Every pair failed (network outage, geo-block, exchange down).
            # Exit non-zero so schedulers (systemd, GitHub Actions) surface it
            # instead of reporting a silent green run.
            raise SystemExit(
                f"All {len(PAIRS)} pairs failed to analyze — see errors above."
            )
        return

    # loop mode
    make_exchange()  # fail fast on a bad exchange id, before entering the loop
    send_telegram(
        f"📡 Signal advisor started. Watching {', '.join(PAIRS)} on {TIMEFRAME}, "
        f"every {LOOP_MINUTES} min. Advisory only — no trades placed."
    )

    # A transient outage must not kill a long-running advisor — but a permanent
    # one must not be silent either, because "no alerts" is indistinguishable
    # from "no signals". So: keep running, and ping once when an outage looks
    # sustained, once more when it clears.
    failures = 0
    outage_reported = False
    while True:
        try:
            ok = run_once(notify_hold=args.notify_hold)
        except Exception as e:  # noqa: BLE001 — the loop must outlive any error
            print(f"[scan failed] {e}")
            ok = 0

        if ok == 0:
            failures += 1
            print(
                f"[outage] all {len(PAIRS)} pairs failed "
                f"({failures} consecutive scan(s)) — staying alive, retrying"
            )
            if failures >= OUTAGE_ALERT_AFTER and not outage_reported:
                send_telegram(
                    f"⚠️ Signal advisor: no pair has been readable for {failures} "
                    f"consecutive scans (~{failures * LOOP_MINUTES} min). Still "
                    f"running and retrying — but treat silence as unverified "
                    f"until this clears."
                )
                outage_reported = True
        else:
            if outage_reported:
                send_telegram("✅ Signal advisor: market data readable again.")
            failures = 0
            outage_reported = False

        time.sleep(LOOP_MINUTES * 60)


if __name__ == "__main__":
    main()
