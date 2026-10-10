from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    Field,
    RootModel,
    SerializeAsAny,
    model_validator,
)
from pydantic_core import PydanticCustomError

from freqtrade.constants import DL_DATA_TIMEFRAMES, IntOrInf
from freqtrade.enums import MarginMode, OrderTypeValues, SignalDirection, TradingMode
from freqtrade.ft_types import AnnotationType, ValidExchangesType
from freqtrade.rpc.api_server.webserver_bgwork import JOB_CATEGORIES, ProgressTask


def _no_base64_strategy(value: str) -> str:
    """
    Reject `StrategyName:base64` strategy names.
    This is a security measure to prevent potential attacks using base64 encoded strategies.
    Embedding a strategy as base64 is a config-file convenience
    (see docs/strategy-advanced.md) - an API caller must never be able to supply one.
    """
    if ":" in value:
        raise PydanticCustomError("strategy_name", "base64 encoded strategies are not allowed.")
    return value


# A strategy name as accepted from an API caller. Every request parameter or payload
# field carrying a strategy name must use this instead of a plain `str`.
StrategyName = Annotated[str, AfterValidator(_no_base64_strategy)]


class ExchangeModePayloadMixin(BaseModel):
    trading_mode: TradingMode | None = None
    margin_mode: MarginMode | None = None
    exchange: str | None = None


class Ping(BaseModel):
    status: str


class AccessToken(BaseModel):
    access_token: str


class AccessAndRefreshToken(AccessToken):
    refresh_token: str


class Version(BaseModel):
    version: str


class StatusMsg(BaseModel):
    status: str


class BgJobStarted(StatusMsg):
    job_id: str


class BackgroundTaskStatus(BaseModel):
    job_id: str
    job_category: JOB_CATEGORIES
    status: str
    running: bool
    progress: float | None = None
    progress_tasks: dict[str, ProgressTask] | None = None
    error: str | None = None


class BackgroundTaskResult(BaseModel):
    error: str | None = None
    status: str


class ResultMsg(BaseModel):
    result: str


class Balance(BaseModel):
    currency: str
    free: float
    balance: float
    used: float
    bot_owned: float | None = None
    est_stake: float
    est_stake_bot: float | None = None
    stake: str
    # Starting with 2.x
    side: str
    is_position: bool
    position: float
    is_bot_managed: bool


class Balances(BaseModel):
    currencies: list[Balance]
    total: float
    total_bot: float
    symbol: str
    value: float
    value_bot: float
    stake: str
    note: str
    starting_capital: float
    starting_capital_ratio: float
    starting_capital_pct: float
    starting_capital_fiat: float
    starting_capital_fiat_ratio: float
    starting_capital_fiat_pct: float


class Count(BaseModel):
    current: int
    max: int
    total_stake: float


class __BaseStatsModel(BaseModel):
    profit_ratio: float
    profit_pct: float
    profit_abs: float
    count: int


class Entry(__BaseStatsModel):
    enter_tag: str


class Exit(__BaseStatsModel):
    exit_reason: str


class MixTag(__BaseStatsModel):
    mix_tag: str


class PerformanceEntry(__BaseStatsModel):
    pair: str
    profit: float


class Profit(BaseModel):
    profit_closed_coin: float
    profit_closed_percent_mean: float
    profit_closed_ratio_mean: float
    profit_closed_percent_sum: float
    profit_closed_ratio_sum: float
    profit_closed_percent: float
    profit_closed_ratio: float
    profit_closed_fiat: float
    profit_all_coin: float
    profit_all_percent_mean: float
    profit_all_ratio_mean: float
    profit_all_percent_sum: float
    profit_all_ratio_sum: float
    profit_all_percent: float
    profit_all_ratio: float
    profit_all_fiat: float
    trade_count: int
    closed_trade_count: int
    first_trade_date: str
    first_trade_humanized: str
    first_trade_timestamp: int
    latest_trade_date: str
    latest_trade_humanized: str
    latest_trade_timestamp: int
    avg_duration: str
    best_pair: str
    best_rate: float
    best_pair_profit_ratio: float
    best_pair_profit_abs: float
    winning_trades: int
    losing_trades: int
    profit_factor: float
    winrate: float
    expectancy: float
    expectancy_ratio: float
    sharpe: float
    sortino: float
    sqn: float
    calmar: float
    cagr: float
    max_drawdown: float
    max_drawdown_abs: float
    max_drawdown_start: str
    max_drawdown_start_timestamp: int
    max_drawdown_end: str
    max_drawdown_end_timestamp: int
    current_drawdown: float
    current_drawdown_abs: float
    current_drawdown_high: float
    current_drawdown_start: str
    current_drawdown_start_timestamp: int
    trading_volume: float | None = None
    bot_start_timestamp: int
    bot_start_date: str


class ProfitAll(BaseModel):
    all: Profit
    long: Profit | None = None
    short: Profit | None = None


class SellReason(BaseModel):
    wins: int
    losses: int
    draws: int


class Stats(BaseModel):
    exit_reasons: dict[str, SellReason]
    durations: dict[str, float | None]


class DailyWeeklyMonthlyRecord(BaseModel):
    date: date
    abs_profit: float
    rel_profit: float
    starting_balance: float
    fiat_value: float
    trade_count: int


class DailyWeeklyMonthly(BaseModel):
    data: list[DailyWeeklyMonthlyRecord]
    fiat_display_currency: str
    stake_currency: str


class UnfilledTimeout(BaseModel):
    entry: int | None = None
    exit: int | None = None
    unit: str | None = None
    exit_timeout_count: int | None = None


class OrderTypes(BaseModel):
    entry: OrderTypeValues
    exit: OrderTypeValues
    emergency_exit: OrderTypeValues | None = None
    force_exit: OrderTypeValues | None = None
    force_entry: OrderTypeValues | None = None
    stoploss: OrderTypeValues
    stoploss_on_exchange: bool
    stoploss_on_exchange_interval: int | None = None


class ShowConfig(BaseModel):
    version: str
    strategy_version: str | None = None
    api_version: float
    dry_run: bool
    trading_mode: str
    margin_mode: str
    short_allowed: bool
    stake_currency: str
    proxy_coin: str | None = None
    stake_amount: str
    available_capital: float | None = None
    stake_currency_decimals: int
    max_open_trades: IntOrInf
    minimal_roi: dict[str, Any]
    stoploss: float | None = None
    stoploss_on_exchange: bool
    trailing_stop: bool | None = None
    trailing_stop_positive: float | None = None
    trailing_stop_positive_offset: float | None = None
    trailing_only_offset_is_reached: bool | None = None
    unfilledtimeout: UnfilledTimeout | None = None  # Empty in webserver mode
    order_types: OrderTypes | None = None
    use_custom_stoploss: bool | None = None
    timeframe: str | None = None
    timeframe_ms: int
    timeframe_min: int
    exchange: str
    demo_trading: bool
    strategy: str | None = None
    force_entry_enable: bool
    exit_pricing: dict[str, Any]
    entry_pricing: dict[str, Any]
    bot_name: str
    state: str
    runmode: str
    position_adjustment_enable: bool
    max_entry_position_adjustment: int


class OrderSchema(BaseModel):
    pair: str
    order_id: str
    status: str
    remaining: float | None = None
    amount: float
    safe_price: float
    cost: float
    filled: float | None = None
    ft_order_side: str
    order_type: str
    is_open: bool
    order_timestamp: int | None = None
    order_filled_timestamp: int | None = None
    ft_fee_base: float | None = None
    ft_order_tag: str | None = None


class TradeSchema(BaseModel):
    trade_id: int
    pair: str
    base_currency: str
    quote_currency: str
    is_open: bool
    is_short: bool
    exchange: str
    amount: float
    amount_requested: float
    stake_amount: float
    max_stake_amount: float | None = None
    strategy: str
    enter_tag: str | None = None
    timeframe: int
    fee_open: float | None = None
    fee_open_cost: float | None = None
    fee_open_currency: str | None = None
    fee_close: float | None = None
    fee_close_cost: float | None = None
    fee_close_currency: str | None = None

    open_date: str
    open_timestamp: int
    open_fill_date: str | None
    open_fill_timestamp: int | None
    open_rate: float
    open_rate_requested: float | None = None
    open_trade_value: float

    close_date: str | None = None
    close_timestamp: int | None = None
    close_rate: float | None = None
    close_rate_requested: float | None = None

    close_profit: float | None = None
    close_profit_pct: float | None = None
    close_profit_abs: float | None = None

    profit_ratio: float | None = None
    profit_pct: float | None = None
    profit_abs: float | None = None
    profit_fiat: float | None = None

    realized_profit: float
    realized_profit_ratio: float | None = None

    exit_reason: str | None = None
    exit_order_status: str | None = None

    stop_loss_abs: float | None = None
    stop_loss_ratio: float | None = None
    stop_loss_pct: float | None = None
    stoploss_last_update: str | None = None
    stoploss_last_update_timestamp: int | None = None
    initial_stop_loss_abs: float | None = None
    initial_stop_loss_ratio: float | None = None
    initial_stop_loss_pct: float | None = None

    min_rate: float | None = None
    max_rate: float | None = None
    nr_of_successful_entries: int
    nr_of_successful_exits: int
    has_open_orders: bool
    orders: list[OrderSchema]

    leverage: float | None = None
    interest_rate: float | None = None
    liquidation_price: float | None = None
    funding_fees: float | None = None
    trading_mode: TradingMode | None = None

    amount_precision: float | None = None
    price_precision: float | None = None
    precision_mode: int | None = None


class OpenTradeSchema(TradeSchema):
    stoploss_current_dist: float | None = None
    stoploss_current_dist_pct: float | None = None
    stoploss_current_dist_ratio: float | None = None
    stoploss_entry_dist: float | None = None
    stoploss_entry_dist_ratio: float | None = None
    current_rate: float
    total_profit_abs: float
    total_profit_fiat: float | None = None
    total_profit_ratio: float | None = None


class TradeResponse(BaseModel):
    trades: list[TradeSchema]
    trades_count: int
    offset: int
    total_trades: int


ForceEnterResponse = RootModel[TradeSchema | StatusMsg]


class LockModel(BaseModel):
    id: int
    active: bool
    lock_end_time: str
    lock_end_timestamp: int
    lock_time: str
    lock_timestamp: int
    pair: str
    side: str
    reason: str | None = None


class Locks(BaseModel):
    lock_count: int
    locks: list[LockModel]


class ReadOnlyMetric(BaseModel):
    value: float | int | None = None
    status: Literal["available", "partial", "unavailable", "unconfigured"]
    source: str
    reason: str | None = None


class PositionCapacityMetric(BaseModel):
    used: int
    limit: int | None = None
    utilization_pct: float | None = None
    status: Literal["available", "partial", "unavailable"]
    source: str
    reason: str | None = None


class ReadOnlyCapability(BaseModel):
    status: Literal["available", "partial", "unavailable", "unconfigured"]
    source: str
    reason: str | None = None


class EffectiveRiskSnapshot(BaseModel):
    generated_timestamp: int
    event_timestamp: int | None = None
    status: Literal["available", "partial", "unavailable"]
    current_drawdown: ReadOnlyMetric
    max_drawdown: ReadOnlyMetric
    max_drawdown_abs: ReadOnlyMetric
    position_capacity: PositionCapacityMetric
    nominal_exposure: ReadOnlyMetric
    today_realized_profit: ReadOnlyMetric
    consecutive_losses: ReadOnlyMetric
    active_locks: list[LockModel]
    locks_status: ReadOnlyCapability
    risk_limit: ReadOnlyCapability


class DecisionJournalEvent(BaseModel):
    id: str
    event_timestamp: int
    strategy: str
    pair: str
    side: Literal["long", "short"]
    stage: Literal["entry", "position", "exit"]
    result: str
    enter_tag: str | None = None
    signal_source: str | None = None
    decision_reason: str | None = None
    rejection_reason: str | None = None
    trade_id: int
    order_id: str | None = None
    order_status: str | None = None
    order_side: str | None = None
    open_rate: float
    close_rate: float | None = None
    profit_ratio: float | None = None
    profit_abs: float | None = None
    source: Literal["trade_persistence"]


class DecisionJournal(BaseModel):
    generated_timestamp: int
    events: list[DecisionJournalEvent]
    offset: int
    count: int
    capabilities: dict[str, ReadOnlyCapability]


MarketObserverTimeframe = Annotated[str, Field(pattern=r"^[1-9]\d*[mhdwM]$")]


class MarketPairObservation(BaseModel):
    pair: str
    timeframe: str
    status: Literal["available", "unavailable"]
    freshness: Literal["fresh", "stale", "unavailable"]
    event_timestamp: int | None = None
    sample_count: int
    close: float | None = None
    change_pct: float | None = None
    range_pct: float | None = None
    volume: float | None = None
    volume_ratio: float | None = None
    source: str
    reason: str | None = None


class MarketBreadth(BaseModel):
    observed: int
    advancing: int
    declining: int
    unchanged: int
    unavailable: int


class MarketTimeframeSummary(BaseModel):
    timeframe: str
    requested_pairs: int
    available: int
    fresh: int
    stale: int
    unavailable: int
    coverage_pct: float
    breadth: MarketBreadth


class MarketObserverHealth(BaseModel):
    requested_timestamp: int
    generated_timestamp: int
    generation_duration_ms: int
    requested_observations: int
    available: int
    fresh: int
    stale: int
    unavailable: int
    coverage_pct: float


class MarketObserverSnapshot(BaseModel):
    mode: Literal["observe_only"]
    affects_trading: Literal[False]
    generated_timestamp: int
    event_timestamp: int | None = None
    status: Literal["available", "partial", "unavailable"]
    timeframe: str
    lookback_candles: int
    pairs: list[MarketPairObservation]
    breadth: MarketBreadth
    timeframes: list[MarketTimeframeSummary]
    health: MarketObserverHealth
    capabilities: dict[str, ReadOnlyCapability]


class ExecutionFeeTotal(BaseModel):
    currency: str
    value: float
    source: str


class OrderLifecycleSummary(BaseModel):
    total: int
    open: int
    filled: int
    cancelled: int
    other: int


class ExecutionQualitySample(BaseModel):
    id: str
    event_timestamp: int
    trade_id: int
    order_id: str | None = None
    pair: str
    side: str
    lifecycle: Literal["open", "filled", "cancelled", "other"]
    created_timestamp: int | None = None
    filled_timestamp: int | None = None
    fill_latency_ms: int | None = None
    requested_price: float | None = None
    average_price: float | None = None
    price_deviation_bps: float | None = None
    source: Literal["order_persistence"]


class ExecutionQualityCoverage(BaseModel):
    sampled_trades: int
    sampled_orders: int
    fee_records: int
    latency_records: int
    price_deviation_records: int


class ExecutionQualitySnapshot(BaseModel):
    mode: Literal["read_only"]
    affects_trading: Literal[False]
    generated_timestamp: int
    event_timestamp: int | None = None
    status: Literal["available", "partial", "unavailable"]
    fee_totals: list[ExecutionFeeTotal]
    fee_status: ReadOnlyCapability
    average_fill_latency_ms: ReadOnlyMetric
    p95_fill_latency_ms: ReadOnlyMetric
    average_price_deviation_bps: ReadOnlyMetric
    lifecycle: OrderLifecycleSummary
    coverage: ExecutionQualityCoverage
    recent_orders: list[ExecutionQualitySample]
    capabilities: dict[str, ReadOnlyCapability]


class StrategyGovernanceIdentity(BaseModel):
    identifier: str
    class_name: str
    version: str | None = None
    fingerprint: str | None = None
    fingerprint_algorithm: Literal["sha256"] | None = None
    fingerprint_status: ReadOnlyCapability


class StrategyBacktestEvidence(BaseModel):
    status: Literal["available", "partial", "unavailable", "not_recorded"]
    source: str
    reason: str | None = None
    result_file: str | None = None
    run_id: str | None = None
    run_timestamp: int | None = None
    sample_start_timestamp: int | None = None
    sample_end_timestamp: int | None = None
    timeframe: str | None = None
    trade_count: ReadOnlyMetric
    profit_ratio: ReadOnlyMetric
    max_drawdown: ReadOnlyMetric
    win_rate: ReadOnlyMetric


class StrategyGovernanceGate(BaseModel):
    id: Literal[
        "backtest",
        "out_of_sample",
        "stress_test",
        "paper_trading",
        "limited_capital",
        "human_approval",
        "rollback_point",
    ]
    label: str
    status: Literal["available", "partial", "unavailable", "not_recorded"]
    source: str
    reason: str | None = None


class StrategyGovernanceSnapshot(BaseModel):
    mode: Literal["read_only"]
    affects_trading: Literal[False]
    promotion_allowed: Literal[False]
    generated_timestamp: int
    status: Literal["available", "partial", "unavailable"]
    strategy: StrategyGovernanceIdentity
    latest_backtest: StrategyBacktestEvidence
    gates: list[StrategyGovernanceGate]
    capabilities: dict[str, ReadOnlyCapability]


class SystemObservabilityAlert(BaseModel):
    id: str
    severity: Literal["warning", "error"]
    title: str
    count: int
    event_timestamp: int | None = None
    source: str


class SystemObservabilitySnapshot(BaseModel):
    mode: Literal["read_only"]
    affects_trading: Literal[False]
    generated_timestamp: int
    status: Literal["available", "partial", "unavailable"]
    runtime_state: str
    heartbeat_age_ms: ReadOnlyMetric
    uptime_ms: ReadOnlyMetric
    database_status: ReadOnlyCapability
    open_trade_count: ReadOnlyMetric
    active_lock_count: ReadOnlyMetric
    active_pair_count: ReadOnlyMetric
    cpu_pct: ReadOnlyMetric
    ram_pct: ReadOnlyMetric
    log_window: dict[str, int | None]
    log_levels: dict[str, int]
    alerts: list[SystemObservabilityAlert]
    capabilities: dict[str, ReadOnlyCapability]


class LocksPayload(BaseModel):
    pair: str
    side: str = "*"  # Default to both sides
    until: AwareDatetime
    reason: str | None = None


class DeleteLockRequest(BaseModel):
    pair: str | None = None
    lockid: int | None = None


class Logs(BaseModel):
    log_count: int
    logs: list[list]


class ForceEnterPayload(BaseModel):
    pair: str
    side: SignalDirection = SignalDirection.LONG
    price: float | None = None
    ordertype: OrderTypeValues | None = None
    stakeamount: float | None = None
    entry_tag: str | None = None
    leverage: float | None = None


class ForceExitPayload(BaseModel):
    tradeid: str | int
    ordertype: OrderTypeValues | None = None
    amount: float | None = None
    price: float | None = None


class BlacklistPayload(BaseModel):
    blacklist: list[str]


class BlacklistResponse(BaseModel):
    blacklist: list[str]
    blacklist_expanded: list[str]
    errors: dict
    length: int
    method: list[str]


class WhitelistResponse(BaseModel):
    whitelist: list[str]
    length: int
    method: list[str]


class WhitelistEvaluateResponse(BackgroundTaskResult):
    result: WhitelistResponse | None = None


class DeleteTrade(BaseModel):
    cancel_order_count: int
    result: str
    result_msg: str
    trade_id: int


class PlotConfig_(BaseModel):
    main_plot: dict[str, Any]
    subplots: dict[str, Any]


PlotConfig = RootModel[PlotConfig_ | dict]


class StrategyListResponse(BaseModel):
    strategies: list[str]


class ExchangeListResponse(BaseModel):
    exchanges: list[ValidExchangesType]


class HyperoptLoss(BaseModel):
    name: str
    description: str


class HyperoptLossListResponse(BaseModel):
    loss_functions: list[HyperoptLoss]


class PairListResponse(BaseModel):
    name: str
    description: str
    is_pairlist_generator: bool
    params: dict[str, Any]


class PairListsResponse(BaseModel):
    pairlists: list[PairListResponse]


class PairListsPayload(ExchangeModePayloadMixin, BaseModel):
    pairlists: list[dict[str, Any]]
    blacklist: list[str]
    stake_currency: str


class DownloadDataPayload(ExchangeModePayloadMixin, BaseModel):
    pairs: list[str]
    timeframes: list[str] | None = DL_DATA_TIMEFRAMES
    days: int | None = None
    timerange: str | None = None
    erase: bool = False
    download_trades: bool = False
    candle_types: list[str] | None = None
    prepend_data: bool = False

    @model_validator(mode="before")
    def check_mutually_exclusive(cls, values):
        timeframes, days = values.get("timerange"), values.get("days")
        if timeframes and days:
            raise ValueError("Only one of timeframes or days can be provided, not both.")
        return values


class FreqAIModelListResponse(BaseModel):
    freqaimodels: list[str]


class __StrategyParameter(BaseModel):
    param_type: str
    name: str
    space: str
    load: bool
    optimize: bool


class IntParameter(__StrategyParameter):
    param_type: Literal["IntParameter"]
    value: int
    low: int
    high: int


class RealParameter(__StrategyParameter):
    param_type: Literal["RealParameter"]
    value: float
    low: float
    high: float


class DecimalParameter(__StrategyParameter):
    param_type: Literal["DecimalParameter"]
    value: float
    low: float
    high: float
    decimals: int


class BooleanParameter(__StrategyParameter):
    param_type: Literal["BooleanParameter"]
    value: bool | None
    opt_range: list[bool]


class CategoricalParameter(__StrategyParameter):
    param_type: Literal["CategoricalParameter"]
    value: Any
    opt_range: list[Any]


AllParameters = Annotated[
    BooleanParameter | CategoricalParameter | DecimalParameter | IntParameter | RealParameter,
    Field(discriminator="param_type"),
]


class StrategyResponse(BaseModel):
    strategy: str
    timeframe: str | None
    params: list[AllParameters] = Field(default_factory=list)
    code: str


class AvailablePairs(BaseModel):
    length: int
    pairs: list[str]
    pair_interval: list[list[str]]


class PairCandlesRequest(BaseModel):
    pair: str
    timeframe: str
    limit: int | None = None
    columns: list[str] | None = None


class PairHistoryRequest(PairCandlesRequest, ExchangeModePayloadMixin):
    timerange: str
    strategy: StrategyName | None = None
    freqaimodel: str | None = None
    live_mode: bool = False


class PairHistory(BaseModel):
    strategy: str
    pair: str
    timeframe: str
    timeframe_ms: int
    columns: list[str]
    all_columns: list[str] = []
    data: SerializeAsAny[list[Any]]
    annotations: list[AnnotationType] | None = None
    length: int
    buy_signals: int
    sell_signals: int
    enter_long_signals: int
    exit_long_signals: int
    enter_short_signals: int
    exit_short_signals: int
    last_analyzed: datetime
    last_analyzed_ts: int
    data_start_ts: int
    data_start: str
    data_stop: str
    data_stop_ts: int


class BacktestFreqAIInputs(BaseModel):
    identifier: str


class BacktestRequest(BaseModel):
    strategy: StrategyName
    timeframe: str | None = None
    timeframe_detail: str | None = None
    timerange: str | None = None
    max_open_trades: IntOrInf | None = None
    stake_amount: str | float | None = None
    enable_protections: bool
    dry_run_wallet: float | None = None
    backtest_cache: str | None = None
    freqaimodel: str | None = None
    freqai: BacktestFreqAIInputs | None = None


class BacktestResponse(BaseModel):
    status: str
    running: bool
    status_msg: str
    step: str
    progress: float
    trade_count: float | None = None
    # TODO: Properly type backtestresult...
    backtest_result: dict[str, Any] | None = None


# TODO: This is a copy of BacktestHistoryEntryType
class BacktestHistoryEntry(BaseModel):
    filename: str
    strategy: str
    run_id: str
    backtest_start_time: int
    notes: str | None = ""
    backtest_start_ts: int | None = None
    backtest_end_ts: int | None = None
    timeframe: str | None = None
    timeframe_detail: str | None = None


class BacktestMetadataUpdate(BaseModel):
    strategy: StrategyName
    notes: str = ""


class BacktestMarketChange(BaseModel):
    columns: list[str]
    length: int
    data: list[list[Any]]


class LookaheadAnalysisRequest(BaseModel):
    strategy: StrategyName
    timeframe: str | None = None
    timerange: str | None = None
    minimum_trade_amount: int = 10
    targeted_trade_amount: int = 20
    lookahead_allow_limit_orders: bool = False


class LookaheadAnalysisResultEntry(BaseModel):
    strategy: str
    has_bias: bool
    total_signals: int
    biased_entry_signals: int
    biased_exit_signals: int
    biased_indicators: list[str]


class LookaheadAnalysisResponse(BaseModel):
    status: str
    running: bool
    status_msg: str
    result: LookaheadAnalysisResultEntry | None = None


class RecursiveAnalysisRequest(BaseModel):
    strategy: StrategyName
    timeframe: str | None = None
    timerange: str | None = None
    startup_candle: list[int] | None = None


class RecursiveAnalysisResultEntry(BaseModel):
    strategy: str
    startup_candles: list[int] = Field(description="The startup candle counts that were tested.")
    strategy_scc: int | None = Field(
        default=None,
        description="The strategy's own startup_candle_count, if it could be determined.",
    )
    results: dict[str, dict[str, float]] = Field(
        description=(
            "Per-indicator variance keyed by indicator name, then by startup candle count. "
            "e.g. { 'rsi': { '199': 0.123, '200': float('nan'), ... }, 'macd': { ... }, ... } }. "
        )
    )


class RecursiveAnalysisResponse(BaseModel):
    status: str
    running: bool
    status_msg: str
    result: RecursiveAnalysisResultEntry | None = None


class WalletHistoryResponse(BaseModel):
    columns: list[str]
    length: int
    data: list[list[Any]]
    # start date of the effectively captured data
    # Before this date, it's based on a reconstructed wallet history
    capture_start_ts: int | None = None


class MarketRequest(ExchangeModePayloadMixin, BaseModel):
    base: str | None = None
    quote: str | None = None
    include_inactive: bool = False


class MarketModel(BaseModel):
    symbol: str
    base: str
    quote: str
    spot: bool
    swap: bool
    active: bool = False  # Assume false if the field is missing.


class MarketResponse(BaseModel):
    markets: dict[str, MarketModel]
    exchange_id: str


class CpuInfo(BaseModel):
    cpu: int
    pct: float


class SysInfo(BaseModel):
    """Information about the system running the bot based on psutil output/measurements

    Note: cpu_pct is deprecated and may be removed in a future release. Use cpu_load instead.
    """

    cpu_pct: list[float] = Field(
        default=[], deprecated=True, description="Use cpu_load object instead"
    )
    cpu_load: list[CpuInfo]
    cpu_load_avg: dict[str, float]
    cpu_count: int = Field(description="Number of logical CPUs as provided by psutil")
    cpu_avg: float = Field(description="Average CPU load across all cores as provided by psutil")
    ram_pct: float = Field(description="RAM usage percentage as provided by psutil")


class Health(BaseModel):
    last_process: datetime | None = None
    last_process_ts: int | None = None
    bot_start: datetime | None = None
    bot_start_ts: int | None = None
    bot_startup: datetime | None = None
    bot_startup_ts: int | None = None


class CustomDataEntry(BaseModel):
    key: str
    type: str
    value: Any
    created_at: datetime
    updated_at: datetime | None = None


class ListCustomData(BaseModel):
    trade_id: int
    custom_data: list[CustomDataEntry]
