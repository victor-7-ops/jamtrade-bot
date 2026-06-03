#!/usr/bin/env python3
"""
sentiment.py — Market-mood CONTEXT module (free, aggregated sources only).
==========================================================================

⚠️  PHILOSOPHY — READ THIS:
    Sentiment here is CONTEXT, never a trigger. This module does NOT tell you
    to buy or sell, and it deliberately does NOT follow any individual trader,
    influencer, or "buy now" tweet. Chasing individual social-media calls is a
    well-documented way to become someone else's exit liquidity.

    Instead, it summarizes the *aggregate crowd mood* from free, ToS-compliant
    sources, so you can SEE the emotional backdrop when you make your own call.

    The most useful read is often CONTRARIAN: extreme greed tends to cluster
    near tops, extreme fear near bottoms. So "the strategy says BUY and the
    crowd is fearful (not euphoric)" is a saner combination than buying into
    peak greed.

Sources (all free, no scraping, no paid API):
    - Crypto Fear & Greed Index  (alternative.me public API)
    - Google Trends search interest  (pytrends, optional)
    - CoinGecko community/market data  (public API, optional)

This module is imported by signal_advisor.py to append a context block to
alerts. It can also be run standalone to print the current mood:

    python scripts/sentiment.py
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import requests


# ── Tunables ───────────────────────────────────────────────────────────
HTTP_TIMEOUT = 12
# Map a coin symbol (from a pair like "BTC/USDT") to a CoinGecko id and a
# Google Trends search term. Extend as you add pairs.
COIN_MAP = {
    "BTC": {"cg_id": "bitcoin", "trend_term": "bitcoin"},
    "ETH": {"cg_id": "ethereum", "trend_term": "ethereum"},
    "SOL": {"cg_id": "solana", "trend_term": "solana"},
    "BNB": {"cg_id": "binancecoin", "trend_term": "bnb crypto"},
}


@dataclass
class Sentiment:
    """Aggregated, advisory-only market-mood snapshot."""

    fng_value: Optional[int] = None          # 0-100
    fng_label: Optional[str] = None          # e.g. "Fear"
    trend_direction: Optional[str] = None    # "rising" | "falling" | "flat"
    cg_price_change_24h: Optional[float] = None
    cg_sentiment_up_pct: Optional[float] = None  # community up-vote %
    notes: list[str] = field(default_factory=list)

    def contrarian_flag(self) -> Optional[str]:
        """A gentle contrarian caution based on Fear & Greed extremes."""
        if self.fng_value is None:
            return None
        if self.fng_value >= 75:
            return "⚠️ Extreme greed — crowds are euphoric; tops often form here."
        if self.fng_value <= 25:
            return "🧊 Extreme fear — crowds are scared; bottoms often form here."
        return None

    def as_message_block(self) -> str:
        """Render a compact context block for a Telegram alert."""
        lines = ["─────────────", "📊 <b>Market mood</b> (context only):"]

        if self.fng_value is not None:
            lines.append(f"  • Fear &amp; Greed: {self.fng_value} ({self.fng_label})")
        else:
            lines.append("  • Fear &amp; Greed: unavailable")

        if self.trend_direction:
            arrow = {"rising": "↗", "falling": "↘", "flat": "→"}.get(
                self.trend_direction, "→"
            )
            lines.append(f"  • Search interest: {arrow} {self.trend_direction}")

        if self.cg_price_change_24h is not None:
            sign = "+" if self.cg_price_change_24h >= 0 else ""
            lines.append(f"  • 24h price: {sign}{self.cg_price_change_24h:.1f}%")

        if self.cg_sentiment_up_pct is not None:
            lines.append(f"  • Community bullish: {self.cg_sentiment_up_pct:.0f}%")

        flag = self.contrarian_flag()
        if flag:
            lines.append(f"  {flag}")

        for n in self.notes:
            lines.append(f"  • {n}")

        lines.append("⚠️ Sentiment ≠ signal. It does NOT mean buy/sell.")
        return "\n".join(lines)


# ── Individual fetchers (each fails soft) ──────────────────────────────
def fetch_fear_greed() -> tuple[Optional[int], Optional[str]]:
    """Crypto Fear & Greed Index from alternative.me (free, no key)."""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()["data"][0]
        return int(data["value"]), str(data["value_classification"])
    except Exception:
        return None, None


def fetch_google_trend(term: str) -> Optional[str]:
    """
    Google Trends search-interest direction over the last week.
    Uses pytrends if installed; returns None if unavailable (it's optional).
    """
    try:
        from pytrends.request import TrendReq  # optional dependency
    except ImportError:
        return None
    try:
        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([term], timeframe="now 7-d")
        df = pytrends.interest_over_time()
        if df is None or df.empty or term not in df:
            return None
        series = df[term].dropna()
        if len(series) < 4:
            return None
        first_half = series.iloc[: len(series) // 2].mean()
        second_half = series.iloc[len(series) // 2 :].mean()
        delta = second_half - first_half
        if delta > 3:
            return "rising"
        if delta < -3:
            return "falling"
        return "flat"
    except Exception:
        return None


def fetch_coingecko(cg_id: str) -> tuple[Optional[float], Optional[float]]:
    """
    CoinGecko public API: 24h price change and community up-vote %.
    Free, no key. Fails soft.
    """
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        }
        r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        change = None
        try:
            change = float(
                data["market_data"]["price_change_percentage_24h"]
            )
        except (KeyError, TypeError):
            pass
        up_pct = None
        try:
            up_pct = float(data["sentiment_votes_up_percentage"])
        except (KeyError, TypeError):
            pass
        return change, up_pct
    except Exception:
        return None, None


# ── Public entry point ─────────────────────────────────────────────────
def get_sentiment(symbol: str, use_trends: bool = True) -> Sentiment:
    """
    Build a Sentiment snapshot for a coin symbol (e.g. "BTC").
    Every source fails soft — a missing source just omits that line.
    """
    s = Sentiment()
    mapping = COIN_MAP.get(symbol.upper(), {})

    # Fear & Greed is crypto-wide (not per coin)
    s.fng_value, s.fng_label = fetch_fear_greed()

    if mapping:
        change, up_pct = fetch_coingecko(mapping["cg_id"])
        s.cg_price_change_24h = change
        s.cg_sentiment_up_pct = up_pct

        if use_trends:
            s.trend_direction = fetch_google_trend(mapping["trend_term"])
    else:
        s.notes.append(f"No sentiment mapping for {symbol} (price-only).")

    return s


def _demo() -> None:
    for sym in ["BTC", "ETH"]:
        print(f"\n=== {sym} ===")
        snap = get_sentiment(sym)
        # Strip HTML tags for clean console output
        block = snap.as_message_block().replace("<b>", "").replace("</b>", "")
        block = block.replace("&amp;", "&")
        print(block)
        time.sleep(1)  # be polite to free APIs


if __name__ == "__main__":
    _demo()
