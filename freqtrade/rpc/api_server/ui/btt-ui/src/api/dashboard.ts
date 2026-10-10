import { ApiError, request } from "./client";
import { createDemoDashboard } from "./demo";
import {
  buildAuditRecords,
  buildRiskSnapshot,
  mapNativeDecisionJournal,
  mapNativeRiskSnapshot,
} from "./risk";
import type {
  Balances,
  DailyProfitResponse,
  DashboardData,
  EquityPoint,
  ExecutionQualitySnapshot,
  Health,
  LocksResponse,
  MarketObserverSnapshot,
  NativeDecisionJournal,
  NativeRiskSnapshot,
  Profit,
  ShowConfig,
  StrategyGovernanceSnapshot,
  SystemObservabilitySnapshot,
  SysInfo,
  Trade,
  TradeResponse,
  WalletHistory,
} from "./types";

type EndpointSpec<T> = { name: string; path: string };

async function capture<T>(spec: EndpointSpec<T>, errors: DashboardData["errors"]): Promise<T | null> {
  try {
    return await request<T>(spec.path);
  } catch (error) {
    errors.push({ endpoint: spec.name, message: error instanceof Error ? error.message : "未知错误" });
    return null;
  }
}

type NativeResult<T> = { data: T | null; fallbackReason?: string };

async function captureNative<T>(spec: EndpointSpec<T>, errors: DashboardData["errors"]): Promise<NativeResult<T>> {
  try {
    return { data: await request<T>(spec.path) };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return { data: null, fallbackReason: "当前后端版本不提供原生端点（404）" };
    }
    errors.push({ endpoint: spec.name, message: error instanceof Error ? error.message : "未知错误" });
    return { data: null, fallbackReason: "原生端点不可用" };
  }
}

export function parseEquity(history: WalletHistory | null): EquityPoint[] {
  if (!history?.data.length) return [];
  const timeIndex = history.columns.findIndex((name) => ["__date_ts", "timestamp", "date"].includes(name));
  const valueIndex = history.columns.findIndex((name) => ["total_quote", "total", "balance", "value"].includes(name));
  if (timeIndex < 0 || valueIndex < 0) return [];
  return history.data.flatMap((row) => {
    const value = Number(row[valueIndex]);
    const rawTime = row[timeIndex];
    const timestamp = typeof rawTime === "number" ? (rawTime < 10_000_000_000 ? rawTime * 1000 : rawTime) : Date.parse(String(rawTime));
    return Number.isFinite(value) && Number.isFinite(timestamp) ? [{ timestamp, value }] : [];
  }).sort((a, b) => a.timestamp - b.timestamp);
}

export async function loadDashboard(useDemo = false): Promise<DashboardData> {
  if (useDemo) return createDemoDashboard();

  const errors: DashboardData["errors"] = [];
  const [
    pingPayload,
    config,
    balances,
    profit,
    openTrades,
    closedTrades,
    history,
    health,
    sysinfo,
    daily,
    locks,
    nativeRisk,
    nativeJournal,
    nativeMarket,
    nativeExecutionQuality,
    nativeGovernance,
    nativeObservability,
  ] = await Promise.all([
    capture<{ status: string }>({ name: "API", path: "/ping" }, errors),
    capture<ShowConfig>({ name: "运行配置", path: "/show_config" }, errors),
    capture<Balances>({ name: "账户余额", path: "/balance" }, errors),
    capture<Profit>({ name: "收益统计", path: "/profit" }, errors),
    capture<Trade[]>({ name: "当前持仓", path: "/status" }, errors),
    capture<TradeResponse>({ name: "历史成交", path: "/trades?limit=50&order_by_id=false" }, errors),
    capture<WalletHistory>({ name: "权益历史", path: "/historic_balance" }, errors),
    capture<Health>({ name: "机器人健康", path: "/health" }, errors),
    capture<SysInfo>({ name: "系统资源", path: "/sysinfo" }, errors),
    capture<DailyProfitResponse>({ name: "当日收益", path: "/daily?timescale=1" }, errors),
    capture<LocksResponse>({ name: "交易锁", path: "/locks" }, errors),
    captureNative<NativeRiskSnapshot>({ name: "原生风险快照", path: "/effective_risk" }, errors),
    captureNative<NativeDecisionJournal>({ name: "原生决策日志", path: "/decision_journal?limit=8" }, errors),
    captureNative<MarketObserverSnapshot>({ name: "市场观察", path: "/market_observer?pair_limit=8&lookback_candles=20" }, errors),
    captureNative<ExecutionQualitySnapshot>({ name: "执行质量", path: "/execution_quality?trade_limit=200" }, errors),
    captureNative<StrategyGovernanceSnapshot>({ name: "策略治理", path: "/strategy_governance" }, errors),
    captureNative<SystemObservabilitySnapshot>({ name: "系统可观测性", path: "/system_observability?log_limit=200" }, errors),
  ]);

  const updatedAt = Date.now();
  const fallbackRisk = buildRiskSnapshot({
    asOf: updatedAt,
    config,
    profit,
    openTrades,
    closedTrades,
    daily,
    locks,
  });
  const risk = nativeRisk.data
    ? mapNativeRiskSnapshot(nativeRisk.data)
    : { ...fallbackRisk, degradationReason: nativeRisk.fallbackReason };
  const fallbackAudit = buildAuditRecords(openTrades, closedTrades);
  const audit = nativeJournal.data ? mapNativeDecisionJournal(nativeJournal.data) : fallbackAudit;
  const fallbackAuditStatus = openTrades === null && closedTrades === null
    ? "unavailable"
    : openTrades === null || closedTrades === null
      ? "partial"
      : "available";

  return {
    config,
    balances,
    profit,
    openTrades: openTrades ?? [],
    closedTrades: closedTrades?.trades ?? [],
    equity: parseEquity(history),
    health,
    sysinfo,
    ping: pingPayload?.status === "pong",
    risk,
    audit,
    auditStatus: nativeJournal.data ? "available" : fallbackAuditStatus,
    auditProvenance: nativeJournal.data ? "server-native" : "client-derived",
    auditCapabilities: nativeJournal.data?.capabilities ?? {
      rejected_or_unfilled_signals: {
        status: "unavailable",
        source: "client-derived",
        reason: nativeJournal.fallbackReason ?? "旧版 API 不提供未成交或被拒绝决策事件",
      },
    },
    market: nativeMarket.data,
    marketProvenance: nativeMarket.data ? "server-native" : "unavailable",
    marketDegradationReason: nativeMarket.fallbackReason,
    executionQuality: nativeExecutionQuality.data,
    executionQualityProvenance: nativeExecutionQuality.data ? "server-native" : "unavailable",
    executionQualityDegradationReason: nativeExecutionQuality.fallbackReason,
    governance: nativeGovernance.data,
    governanceProvenance: nativeGovernance.data ? "server-native" : "unavailable",
    governanceDegradationReason: nativeGovernance.fallbackReason,
    observability: nativeObservability.data,
    observabilityProvenance: nativeObservability.data ? "server-native" : "unavailable",
    observabilityDegradationReason: nativeObservability.fallbackReason,
    errors,
    updatedAt,
    source: "live",
  };
}
