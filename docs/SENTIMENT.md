# Sentiment Context Module

A market-mood add-on for your alerts. It appends a short "crowd mood" block to each
buy/hold/sell message so you can see the emotional backdrop when you decide.

## The one thing to understand

**This is context, not a signal.** It never tells you to buy or sell, and it deliberately
does **not** follow any individual trader, influencer, or "buy now" tweet. It summarizes the
*aggregate* mood from free, public, ToS-compliant sources.

Why it's built this way: chasing individual finfluencer calls is one of the most reliable
ways retail traders lose money. Big accounts often post "BUY" while selling into the crowd
they just excited (you become their exit liquidity). Survivorship bias makes the lucky look
like prophets. So this module gives you the *room temperature*, not a stranger's order.

The most useful read is often **contrarian**:
- Extreme **greed** (Fear & Greed ≥ 75) tends to cluster near **tops**
- Extreme **fear** (≤ 25) tends to cluster near **bottoms**

So "the strategy fired BUY and the crowd is fearful (not euphoric)" is a saner combination
than buying into peak greed.

## Sources (all free, no scraping, no paid API)

| Source | What it gives | Cost | Notes |
|--------|---------------|------|-------|
| Crypto Fear & Greed Index (alternative.me) | One 0–100 mood number | Free | Crypto-wide, no key |
| CoinGecko public API | 24h price change, community bullish % | Free | Per coin, no key |
| Google Trends (pytrends) | Search-interest direction | Free | Optional, can be flaky |

Every source **fails soft** — if one is down or missing, that line is simply omitted and the
alert still sends.

## What it looks like in an alert

```
🟢 BUY — BTC/USDT (4h)
Price: 64,320
RSI: 33.2 | ADX: 27.1 | MACD hist: 0.0042
Buy score: 4/6 | Sell score: 0/3
Regime: ✅ trend present
Layers:
  ✅ trend(EMA50)
  ✅ rsi<38
  ✅ macd_up
  ▫️ below_BB
  ✅ vol_spike
  ▫️ divergence
─────────────
📊 Market mood (context only):
  • Fear & Greed: 38 (Fear)
  • 24h price: -3.4%
  • Community bullish: 61%
⚠️ Sentiment ≠ signal. It does NOT mean buy/sell.
2026-06-03 08:00 UTC
⚠️ Advisory only. Check the chart yourself before acting.
```

Notice the sentiment sits *below* your real strategy signal and is clearly labelled. The
decision (BUY/HOLD/SELL) comes only from your 6-layer strategy — sentiment never changes it.

## Usage

**Standalone (see current mood):**
```bash
python scripts/sentiment.py
```

**In the advisor (automatic):** it's wired into `signal_advisor.py` already. Control it via
environment variables:

```bash
# Turn the sentiment block on/off (default on if module present)
export ADVISOR_SHOW_SENTIMENT=1

# Enable the Google Trends line (default off — adds latency, can be flaky)
export ADVISOR_SENTIMENT_TRENDS=0
```

## Adding more coins

Edit `COIN_MAP` at the top of `scripts/sentiment.py`:
```python
COIN_MAP = {
    "BTC": {"cg_id": "bitcoin", "trend_term": "bitcoin"},
    # add e.g.:
    "ADA": {"cg_id": "cardano", "trend_term": "cardano"},
}
```
Find a coin's CoinGecko id by visiting its CoinGecko page — the id is in the URL.

## Ideas for later (ask Claude Code)

- **Reddit mood**: the free Reddit API can give post volume / up-vote ratios from
  r/cryptocurrency or r/wallstreetbets as another aggregate gauge. Still context, not signal.
- **Sentiment as a soft filter**: e.g. *suppress* a BUY alert (or tag it "caution") when
  Fear & Greed is in extreme greed — a contrarian guardrail. Keep it advisory.
- **A small history log**: store the daily Fear & Greed value to chart mood vs. your
  strategy's entries over time.

## What this module will never do

- Follow or parrot a specific person's trade calls.
- Auto-execute anything based on social media.
- Treat a sentiment reading as a buy/sell trigger.

That restraint is the point. Sentiment widens your awareness; your strategy and your judgment
make the call.
