import { request } from "./client";

export type ProviderStatus = "connected" | "unconfigured" | "error";
export type FreshnessStatus = "fresh" | "stale" | "unavailable";
export type Sentiment = "positive" | "neutral" | "negative";
export type Impact = "low" | "medium" | "high" | "critical";

export interface ProviderConnection {
  provider_id: string;
  label: string;
  status: ProviderStatus;
  message: string;
  last_success_at: string | null;
  latency_ms: number | null;
}

export interface MarketEvent {
  event_id: string;
  headline: string;
  summary: string;
  source: string;
  source_url: string | null;
  published_at: string;
  received_at: string;
  symbols: string[];
  sentiment: Sentiment;
  impact: Impact;
}

export interface RoundtableOpinion {
  role_id: string;
  role: string;
  status: "ready" | "unavailable";
  thesis: string;
  confidence: number | null;
  evidence: Array<{ event_id: string; source: string; headline: string }>;
  valid_until: string | null;
  simulated: boolean;
}

export interface MarketIntelligence {
  snapshot_id: string;
  source_mode: "live" | "demo";
  generated_at: string;
  market_summary: string;
  market_regime: "risk_on" | "neutral" | "risk_off" | "unavailable";
  freshness: {
    status: FreshnessStatus;
    age_seconds: number | null;
    max_age_seconds: number;
  };
  providers: ProviderConnection[];
  events: MarketEvent[];
  roundtable: {
    status: "ready" | "unavailable";
    consensus: string;
    disagreements: string[];
    suggested_action: "observe" | "hold" | "reduce" | "enter" | "exit";
    opinions: RoundtableOpinion[];
  };
  risk_decision: {
    status: "approved" | "rejected" | "unavailable";
    approved: boolean;
    veto_reasons: string[];
    constraints: {
      max_position_pct: number;
      max_drawdown_pct: number;
      max_daily_loss_pct: number;
      max_data_age_seconds: number;
      circuit_breaker_enabled: boolean;
    };
  };
  execution: {
    mode: "observe_only";
    status: "disabled";
    message: string;
  };
}

const demoNow = () => new Date();
const isoBefore = (now: Date, seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString();
const isoAfter = (now: Date, seconds: number) => new Date(now.getTime() + seconds * 1000).toISOString();

export function createDemoIntelligence(): MarketIntelligence {
  const now = demoNow();
  const events: MarketEvent[] = [
    {
      event_id: "demo-fed-minutes",
      headline: "美联储会议纪要维持数据依赖立场",
      summary: "政策路径仍取决于通胀与就业数据，风险资产短线波动可能放大。",
      source: "DEMO · Macro Wire",
      source_url: null,
      published_at: isoBefore(now, 95),
      received_at: isoBefore(now, 82),
      symbols: ["BTC", "ETH"],
      sentiment: "neutral",
      impact: "high",
    },
    {
      event_id: "demo-exchange-flow",
      headline: "主要交易所 BTC 净流入短时上升",
      summary: "演示链上流量提示潜在卖压，需结合价格与衍生品仓位确认。",
      source: "DEMO · Chain Monitor",
      source_url: null,
      published_at: isoBefore(now, 210),
      received_at: isoBefore(now, 188),
      symbols: ["BTC"],
      sentiment: "negative",
      impact: "medium",
    },
    {
      event_id: "demo-protocol",
      headline: "以太坊核心开发者公布测试网升级窗口",
      summary: "升级计划进入测试阶段，当前尚未形成可直接交易的确定性催化。",
      source: "DEMO · Protocol Bulletin",
      source_url: null,
      published_at: isoBefore(now, 420),
      received_at: isoBefore(now, 401),
      symbols: ["ETH"],
      sentiment: "positive",
      impact: "medium",
    },
  ];
  const evidence = events.map(({ event_id, source, headline }) => ({ event_id, source, headline }));
  return {
    snapshot_id: `demo-${now.getTime()}`,
    source_mode: "demo",
    generated_at: now.toISOString(),
    market_summary: "模拟情报显示宏观不确定性与交易所流入共同抬升短线波动，协议升级提供中期正向观察点。",
    market_regime: "neutral",
    freshness: { status: "fresh", age_seconds: 0, max_age_seconds: 300 },
    providers: [
      { provider_id: "demo-news", label: "模拟新闻聚合", status: "connected", message: "仅用于界面与流程评估，不代表实时连接。", last_success_at: now.toISOString(), latency_ms: 180 },
      { provider_id: "demo-ai", label: "模拟 AI 圆桌", status: "connected", message: "观点为演示生成，不来自真实模型服务。", last_success_at: now.toISOString(), latency_ms: 740 },
    ],
    events,
    roundtable: {
      status: "ready",
      consensus: "保持观察，等待宏观事件落地与流入压力缓解；不建议由当前快照触发自动仓位。",
      disagreements: ["技术面角色认为趋势结构仍偏强；风险角色认为事件窗口前应降低暴露。"],
      suggested_action: "observe",
      opinions: [
        { role_id: "macro_news", role: "宏观 / 新闻", status: "ready", thesis: "宏观路径不明，事件前方向性信号质量较低。", confidence: 0.72, evidence: [evidence[0]], valid_until: isoAfter(now, 900), simulated: true },
        { role_id: "technical", role: "技术面", status: "ready", thesis: "趋势结构未被破坏，但新闻驱动波动可能造成假突破。", confidence: 0.64, evidence: [evidence[1]], valid_until: isoAfter(now, 600), simulated: true },
        { role_id: "risk", role: "风险", status: "ready", thesis: "净流入上升与高影响宏观事件叠加，应保持仓位上限与熔断保护。", confidence: 0.81, evidence: [evidence[0], evidence[1]], valid_until: isoAfter(now, 600), simulated: true },
        { role_id: "execution", role: "执行", status: "ready", thesis: "当前仅建议观察；若后续获批，也应使用限价与滑点保护。", confidence: 0.77, evidence: [evidence[1]], valid_until: isoAfter(now, 300), simulated: true },
      ],
    },
    risk_decision: {
      status: "approved",
      approved: true,
      veto_reasons: [],
      constraints: { max_position_pct: 0.1, max_drawdown_pct: 0.12, max_daily_loss_pct: 0.04, max_data_age_seconds: 300, circuit_breaker_enabled: true },
    },
    execution: {
      mode: "observe_only",
      status: "disabled",
      message: "演示环境仅展示建议。执行器禁用，不会发送真实订单。",
    },
  };
}

export function isIntelligenceStale(data: MarketIntelligence, now = Date.now()): boolean {
  if (data.freshness.status !== "fresh") return true;
  return now - Date.parse(data.generated_at) > data.freshness.max_age_seconds * 1000;
}

export async function loadMarketIntelligence(useDemo: boolean): Promise<MarketIntelligence> {
  return useDemo ? createDemoIntelligence() : request<MarketIntelligence>("/market_intelligence");
}
