import type {
  AuditRecord,
  DailyProfitResponse,
  DataMetric,
  LocksResponse,
  NativeDecisionJournal,
  NativeReadOnlyMetric,
  NativeRiskSnapshot,
  Profit,
  RiskSnapshot,
  ShowConfig,
  Trade,
  TradeResponse,
} from "./types";

const available = <T>(value: T, source: string): DataMetric<T> => ({ value, status: "available", source });
const unavailable = <T>(source: string, reason: string): DataMetric<T> => ({ value: null, status: "unavailable", source, reason });

export function buildAuditRecords(openTrades: Trade[] | null, closedTrades: TradeResponse | null): AuditRecord[] {
  const trades = [...(openTrades ?? []), ...(closedTrades?.trades ?? [])]
    .sort((a, b) => (b.close_timestamp ?? b.open_timestamp) - (a.close_timestamp ?? a.open_timestamp))
    .slice(0, 8);

  return trades.map((trade) => {
    const profitRatio = trade.is_open ? trade.total_profit_ratio : trade.profit_ratio;
    const profitAbs = trade.is_open ? trade.total_profit_abs : trade.profit_abs;
    return {
      id: `trade:${trade.trade_id}`,
      strategy: trade.strategy,
      pair: trade.pair,
      side: trade.is_short ? "short" : "long",
      decisionAt: trade.open_timestamp,
      executionAt: trade.open_fill_timestamp ?? trade.open_timestamp,
      completedAt: trade.close_timestamp,
      executionStatus: trade.is_open ? (trade.has_open_orders ? "open_order" : "open") : "closed",
      signalSource: trade.enter_tag
        ? available(trade.enter_tag, "trade.enter_tag")
        : unavailable("trade.enter_tag", "Freqtrade 未记录入场标签"),
      exitReason: trade.exit_reason
        ? available(trade.exit_reason, "trade.exit_reason")
        : unavailable("trade.exit_reason", trade.is_open ? "持仓尚未退出" : "退出原因未记录"),
      expectedOutcome: unavailable("not_provided", "Freqtrade 交易 API 不提供预期结果"),
      actualProfitRatio: profitRatio != null
        ? available(profitRatio, trade.is_open ? "trade.total_profit_ratio" : "trade.profit_ratio")
        : unavailable("trade.profit_ratio", "盈亏比例不可用"),
      actualProfitAbs: profitAbs != null
        ? available(profitAbs, trade.is_open ? "trade.total_profit_abs" : "trade.profit_abs")
        : unavailable("trade.profit_abs", "盈亏金额不可用"),
      provenance: "client-derived",
    };
  });
}

function consecutiveLossMetric(closedTrades: TradeResponse | null): DataMetric<number> {
  if (!closedTrades) return unavailable("trades", "历史成交接口不可用");
  if (!closedTrades.trades.length) return available(0, "trades");

  const sorted = [...closedTrades.trades].sort((a, b) => (b.close_timestamp ?? 0) - (a.close_timestamp ?? 0));
  let count = 0;
  for (const trade of sorted) {
    if (trade.profit_abs == null) return unavailable("trades.profit_abs", "近期成交缺少盈亏金额");
    if (trade.profit_abs >= 0) return available(count, "trades");
    count += 1;
  }

  return closedTrades.total_trades > sorted.length
    ? unavailable("trades", `最近 ${sorted.length} 笔均为亏损，需更多历史确定连续次数`)
    : available(count, "trades");
}

function nominalExposureMetric(openTrades: Trade[] | null): DataMetric<number> {
  if (!openTrades) return unavailable("status", "当前持仓接口不可用");
  let exposure = 0;
  for (const trade of openTrades) {
    if (trade.amount == null || trade.current_rate == null || !Number.isFinite(trade.amount) || !Number.isFinite(trade.current_rate)) {
      return unavailable("status", "持仓缺少数量或当前价格");
    }
    exposure += Math.abs(trade.amount * trade.current_rate);
  }
  return available(exposure, "status.amount × status.current_rate");
}

export function buildRiskSnapshot(input: {
  asOf: number;
  config: ShowConfig | null;
  profit: Profit | null;
  openTrades: Trade[] | null;
  closedTrades: TradeResponse | null;
  daily: DailyProfitResponse | null;
  locks: LocksResponse | null;
  provenance?: "client-derived" | "demo";
}): RiskSnapshot {
  const { asOf, config, profit, openTrades, closedTrades, daily, locks, provenance = "client-derived" } = input;
  const limit = Number(config?.max_open_trades);
  const validLimit = Number.isFinite(limit) && limit > 0;
  const today = daily?.data[0];

  return {
    asOf,
    eventAt: null,
    staleAfterMs: 90_000,
    provenance,
    currentDrawdown: profit
      ? available(profit.current_drawdown, "profit.current_drawdown")
      : unavailable("profit", "收益统计接口不可用"),
    maxDrawdown: profit
      ? available(profit.max_drawdown, "profit.max_drawdown")
      : unavailable("profit", "收益统计接口不可用"),
    maxDrawdownAbs: profit
      ? available(profit.max_drawdown_abs, "profit.max_drawdown_abs")
      : unavailable("profit", "收益统计接口不可用"),
    positionCapacity: openTrades && validLimit
      ? available({ used: openTrades.length, limit, utilizationPct: Math.min(openTrades.length / limit * 100, 100) }, "status + show_config")
      : unavailable("status + show_config", openTrades ? "最大持仓配置不可用" : "当前持仓接口不可用"),
    nominalExposure: nominalExposureMetric(openTrades),
    todayProfit: today
      ? available(today.abs_profit, "daily.abs_profit")
      : unavailable("daily", daily ? "当日统计为空" : "当日收益接口不可用"),
    todayLoss: today
      ? available(Math.min(today.abs_profit, 0), "daily.abs_profit")
      : unavailable("daily", daily ? "当日统计为空" : "当日收益接口不可用"),
    consecutiveLosses: consecutiveLossMetric(closedTrades),
    tradeLocks: locks
      ? available({ count: locks.lock_count, locks: locks.locks.filter((lock) => lock.active) }, "locks")
      : unavailable("locks", "交易锁接口不可用"),
    riskBudget: { value: null, status: "unconfigured", source: "not_provided", reason: "Freqtrade API 不提供组合风险预算" },
  };
}

function nativeMetric(metric: NativeReadOnlyMetric): DataMetric<number> {
  return {
    value: metric.value,
    status: metric.status,
    source: metric.source,
    reason: metric.reason ?? undefined,
  };
}

export function mapNativeRiskSnapshot(snapshot: NativeRiskSnapshot): RiskSnapshot {
  return {
    asOf: snapshot.generated_timestamp,
    eventAt: snapshot.event_timestamp,
    staleAfterMs: 90_000,
    provenance: "server-native",
    currentDrawdown: nativeMetric(snapshot.current_drawdown),
    maxDrawdown: nativeMetric(snapshot.max_drawdown),
    maxDrawdownAbs: nativeMetric(snapshot.max_drawdown_abs),
    positionCapacity: {
      value: {
        used: snapshot.position_capacity.used,
        limit: snapshot.position_capacity.limit,
        utilizationPct: snapshot.position_capacity.utilization_pct,
      },
      status: snapshot.position_capacity.status,
      source: snapshot.position_capacity.source,
      reason: snapshot.position_capacity.reason ?? undefined,
    },
    nominalExposure: nativeMetric(snapshot.nominal_exposure),
    todayProfit: nativeMetric(snapshot.today_realized_profit),
    todayLoss: {
      ...nativeMetric(snapshot.today_realized_profit),
      value: snapshot.today_realized_profit.value == null ? null : Math.min(snapshot.today_realized_profit.value, 0),
    },
    consecutiveLosses: nativeMetric(snapshot.consecutive_losses),
    tradeLocks: {
      value: snapshot.locks_status.status === "unavailable"
        ? null
        : { count: snapshot.active_locks.length, locks: snapshot.active_locks },
      status: snapshot.locks_status.status,
      source: snapshot.locks_status.source,
      reason: snapshot.locks_status.reason ?? undefined,
    },
    riskBudget: {
      value: null,
      status: snapshot.risk_limit.status,
      source: snapshot.risk_limit.source,
      reason: snapshot.risk_limit.reason ?? undefined,
    },
  };
}

export function mapNativeDecisionJournal(journal: NativeDecisionJournal): AuditRecord[] {
  return journal.events.map((event) => ({
    id: event.id,
    strategy: event.strategy,
    pair: event.pair,
    side: event.side,
    decisionAt: event.event_timestamp,
    executionAt: event.event_timestamp,
    completedAt: event.stage === "exit" ? event.event_timestamp : null,
    executionStatus: event.stage === "exit"
      ? "closed"
      : event.result === "pending_order"
        ? "open_order"
        : "open",
    signalSource: event.signal_source
      ? available(event.signal_source, "decision_journal.signal_source")
      : unavailable("decision_journal.signal_source", "持久化交易未记录入场标签"),
    exitReason: event.stage === "exit" && event.decision_reason
      ? available(event.decision_reason, "decision_journal.decision_reason")
      : unavailable("decision_journal.decision_reason", event.stage === "exit" ? "退出原因未记录" : "持仓尚未退出"),
    expectedOutcome: unavailable("decision_journal", "服务端未持久化预期结果"),
    actualProfitRatio: event.profit_ratio != null
      ? available(event.profit_ratio, "decision_journal.profit_ratio")
      : unavailable("decision_journal.profit_ratio", "实际盈亏比例不可用"),
    actualProfitAbs: event.profit_abs != null
      ? available(event.profit_abs, "decision_journal.profit_abs")
      : unavailable("decision_journal.profit_abs", "实际盈亏金额不可用"),
    provenance: "server-native",
  }));
}
