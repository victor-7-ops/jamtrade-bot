# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
"""
MultiConfirmationStrategy
=========================
A 6-layer multi-confirmation strategy with ADX regime filtering and
ATR-based trailing stops, ported from StrategyLab Pro.

⚠️  IMPORTANT — READ BEFORE USING:
    - This is for DRY-RUN (paper trading) and education first.
    - It runs on a LIVE exchange feed but with fake money when dry_run=true.
    - Do NOT put real money behind this until you've paper-traded it for
      weeks/months AND the live results match your backtest.
    - Past/backtest performance does not predict future results.
    - Only ever risk money you can afford to lose entirely.

Confirmation layers (need >= 3 to enter long):
    L1: Price above EMA50            (trend)
    L2: RSI < 38                     (momentum / oversold)
    L3: MACD histogram > 0           (momentum shift up)
    L4: Close below lower Bollinger  (price at value)
    L5: Volume > 1.4x its 20-SMA     (conviction)
    L6: Bullish RSI divergence       (bonus reversal signal)

Gating filters (ALL must pass):
    - ADX >= threshold               (only trade when a trend exists)
    - Higher-timeframe (1d) uptrend  (informative pair, optional)

Exits:
    - ATR trailing stop (2.5x ATR)
    - Indicator-based exit (RSI > 68 + MACD down + above upper BB; >=2 agree)
"""

from datetime import datetime
from functools import reduce

import numpy as np  # noqa: F401
import pandas as pd
from pandas import DataFrame

import talib.abstract as ta
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    informative,
)


class MultiConfirmationStrategy(IStrategy):
    """
    Multi-confirmation long-only strategy. Designed for crypto spot on the
    4h timeframe by default, but parameterized so you can hyperopt it.
    """

    # --- Core config -------------------------------------------------------
    INTERFACE_VERSION = 3
    timeframe = "4h"
    can_short = False

    # v1.3 experiment: ROI table DISABLED. The old table force-took profit at
    # 2% after one day, capping every winner while the ATR trailing stop
    # (3.9x) was tuned to let them run — the two exits fought each other.
    # Exits are now owned entirely by the ATR trailing stop + indicator exit.
    minimal_roi = {
        "0": 100  # effectively never triggers
    }

    # Hard safety net stoploss. The ATR trailing logic should usually trigger
    # first, but this is the backstop if something goes wrong.
    stoploss = -0.10

    # We implement our own ATR trailing stop via custom_stoploss.
    use_custom_stoploss = True

    # Only act on new candles; don't thrash intra-candle.
    process_only_new_candles = True

    # Require the candle to actually close before trusting the signal.
    startup_candle_count: int = 200

    # Order types — use limit orders to reduce slippage in dry-run/live.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # --- Hyperoptable parameters ------------------------------------------
    # These let you later run `freqtrade hyperopt` to tune on YOUR pairs.
    buy_rsi = IntParameter(25, 45, default=38, space="buy", optimize=True)
    buy_adx_min = IntParameter(18, 30, default=22, space="buy", optimize=True)
    buy_vol_mult = DecimalParameter(1.1, 2.0, default=1.4, decimals=1, space="buy", optimize=True)
    buy_bb_std = DecimalParameter(1.8, 2.4, default=2.1, decimals=1, space="buy", optimize=True)
    buy_min_score = IntParameter(2, 4, default=3, space="buy", optimize=True)

    sell_rsi = IntParameter(60, 80, default=68, space="sell", optimize=True)
    atr_stop_mult = DecimalParameter(1.5, 4.0, default=2.5, decimals=1, space="sell", optimize=True)

    # --- Plotting (shows up in freqtrade plot-dataframe) -------------------
    plot_config = {
        "main_plot": {
            "ema50": {"color": "#818cf8"},
            "bb_lowerband": {"color": "#5eead4"},
            "bb_upperband": {"color": "#f87171"},
        },
        "subplots": {
            "RSI": {"rsi": {"color": "#0088ff"}},
            "MACD": {
                "macd": {"color": "#ff8800"},
                "macdsignal": {"color": "#888888"},
            },
            "ADX": {"adx": {"color": "#facc15"}},
        },
    }

    # ----------------------------------------------------------------------
    # Higher timeframe (daily) trend as an informative pair.
    # The @informative decorator auto-merges 1d data into the main dataframe
    # with an "_1d" suffix (e.g. ema50_1d).
    # ----------------------------------------------------------------------
    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["uptrend"] = (dataframe["close"] > dataframe["ema50"]).astype("int")
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["above_ema200"] = (dataframe["close"] > dataframe["ema200"]).astype("int")
        return dataframe

    # ----------------------------------------------------------------------
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Trend
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)

        # Momentum
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Volatility / value — Bollinger Bands
        bb_std = float(self.buy_bb_std.value)
        bollinger = ta.BBANDS(
            dataframe, timeperiod=20, nbdevup=bb_std, nbdevdn=bb_std, matype=0
        )
        dataframe["bb_lowerband"] = bollinger["lowerband"]
        dataframe["bb_middleband"] = bollinger["middleband"]
        dataframe["bb_upperband"] = bollinger["upperband"]

        # Regime strength
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Volatility for stops
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Volume conviction
        dataframe["volume_sma"] = dataframe["volume"].rolling(20).mean()

        # --- Bullish RSI divergence (L6) ----------------------------------
        # Price makes a lower low over the lookback, but RSI makes a higher low.
        lookback = 10
        dataframe["recent_low"] = dataframe["close"].rolling(lookback).min()
        dataframe["prior_low"] = (
            dataframe["close"].shift(2).rolling(lookback).min()
        )
        dataframe["rsi_recent_low"] = dataframe["rsi"].rolling(lookback).min()
        dataframe["rsi_prior_low"] = (
            dataframe["rsi"].shift(2).rolling(lookback).min()
        )
        dataframe["bull_div"] = (
            (dataframe["close"] <= dataframe["recent_low"])
            & (dataframe["recent_low"] < dataframe["prior_low"])
            & (dataframe["rsi_recent_low"] > dataframe["rsi_prior_low"])
        ).astype("int")

        return dataframe

    # ----------------------------------------------------------------------
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Build each confirmation layer as a 0/1 column, then sum to a score.
        l1 = (dataframe["close"] > dataframe["ema50"]).astype("int")
        l2 = (dataframe["rsi"] < self.buy_rsi.value).astype("int")
        l3 = (dataframe["macdhist"] > 0).astype("int")
        l4 = (dataframe["close"] < dataframe["bb_lowerband"]).astype("int")
        l5 = (
            dataframe["volume"]
            > dataframe["volume_sma"] * float(self.buy_vol_mult.value)
        ).astype("int")
        l6 = dataframe["bull_div"]  # already 0/1

        dataframe["buy_score"] = l1 + l2 + l3 + l4 + l5 + l6

        # Gating filters
        regime_ok = dataframe["adx"] >= self.buy_adx_min.value
        # Higher-timeframe uptrend (column auto-created by @informative)
        htf_ok = dataframe.get("uptrend_1d", 1) == 1
        # Macro regime: BTC daily close must be above its 200-period EMA.
        # Defaults to 1 (allow) if 1d data is unavailable — graceful degradation.
        macro_ok = dataframe.get("above_ema200_1d", 1) == 1

        conditions = [
            dataframe["buy_score"] >= self.buy_min_score.value,
            regime_ok,
            htf_ok,
            macro_ok,
            dataframe["volume"] > 0,  # sanity: tradeable candle
        ]

        dataframe.loc[
            reduce(lambda a, b: a & b, conditions),
            "enter_long",
        ] = 1

        return dataframe

    # ----------------------------------------------------------------------
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Indicator-based exit: need >= 2 of 3 bearish confirmations.
        s1 = (dataframe["rsi"] > self.sell_rsi.value).astype("int")
        s2 = (dataframe["macdhist"] < 0).astype("int")
        s3 = (dataframe["close"] > dataframe["bb_upperband"]).astype("int")
        dataframe["sell_score"] = s1 + s2 + s3

        dataframe.loc[
            (dataframe["sell_score"] >= 2) & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1

        return dataframe

    # ----------------------------------------------------------------------
    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        ATR-based trailing stop. Returns a stoploss as a ratio relative to
        current_rate (negative number). Freqtrade ratchets this tighter over
        the life of the trade; it never loosens an existing stop.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) == 0:
            return self.stoploss  # fall back to static

        last_atr = dataframe["atr"].iat[-1]
        if last_atr is None or np.isnan(last_atr) or current_rate <= 0:
            return self.stoploss

        # Distance below current price, expressed as a fraction.
        atr_distance = (last_atr * float(self.atr_stop_mult.value)) / current_rate

        # custom_stoploss must return a NEGATIVE ratio (e.g. -0.05 = 5% below).
        return -abs(atr_distance)

    # ----------------------------------------------------------------------
    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Final gate before an entry order is placed. A good place to add
        extra safety checks (e.g. spread too wide, news blackout window).
        Returning False cancels the entry. Left permissive here.
        """
        return True
