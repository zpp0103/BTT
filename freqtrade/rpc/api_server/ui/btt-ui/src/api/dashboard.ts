import { request } from "./client";
import { createDemoDashboard } from "./demo";
import type {
  Balances,
  DashboardData,
  EquityPoint,
  Health,
  Profit,
  ShowConfig,
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
  ] = await Promise.all([
    capture<{ status: string }>({ name: "API", path: "/ping" }, errors),
    capture<ShowConfig>({ name: "运行配置", path: "/show_config" }, errors),
    capture<Balances>({ name: "账户余额", path: "/balance" }, errors),
    capture<Profit>({ name: "收益统计", path: "/profit" }, errors),
    capture<Trade[]>({ name: "当前持仓", path: "/status" }, errors),
    capture<TradeResponse>({ name: "历史成交", path: "/trades?limit=8&order_by_id=false" }, errors),
    capture<WalletHistory>({ name: "权益历史", path: "/historic_balance" }, errors),
    capture<Health>({ name: "机器人健康", path: "/health" }, errors),
    capture<SysInfo>({ name: "系统资源", path: "/sysinfo" }, errors),
  ]);

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
    errors,
    updatedAt: Date.now(),
    source: "live",
  };
}
