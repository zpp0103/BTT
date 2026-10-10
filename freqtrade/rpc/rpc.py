"""
This module contains class to define a RPC communications
"""

import hashlib
import inspect
import json
import logging
from abc import abstractmethod
from collections.abc import Generator, Sequence
from datetime import UTC, date, datetime, timedelta
from math import ceil, isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zipfile import BadZipFile, ZipFile

import psutil
from dateutil.relativedelta import relativedelta
from dateutil.tz import tzlocal
from numpy import inf, isnan, mean, nan
from pandas import DataFrame, NaT, read_sql
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from freqtrade import __version__
from freqtrade.configuration.timerange import TimeRange
from freqtrade.constants import CANCEL_REASON, DEFAULT_DATAFRAME_COLUMNS, Config
from freqtrade.data.history import load_data
from freqtrade.data.metrics import (
    DrawDownResult,
    calculate_cagr,
    calculate_calmar,
    calculate_expectancy,
    calculate_max_drawdown,
    calculate_sharpe,
    calculate_sortino,
    calculate_sqn,
)
from freqtrade.enums import (
    CandleType,
    ExitCheckTuple,
    ExitType,
    MarketDirection,
    SignalDirection,
    State,
    TradingMode,
)
from freqtrade.exceptions import ExchangeError, OperationalException, PricingError
from freqtrade.exchange import Exchange, timeframe_to_minutes, timeframe_to_msecs
from freqtrade.exchange.exchange_utils import price_to_precision
from freqtrade.ft_types import AnnotationType
from freqtrade.loggers import bufferHandler
from freqtrade.misc import is_file_in_dir
from freqtrade.persistence import CustomDataWrapper, KeyValueStore, Order, PairLocks, Trade
from freqtrade.persistence.models import PairLock, custom_data_rpc_wrapper
from freqtrade.plugins.pairlist.pairlist_helpers import expand_pairlist
from freqtrade.rpc.fiat_convert import CryptoToFiatConverter
from freqtrade.rpc.rpc_types import RPCSendMsg
from freqtrade.util import (
    decimals_per_coin,
    dt_from_ts,
    dt_humanize_delta,
    dt_now,
    dt_ts,
    dt_ts_def,
    format_date,
    format_pct,
    shorten_date,
)
from freqtrade.wallets import PositionWallet, Wallet


logger = logging.getLogger(__name__)


class RPCException(Exception):
    """
    Should be raised with a rpc-formatted message in an _rpc_* method
    if the required state is wrong, i.e.:

    raise RPCException('*Status:* `no active trade`')
    """

    def __init__(self, message: str) -> None:
        super().__init__(self)
        self.message = message

    def __str__(self):
        return self.message

    def __json__(self):
        return {"msg": self.message}


class RPCHandler:
    def __init__(self, rpc: "RPC", config: Config) -> None:
        """
        Initializes RPCHandlers
        :param rpc: instance of RPC Helper class
        :param config: Configuration object
        :return: None
        """
        self._rpc = rpc
        self._config: Config = config

    @property
    def name(self) -> str:
        """Returns the lowercase name of the implementation"""
        return self.__class__.__name__.lower()

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup pending module resources"""

    @abstractmethod
    def send_msg(self, msg: RPCSendMsg) -> None:
        """Sends a message to all registered rpc modules"""


class RPC:
    """
    RPC class can be used to have extra feature, like bot data, and access to DB data
    """

    # Bind _fiat_converter if needed
    _fiat_converter: CryptoToFiatConverter | None = None
    if TYPE_CHECKING:
        from freqtrade.freqtradebot import FreqtradeBot

        _freqtrade: FreqtradeBot

    def __init__(self, freqtrade) -> None:
        """
        Initializes all enabled rpc modules
        :param freqtrade: Instance of a freqtrade bot
        :return: None
        """
        self._freqtrade = freqtrade
        self._config: Config = freqtrade.config
        if self._config.get("fiat_display_currency"):
            self._fiat_converter = CryptoToFiatConverter(self._config)

    @staticmethod
    def _rpc_show_config(
        config, botstate: State | str, strategy_version: str | None = None
    ) -> dict[str, Any]:
        """
        Return a dict of config options.
        Explicitly does NOT return the full config to avoid leakage of sensitive
        information via rpc.
        """
        val = {
            "version": __version__,
            "strategy_version": strategy_version,
            "dry_run": config["dry_run"],
            "trading_mode": config.get("trading_mode", "spot"),
            "margin_mode": config.get("margin_mode", ""),
            "short_allowed": config.get("trading_mode", "spot") != "spot",
            "stake_currency": config["stake_currency"],
            "stake_currency_decimals": decimals_per_coin(config["stake_currency"]),
            "stake_amount": str(config["stake_amount"]),
            "available_capital": config.get("available_capital"),
            "max_open_trades": (
                config.get("max_open_trades", 0)
                if config.get("max_open_trades", 0) != float("inf")
                else -1
            ),
            "minimal_roi": config["minimal_roi"].copy() if "minimal_roi" in config else {},
            "stoploss": config.get("stoploss"),
            "stoploss_on_exchange": config.get("order_types", {}).get(
                "stoploss_on_exchange", False
            ),
            "trailing_stop": config.get("trailing_stop"),
            "trailing_stop_positive": config.get("trailing_stop_positive"),
            "trailing_stop_positive_offset": config.get("trailing_stop_positive_offset"),
            "trailing_only_offset_is_reached": config.get("trailing_only_offset_is_reached"),
            "unfilledtimeout": config.get("unfilledtimeout"),
            "use_custom_stoploss": config.get("use_custom_stoploss"),
            "order_types": config.get("order_types"),
            "bot_name": config.get("bot_name", "freqtrade"),
            "timeframe": config.get("timeframe"),
            "timeframe_ms": timeframe_to_msecs(config["timeframe"]) if "timeframe" in config else 0,
            "timeframe_min": (
                timeframe_to_minutes(config["timeframe"]) if "timeframe" in config else 0
            ),
            "exchange": config["exchange"]["name"],
            "demo_trading": config["exchange"].get("demo_trading", False),
            "strategy": config["strategy"],
            "force_entry_enable": config.get("force_entry_enable", False),
            "exit_pricing": config.get("exit_pricing", {}),
            "entry_pricing": config.get("entry_pricing", {}),
            "state": str(botstate),
            "runmode": config["runmode"].value,
            "position_adjustment_enable": config.get("position_adjustment_enable", False),
            "max_entry_position_adjustment": (
                config.get("max_entry_position_adjustment", -1)
                if config.get("max_entry_position_adjustment") != float("inf")
                else -1
            ),
        }
        if config.get("trading_mode", "spot") == TradingMode.FUTURES and (
            proxy_coin := config.get("proxy_coin")
        ):
            val["proxy_coin"] = proxy_coin
        return val

    def _rpc_trade_status(self, trade_ids: list[int] | None = None) -> list[dict[str, Any]]:
        """
        Below follows the RPC backend it is prefixed with rpc_ to raise awareness that it is
        a remotely exposed function
        """
        # Fetch open trades
        if trade_ids:
            trades: Sequence[Trade] = Trade.get_trades(trade_filter=Trade.id.in_(trade_ids)).all()
        else:
            trades = Trade.get_open_trades()

        if not trades:
            raise RPCException("no active trade")
        else:
            results = []
            for trade in trades:
                current_profit_fiat: float | None = None
                total_profit_fiat: float | None = None

                # prepare open orders details
                oo_details: str | None = ""
                oo_details_lst = [
                    f"({oo.order_type} {oo.side} rem={oo.safe_remaining:.8f})"
                    for oo in trade.open_orders
                    if oo.ft_order_side not in ["stoploss"]
                ]
                oo_details = ", ".join(oo_details_lst)

                total_profit_abs = 0.0
                total_profit_ratio: float | None = None
                # calculate profit and send message to user
                if trade.is_open:
                    try:
                        current_rate: float = self._freqtrade.exchange.get_rate(
                            trade.pair, side="exit", is_short=trade.is_short, refresh=False
                        )
                    except (ExchangeError, PricingError):
                        current_rate = nan
                    if len(trade.select_filled_orders(trade.entry_side)) > 0:
                        current_profit = current_profit_abs = current_profit_fiat = nan
                        if not isnan(current_rate):
                            prof = trade.calculate_profit(current_rate)
                            current_profit = prof.profit_ratio
                            current_profit_abs = prof.profit_abs
                            total_profit_abs = prof.total_profit
                            total_profit_ratio = prof.total_profit_ratio
                    else:
                        current_profit = current_profit_abs = current_profit_fiat = 0.0

                else:
                    # Closed trade ...
                    current_rate = trade.close_rate or 0.0
                    current_profit = trade.close_profit or 0.0
                    current_profit_abs = trade.close_profit_abs or 0.0

                # Calculate fiat profit
                if not isnan(current_profit_abs) and self._fiat_converter:
                    current_profit_fiat = self._fiat_converter.convert_amount(
                        current_profit_abs,
                        self._freqtrade.config["stake_currency"],
                        self._freqtrade.config["fiat_display_currency"],
                    )
                    total_profit_fiat = self._fiat_converter.convert_amount(
                        total_profit_abs,
                        self._freqtrade.config["stake_currency"],
                        self._freqtrade.config["fiat_display_currency"],
                    )

                # Calculate guaranteed profit (in case of trailing stop)
                stop_entry = trade.calculate_profit(trade.stop_loss)

                stoploss_entry_dist = stop_entry.profit_abs
                stoploss_entry_dist_ratio = stop_entry.profit_ratio

                # calculate distance to stoploss
                stoploss_current_dist = price_to_precision(
                    trade.stop_loss - current_rate,
                    trade.price_precision,
                    trade.precision_mode_price,
                )
                stoploss_current_dist_ratio = stoploss_current_dist / current_rate

                trade_dict = trade.to_json()
                trade_dict.update(
                    {
                        "close_profit": trade.close_profit if not trade.is_open else None,
                        "current_rate": current_rate,
                        "profit_ratio": current_profit,
                        "profit_pct": round(current_profit * 100, 2),
                        "profit_abs": current_profit_abs,
                        "profit_fiat": current_profit_fiat,
                        "total_profit_abs": total_profit_abs,
                        "total_profit_fiat": total_profit_fiat,
                        "total_profit_ratio": total_profit_ratio,
                        "stoploss_current_dist": stoploss_current_dist,
                        "stoploss_current_dist_ratio": round(stoploss_current_dist_ratio, 8),
                        "stoploss_current_dist_pct": round(stoploss_current_dist_ratio * 100, 2),
                        "stoploss_entry_dist": stoploss_entry_dist,
                        "stoploss_entry_dist_ratio": round(stoploss_entry_dist_ratio, 8),
                        "open_orders": oo_details,
                        "nr_of_successful_entries": trade.nr_of_successful_entries,
                    }
                )
                results.append(trade_dict)
            return results

    def _rpc_status_table(
        self, stake_currency: str, fiat_display_currency: str
    ) -> tuple[list, list, float, float]:
        """
        :return: list of trades, list of columns, sum of fiat profit
        """
        nonspot = self._config.get("trading_mode", TradingMode.SPOT) != TradingMode.SPOT
        if not Trade.get_open_trades():
            raise RPCException("no active trade")

        trades_list = []
        fiat_profit_sum = nan
        fiat_total_profit_sum = nan
        for trade in self._rpc_trade_status():
            # Format profit as a string with the right sign
            profit = f"{format_pct(trade['profit_ratio'])}"
            fiat_profit = trade.get("profit_fiat", None)
            if fiat_profit is None or isnan(fiat_profit):
                fiat_profit = trade.get("profit_abs", 0.0)
            if not isnan(fiat_profit):
                profit += f" ({fiat_profit:.2f})"
                fiat_profit_sum = (
                    fiat_profit if isnan(fiat_profit_sum) else fiat_profit_sum + fiat_profit
                )
            total_profit = trade.get("total_profit_fiat", None)
            if total_profit is None or isnan(total_profit):
                total_profit = trade.get("total_profit_abs", 0.0)
            if not isnan(total_profit):
                fiat_total_profit_sum = (
                    total_profit
                    if isnan(fiat_total_profit_sum)
                    else fiat_total_profit_sum + total_profit
                )

            # Format the active order side symbols
            active_order_side = ""
            orders = trade.get("orders", [])
            if orders:
                active_order_side = ".".join(
                    "*" if (o.get("is_open") and o.get("ft_is_entry")) else "**"
                    for o in orders
                    if o.get("is_open") and o.get("ft_order_side") != "stoploss"
                )

            # Direction string for non-spot
            direction_str = ""
            if nonspot:
                leverage = trade.get("leverage", 1.0)
                direction_str = f"{'S' if trade.get('is_short') else 'L'} {leverage:.3g}x"

            detail_trade = [
                f"{trade['trade_id']} {direction_str}",
                f"{trade['pair']}{active_order_side}",
                shorten_date(dt_humanize_delta(dt_from_ts(trade["open_timestamp"]))),
                profit,
            ]

            # Add number of entries if position adjustment is enabled
            if self._config.get("position_adjustment_enable", False):
                max_entry_str = ""
                if self._config.get("max_entry_position_adjustment", -1) > 0:
                    max_entry_str = f"/{self._config['max_entry_position_adjustment'] + 1}"
                filled_entries = trade.get("nr_of_successful_entries", 0)
                detail_trade.append(f"{filled_entries}{max_entry_str}")

            trades_list.append(detail_trade)

        columns = [
            "ID L/S" if nonspot else "ID",
            "Pair",
            "Since",
            f"Profit ({fiat_display_currency if self._fiat_converter else stake_currency})",
        ]

        if self._config.get("position_adjustment_enable", False):
            columns.append("# Entries")

        return trades_list, columns, fiat_profit_sum, fiat_total_profit_sum

    def _rpc_timeunit_profit(
        self,
        timescale: int,
        stake_currency: str,
        fiat_display_currency: str,
        timeunit: str = "days",
    ) -> dict[str, Any]:
        """
        :param timeunit: Valid entries are 'days', 'weeks', 'months'
        """
        start_date = datetime.now(UTC).date()
        if timeunit == "weeks":
            # weekly
            start_date = start_date - timedelta(days=start_date.weekday())  # Monday
        if timeunit == "months":
            start_date = start_date.replace(day=1)

        def time_offset(step: int):
            if timeunit == "months":
                return relativedelta(months=step)
            return timedelta(**{timeunit: step})

        if not (isinstance(timescale, int) and timescale > 0):
            raise RPCException("timescale must be an integer greater than 0")

        profit_units: dict[date, dict] = {}
        daily_stake = self._freqtrade.wallets.get_total_stake_amount()

        for day in range(timescale):
            profitday = start_date - time_offset(day)
            # Only query for necessary columns for performance reasons.
            trades = Trade.session.execute(
                select(Trade.close_profit_abs)
                .filter(
                    Trade.is_open.is_(False),
                    Trade.close_date >= profitday,
                    Trade.close_date < (profitday + time_offset(1)),
                )
                .order_by(Trade.close_date)
            ).all()

            curdayprofit = sum(
                trade.close_profit_abs for trade in trades if trade.close_profit_abs is not None
            )
            # Calculate this periods starting balance
            daily_stake = daily_stake - curdayprofit
            profit_units[profitday] = {
                "amount": curdayprofit,
                "daily_stake": daily_stake,
                "rel_profit": round(curdayprofit / daily_stake, 8) if daily_stake > 0 else 0,
                "trades": len(trades),
            }

        data = [
            {
                "date": key,
                "abs_profit": value["amount"],
                "starting_balance": value["daily_stake"],
                "rel_profit": value["rel_profit"],
                "fiat_value": (
                    self._fiat_converter.convert_amount(
                        value["amount"], stake_currency, fiat_display_currency
                    )
                    if self._fiat_converter
                    else 0
                ),
                "trade_count": value["trades"],
            }
            for key, value in profit_units.items()
        ]
        return {
            "stake_currency": stake_currency,
            "fiat_display_currency": fiat_display_currency,
            "data": data,
        }

    def _rpc_trade_history(self, limit: int, offset: int = 0, order_by_id: bool = False) -> dict:
        """Returns the X last trades"""
        order_by: Any = Trade.id if order_by_id else Trade.close_date.desc()
        if limit:
            trades = Trade.session.scalars(
                Trade.get_trades_query([Trade.is_open.is_(False)])
                .order_by(order_by)
                .limit(limit)
                .offset(offset)
            )
        else:
            trades = Trade.session.scalars(
                Trade.get_trades_query([Trade.is_open.is_(False)]).order_by(Trade.close_date.desc())
            )

        output = [trade.to_json() for trade in trades]
        total_trades = Trade.session.scalar(
            select(func.count(Trade.id)).filter(Trade.is_open.is_(False))
        )

        return {
            "trades": output,
            "trades_count": len(output),
            "offset": offset,
            "total_trades": total_trades,
        }

    def _rpc_stats(self) -> dict[str, Any]:
        """
        Generate generic stats for trades in database
        """

        def trade_win_loss(trade):
            if trade.close_profit > 0:
                return "wins"
            elif trade.close_profit < 0:
                return "losses"
            else:
                return "draws"

        trades = Trade.get_trades([Trade.is_open.is_(False)], include_orders=False)
        # Duration
        dur: dict[str, list[float]] = {"wins": [], "draws": [], "losses": []}
        # Exit reason
        exit_reasons = {}
        for trade in trades:
            if trade.exit_reason not in exit_reasons:
                exit_reasons[trade.exit_reason] = {"wins": 0, "losses": 0, "draws": 0}
            exit_reasons[trade.exit_reason][trade_win_loss(trade)] += 1

            if trade.close_date is not None and trade.open_date is not None:
                trade_dur = (trade.close_date - trade.open_date).total_seconds()
                dur[trade_win_loss(trade)].append(trade_dur)

        wins_dur = sum(dur["wins"]) / len(dur["wins"]) if len(dur["wins"]) > 0 else None
        draws_dur = sum(dur["draws"]) / len(dur["draws"]) if len(dur["draws"]) > 0 else None
        losses_dur = sum(dur["losses"]) / len(dur["losses"]) if len(dur["losses"]) > 0 else None

        durations = {"wins": wins_dur, "draws": draws_dur, "losses": losses_dur}
        return {"exit_reasons": exit_reasons, "durations": durations}

    def _collect_trade_statistics_data(
        self,
        trades: Sequence["Trade"],
        stake_currency: str,
        fiat_display_currency: str,
    ) -> dict[str, Any]:
        """Iterate trades, calculate various statistics, and return intermediate results."""
        profit_all_coin = []
        profit_all_ratio = []
        profit_closed_coin = []
        profit_closed_ratio = []
        durations = []
        winning_trades = 0
        losing_trades = 0
        winning_profit = 0.0
        losing_profit = 0.0

        for trade in trades:
            current_rate: float = 0.0

            if trade.close_date:
                durations.append((trade.close_date - trade.open_date).total_seconds())

            if not trade.is_open:
                profit_ratio = trade.close_profit or 0.0
                profit_abs = trade.close_profit_abs or 0.0
                profit_closed_coin.append(profit_abs)
                profit_closed_ratio.append(profit_ratio)
                if profit_ratio >= 0:
                    winning_trades += 1
                    winning_profit += profit_abs
                else:
                    losing_trades += 1
                    losing_profit += profit_abs
            else:
                # Get current rate for open trades
                if len(trade.select_filled_orders(trade.entry_side)) == 0:
                    # Skip trades with no filled orders
                    continue
                try:
                    current_rate = self._freqtrade.exchange.get_rate(
                        trade.pair, side="exit", is_short=trade.is_short, refresh=False
                    )
                except (PricingError, ExchangeError):
                    current_rate = nan
                    profit_ratio = nan
                    profit_abs = nan
                else:
                    _profit = trade.calculate_profit(trade.close_rate or current_rate)
                    profit_ratio = _profit.profit_ratio
                    profit_abs = _profit.total_profit

            profit_all_coin.append(profit_abs)
            profit_all_ratio.append(profit_ratio)

        return {
            "profit_all_coin": profit_all_coin,
            "profit_all_ratio": profit_all_ratio,
            "profit_closed_coin": profit_closed_coin,
            "profit_closed_ratio": profit_closed_ratio,
            "durations": durations,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "winning_profit": winning_profit,
            "losing_profit": losing_profit,
        }

    def _rpc_trade_statistics(
        self,
        stake_currency: str,
        fiat_display_currency: str,
        start_date: datetime | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        """
        Returns cumulative profit statistics, with optional direction filter (long/short)
        """
        start_date = dt_from_ts(0) if start_date is None else start_date

        trade_filter = (
            Trade.is_open.is_(False) & (Trade.close_date >= start_date)
        ) | Trade.is_open.is_(True)

        if direction == "long":
            dir_filter = Trade.is_short.is_(False)
            trade_filter = trade_filter & dir_filter
        elif direction == "short":
            dir_filter = Trade.is_short.is_(True)
            trade_filter = trade_filter & dir_filter

        trades: Sequence[Trade] = Trade.session.scalars(
            Trade.get_trades_query(trade_filter, include_orders=False).order_by(Trade.id)
        ).all()

        stats = self._collect_trade_statistics_data(trades, stake_currency, fiat_display_currency)

        profit_all_coin = stats["profit_all_coin"]
        profit_all_ratio = stats["profit_all_ratio"]
        profit_closed_coin = stats["profit_closed_coin"]
        profit_closed_ratio = stats["profit_closed_ratio"]
        durations = stats["durations"]
        winning_trades = stats["winning_trades"]
        losing_trades = stats["losing_trades"]
        winning_profit = stats["winning_profit"]
        losing_profit = stats["losing_profit"]

        closed_trade_count = len([t for t in trades if not t.is_open])

        best_pair_filters = [Trade.close_date > start_date]
        trading_volume_filters = [Order.order_filled_date >= start_date]

        if direction:
            best_pair_filters.append(dir_filter)
            trading_volume_filters.append(dir_filter)

        best_pair = Trade.get_best_pair(best_pair_filters)
        trading_volume = Trade.get_trading_volume(trading_volume_filters)

        # Prepare data to display
        profit_closed_coin_sum = round(sum(profit_closed_coin), 8)
        profit_closed_ratio_mean = float(mean(profit_closed_ratio) if profit_closed_ratio else 0.0)
        profit_closed_ratio_sum = sum(profit_closed_ratio) if profit_closed_ratio else 0.0

        profit_closed_fiat = (
            self._fiat_converter.convert_amount(
                profit_closed_coin_sum, stake_currency, fiat_display_currency
            )
            if self._fiat_converter
            else 0
        )

        profit_all_coin_sum = round(sum(profit_all_coin), 8)
        profit_all_ratio_mean = float(mean(profit_all_ratio) if profit_all_ratio else 0.0)
        # Doing the sum is not right - overall profit needs to be based on initial capital
        profit_all_ratio_sum = sum(profit_all_ratio) if profit_all_ratio else 0.0
        starting_balance = self._freqtrade.wallets.get_starting_balance()
        profit_closed_ratio_fromstart = 0.0
        profit_all_ratio_fromstart = 0.0
        if starting_balance:
            profit_closed_ratio_fromstart = profit_closed_coin_sum / starting_balance
            profit_all_ratio_fromstart = profit_all_coin_sum / starting_balance

        profit_factor = winning_profit / abs(losing_profit) if losing_profit else float("inf")

        winrate = (winning_trades / closed_trade_count) if closed_trade_count > 0 else 0

        trades_df = DataFrame(
            [
                {
                    "close_date": format_date(trade.close_date),
                    "close_date_dt": trade.close_date,
                    "profit_abs": trade.close_profit_abs,
                }
                for trade in trades
                if not trade.is_open and trade.close_date
            ]
        )

        expectancy, expectancy_ratio = calculate_expectancy(trades_df)

        drawdown = DrawDownResult()
        if len(trades_df) > 0:
            try:
                drawdown = calculate_max_drawdown(
                    trades_df,
                    value_col="profit_abs",
                    date_col="close_date_dt",
                    starting_balance=starting_balance,
                )
            except ValueError:
                # ValueError if no losing trade.
                pass

        profit_all_fiat = (
            self._fiat_converter.convert_amount(
                profit_all_coin_sum, stake_currency, fiat_display_currency
            )
            if self._fiat_converter
            else 0
        )

        first_date = trades[0].open_date_utc if trades else None
        last_date = trades[-1].open_date_utc if trades else None
        num = float(len(durations) or 1)
        bot_start = KeyValueStore.get_datetime_value("bot_start_time")

        sharpe = calculate_sharpe(
            trades=trades_df,
            min_date=first_date,
            max_date=last_date,
            starting_balance=starting_balance,
        )
        sortino = calculate_sortino(
            trades=trades_df,
            min_date=first_date,
            max_date=last_date,
            starting_balance=starting_balance,
        )
        sqn = calculate_sqn(trades=trades_df, starting_balance=starting_balance)
        calmar = calculate_calmar(
            trades=trades_df,
            min_date=first_date,
            max_date=last_date,
            starting_balance=starting_balance,
        )
        current_balance = self._freqtrade.wallets.get_total_stake_amount()
        days_passed = max(1, (last_date - first_date).days) if first_date and last_date else 1
        cagr = calculate_cagr(
            starting_balance=starting_balance,
            final_balance=current_balance,
            days_passed=days_passed,
        )

        return {
            "profit_closed_coin": profit_closed_coin_sum,
            "profit_closed_percent_mean": round(profit_closed_ratio_mean * 100, 2),
            "profit_closed_ratio_mean": profit_closed_ratio_mean,
            "profit_closed_percent_sum": round(profit_closed_ratio_sum * 100, 2),
            "profit_closed_ratio_sum": profit_closed_ratio_sum,
            "profit_closed_ratio": profit_closed_ratio_fromstart,
            "profit_closed_percent": round(profit_closed_ratio_fromstart * 100, 2),
            "profit_closed_fiat": profit_closed_fiat,
            "profit_all_coin": profit_all_coin_sum,
            "profit_all_percent_mean": round(profit_all_ratio_mean * 100, 2),
            "profit_all_ratio_mean": profit_all_ratio_mean,
            "profit_all_percent_sum": round(profit_all_ratio_sum * 100, 2),
            "profit_all_ratio_sum": profit_all_ratio_sum,
            "profit_all_ratio": profit_all_ratio_fromstart,
            "profit_all_percent": round(profit_all_ratio_fromstart * 100, 2),
            "profit_all_fiat": profit_all_fiat,
            "trade_count": len(trades),
            "closed_trade_count": closed_trade_count,
            "first_trade_date": format_date(first_date),
            "first_trade_humanized": dt_humanize_delta(first_date) if first_date else "",
            "first_trade_timestamp": dt_ts_def(first_date, 0),
            "latest_trade_date": format_date(last_date),
            "latest_trade_humanized": dt_humanize_delta(last_date) if last_date else "",
            "latest_trade_timestamp": dt_ts_def(last_date, 0),
            "avg_duration": str(timedelta(seconds=sum(durations) / num)).split(".")[0],
            "best_pair": best_pair[0] if best_pair else "",
            "best_rate": round(best_pair[1] * 100, 2) if best_pair else 0,  # Deprecated
            "best_pair_profit_ratio": best_pair[1] if best_pair else 0,
            "best_pair_profit_abs": best_pair[2] if best_pair else 0,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "profit_factor": profit_factor,
            "winrate": winrate,
            "expectancy": expectancy,
            "expectancy_ratio": expectancy_ratio,
            "sharpe": sharpe,
            "sortino": sortino,
            "sqn": sqn,
            "calmar": calmar,
            "cagr": cagr,
            "max_drawdown": drawdown.relative_account_drawdown,
            "max_drawdown_abs": drawdown.drawdown_abs,
            "max_drawdown_start": format_date(drawdown.high_date),
            "max_drawdown_start_timestamp": dt_ts_def(drawdown.high_date),
            "max_drawdown_end": format_date(drawdown.low_date),
            "max_drawdown_end_timestamp": dt_ts_def(drawdown.low_date),
            "drawdown_high": drawdown.high_value,
            "drawdown_low": drawdown.low_value,
            "current_drawdown": drawdown.current_relative_account_drawdown,
            "current_drawdown_abs": drawdown.current_drawdown_abs,
            "current_drawdown_high": drawdown.current_high_value,
            "current_drawdown_start": format_date(drawdown.current_high_date),
            "current_drawdown_start_timestamp": dt_ts_def(drawdown.current_high_date),
            "trading_volume": trading_volume,
            "bot_start_timestamp": dt_ts_def(bot_start, 0),
            "bot_start_date": format_date(bot_start),
        }

    def _rpc_get_historic_balance(self) -> tuple[DataFrame, int]:
        """
        Returns the historic balance of the bot
        :return: DataFrame with the balance history and the timestamp of the migration
        """
        results = read_sql("wallet_history", con=Trade.session.bind, parse_dates=["timestamp"])

        results = results.rename({"timestamp": "date"}, axis=1)
        results.loc[:, "__date_ts"] = results.loc[:, "date"].dt.as_unit("ms").astype("int64")
        # Exclude non-bot managed for now
        results_filtered = results.loc[results["bot_managed"].astype(bool)]

        results_final = (
            results_filtered.groupby(["date", "__date_ts"])
            .agg({"total_quote": "sum"})
            .reset_index()
        )
        hist = KeyValueStore.get_datetime_value("wallet_history_migration_date")
        return results_final, dt_ts_def(hist, 0)

    def __balance_get_est_stake(
        self, coin: str, stake_currency: str, amount: float, balance: Wallet
    ) -> tuple[float, float]:
        est_stake = 0.0
        est_bot_stake = 0.0
        is_futures = self._config.get("trading_mode", TradingMode.SPOT) == TradingMode.FUTURES
        if coin == self._freqtrade.exchange.get_proxy_coin():
            est_stake = balance.total
            if is_futures:
                # in Futures, "total" includes the locked stake, and therefore all positions
                est_stake = balance.free
            est_bot_stake = amount
        else:
            try:
                rate: float | None = self._freqtrade.exchange.get_conversion_rate(
                    coin, stake_currency
                )
                if rate:
                    est_stake = rate * (balance.free if is_futures else balance.total)
                    est_bot_stake = rate * amount

                return est_stake, est_bot_stake
            except (ExchangeError, PricingError) as e:
                logger.warning(f"Error {e} getting rate for {coin}")
        return est_stake, est_bot_stake

    def _rpc_balance(self, stake_currency: str, fiat_display_currency: str) -> dict:
        """Returns current account balance per crypto"""
        currencies: list[dict] = []
        total = 0.0
        total_bot = 0.0

        open_trades: list[Trade] = Trade.get_open_trades()
        open_assets: dict[str, Trade] = {t.safe_base_currency: t for t in open_trades}
        self._freqtrade.wallets.update(require_update=False)
        starting_capital = self._freqtrade.wallets.get_starting_balance()
        starting_cap_fiat = (
            self._fiat_converter.convert_amount(
                starting_capital, stake_currency, fiat_display_currency
            )
            if self._fiat_converter
            else 0
        )
        coin: str
        balance: Wallet
        for coin, balance in self._freqtrade.wallets.get_all_balances().items():
            if not balance.total and not balance.free:
                continue

            trade = (
                open_assets.get(coin, None)
                if self._freqtrade.trading_mode != TradingMode.FUTURES
                else None
            )
            is_stake_currency = coin == self._freqtrade.exchange.get_proxy_coin()
            is_bot_managed = is_stake_currency or trade is not None
            trade_amount = trade.amount if trade else 0
            if is_stake_currency:
                trade_amount = self._freqtrade.wallets.get_available_stake_amount()

            est_stake, est_stake_bot = self.__balance_get_est_stake(
                coin, stake_currency, trade_amount, balance
            )

            total += est_stake

            if is_bot_managed:
                total_bot += est_stake_bot
            currencies.append(
                {
                    "currency": coin,
                    "free": balance.free,
                    "balance": balance.total,
                    "used": balance.used,
                    "bot_owned": trade_amount,
                    "est_stake": est_stake or 0,
                    "est_stake_bot": est_stake_bot if is_bot_managed else 0,
                    "stake": stake_currency,
                    "side": "long",
                    "position": 0,
                    "is_bot_managed": is_bot_managed,
                    "is_position": False,
                }
            )
        symbol: str
        pos: PositionWallet
        for symbol, pos in self._freqtrade.wallets.get_all_positions().items():
            est_stake = pos.collateral
            pos_base = self._freqtrade.exchange.get_pair_base_currency(symbol)
            if pos.leverage and pos.position:
                try:
                    rate = self._freqtrade.exchange.get_conversion_rate(pos_base, stake_currency)
                    if rate:
                        # For a leveraged position, equity (what we want as est_stake) is:
                        #   equity = collateral + unlevered PnL
                        # For longs: unlevered PnL = current_value - open_value
                        #   est_stake = rate * pos.position - pos.collateral * (pos.leverage - 1)
                        # For shorts: unlevered PnL = open_value - current_value
                        #   est_stake = collateral + (open_value - current_value)
                        #            = collateral + (pos.collateral * pos.leverage)
                        #              - rate * pos.position
                        if pos.side == "long":
                            est_stake = rate * pos.position - pos.collateral * (pos.leverage - 1)
                        else:
                            est_stake = pos.collateral * (1 + pos.leverage) - rate * pos.position
                except (ExchangeError, PricingError) as e:
                    logger.warning(f"Error {e} getting rate for futures {symbol} / {pos_base}")

            # Add the estimated stake (collateral + unlevered PnL) to totals
            total += est_stake
            total_bot += est_stake

            currencies.append(
                {
                    "currency": symbol,
                    "free": 0,
                    "balance": 0,
                    "used": 0,
                    "position": pos.position,
                    "est_stake": est_stake,
                    "est_stake_bot": est_stake,
                    "stake": stake_currency,
                    "side": pos.side,
                    "is_bot_managed": pos_base in open_assets,
                    "is_position": True,
                }
            )

        value = (
            self._fiat_converter.convert_amount(total, stake_currency, fiat_display_currency)
            if self._fiat_converter
            else 0
        )
        value_bot = (
            self._fiat_converter.convert_amount(total_bot, stake_currency, fiat_display_currency)
            if self._fiat_converter
            else 0
        )

        trade_count = len(Trade.get_trades_proxy())
        starting_capital_ratio = (total_bot / starting_capital) - 1 if starting_capital else 0.0
        starting_cap_fiat_ratio = (value_bot / starting_cap_fiat) - 1 if starting_cap_fiat else 0.0

        return {
            "currencies": currencies,
            "total": total,
            "total_bot": total_bot,
            "symbol": fiat_display_currency,
            "value": value,
            "value_bot": value_bot,
            "stake": stake_currency,
            "starting_capital": starting_capital,
            "starting_capital_ratio": starting_capital_ratio,
            "starting_capital_pct": round(starting_capital_ratio * 100, 2),
            "starting_capital_fiat": starting_cap_fiat,
            "starting_capital_fiat_ratio": starting_cap_fiat_ratio,
            "starting_capital_fiat_pct": round(starting_cap_fiat_ratio * 100, 2),
            "trade_count": trade_count,
            "note": "Simulated balances" if self._freqtrade.config["dry_run"] else "",
        }

    def _rpc_start(self) -> dict[str, str]:
        """Handler for start"""
        if self._freqtrade.state == State.RUNNING:
            return {"status": "already running"}

        self._freqtrade.state = State.RUNNING
        return {"status": "starting trader ..."}

    def _rpc_stop(self) -> dict[str, str]:
        """Handler for stop"""
        if self._freqtrade.state != State.STOPPED:
            self._freqtrade.state = State.STOPPED
            return {"status": "stopping trader ..."}

        return {"status": "already stopped"}

    def _rpc_reload_config(self) -> dict[str, str]:
        """Handler for reload_config."""
        self._freqtrade.state = State.RELOAD_CONFIG
        return {"status": "Reloading config ..."}

    def _rpc_pause(self) -> dict[str, str]:
        """
        Handler to pause trading (stop entering new trades), but handle open trades gracefully.
        """
        if self._freqtrade.state == State.RUNNING:
            self._freqtrade.state = State.PAUSED

        if self._freqtrade.state == State.STOPPED:
            self._freqtrade.state = State.PAUSED
            return {
                "status": (
                    "starting bot with trader in paused state, no entries will occur. "
                    "Run /start to enable entries."
                )
            }

        return {
            "status": "paused, no more entries will occur from now. Run /start to enable entries."
        }

    def _rpc_reload_trade_from_exchange(self, trade_id: int) -> dict[str, str]:
        """
        Handler for reload_trade_from_exchange.
        Reloads a trade from it's orders, should manual interaction have happened.
        """
        trade = Trade.get_trades(trade_filter=[Trade.id == trade_id]).first()
        if not trade:
            raise RPCException(f"Could not find trade with id {trade_id}.")

        self._freqtrade.handle_onexchange_order(trade)
        return {"status": "Reloaded from orders from exchange"}

    def __exec_force_exit(
        self,
        trade: Trade,
        ordertype: str | None,
        amount: float | None = None,
        price: float | None = None,
    ) -> bool:
        # Check if there is there are open orders
        trade_entry_cancelation_registry = []
        for oo in trade.open_orders:
            trade_entry_cancelation_res = {"order_id": oo.order_id, "cancel_state": False}
            order = self._freqtrade.exchange.fetch_order(oo.order_id, trade.pair)

            if order["side"] == trade.entry_side:
                fully_canceled = self._freqtrade.handle_cancel_enter(
                    trade, order, oo, CANCEL_REASON["FORCE_EXIT"]
                )
                trade_entry_cancelation_res["cancel_state"] = fully_canceled
                trade_entry_cancelation_registry.append(trade_entry_cancelation_res)

            if order["side"] == trade.exit_side:
                # Cancel order - so it is placed anew with a fresh price.
                self._freqtrade.handle_cancel_exit(trade, order, oo, CANCEL_REASON["FORCE_EXIT"])

        if all(tocr["cancel_state"] is False for tocr in trade_entry_cancelation_registry):
            if trade.has_open_orders:
                # Order cancellation failed, so we can't exit.
                return False
            # Get current rate and execute sell

            current_rate = (
                self._freqtrade.exchange.get_rate(
                    trade.pair, side="exit", is_short=trade.is_short, refresh=True
                )
                if ordertype == "market" or price is None
                else price
            )
            exit_check = ExitCheckTuple(exit_type=ExitType.FORCE_EXIT)
            order_type = ordertype or self._freqtrade.strategy.order_types.get(
                "force_exit", self._freqtrade.strategy.order_types["exit"]
            )
            sub_amount: float | None = None
            if amount and amount < trade.amount:
                # Partial exit ...
                min_exit_stake = self._freqtrade.exchange.get_min_pair_stake_amount(
                    trade.pair, current_rate, trade.stop_loss_pct or 0.0
                )
                remaining = (trade.amount - amount) * current_rate
                if min_exit_stake and remaining < min_exit_stake:
                    raise RPCException(f"Remaining amount of {remaining} would be too small.")
                sub_amount = amount

            self._freqtrade.execute_trade_exit(
                trade,
                current_rate,
                exit_check,
                ordertype=order_type,
                sub_trade_amt=sub_amount,
                skip_custom_exit_price=price is not None and ordertype == "limit",
            )

            return True
        return False

    def _rpc_force_exit(
        self,
        trade_id: str,
        ordertype: str | None = None,
        *,
        amount: float | None = None,
        price: float | None = None,
    ) -> dict[str, str]:
        """
        Handler for forceexit <id>.
        exits the given trade. Uses current price if price is None.
        """

        if self._freqtrade.state == State.STOPPED:
            raise RPCException("trader is not running")

        with self._freqtrade._exit_lock:
            if trade_id == "all":
                # Execute exit for all open orders
                for trade in Trade.get_open_trades():
                    self.__exec_force_exit(trade, ordertype)
                Trade.commit()
                self._freqtrade.wallets.update()
                return {"result": "Created exit orders for all open trades."}

            # Query for trade
            trade = (
                Trade.get_trades(
                    trade_filter=[
                        Trade.id == int(trade_id),
                        Trade.is_open.is_(True),
                    ]
                ).first()
                if trade_id.isdigit()
                else None
            )
            if not trade:
                logger.warning("force_exit: Invalid argument received")
                raise RPCException("invalid argument")

            result = self.__exec_force_exit(trade, ordertype, amount, price)
            Trade.commit()
            self._freqtrade.wallets.update()
            if not result:
                raise RPCException("Failed to exit trade.")
            return {"result": f"Created exit order for trade {trade_id}."}

    def _force_entry_validations(self, pair: str, order_side: SignalDirection):
        if not self._freqtrade.config.get("force_entry_enable", False):
            raise RPCException("Force_entry not enabled.")

        if self._freqtrade.state != State.RUNNING:
            raise RPCException("trader is not running")

        if order_side == SignalDirection.SHORT and self._freqtrade.trading_mode == TradingMode.SPOT:
            raise RPCException("Can't go short on Spot markets.")

        if pair not in self._freqtrade.exchange.get_markets(tradable_only=True):
            raise RPCException("Symbol does not exist or market is not active.")
        # Check if pair quote currency equals to the stake currency.
        stake_currency = self._freqtrade.config.get("stake_currency")
        if not self._freqtrade.exchange.get_pair_quote_currency(pair) == stake_currency:
            raise RPCException(
                f"Wrong pair selected. Only pairs with stake-currency {stake_currency} allowed."
            )

    def _rpc_force_entry(
        self,
        pair: str,
        price: float | None,
        *,
        order_type: str | None = None,
        order_side: SignalDirection = SignalDirection.LONG,
        stake_amount: float | None = None,
        enter_tag: str | None = "force_entry",
        leverage: float | None = None,
    ) -> Trade | None:
        """
        Handler for forcebuy <asset> <price>
        Buys a pair trade at the given or current price
        """
        self._force_entry_validations(pair, order_side)

        # check if valid pair

        # check if pair already has an open pair
        trade: Trade | None = Trade.get_trades(
            [Trade.is_open.is_(True), Trade.pair == pair]
        ).first()
        is_short = order_side == SignalDirection.SHORT
        if trade:
            is_short = trade.is_short
            if not self._freqtrade.strategy.position_adjustment_enable:
                raise RPCException(f"position for {pair} already open - id: {trade.id}")
            if trade.has_open_orders:
                raise RPCException(
                    f"position for {pair} already open - id: {trade.id} "
                    f"and has open order {','.join(trade.open_orders_ids)}"
                )
        else:
            if Trade.get_open_trade_count() >= self._config["max_open_trades"]:
                raise RPCException("Maximum number of trades is reached.")

        if not stake_amount:
            # gen stake amount
            stake_amount = self._freqtrade.wallets.get_trade_stake_amount(
                pair, self._config["max_open_trades"]
            )

        # execute buy
        if not order_type:
            order_type = self._freqtrade.strategy.order_types.get(
                "force_entry", self._freqtrade.strategy.order_types["entry"]
            )
        with self._freqtrade._exit_lock:
            if self._freqtrade.execute_entry(
                pair,
                stake_amount,
                price,
                ordertype=order_type,
                trade=trade,
                is_short=is_short,
                enter_tag=enter_tag,
                leverage_=leverage,
                mode="pos_adjust" if trade else "initial",
            ):
                Trade.commit()
                trade = Trade.get_trades([Trade.is_open.is_(True), Trade.pair == pair]).first()
                return trade
            else:
                raise RPCException(f"Failed to enter position for {pair}.")

    def _rpc_cancel_open_order(self, trade_id: int):
        if self._freqtrade.state == State.STOPPED:
            raise RPCException("trader is not running")
        with self._freqtrade._exit_lock:
            # Query for trade
            trade = Trade.get_trades(
                trade_filter=[
                    Trade.id == trade_id,
                    Trade.is_open.is_(True),
                ]
            ).first()
            if not trade:
                logger.warning("cancel_open_order: Invalid trade_id received.")
                raise RPCException("Invalid trade_id.")
            if not trade.has_open_orders:
                logger.warning("cancel_open_order: No open order for trade_id.")
                raise RPCException("No open order for trade_id.")

            for open_order in trade.open_orders:
                try:
                    order = self._freqtrade.exchange.fetch_order(open_order.order_id, trade.pair)
                except ExchangeError as e:
                    logger.info(f"Cannot query order for {trade} due to {e}.", exc_info=True)
                    raise RPCException("Order not found.")
                self._freqtrade.handle_cancel_order(
                    order, open_order, trade, CANCEL_REASON["USER_CANCEL"]
                )
            Trade.commit()

    def _rpc_delete(self, trade_id: int) -> dict[str, str | int]:
        """
        Handler for delete <id>.
        Delete the given trade and close eventually existing open orders.
        """
        with self._freqtrade._exit_lock:
            c_count = 0
            trade = Trade.get_trades(trade_filter=[Trade.id == trade_id]).first()
            if not trade:
                logger.warning("delete trade: Invalid argument received")
                raise RPCException(f"Trade with id '{trade_id}' not found.")

            # Try cancelling regular order if that exists
            for open_order in trade.open_orders:
                try:
                    self._freqtrade.exchange.cancel_order(open_order.order_id, trade.pair)
                    c_count += 1
                except ExchangeError:
                    pass

            # cancel stoploss on exchange orders ...
            if (
                self._freqtrade.strategy.order_types.get("stoploss_on_exchange")
                and trade.has_open_sl_orders
            ):
                for oslo in trade.open_sl_orders:
                    try:
                        self._freqtrade.exchange.cancel_stoploss_order(oslo.order_id, trade.pair)
                        c_count += 1
                    except ExchangeError:
                        pass
            trade_pair = trade.pair
            trade.delete()
            self._freqtrade.wallets.update()
            return {
                "result": "success",
                "trade_id": trade_id,
                "result_msg": (
                    f"Deleted trade #{trade_id} for pair {trade_pair}. "
                    f"Closed {c_count} open orders."
                ),
                "cancel_order_count": c_count,
            }

    @custom_data_rpc_wrapper
    def _rpc_list_custom_data(
        self, trade_id: int | None = None, key: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        Fetch custom data for a specific trade, or all open trades if `trade_id` is not provided.
        Pagination is applied via `limit` and `offset`.

        Returns an array of dictionaries, each containing:
        - "trade_id": the ID of the trade (int)
        - "custom_data": a list of custom data dicts, each with the fields:
                "id", "key", "type", "value", "created_at", "updated_at"
        """

        trades: Sequence[Trade]
        if trade_id is None:
            # Get all open trades
            trades = Trade.session.scalars(
                Trade.get_trades_query([Trade.is_open.is_(True)])
                .order_by(Trade.id)
                .limit(limit)
                .offset(offset)
            ).all()
        else:
            trades = Trade.get_trades(trade_filter=[Trade.id == trade_id]).all()

        if not trades:
            raise RPCException(
                f"No trade found for trade_id: {trade_id}" if trade_id else "No open trades found."
            )

        results = []
        for trade in trades:
            # Depending on whether a specific key is provided, retrieve custom data accordingly.
            if key:
                data = trade.get_custom_data_entry(key=key)
                # If data exists, wrap it in a list so the output remains consistent.
                custom_data = [data] if data else []
            else:
                custom_data = trade.get_all_custom_data()

            # Format and Append result for the trade if any custom data was found.
            if custom_data:
                formatted_custom_data = [
                    {
                        "key": data_entry.cd_key,
                        "type": data_entry.cd_type,
                        "value": CustomDataWrapper._convert_custom_data(data_entry).value,
                        "created_at": data_entry.created_at,
                        "updated_at": data_entry.updated_at,
                    }
                    for data_entry in custom_data
                ]
                results.append({"trade_id": trade.id, "custom_data": formatted_custom_data})

            # Handle case when there is no custom data found across trades.
            if not results:
                message_details = ""
                if key:
                    message_details += f"with key '{key}' "
                message_details += (
                    f"found for Trade ID: {trade_id}." if trade_id else "found for any open trades."
                )
                raise RPCException(f"No custom-data {message_details}")

        return results

    def _rpc_performance(self) -> list[dict[str, Any]]:
        """
        Handler for performance.
        Shows a performance statistic from finished trades
        """
        pair_rates = Trade.get_overall_performance()

        return pair_rates

    def _rpc_enter_tag_performance(self, pair: str | None) -> list[dict[str, Any]]:
        """
        Handler for buy tag performance.
        Shows a performance statistic from finished trades
        """
        return Trade.get_enter_tag_performance(pair)

    def _rpc_exit_reason_performance(self, pair: str | None) -> list[dict[str, Any]]:
        """
        Handler for exit reason performance.
        Shows a performance statistic from finished trades
        """
        return Trade.get_exit_reason_performance(pair)

    def _rpc_mix_tag_performance(self, pair: str | None) -> list[dict[str, Any]]:
        """
        Handler for mix tag (enter_tag + exit_reason) performance.
        Shows a performance statistic from finished trades
        """
        mix_tags = Trade.get_mix_tag_performance(pair)

        return mix_tags

    def _rpc_count(self) -> dict[str, float]:
        """Returns the number of trades running"""
        if self._freqtrade.state == State.STOPPED:
            raise RPCException("trader is not running")

        trades = Trade.get_open_trades()
        return {
            "current": len(trades),
            "max": (
                int(self._freqtrade.config["max_open_trades"])
                if self._freqtrade.config["max_open_trades"] != float("inf")
                else -1
            ),
            "total_stake": sum((trade.open_rate * trade.amount) for trade in trades),
        }

    def _rpc_effective_risk_snapshot(
        self, stake_currency: str, fiat_display_currency: str
    ) -> dict[str, Any]:
        """Build a read-only risk snapshot from persisted trades, locks, and existing statistics."""
        generated_timestamp = dt_ts(dt_now())
        open_trades = Trade.get_open_trades()
        active_locks = [lock.to_json() for lock in PairLocks.get_pair_locks(None)]
        event_timestamps: list[int] = [
            int(trade.open_date_utc.timestamp() * 1000) for trade in open_trades
        ]
        event_timestamps.extend(lock["lock_timestamp"] for lock in active_locks)

        try:
            stats = self._rpc_trade_statistics(stake_currency, fiat_display_currency)
            current_drawdown = {
                "value": stats["current_drawdown"],
                "status": "available",
                "source": "trade_statistics.current_drawdown",
            }
            max_drawdown = {
                "value": stats["max_drawdown"],
                "status": "available",
                "source": "trade_statistics.max_drawdown",
            }
            max_drawdown_abs = {
                "value": stats["max_drawdown_abs"],
                "status": "available",
                "source": "trade_statistics.max_drawdown_abs",
            }
            if stats["latest_trade_timestamp"]:
                event_timestamps.append(stats["latest_trade_timestamp"])
        except (RPCException, ValueError):
            logger.warning("Unable to calculate trade statistics for effective risk snapshot")
            current_drawdown = {
                "value": None,
                "status": "unavailable",
                "source": "trade_statistics.current_drawdown",
                "reason": "trade statistics unavailable",
            }
            max_drawdown = {
                "value": None,
                "status": "unavailable",
                "source": "trade_statistics.max_drawdown",
                "reason": "trade statistics unavailable",
            }
            max_drawdown_abs = {
                "value": None,
                "status": "unavailable",
                "source": "trade_statistics.max_drawdown_abs",
                "reason": "trade statistics unavailable",
            }

        configured_limit = self._freqtrade.config.get("max_open_trades")
        capacity: dict[str, str | int | float | None]
        if configured_limit == float("inf"):
            capacity = {
                "used": len(open_trades),
                "limit": None,
                "utilization_pct": None,
                "status": "available",
                "source": "config.max_open_trades + trade_persistence",
                "reason": "unbounded position capacity",
            }
        elif isinstance(configured_limit, (int, float)) and configured_limit > 0:
            capacity = {
                "used": len(open_trades),
                "limit": int(configured_limit),
                "utilization_pct": min(len(open_trades) / configured_limit * 100, 100),
                "status": "available",
                "source": "config.max_open_trades + trade_persistence",
            }
        else:
            capacity = {
                "used": len(open_trades),
                "limit": None,
                "utilization_pct": None,
                "status": "partial",
                "source": "trade_persistence",
                "reason": "position limit is not configured",
            }

        nominal_exposure = {
            "value": sum(abs(trade.amount * trade.open_rate) for trade in open_trades),
            "status": "available",
            "source": "trade_persistence.amount x open_rate",
        }

        today = dt_now().date()
        tomorrow = today + timedelta(days=1)
        today_profit = Trade.session.scalar(
            select(func.sum(Trade.close_profit_abs)).filter(
                Trade.is_open.is_(False),
                Trade.close_date >= today,
                Trade.close_date < tomorrow,
            )
        )
        today_realized_profit = {
            "value": float(today_profit or 0.0),
            "status": "available",
            "source": "trade_persistence.close_profit_abs",
        }

        recent_closed = Trade.session.scalars(
            Trade.get_trades_query(Trade.is_open.is_(False), include_orders=False)
            .order_by(Trade.close_date.desc())
            .limit(101)
        ).all()
        consecutive_count = 0
        consecutive_complete = True
        for index, trade in enumerate(recent_closed):
            if index == 100:
                consecutive_complete = False
                break
            if trade.close_profit_abs is None:
                consecutive_complete = False
                break
            if trade.close_profit_abs >= 0:
                break
            consecutive_count += 1
        if recent_closed and recent_closed[0].close_date_utc:
            event_timestamps.append(int(recent_closed[0].close_date_utc.timestamp() * 1000))
        consecutive_losses = (
            {
                "value": consecutive_count,
                "status": "available",
                "source": "trade_persistence.close_profit_abs",
            }
            if consecutive_complete
            else {
                "value": None,
                "status": "partial",
                "source": "trade_persistence.close_profit_abs",
                "reason": "available history does not prove the loss streak boundary",
            }
        )

        metrics = [
            current_drawdown,
            max_drawdown,
            max_drawdown_abs,
            capacity,
            nominal_exposure,
            today_realized_profit,
            consecutive_losses,
        ]
        snapshot_status = (
            "available" if all(metric["status"] == "available" for metric in metrics) else "partial"
        )
        return {
            "generated_timestamp": generated_timestamp,
            "event_timestamp": max(event_timestamps) if event_timestamps else None,
            "status": snapshot_status,
            "current_drawdown": current_drawdown,
            "max_drawdown": max_drawdown,
            "max_drawdown_abs": max_drawdown_abs,
            "position_capacity": capacity,
            "nominal_exposure": nominal_exposure,
            "today_realized_profit": today_realized_profit,
            "consecutive_losses": consecutive_losses,
            "active_locks": active_locks,
            "locks_status": {
                "status": "available",
                "source": "pairlock_persistence",
            },
            "risk_limit": {
                "status": "unconfigured",
                "source": "config",
                "reason": "no native portfolio risk-limit contract is configured",
            },
        }

    def _rpc_decision_journal(self, limit: int, offset: int = 0) -> dict[str, Any]:
        """Return a read-only journal derived from persisted trade and order state."""
        generated_timestamp = dt_ts(dt_now())
        trades = Trade.session.scalars(
            Trade.get_trades_query()
            .order_by(func.coalesce(Trade.close_date, Trade.open_date).desc(), Trade.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        events: list[dict[str, Any]] = []

        for trade in trades:
            orders = sorted(
                trade.orders,
                key=lambda order: (
                    order.order_filled_utc
                    or order.order_date_utc
                    or datetime.min.replace(tzinfo=UTC)
                ),
                reverse=True,
            )
            latest_order = orders[0] if orders else None
            event_time = (
                trade.close_date_utc
                or (
                    latest_order.order_filled_utc or latest_order.order_date_utc
                    if latest_order
                    else None
                )
                or trade.open_date_utc
            )
            stage = (
                "exit"
                if not trade.is_open
                else "position"
                if trade.nr_of_successful_entries > 0
                else "entry"
            )
            result = (
                trade.exit_reason or "closed"
                if stage == "exit"
                else "pending_order"
                if trade.has_open_orders
                else "open"
            )
            events.append(
                {
                    "id": f"trade:{trade.id}",
                    "event_timestamp": int(event_time.timestamp() * 1000),
                    "strategy": trade.strategy,
                    "pair": trade.pair,
                    "side": "short" if trade.is_short else "long",
                    "stage": stage,
                    "result": result,
                    "enter_tag": trade.enter_tag,
                    "signal_source": trade.enter_tag,
                    "decision_reason": trade.exit_reason if stage == "exit" else None,
                    "rejection_reason": None,
                    "trade_id": trade.id,
                    "order_id": latest_order.order_id if latest_order else None,
                    "order_status": latest_order.status if latest_order else None,
                    "order_side": latest_order.ft_order_side if latest_order else None,
                    "open_rate": trade.open_rate,
                    "close_rate": trade.close_rate,
                    "profit_ratio": trade.close_profit,
                    "profit_abs": trade.close_profit_abs,
                    "source": "trade_persistence",
                }
            )

        return {
            "generated_timestamp": generated_timestamp,
            "events": events,
            "offset": offset,
            "count": len(events),
            "capabilities": {
                "persisted_trade_events": {
                    "status": "available",
                    "source": "trade_persistence",
                },
                "signal_source": {
                    "status": "partial",
                    "source": "trade.enter_tag",
                    "reason": "available only when the strategy persisted an enter tag",
                },
                "decision_reason": {
                    "status": "partial",
                    "source": "trade.exit_reason",
                    "reason": "entry rationale is not persisted",
                },
                "rejected_or_unfilled_signals": {
                    "status": "unavailable",
                    "source": "trade_persistence",
                    "reason": "signals without a persisted trade have no durable source",
                },
            },
        }

    def _rpc_execution_quality(self, trade_limit: int = 200) -> dict[str, Any]:
        """Analyze persisted order execution facts without affecting trading."""
        generated_timestamp = dt_ts(dt_now())
        trades = Trade.session.scalars(
            Trade.get_trades_query()
            .order_by(func.coalesce(Trade.close_date, Trade.open_date).desc(), Trade.id.desc())
            .limit(trade_limit)
        ).all()

        fee_totals: dict[str, float] = {}
        fee_records = 0
        latencies: list[int] = []
        price_deviations: list[float] = []
        lifecycle_counts = {"open": 0, "filled": 0, "cancelled": 0, "other": 0}
        samples: list[dict[str, Any]] = []

        for trade in trades:
            for fee_cost, fee_currency in (
                (trade.fee_open_cost, trade.fee_open_currency),
                (trade.fee_close_cost, trade.fee_close_currency),
            ):
                if fee_cost is not None and fee_currency:
                    fee_totals[fee_currency] = fee_totals.get(fee_currency, 0.0) + fee_cost
                    fee_records += 1

            for order in trade.orders:
                status = (order.status or "").lower()
                lifecycle = (
                    "open"
                    if order.ft_is_open
                    else "filled"
                    if status in {"closed", "filled"}
                    else "cancelled"
                    if "cancel" in status or order.ft_cancel_reason
                    else "other"
                )
                lifecycle_counts[lifecycle] += 1

                created = order.order_date_utc
                filled = order.order_filled_utc
                latency = (
                    max(0, int((filled - created).total_seconds() * 1000))
                    if created and filled
                    else None
                )
                if latency is not None:
                    latencies.append(latency)

                requested_price = order.safe_placement_price
                average_price = order.average
                price_deviation = (
                    abs((average_price / requested_price) - 1) * 10_000
                    if requested_price and average_price
                    else None
                )
                if price_deviation is not None:
                    price_deviations.append(price_deviation)

                event_time = filled or order.order_update_date or created
                samples.append(
                    {
                        "id": f"trade:{trade.id}:order:{order.id}",
                        "event_timestamp": dt_ts(event_time),
                        "trade_id": trade.id,
                        "order_id": order.order_id,
                        "pair": trade.pair,
                        "side": order.ft_order_side,
                        "lifecycle": lifecycle,
                        "created_timestamp": dt_ts(created),
                        "filled_timestamp": dt_ts(filled) if filled else None,
                        "fill_latency_ms": latency,
                        "requested_price": requested_price,
                        "average_price": average_price,
                        "price_deviation_bps": price_deviation,
                        "source": "order_persistence",
                    }
                )

        samples.sort(key=lambda item: (item["event_timestamp"], item["id"]), reverse=True)
        order_count = sum(lifecycle_counts.values())

        def metric(value: float | None, source: str) -> dict[str, Any]:
            return {
                "status": "available" if value is not None else "unavailable",
                "value": value,
                "source": source,
                "reason": (
                    None if value is not None else "required persisted values are not available"
                ),
            }

        sorted_latencies = sorted(latencies)
        p95_index = max(0, ceil(len(sorted_latencies) * 0.95) - 1)
        status = (
            "unavailable"
            if not trades
            else "available"
            if order_count and latencies and price_deviations and fee_records
            else "partial"
        )

        return {
            "mode": "read_only",
            "affects_trading": False,
            "generated_timestamp": generated_timestamp,
            "event_timestamp": samples[0]["event_timestamp"] if samples else None,
            "status": status,
            "fee_totals": [
                {
                    "currency": currency,
                    "value": value,
                    "source": "trade_persistence",
                }
                for currency, value in sorted(fee_totals.items())
            ],
            "fee_status": {
                "status": "available" if fee_records else "unavailable",
                "source": "trade_persistence",
                "reason": None
                if fee_records
                else "no persisted fee cost and currency pairs are available",
            },
            "average_fill_latency_ms": metric(
                sum(latencies) / len(latencies) if latencies else None,
                "order_persistence",
            ),
            "p95_fill_latency_ms": metric(
                sorted_latencies[p95_index] if sorted_latencies else None,
                "order_persistence",
            ),
            "average_price_deviation_bps": metric(
                sum(price_deviations) / len(price_deviations) if price_deviations else None,
                "order_persistence",
            ),
            "lifecycle": {"total": order_count, **lifecycle_counts},
            "coverage": {
                "sampled_trades": len(trades),
                "sampled_orders": order_count,
                "fee_records": fee_records,
                "latency_records": len(latencies),
                "price_deviation_records": len(price_deviations),
            },
            "recent_orders": samples[:20],
            "capabilities": {
                "local_fill_latency": {
                    "status": "available" if latencies else "unavailable",
                    "source": "order.order_date/order_filled_date",
                    "reason": None
                    if latencies
                    else "paired order creation and fill timestamps are unavailable",
                },
                "requested_to_average_price_deviation": {
                    "status": "available" if price_deviations else "unavailable",
                    "source": "order.price/order.average",
                    "reason": None
                    if price_deviations
                    else "paired requested and average fill prices are unavailable",
                },
                "exchange_ack_latency": {
                    "status": "unavailable",
                    "source": "order_persistence",
                    "reason": "exchange acknowledgement timestamps are not persisted",
                },
                "decision_to_order_latency": {
                    "status": "unavailable",
                    "source": "order_persistence",
                    "reason": "decision timestamps are not persisted",
                },
            },
        }

    def _rpc_strategy_governance(  # noqa: C901
        self, backtest_results_dir: Path
    ) -> dict[str, Any]:
        """Return bounded validation evidence without changing or promoting a strategy."""
        from freqtrade.data.btanalysis import get_latest_backtest_filename

        generated_timestamp = dt_ts(dt_now())
        strategy = self._freqtrade.strategy
        identifier = self._freqtrade.config.get("strategy") or strategy.__class__.__name__
        source_file = getattr(strategy, "__file__", None)
        if not source_file:
            try:
                source_file = inspect.getsourcefile(strategy.__class__)
            except (OSError, TypeError):
                source_file = None
        fingerprint = None
        fingerprint_reason = None
        if source_file:
            try:
                source_path = Path(source_file)
                if source_path.is_file() and source_path.stat().st_size <= 2 * 1024 * 1024:
                    fingerprint = hashlib.sha256(source_path.read_bytes()).hexdigest()
                else:
                    fingerprint_reason = "strategy source is unavailable or exceeds the 2 MiB limit"
            except OSError:
                fingerprint_reason = "strategy source is unavailable"
        else:
            fingerprint_reason = "strategy source location is unavailable"

        def metric(data: dict[str, Any] | None, key: str, source: str) -> dict[str, Any]:
            value = data.get(key) if data else None
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(float(value))
            ):
                value = None
            return {
                "value": value,
                "status": "available" if value is not None else "unavailable",
                "source": source,
                "reason": None if value is not None else f"{key} is not recorded",
            }

        backtest: dict[str, Any] = {
            "status": "not_recorded",
            "source": "backtest_results/.last_result.json",
            "reason": "no bounded latest backtest result is recorded for the active strategy",
            "trade_count": metric(None, "total_trades", "backtest_result"),
            "profit_ratio": metric(None, "profit_total", "backtest_result"),
            "max_drawdown": metric(None, "max_drawdown", "backtest_result"),
            "win_rate": metric(None, "win_rate", "backtest_result"),
        }
        max_result_size = 25 * 1024 * 1024
        try:
            latest_name = get_latest_backtest_filename(backtest_results_dir)
            result_path = (backtest_results_dir / latest_name).resolve()
            if result_path.suffix not in {".json", ".zip"} or not is_file_in_dir(
                result_path, backtest_results_dir
            ):
                raise ValueError("latest backtest result is outside the configured directory")

            if result_path.suffix == ".zip":
                with ZipFile(result_path) as archive:
                    member = archive.getinfo(result_path.with_suffix(".json").name)
                    if member.file_size > max_result_size:
                        raise ValueError("latest backtest result exceeds the 25 MiB limit")
                    payload = archive.read(member)
            else:
                if result_path.stat().st_size > max_result_size:
                    raise ValueError("latest backtest result exceeds the 25 MiB limit")
                payload = result_path.read_bytes()
            result = json.loads(payload)
            strategy_data = result.get("strategy", {}).get(identifier)
            metadata = result.get("metadata", {}).get(identifier, {})
            if strategy_data:
                total_trades = strategy_data.get("total_trades")
                wins = strategy_data.get("wins")
                win_rate = (
                    wins / total_trades
                    if wins is not None and total_trades not in (None, 0)
                    else None
                )
                run_timestamp = metadata.get("backtest_start_time")
                if isinstance(run_timestamp, (int, float)):
                    run_timestamp = int(
                        run_timestamp * 1000 if run_timestamp < 10_000_000_000 else run_timestamp
                    )
                else:
                    run_timestamp = None
                backtest_metrics = {
                    "trade_count": metric(
                        strategy_data, "total_trades", "backtest_result.total_trades"
                    ),
                    "profit_ratio": metric(
                        strategy_data, "profit_total", "backtest_result.profit_total"
                    ),
                    "max_drawdown": metric(
                        strategy_data, "max_drawdown", "backtest_result.max_drawdown"
                    ),
                    "win_rate": {
                        "value": win_rate,
                        "status": "available" if win_rate is not None else "unavailable",
                        "source": "backtest_result.wins / total_trades",
                        "reason": None
                        if win_rate is not None
                        else "wins or total_trades is not recorded",
                    },
                }
                evidence_status = (
                    "available"
                    if all(item["status"] == "available" for item in backtest_metrics.values())
                    else "partial"
                )
                backtest = {
                    "status": evidence_status,
                    "source": "bounded_latest_backtest_result",
                    "reason": None
                    if evidence_status == "available"
                    else "latest result contains only partial recorded metrics",
                    "result_file": result_path.name,
                    "run_id": metadata.get("run_id"),
                    "run_timestamp": run_timestamp,
                    "sample_start_timestamp": strategy_data.get("backtest_start_ts"),
                    "sample_end_timestamp": strategy_data.get("backtest_end_ts"),
                    "timeframe": strategy_data.get("timeframe"),
                    **backtest_metrics,
                }
        except (AttributeError, BadZipFile, KeyError, OSError, TypeError, ValueError):
            logger.warning("Unable to load bounded latest backtest evidence")

        gates = [
            {
                "id": "backtest",
                "label": "历史回测",
                "status": backtest["status"],
                "source": backtest["source"],
                "reason": backtest.get("reason"),
            },
            *[
                {
                    "id": gate_id,
                    "label": label,
                    "status": "not_recorded",
                    "source": "governance_metadata",
                    "reason": reason,
                }
                for gate_id, label, reason in (
                    ("out_of_sample", "样本外验证", "no durable out-of-sample record exists"),
                    ("stress_test", "压力测试", "no durable stress-test record exists"),
                    (
                        "paper_trading",
                        "模拟盘验证",
                        "no durable paper-trading approval record exists",
                    ),
                    (
                        "limited_capital",
                        "小资金灰度",
                        "no durable limited-capital rollout record exists",
                    ),
                    ("human_approval", "人工批准", "no durable human approval record exists"),
                    ("rollback_point", "回滚点", "no durable rollback point is recorded"),
                )
            ],
        ]
        return {
            "mode": "read_only",
            "affects_trading": False,
            "promotion_allowed": False,
            "generated_timestamp": generated_timestamp,
            "status": "partial"
            if fingerprint or backtest["status"] == "available"
            else "unavailable",
            "strategy": {
                "identifier": identifier,
                "class_name": strategy.__class__.__name__,
                "version": strategy.version(),
                "fingerprint": fingerprint,
                "fingerprint_algorithm": "sha256" if fingerprint else None,
                "fingerprint_status": {
                    "status": "available" if fingerprint else "unavailable",
                    "source": "active_strategy_source",
                    "reason": fingerprint_reason,
                },
            },
            "latest_backtest": backtest,
            "gates": gates,
            "capabilities": {
                "automatic_promotion": {
                    "status": "unavailable",
                    "source": "strategy_governance",
                    "reason": "this endpoint cannot publish, switch, or approve a strategy",
                },
                "performance_interpretation": {
                    "status": "unavailable",
                    "source": "strategy_governance",
                    "reason": "backtest metrics are evidence only, not deployment eligibility",
                },
            },
        }

    def _rpc_system_observability(self, log_limit: int = 200) -> dict[str, Any]:
        """Aggregate bounded runtime diagnostics without changing trading state."""
        generated_timestamp = dt_ts(dt_now())
        health = self.health()
        last_process_ts = health["last_process_ts"]
        bot_start_ts = health["bot_start_ts"]

        def metric(value: float | None, source: str, reason: str) -> dict[str, Any]:
            return {
                "value": value,
                "status": "available" if value is not None else "unavailable",
                "source": source,
                "reason": None if value is not None else reason,
            }

        heartbeat_age_ms = (
            max(0, generated_timestamp - last_process_ts * 1000)
            if isinstance(last_process_ts, int)
            else None
        )
        uptime_ms = (
            max(0, generated_timestamp - bot_start_ts * 1000)
            if isinstance(bot_start_ts, int)
            else None
        )

        db_reason = None
        try:
            Trade.session.scalar(select(1))
            open_trade_count = Trade.session.scalar(
                select(func.count(Trade.id)).filter(Trade.is_open.is_(True))
            )
            active_lock_count = PairLock.session.scalar(
                select(func.count(PairLock.id)).filter(
                    PairLock.active.is_(True),
                    PairLock.lock_end_time > dt_now(),
                )
            )
            database_available = True
        except SQLAlchemyError:
            logger.warning("Unable to query database observability metrics")
            database_available = False
            open_trade_count = None
            active_lock_count = None
            db_reason = "database diagnostics are unavailable"

        cpu_values = psutil.cpu_percent(interval=None, percpu=True)
        cpu_pct = sum(cpu_values) / len(cpu_values) if cpu_values else None
        ram_pct = psutil.virtual_memory().percent
        records = [
            record
            for record in bufferHandler.buffer[-log_limit:]
            if hasattr(record, "levelname") and hasattr(record, "created")
        ]
        log_levels = {
            level: len([record for record in records if record.levelname.upper() == level])
            for level in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
        }
        alerts = []
        for level, severity, title in (
            ("CRITICAL", "error", "日志窗口记录到 CRITICAL 事件"),
            ("ERROR", "error", "日志窗口记录到 ERROR 事件"),
            ("WARNING", "warning", "日志窗口记录到 WARNING 事件"),
        ):
            matching = [record for record in records if record.levelname.upper() == level]
            if matching:
                alerts.append(
                    {
                        "id": f"logs:{level.lower()}",
                        "severity": severity,
                        "title": title,
                        "count": len(matching),
                        "event_timestamp": int(max(record.created for record in matching) * 1000),
                        "source": "bounded_log_buffer_levels",
                    }
                )
        if heartbeat_age_ms is None:
            alerts.append(
                {
                    "id": "runtime:heartbeat_missing",
                    "severity": "warning",
                    "title": "交易引擎尚无可用心跳时间",
                    "count": 1,
                    "event_timestamp": None,
                    "source": "runtime.last_process",
                }
            )
        if not database_available:
            alerts.append(
                {
                    "id": "database:unavailable",
                    "severity": "error",
                    "title": "数据库诊断查询不可用",
                    "count": 1,
                    "event_timestamp": generated_timestamp,
                    "source": "persistence",
                }
            )

        runtime_state = getattr(self._freqtrade.state, "name", str(self._freqtrade.state))
        return {
            "mode": "read_only",
            "affects_trading": False,
            "generated_timestamp": generated_timestamp,
            "status": "available"
            if database_available and heartbeat_age_ms is not None
            else "partial",
            "runtime_state": runtime_state,
            "heartbeat_age_ms": metric(
                heartbeat_age_ms,
                "runtime.last_process",
                "the engine has not recorded a process timestamp",
            ),
            "uptime_ms": metric(
                uptime_ms,
                "key_value_store.bot_start_time",
                "bot start time is not recorded",
            ),
            "database_status": {
                "status": "available" if database_available else "unavailable",
                "source": "persistence.select",
                "reason": db_reason,
            },
            "open_trade_count": metric(
                open_trade_count,
                "trade_persistence",
                "open trade count is unavailable",
            ),
            "active_lock_count": metric(
                active_lock_count,
                "pairlock_persistence",
                "active lock count is unavailable",
            ),
            "active_pair_count": metric(
                len(self._freqtrade.active_pair_whitelist),
                "runtime.active_pair_whitelist",
                "active pair whitelist is unavailable",
            ),
            "cpu_pct": metric(cpu_pct, "psutil.cpu_percent", "CPU telemetry is unavailable"),
            "ram_pct": metric(ram_pct, "psutil.virtual_memory", "RAM telemetry is unavailable"),
            "log_window": {
                "requested_limit": log_limit,
                "record_count": len(records),
                "oldest_timestamp": int(records[0].created * 1000) if records else None,
                "newest_timestamp": int(records[-1].created * 1000) if records else None,
            },
            "log_levels": log_levels,
            "alerts": alerts,
            "capabilities": {
                "raw_log_messages": {
                    "status": "unavailable",
                    "source": "system_observability",
                    "reason": "messages and stack traces are intentionally excluded",
                },
                "notification_delivery": {
                    "status": "unavailable",
                    "source": "system_observability",
                    "reason": "this read-only endpoint does not send notifications",
                },
                "configured_alert_thresholds": {
                    "status": "unconfigured",
                    "source": "config",
                    "reason": "no user-defined system alert thresholds are configured here",
                },
            },
        }

    def _rpc_market_observer(
        self,
        pair_limit: int = 12,
        lookback_candles: int = 20,
        timeframes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Observe cached analyzed OHLCV data without changing strategy or execution state."""
        requested_timestamp = dt_ts(dt_now())
        configured_timeframe = self._freqtrade.config["timeframe"]
        requested_timeframes = list(dict.fromkeys(timeframes or [configured_timeframe, "1h", "4h"]))
        pairs = self._freqtrade.active_pair_whitelist[:pair_limit]
        observations: list[dict[str, Any]] = []
        event_timestamps: list[int] = []

        for timeframe in requested_timeframes:
            for pair in pairs:
                try:
                    dataframe, last_analyzed = self._freqtrade.dataprovider.get_analyzed_dataframe(
                        pair, timeframe
                    )
                    window = dataframe.tail(lookback_candles)
                    required_columns = {"close", "high", "low", "volume"}
                    if len(window) < 2 or not required_columns.issubset(window.columns):
                        observations.append(
                            {
                                "pair": pair,
                                "timeframe": timeframe,
                                "status": "unavailable",
                                "freshness": "unavailable",
                                "sample_count": len(window),
                                "source": "dataprovider.analyzed_ohlcv_cache",
                                "reason": "insufficient cached analyzed OHLCV data",
                            }
                        )
                        continue

                    candle_time = window["date"].iloc[-1] if "date" in window.columns else None
                    if candle_time is not None and hasattr(candle_time, "to_pydatetime"):
                        candle_time = candle_time.to_pydatetime()
                    event_time = candle_time or last_analyzed
                    if not isinstance(event_time, datetime):
                        observations.append(
                            {
                                "pair": pair,
                                "timeframe": timeframe,
                                "status": "unavailable",
                                "freshness": "unavailable",
                                "sample_count": len(window),
                                "source": "dataprovider.analyzed_ohlcv_cache",
                                "reason": "cached candles do not expose an event time",
                            }
                        )
                        continue
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=UTC)

                    first_close = float(window["close"].iloc[0])
                    last_close = float(window["close"].iloc[-1])
                    highest = float(window["high"].max())
                    lowest = float(window["low"].min())
                    latest_volume = float(window["volume"].iloc[-1])
                    median_volume = float(window["volume"].median())
                    event_timestamp = int(event_time.timestamp() * 1000)
                    age_ms = max(0, requested_timestamp - event_timestamp)
                    freshness = "fresh" if age_ms <= timeframe_to_msecs(timeframe) * 3 else "stale"
                    event_timestamps.append(event_timestamp)
                    observations.append(
                        {
                            "pair": pair,
                            "timeframe": timeframe,
                            "status": "available",
                            "freshness": freshness,
                            "event_timestamp": event_timestamp,
                            "sample_count": len(window),
                            "close": last_close,
                            "change_pct": (
                                (last_close / first_close - 1) * 100 if first_close else None
                            ),
                            "range_pct": (
                                (highest - lowest) / last_close * 100 if last_close else None
                            ),
                            "volume": latest_volume,
                            "volume_ratio": (
                                latest_volume / median_volume if median_volume > 0 else None
                            ),
                            "source": "dataprovider.analyzed_ohlcv_cache",
                        }
                    )
                except (KeyError, OperationalException, ValueError, RPCException):
                    logger.warning(
                        "Unable to build cached market observation for %s %s",
                        pair,
                        timeframe,
                    )
                    observations.append(
                        {
                            "pair": pair,
                            "timeframe": timeframe,
                            "status": "unavailable",
                            "freshness": "unavailable",
                            "sample_count": 0,
                            "source": "dataprovider.analyzed_ohlcv_cache",
                            "reason": "cached analyzed OHLCV data unavailable",
                        }
                    )

        def breadth(items: list[dict[str, Any]]) -> dict[str, int]:
            available_items = [item for item in items if item["status"] == "available"]
            advancing = len([item for item in available_items if (item["change_pct"] or 0) > 0])
            declining = len([item for item in available_items if (item["change_pct"] or 0) < 0])
            return {
                "observed": len(available_items),
                "advancing": advancing,
                "declining": declining,
                "unchanged": len(available_items) - advancing - declining,
                "unavailable": len(items) - len(available_items),
            }

        timeframe_summaries = []
        for timeframe in requested_timeframes:
            items = [item for item in observations if item["timeframe"] == timeframe]
            available_items = [item for item in items if item["status"] == "available"]
            fresh_count = len([item for item in available_items if item["freshness"] == "fresh"])
            stale_count = len(available_items) - fresh_count
            timeframe_summaries.append(
                {
                    "timeframe": timeframe,
                    "requested_pairs": len(pairs),
                    "available": len(available_items),
                    "fresh": fresh_count,
                    "stale": stale_count,
                    "unavailable": len(items) - len(available_items),
                    "coverage_pct": (len(available_items) / len(items) * 100 if items else 0),
                    "breadth": breadth(items),
                }
            )

        available = [item for item in observations if item["status"] == "available"]
        fresh_count = len([item for item in available if item["freshness"] == "fresh"])
        stale_count = len(available) - fresh_count
        unavailable_count = len(observations) - len(available)
        status = (
            "available"
            if available and unavailable_count == 0 and stale_count == 0
            else "partial"
            if available
            else "unavailable"
        )
        generated_timestamp = dt_ts(dt_now())
        return {
            "mode": "observe_only",
            "affects_trading": False,
            "generated_timestamp": generated_timestamp,
            "event_timestamp": max(event_timestamps) if event_timestamps else None,
            "status": status,
            "timeframe": requested_timeframes[0],
            "lookback_candles": lookback_candles,
            "pairs": observations,
            "breadth": breadth(observations),
            "timeframes": timeframe_summaries,
            "health": {
                "requested_timestamp": requested_timestamp,
                "generated_timestamp": generated_timestamp,
                "generation_duration_ms": generated_timestamp - requested_timestamp,
                "requested_observations": len(observations),
                "available": len(available),
                "fresh": fresh_count,
                "stale": stale_count,
                "unavailable": unavailable_count,
                "coverage_pct": (len(available) / len(observations) * 100 if observations else 0),
            },
            "capabilities": {
                "ohlcv_observation": {
                    "status": "available" if available else "unavailable",
                    "source": "dataprovider.analyzed_ohlcv_cache",
                },
                "snapshot_history": {
                    "status": "unavailable",
                    "source": "market_observer",
                    "reason": (
                        "snapshots are not persisted; adding writes or a migration is out of scope"
                    ),
                },
                "regime_classification": {
                    "status": "unavailable",
                    "source": "market_observer",
                    "reason": "observe-only layer does not classify market regimes",
                },
                "execution_integration": {
                    "status": "unavailable",
                    "source": "market_observer",
                    "reason": (
                        "market observations are not connected to strategy selection or orders"
                    ),
                },
            },
        }

    def _rpc_locks(self) -> dict[str, Any]:
        """Returns the current locks"""

        locks = PairLocks.get_pair_locks(None)
        return {"lock_count": len(locks), "locks": [lock.to_json() for lock in locks]}

    def _rpc_delete_lock(
        self, lockid: int | None = None, pair: str | None = None
    ) -> dict[str, Any]:
        """Delete specific lock(s)"""
        locks: Sequence[PairLock] = []

        if pair:
            locks = PairLocks.get_pair_locks(pair)
        if lockid:
            locks = PairLock.session.scalars(select(PairLock).filter(PairLock.id == lockid)).all()

        for lock in locks:
            lock.active = False
            lock.lock_end_time = datetime.now(UTC)

        Trade.commit()

        return self._rpc_locks()

    def _rpc_add_lock(self, pair: str, until: datetime, reason: str | None, side: str) -> PairLock:
        lock = PairLocks.lock_pair(
            pair=pair,
            until=until,
            reason=reason,
            side=side,
        )
        return lock

    def _rpc_whitelist(self) -> dict:
        """Returns the currently active whitelist"""
        res = {
            "method": self._freqtrade.pairlists.name_list,
            "length": len(self._freqtrade.active_pair_whitelist),
            "whitelist": self._freqtrade.active_pair_whitelist,
        }
        return res

    def _rpc_blacklist_delete(self, delete: list[str]) -> dict:
        """Removes pairs from currently active blacklist"""
        errors = {}
        for pair in delete:
            if pair in self._freqtrade.pairlists.blacklist:
                self._freqtrade.pairlists.blacklist.remove(pair)
            else:
                errors[pair] = {"error_msg": f"Pair {pair} is not in the current blacklist."}
        resp = self._rpc_blacklist()
        resp["errors"] = errors
        return resp

    def _rpc_blacklist(self, add: list[str] | None = None) -> dict:
        """Returns the currently active blacklist"""
        errors = {}
        if add:
            for pair in add:
                if pair not in self._freqtrade.pairlists.blacklist:
                    try:
                        expand_pairlist([pair], list(self._freqtrade.exchange.get_markets().keys()))
                        self._freqtrade.pairlists.blacklist.append(pair)

                    except ValueError:
                        errors[pair] = {"error_msg": f"Pair {pair} is not a valid wildcard."}
                else:
                    errors[pair] = {"error_msg": f"Pair {pair} already in pairlist."}

        res = {
            "method": self._freqtrade.pairlists.name_list,
            "length": len(self._freqtrade.pairlists.blacklist),
            "blacklist": self._freqtrade.pairlists.blacklist,
            "blacklist_expanded": self._freqtrade.pairlists.expanded_blacklist,
            "errors": errors,
        }
        return res

    @staticmethod
    def _rpc_get_logs(limit: int | None) -> dict[str, Any]:
        """Returns the last X logs"""
        if limit:
            buffer = bufferHandler.buffer[-limit:]
        else:
            buffer = bufferHandler.buffer
        records = [
            [
                format_date(dt_from_ts(r.created)),
                r.created * 1000,
                r.name,
                r.levelname,
                r.message + ("\n" + r.exc_text if r.exc_text else ""),
            ]
            for r in buffer
            if hasattr(r, "message")
        ]

        # Log format:
        # [logtime-formatted, logepoch, logger-name, loglevel, message \n + exception]
        # e.g. ["2020-08-27 11:35:01", 1598520901097.9397,
        #       "freqtrade.worker", "INFO", "Starting worker develop"]

        return {"log_count": len(records), "logs": records}

    @staticmethod
    def _convert_dataframe_to_dict(
        strategy: str,
        pair: str,
        timeframe: str,
        dataframe: DataFrame,
        last_analyzed: datetime,
        selected_cols: list[str] | None,
        annotations: list[AnnotationType],
    ) -> dict[str, Any]:
        has_content = len(dataframe) != 0
        dataframe_columns = list(dataframe.columns)
        signals = {
            "enter_long": 0,
            "exit_long": 0,
            "enter_short": 0,
            "exit_short": 0,
        }
        if has_content:
            if selected_cols is not None:
                # Ensure OHLCV columns are always present
                cols_set = set(DEFAULT_DATAFRAME_COLUMNS + list(signals.keys()) + selected_cols)
                df_cols = [col for col in dataframe_columns if col in cols_set]
                dataframe = dataframe.loc[:, df_cols]

            dataframe.loc[:, "__date_ts"] = (
                dataframe.loc[:, "date"].dt.as_unit("ms").astype("int64")
            )
            # Move signal close to separate column when signal for easy plotting
            for sig_type in signals:
                if sig_type in dataframe.columns:
                    mask = dataframe[sig_type] == 1
                    signals[sig_type] = int(mask.sum())
                    dataframe.loc[mask, f"_{sig_type}_signal_close"] = dataframe.loc[mask, "close"]

            # band-aid until this is fixed:
            # https://github.com/pandas-dev/pandas/issues/45836
            date_columns = dataframe.select_dtypes(include=["datetime", "datetime64", "datetimetz"])
            for date_column in date_columns:
                # replace NaT with `None`
                dataframe[date_column] = dataframe[date_column].astype(object).replace({NaT: None})

            dataframe = dataframe.replace({inf: None, -inf: None, nan: None})

        res = {
            "pair": pair,
            "timeframe": timeframe,
            "timeframe_ms": timeframe_to_msecs(timeframe),
            "strategy": strategy,
            "all_columns": dataframe_columns,
            "columns": list(dataframe.columns),
            "data": dataframe.values.tolist(),
            "length": len(dataframe),
            "buy_signals": signals["enter_long"],  # Deprecated
            "sell_signals": signals["exit_long"],  # Deprecated
            "enter_long_signals": signals["enter_long"],
            "exit_long_signals": signals["exit_long"],
            "enter_short_signals": signals["enter_short"],
            "exit_short_signals": signals["exit_short"],
            "last_analyzed": last_analyzed,
            "last_analyzed_ts": int(last_analyzed.timestamp()),
            "data_start": "",
            "data_start_ts": 0,
            "data_stop": "",
            "data_stop_ts": 0,
            "annotations": annotations,
        }
        if has_content:
            res.update(
                {
                    "data_start": str(dataframe.iloc[0]["date"]),
                    "data_start_ts": int(dataframe.iloc[0]["__date_ts"]),
                    "data_stop": str(dataframe.iloc[-1]["date"]),
                    "data_stop_ts": int(dataframe.iloc[-1]["__date_ts"]),
                }
            )
        return res

    def _rpc_analysed_dataframe(
        self, pair: str, timeframe: str, limit: int | None, selected_cols: list[str] | None
    ) -> dict[str, Any]:
        """Analyzed dataframe in Dict form"""

        _data, last_analyzed = self.__rpc_analysed_dataframe_raw(pair, timeframe, limit)
        annotations = self._freqtrade.strategy.ft_plot_annotations(pair=pair, dataframe=_data)

        return RPC._convert_dataframe_to_dict(
            self._freqtrade.config["strategy"],
            pair,
            timeframe,
            _data,
            last_analyzed,
            selected_cols,
            annotations,
        )

    def __rpc_analysed_dataframe_raw(
        self, pair: str, timeframe: str, limit: int | None
    ) -> tuple[DataFrame, datetime]:
        """
        Get the dataframe and last analyze from the dataprovider

        :param pair: The pair to get
        :param timeframe: The timeframe of data to get
        :param limit: The amount of candles in the dataframe
        """
        _data, last_analyzed = self._freqtrade.dataprovider.get_analyzed_dataframe(pair, timeframe)
        _data = _data.copy()

        if limit:
            _data = _data.iloc[-limit:]

        return _data, last_analyzed

    def _ws_all_analysed_dataframes(
        self, pairlist: list[str], limit: int | None
    ) -> Generator[dict[str, Any], None, None]:
        """
        Get the analysed dataframes of each pair in the pairlist.
        If specified, only return the most recent `limit` candles for
        each dataframe.

        :param pairlist: A list of pairs to get
        :param limit: If an integer, limits the size of dataframe
                      If a list of string date times, only returns those candles
        :returns: A generator of dictionaries with the key, dataframe, and last analyzed timestamp
        """
        timeframe = self._freqtrade.config["timeframe"]
        candle_type = self._freqtrade.config.get("candle_type_def", CandleType.SPOT)

        for pair in pairlist:
            dataframe, last_analyzed = self.__rpc_analysed_dataframe_raw(pair, timeframe, limit)

            yield {"key": (pair, timeframe, candle_type), "df": dataframe, "la": last_analyzed}

    def _ws_request_analyzed_df(self, limit: int | None = None, pair: str | None = None):
        """Historical Analyzed Dataframes for WebSocket"""
        pairlist = [pair] if pair else self._freqtrade.active_pair_whitelist

        return self._ws_all_analysed_dataframes(pairlist, limit)

    def _ws_request_whitelist(self):
        """Whitelist data for WebSocket"""
        return self._freqtrade.active_pair_whitelist

    @staticmethod
    def _rpc_analysed_history_full(
        config: Config,
        pair: str,
        timeframe: str,
        exchange: Exchange,
        selected_cols: list[str] | None,
        live: bool,
    ) -> dict[str, Any]:
        """
        Analyzed dataframe in Dict form, with full history loading and strategy analysis.
        Loads the full history from disk or exchange, and runs the strategy analysis on it.
        Should only be used in webserver mode, as it can interfere with a running bot.
        """
        timerange_parsed = TimeRange.parse_timerange(config.get("timerange"))

        from freqtrade.data.converter import trim_dataframe
        from freqtrade.data.dataprovider import DataProvider
        from freqtrade.persistence.usedb_context import FtNoDBContext
        from freqtrade.resolvers.strategy_resolver import StrategyResolver

        with FtNoDBContext():
            strategy_name = ""
            startup_candles = 0
            if config.get("strategy"):
                strategy = StrategyResolver.load_strategy(config)
                startup_candles = strategy.startup_candle_count
                strategy_name = strategy.get_strategy_name()

            if live:
                data = exchange.get_historic_ohlcv(
                    pair=pair,
                    timeframe=timeframe,
                    since_ms=timerange_parsed.startts * 1000
                    if timerange_parsed.startts
                    else dt_ts(dt_now() - timedelta(days=30)),
                    is_new_pair=True,  # history is never available - so always treat as new pair
                    candle_type=config.get("candle_type_def", CandleType.SPOT),
                    until_ms=timerange_parsed.stopts * 1000 if timerange_parsed.stopts else None,
                )
                if timerange_parsed.stopts and len(data) > 1:
                    # trim last candle if it is newer than the stop time
                    data = data.loc[data["date"] <= timerange_parsed.stopdt]
            else:
                _data = load_data(
                    datadir=config["datadir"],
                    pairs=[pair],
                    timeframe=timeframe,
                    timerange=timerange_parsed,
                    data_format=config["dataformat_ohlcv"],
                    candle_type=config.get("candle_type_def", CandleType.SPOT),
                    startup_candles=startup_candles,
                )
                if pair not in _data:
                    raise RPCException(
                        f"No data for {pair}, {timeframe} in {config.get('timerange')} found."
                    )
                data = _data[pair]

            annotations = []
            if config.get("strategy"):
                strategy.dp = DataProvider(config, exchange=exchange, pairlists=None)
                strategy.ft_bot_start()

                df_analyzed = strategy.analyze_ticker(data, {"pair": pair})
                prev_len = len(df_analyzed)
                df_analyzed = trim_dataframe(
                    df_analyzed, timerange_parsed, startup_candles=startup_candles
                )
                if prev_len > 0 and len(df_analyzed) == 0:
                    raise RPCException(
                        f"After trimming by startup_candle_count, no data for "
                        f"{pair}, {timeframe} in {config.get('timerange')} left."
                    )
                annotations = strategy.ft_plot_annotations(pair=pair, dataframe=df_analyzed)

            else:
                df_analyzed = data

            return RPC._convert_dataframe_to_dict(
                strategy_name,
                pair,
                timeframe,
                df_analyzed.copy(),
                dt_now(),
                selected_cols,
                annotations,
            )

    def _rpc_plot_config(self) -> dict[str, Any]:
        if (
            self._freqtrade.strategy.plot_config
            and "subplots" not in self._freqtrade.strategy.plot_config
        ):
            self._freqtrade.strategy.plot_config["subplots"] = {}
        return self._freqtrade.strategy.plot_config

    @staticmethod
    def _rpc_plot_config_with_strategy(config: Config) -> dict[str, Any]:
        from freqtrade.resolvers.strategy_resolver import StrategyResolver

        strategy = StrategyResolver.load_strategy(config)
        # Manually load hyperparameters, as we don't call the bot-start callback.
        strategy.ft_load_hyper_params(False)

        if strategy.plot_config and "subplots" not in strategy.plot_config:
            strategy.plot_config["subplots"] = {}
        return strategy.plot_config

    @staticmethod
    def _rpc_sysinfo() -> dict[str, Any]:
        cpu_pct = psutil.cpu_percent(interval=0.1, percpu=True)
        load_avg = psutil.getloadavg()
        return {
            "cpu_pct": cpu_pct,  # Deprecated, use cpu_load instead
            "cpu_load": [
                {
                    "cpu": idx,
                    "pct": pct,
                }
                for idx, pct in enumerate(cpu_pct)
            ],
            "cpu_avg": sum(cpu_pct) / len(cpu_pct) if cpu_pct else 0.0,
            "cpu_load_avg": {
                "1m": load_avg[0],
                "5m": load_avg[1],
                "15m": load_avg[2],
            },
            "cpu_count": len(cpu_pct),
            "ram_pct": psutil.virtual_memory().percent,
        }

    def health(self) -> dict[str, str | int | None]:
        last_p = self._freqtrade.last_process
        res: dict[str, str | int | None] = {
            "last_process": None,
            "last_process_loc": None,
            "last_process_ts": None,
            "bot_start": None,
            "bot_start_loc": None,
            "bot_start_ts": None,
            "bot_startup": None,
            "bot_startup_loc": None,
            "bot_startup_ts": None,
        }

        if last_p is not None:
            res.update(
                {
                    "last_process": str(last_p),
                    "last_process_loc": format_date(last_p.astimezone(tzlocal())),
                    "last_process_ts": int(last_p.timestamp()),
                }
            )

        if bot_start := KeyValueStore.get_datetime_value("bot_start_time"):
            res.update(
                {
                    "bot_start": str(bot_start),
                    "bot_start_loc": format_date(bot_start.astimezone(tzlocal())),
                    "bot_start_ts": int(bot_start.timestamp()),
                }
            )
        if bot_startup := KeyValueStore.get_datetime_value("startup_time"):
            res.update(
                {
                    "bot_startup": str(bot_startup),
                    "bot_startup_loc": format_date(bot_startup.astimezone(tzlocal())),
                    "bot_startup_ts": int(bot_startup.timestamp()),
                }
            )

        return res

    def _update_market_direction(self, direction: MarketDirection) -> None:
        self._freqtrade.strategy.market_direction = direction

    def _get_market_direction(self) -> MarketDirection:
        return self._freqtrade.strategy.market_direction
