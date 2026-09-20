"""Freqtrade strategy using the local four-role roundtable engine."""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy
from user_data.roundtable.engine import evaluate


class RoundTableStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "15m"
    can_short = True
    process_only_new_candles = True
    startup_candle_count = 200
    minimal_roi = {"0": 0.02}
    stoploss = -0.01
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False

    def leverage(self, pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side, **kwargs):
        """Hard cap leverage at the project's phase-one limit."""
        return min(2.0, max_leverage)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_mid"] = bb["middleband"]
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        decisions = dataframe.apply(lambda row: evaluate(row) if row.notna().all() else None, axis=1)
        dataframe["roundtable_approved"] = decisions.map(lambda d: d.approved if d else False)
        dataframe["roundtable_direction"] = decisions.map(lambda d: d.direction if d else "pass")
        dataframe.loc[(dataframe["roundtable_approved"]) & (dataframe["roundtable_direction"] == "long"), "enter_long"] = 1
        dataframe.loc[(dataframe["roundtable_approved"]) & (dataframe["roundtable_direction"] == "short"), "enter_short"] = 1
        dataframe.loc[dataframe["volume"] <= 0, ["enter_long", "enter_short"]] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] > 70) | (dataframe["rsi"] < 30), "exit_long"] = 1
        dataframe.loc[(dataframe["rsi"] > 70) | (dataframe["rsi"] < 30), "exit_short"] = 1
        return dataframe
