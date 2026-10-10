<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import EquityChart from "@/components/EquityChart.vue";
import Icon from "@/components/Icon.vue";
import StateBlock from "@/components/StateBlock.vue";
import type { AuditRecord, DashboardData, LoadState, Trade } from "@/api/types";

const props = defineProps<{ data: DashboardData | null; state: LoadState; demo: boolean }>();
const emit = defineEmits<{ refresh: []; "toggle-demo": []; navigate: [path: string] }>();
const clock = ref(Date.now());
let clockTimer: number | undefined;

const currency = computed(() => props.data?.config?.stake_currency ?? props.data?.balances?.stake ?? "USDT");
const equity = computed(() => props.data?.balances?.total_bot ?? props.data?.balances?.total ?? null);
const healthAge = computed(() => props.data?.health?.last_process_ts ? clock.value - normalizedTs(props.data.health.last_process_ts) : null);
const healthFresh = computed(() => healthAge.value !== null && healthAge.value < 60_000);
const dataAge = computed(() => props.data ? Math.max(0, clock.value - props.data.updatedAt) : null);
const dataFreshness = computed(() => {
  if (dataAge.value === null) return { label: "等待数据", level: "unavailable" };
  if (props.demo) return { label: "演示快照", level: "demo" };
  if (dataAge.value < 45_000) return { label: "数据新鲜", level: "ok" };
  if (dataAge.value < 120_000) return { label: "数据延迟", level: "warn" };
  return { label: "数据陈旧", level: "danger" };
});
const riskAge = computed(() => props.data ? Math.max(0, clock.value - props.data.risk.asOf) : null);
const riskStale = computed(() => riskAge.value !== null && riskAge.value > (props.data?.risk.staleAfterMs ?? 0));
const riskStatus = computed(() => {
  if (riskStale.value) return { label: "风险快照过期", level: "warn" };
  const locks = props.data?.risk.tradeLocks;
  if (locks?.status === "available" && (locks.value?.count ?? 0) > 0) return { label: "交易锁生效", level: "danger" };
  const drawdown = props.data?.risk.currentDrawdown.value;
  if (drawdown == null) return { label: "风险数据不可用", level: "unavailable" };
  if (drawdown >= 0.1) return { label: "回撤升高", level: "danger" };
  if (drawdown >= 0.05) return { label: "关注回撤", level: "warn" };
  return { label: "回撤受控", level: "ok" };
});
const latestAudit = computed(() => props.data?.audit[0] ?? null);
const rejectedSignalCapability = computed(() => props.data?.auditCapabilities.rejected_or_unfilled_signals);
const marketAge = computed(() => props.data?.market ? Math.max(0, clock.value - props.data.market.generated_timestamp) : null);
const marketEventAge = computed(() => props.data?.market?.event_timestamp ? Math.max(0, clock.value - props.data.market.event_timestamp) : null);
const marketStale = computed(() => {
  if (!props.data?.market || marketEventAge.value === null) return false;
  return marketEventAge.value > timeframeMs(props.data.market.timeframe) * 3;
});
const marketStatus = computed(() => {
  if (!props.data?.market) return { label: "观察不可用", level: "unavailable" };
  if (marketStale.value) return { label: "市场数据过期", level: "warn" };
  if (props.data.market.status === "partial") return { label: "部分市场可用", level: "warn" };
  if (props.data.market.status === "unavailable") return { label: "观察不可用", level: "unavailable" };
  return { label: "观察正常", level: "ok" };
});
const visibleMarketObservations = computed(() => {
  const market = props.data?.market;
  if (!market) return [];
  return market.timeframes.flatMap((summary) =>
    market.pairs.filter((item) => item.timeframe === summary.timeframe).slice(0, 2)
  );
});
const executionQualityStatus = computed(() => {
  const quality = props.data?.executionQuality;
  if (!quality) return { label: "分析不可用", level: "unavailable" };
  if (quality.status === "partial") return { label: "部分样本可用", level: "warn" };
  if (quality.status === "unavailable") return { label: "无执行样本", level: "unavailable" };
  return { label: "分析可用", level: "ok" };
});
const observabilityStatus = computed(() => {
  const snapshot = props.data?.observability;
  if (!snapshot) return { label: "聚合不可用", level: "unavailable" };
  if (snapshot.status === "partial") return { label: "部分遥测", level: "warn" };
  if (snapshot.status === "unavailable") return { label: "遥测不可用", level: "unavailable" };
  return { label: "遥测在线", level: "ok" };
});
const errorSummary = computed(() => props.data?.errors.map((error) => `${error.endpoint}: ${error.message}`).join("；") ?? "");

function normalizedTs(value: number): number {
  return value < 10_000_000_000 ? value * 1000 : value;
}

function elapsed(value: number | null): string {
  if (value === null) return "不可用";
  if (value < 5_000) return "刚刚";
  if (value < 60_000) return `${Math.floor(value / 1000)} 秒前`;
  if (value < 3_600_000) return `${Math.floor(value / 60_000)} 分钟前`;
  return `${Math.floor(value / 3_600_000)} 小时前`;
}

function timeframeMs(value: string): number {
  const match = value.match(/^(\d+)([mhd])$/);
  if (!match) return 60_000;
  const unit = match[2] === "d" ? 86_400_000 : match[2] === "h" ? 3_600_000 : 60_000;
  return Number(match[1]) * unit;
}

const money = (value: number, digits = 2) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
const duration = (value: number | null | undefined) => value == null ? "—" : value < 1000 ? `${value.toFixed(0)}ms` : `${(value / 1000).toFixed(2)}s`;
const percent = (value: number | null | undefined) => `${(value ?? 0) >= 0 ? "+" : ""}${(value ?? 0).toFixed(2)}%`;
const tradeProfit = (trade: Trade) => trade.total_profit_ratio != null ? trade.total_profit_ratio * 100 : (trade.profit_pct ?? 0);
const auditProfit = (record: AuditRecord) => record.actualProfitRatio.value != null ? record.actualProfitRatio.value * 100 : null;
const timestamp = (value: number | null) => value ? new Date(normalizedTs(value)).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "进行中";
const provenanceLabel = (value: DashboardData["risk"]["provenance"]) => value === "server-native" ? "SERVER NATIVE" : value === "demo" ? "DEMO" : value === "unavailable" ? "UNAVAILABLE" : "CLIENT FALLBACK";

onMounted(() => {
  clockTimer = window.setInterval(() => {
    clock.value = Date.now();
  }, 5_000);
});

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});
</script>

<template>
  <section class="view dashboard-view">
    <header class="view-header">
      <div>
        <div class="header-kicker"><span>交易工作台</span><span>/</span><span>指挥总览</span></div>
        <h1>交易总览</h1>
        <p>组合状态、策略决策、风险约束与执行质量的统一运行视图</p>
      </div>
      <div class="header-actions">
        <div v-if="data" class="freshness-badge" :class="dataFreshness.level">
          <span class="status-dot"></span>
          <div><strong>{{ dataFreshness.label }}</strong><small>更新于 {{ elapsed(dataAge) }}</small></div>
        </div>
        <button class="mode-toggle" :class="{ demo }" type="button" @click="emit('toggle-demo')">
          <span class="status-dot"></span>{{ demo ? "DEMO 演示数据" : "LIVE 实时数据" }}
        </button>
        <button class="icon-button" type="button" aria-label="刷新数据" :disabled="state === 'loading'" @click="emit('refresh')"><Icon name="refresh" /></button>
      </div>
    </header>

    <StateBlock v-if="state === 'loading' && !data" state="loading" detail="正在连接 Freqtrade API 并加载账户数据" />
    <div v-else-if="state === 'error'" class="dashboard-error">
      <StateBlock state="error" title="无法加载实时数据" detail="所有总览接口均请求失败。为避免显示误导性的零值，数据面板已暂停展示。" />
      <div class="recovery-actions">
        <button class="primary-button" type="button" @click="emit('refresh')">重新连接</button>
        <button class="secondary-button" type="button" @click="emit('navigate', '/settings')">检查系统设置</button>
      </div>
    </div>
    <template v-else-if="data">
      <div class="command-bar" aria-label="运行状态摘要">
        <div>
          <span class="command-label">交易引擎</span>
          <strong :class="healthFresh ? 'state-ok' : 'state-danger'"><i></i>{{ healthFresh ? "心跳正常" : "心跳异常" }}</strong>
          <small>{{ elapsed(healthAge) }}</small>
        </div>
        <div>
          <span class="command-label">策略状态</span>
          <strong :class="data.config?.state === 'running' ? 'state-ok' : 'state-warn'"><i></i>{{ data.config?.state ?? "不可用" }}</strong>
          <small>{{ data.config ? (data.config.dry_run ? "模拟交易" : "实盘交易") : "配置不可用" }}</small>
        </div>
        <div>
          <span class="command-label">执行场所</span>
          <strong :class="data.config?.exchange ? 'state-ok' : 'state-muted'"><i></i>{{ data.config?.exchange ?? "未连接" }}</strong>
          <small>{{ data.config?.trading_mode ?? "模式不可用" }}</small>
        </div>
        <div>
          <span class="command-label">数据完整性</span>
          <strong :class="data.errors.length ? 'state-warn' : 'state-ok'"><i></i>{{ data.errors.length ? `${data.errors.length} 项缺失` : "接口完整" }}</strong>
          <small>{{ data.source === "demo" ? "演示源" : "Freqtrade API" }}</small>
        </div>
      </div>

      <div v-if="data.errors.length" class="inline-alert" role="alert">
        <Icon name="alert" /><div><strong>部分实时数据加载失败</strong><span>{{ errorSummary }}</span></div>
      </div>

      <div class="metric-strip">
        <article class="metric-primary">
          <span class="metric-label">机器人管理净值 <em>{{ currency }}</em></span>
          <strong>{{ equity !== null ? money(equity) : "—" }}</strong>
          <span class="metric-caption">{{ equity !== null ? "来自账户余额接口" : "账户余额接口不可用" }}</span>
        </article>
        <article>
          <span class="metric-label">今日已实现盈亏</span>
          <strong v-if="data.risk.todayProfit.value !== null" :class="data.risk.todayProfit.value < 0 ? 'loss' : 'profit'">{{ data.risk.todayProfit.value >= 0 ? "+" : "" }}{{ money(data.risk.todayProfit.value) }}</strong>
          <strong v-else>—</strong>
          <span class="metric-caption">{{ data.risk.todayProfit.status === "available" ? "来自当日已平仓交易" : data.risk.todayProfit.reason }}</span>
        </article>
        <article>
          <span class="metric-label">累计策略收益</span>
          <strong v-if="data.profit" :class="data.profit.profit_all_coin < 0 ? 'loss' : 'profit'">{{ data.profit.profit_all_coin >= 0 ? "+" : "" }}{{ money(data.profit.profit_all_coin) }}</strong>
          <strong v-else>—</strong>
          <span class="metric-caption">{{ data.profit ? percent(data.profit.profit_all_percent) : "收益接口不可用" }}</span>
        </article>
        <article>
          <span class="metric-label">仓位容量</span>
          <strong v-if="data.risk.positionCapacity.value">{{ data.risk.positionCapacity.value.used }} <small>/ {{ data.risk.positionCapacity.value.limit }}</small></strong>
          <strong v-else>—</strong>
          <span class="metric-caption">{{ data.risk.positionCapacity.value?.utilizationPct != null ? `已使用 ${data.risk.positionCapacity.value.utilizationPct.toFixed(0)}% 策略槽位` : data.risk.positionCapacity.reason ?? "未设置有限容量" }}</span>
        </article>
      </div>

      <div class="dashboard-grid">
        <article class="panel equity-panel">
          <div class="panel-head">
            <div><span class="section-label">PORTFOLIO / PERFORMANCE</span><h2>权益与组合轨迹</h2></div>
            <span class="period-label">历史全量</span>
          </div>
          <EquityChart v-if="data.equity.length > 1" :points="data.equity" :currency="currency" />
          <StateBlock v-else state="empty" title="暂无权益历史" detail="Freqtrade 记录两个以上钱包快照后将显示曲线。" />
        </article>

        <article class="panel decision-panel">
          <div class="panel-head">
            <div><span class="section-label">DECISION CONTEXT</span><h2>策略与决策上下文</h2></div>
            <span class="status-pill" :class="data.config?.state === 'running' ? 'ok' : 'warn'">{{ data.config?.state ?? "未知" }}</span>
          </div>
          <div class="strategy-name">
            <span class="strategy-mark">B</span>
            <div><strong>{{ data.config?.strategy ?? "未加载策略" }}</strong><span>{{ data.config?.exchange ?? "—" }} · {{ data.config?.trading_mode ?? "—" }}</span></div>
          </div>
          <dl class="data-list">
            <div><dt>运行环境</dt><dd>{{ data.config ? (data.config.dry_run ? "DRY RUN" : "LIVE") : "不可用" }}</dd></div>
            <div><dt>决策模型</dt><dd>Freqtrade 策略</dd></div>
            <div><dt>最近信号来源</dt><dd :class="{ unavailable: latestAudit?.signalSource.status !== 'available' }">{{ latestAudit?.signalSource.value ?? "待接入" }}</dd></div>
            <div :class="{ 'unavailable-row': !data.market }"><dt>市场观察层</dt><dd>{{ data.market ? "在线 · 不做状态分类" : "不可用" }}</dd></div>
            <div class="unavailable-row"><dt>完整决策理由</dt><dd>API 未提供</dd></div>
          </dl>
        </article>

        <article class="panel risk-panel">
          <div class="panel-head">
            <div><span class="section-label">RISK FIRST</span><h2>风险与资金约束</h2></div>
            <div class="panel-status-stack"><span class="source-badge" :class="data.risk.provenance">{{ provenanceLabel(data.risk.provenance) }}</span><span class="risk-level" :class="riskStatus.level">{{ riskStatus.label }}</span></div>
          </div>
          <div class="risk-gauge">
            <div><span>当前回撤</span><strong>{{ data.risk.currentDrawdown.value !== null ? `${(data.risk.currentDrawdown.value * 100).toFixed(2)}%` : "—" }}</strong></div>
            <div class="gauge-track" :class="{ unavailable: data.risk.currentDrawdown.status === 'unavailable' }"><span :style="{ width: `${data.risk.currentDrawdown.value !== null ? Math.min(data.risk.currentDrawdown.value * 500, 100) : 0}%` }"></span></div>
          </div>
          <dl class="risk-stats risk-stats-dense">
            <div><dt>最大回撤</dt><dd>{{ data.risk.maxDrawdown.value !== null ? `${(data.risk.maxDrawdown.value * 100).toFixed(2)}%` : "—" }}</dd></div>
            <div><dt>名义敞口</dt><dd>{{ data.risk.nominalExposure.value !== null ? money(data.risk.nominalExposure.value, 0) : "—" }}</dd></div>
            <div><dt>今日亏损</dt><dd :class="{ loss: (data.risk.todayLoss.value ?? 0) < 0 }">{{ data.risk.todayLoss.value !== null ? money(data.risk.todayLoss.value, 0) : "—" }}</dd></div>
            <div><dt>连续亏损</dt><dd>{{ data.risk.consecutiveLosses.value ?? "—" }}</dd></div>
          </dl>
          <div class="lock-summary" :class="{ active: (data.risk.tradeLocks.value?.count ?? 0) > 0, unavailable: data.risk.tradeLocks.status === 'unavailable' }">
            <span>交易锁 / Protections</span>
            <strong v-if="data.risk.tradeLocks.value">{{ data.risk.tradeLocks.value.count ? `${data.risk.tradeLocks.value.count} 项活动限制` : "无活动交易锁" }}</strong>
            <strong v-else>{{ data.risk.tradeLocks.reason }}</strong>
            <small v-if="data.risk.tradeLocks.value?.locks.length">{{ data.risk.tradeLocks.value.locks.slice(0, 2).map((lock) => `${lock.pair} · ${lock.reason ?? "未记录原因"}`).join("；") }}</small>
          </div>
          <div class="capability-note"><span>风险快照 {{ riskStale ? "已过期" : elapsed(riskAge) }}<template v-if="data.risk.eventAt"> · 事件 {{ timestamp(data.risk.eventAt) }}</template></span><strong>{{ data.risk.degradationReason ?? data.risk.riskBudget.reason }}</strong></div>
        </article>

        <article class="panel positions-panel">
          <div class="panel-head"><div><span class="section-label">EXECUTION / POSITIONS</span><h2>持仓与执行</h2></div><a href="/positions" @click.prevent="emit('navigate', '/positions')">查看全部</a></div>
          <div v-if="data.openTrades.length" class="positions-list">
            <div v-for="trade in data.openTrades.slice(0, 4)" :key="trade.trade_id" class="position-row">
              <div><strong>{{ trade.pair }}</strong><span>{{ trade.is_short ? "SHORT" : "LONG" }} · {{ money(trade.stake_amount, 0) }} {{ currency }}<b v-if="trade.has_open_orders">挂单中</b></span></div>
              <div class="position-price"><span>{{ money(trade.current_rate ?? trade.open_rate, 4) }}</span><strong :class="tradeProfit(trade) < 0 ? 'loss' : 'profit'">{{ percent(tradeProfit(trade)) }}</strong></div>
            </div>
          </div>
          <StateBlock v-else state="empty" title="当前无持仓" detail="策略产生有效入场信号后，仓位会显示在这里。" />
        </article>

        <article class="panel execution-quality-panel">
          <div class="panel-head">
            <div><span class="section-label">EXECUTION QUALITY / READ ONLY</span><h2>执行质量分析</h2></div>
            <div class="panel-status-stack">
              <span class="source-badge" :class="data.executionQualityProvenance">{{ provenanceLabel(data.executionQualityProvenance) }}</span>
              <span class="risk-level" :class="executionQualityStatus.level">{{ executionQualityStatus.label }}</span>
            </div>
          </div>
          <template v-if="data.executionQuality">
            <div class="market-summary execution-summary">
              <div><span>平均成交延迟</span><strong>{{ duration(data.executionQuality.average_fill_latency_ms.value) }}</strong><small>{{ data.executionQuality.coverage.latency_records }} / {{ data.executionQuality.coverage.sampled_orders }} 订单有时间样本</small></div>
              <div><span>P95 成交延迟</span><strong>{{ duration(data.executionQuality.p95_fill_latency_ms.value) }}</strong><small>本地订单创建至成交</small></div>
              <div><span>平均价格偏差</span><strong>{{ data.executionQuality.average_price_deviation_bps.value !== null ? `${data.executionQuality.average_price_deviation_bps.value.toFixed(2)} bps` : "—" }}</strong><small>requested 与 average 的绝对差</small></div>
              <div><span>已记录费用</span><strong>{{ data.executionQuality.fee_totals.length ? data.executionQuality.fee_totals.map((fee) => `${money(fee.value, 4)} ${fee.currency}`).join(" · ") : "—" }}</strong><small>{{ data.executionQuality.coverage.fee_records }} 条真实费用记录</small></div>
            </div>
            <div class="execution-lifecycle">
              <span>订单生命周期</span>
              <strong>{{ data.executionQuality.lifecycle.filled }} filled</strong>
              <strong>{{ data.executionQuality.lifecycle.open }} open</strong>
              <strong>{{ data.executionQuality.lifecycle.cancelled }} cancelled</strong>
              <small>共 {{ data.executionQuality.lifecycle.total }} 条持久化订单</small>
            </div>
            <div v-if="data.executionQuality.recent_orders.length" class="market-pairs execution-orders">
              <div v-for="order in data.executionQuality.recent_orders.slice(0, 4)" :key="order.id" class="market-pair-row">
                <div><strong>{{ order.pair }} <em>{{ order.side }}</em></strong><small>{{ order.lifecycle }} · {{ timestamp(order.event_timestamp) }}</small></div>
                <span>{{ duration(order.fill_latency_ms) }}</span>
                <span>{{ order.price_deviation_bps !== null ? `${order.price_deviation_bps.toFixed(2)} bps` : "偏差 —" }}</span>
                <span>{{ order.requested_price !== null ? `请求 ${money(order.requested_price, 4)}` : "请求价 —" }}</span>
                <span>{{ order.average_price !== null ? `成交 ${money(order.average_price, 4)}` : "成交价 —" }}</span>
              </div>
            </div>
            <div class="observe-only-note"><strong>READ ONLY</strong><span>只分析持久化 Order / Trade，不改变订单行为；{{ data.executionQuality.capabilities.exchange_ack_latency?.reason }}</span></div>
          </template>
          <StateBlock v-else state="empty" title="执行质量分析不可用" :detail="data.executionQualityDegradationReason ?? '当前后端未提供只读执行质量端点。'" />
        </article>

        <article class="panel market-panel">
          <div class="panel-head">
            <div><span class="section-label">MARKET OBSERVER / SHADOW</span><h2>市场只读观察</h2></div>
            <div class="panel-status-stack">
              <span class="source-badge" :class="data.marketProvenance">{{ provenanceLabel(data.marketProvenance) }}</span>
              <span class="risk-level" :class="marketStatus.level">{{ marketStatus.label }}</span>
            </div>
          </div>
          <template v-if="data.market">
            <div class="market-summary">
              <div><span>覆盖率</span><strong>{{ data.market.health.coverage_pct.toFixed(0) }}%</strong><small>{{ data.market.health.available }} / {{ data.market.health.requested_observations }} 项可用</small></div>
              <div><span>上涨</span><strong class="profit">{{ data.market.breadth.advancing }}</strong><small>仅价格变化计数</small></div>
              <div><span>下跌</span><strong class="loss">{{ data.market.breadth.declining }}</strong><small>不代表交易信号</small></div>
              <div><span>数据健康</span><strong>{{ data.market.health.stale }} 过期</strong><small>{{ data.market.health.unavailable }} 不可用 · {{ data.market.health.generation_duration_ms }}ms</small></div>
            </div>
            <div class="timeframe-strip" aria-label="周期覆盖">
              <div v-for="summary in data.market.timeframes" :key="summary.timeframe">
                <strong>{{ summary.timeframe }}</strong>
                <span>{{ summary.coverage_pct.toFixed(0) }}% 覆盖</span>
                <small>{{ summary.fresh }} fresh · {{ summary.stale }} stale · {{ summary.unavailable }} unavailable</small>
              </div>
            </div>
            <div v-if="data.market.pairs.length" class="market-pairs">
              <div v-for="pair in visibleMarketObservations" :key="`${pair.pair}-${pair.timeframe}`" class="market-pair-row">
                <div><strong>{{ pair.pair }} <em :class="pair.freshness">{{ pair.timeframe }}</em></strong><small>{{ pair.status === "available" ? `${pair.sample_count} 样本 · ${pair.freshness}` : pair.reason }}</small></div>
                <span>{{ pair.close !== null ? money(pair.close, 2) : "—" }}</span>
                <span :class="pair.change_pct !== null && pair.change_pct < 0 ? 'loss' : pair.change_pct !== null ? 'profit' : ''">{{ pair.change_pct !== null ? percent(pair.change_pct) : "—" }}</span>
                <span>{{ pair.range_pct !== null ? `振幅 ${pair.range_pct.toFixed(2)}%` : "振幅 —" }}</span>
                <span>{{ pair.volume_ratio !== null ? `量比 ${pair.volume_ratio.toFixed(2)}` : "量比 —" }}</span>
              </div>
            </div>
            <div class="observe-only-note"><strong>OBSERVE ONLY</strong><span>本区域不参与策略选择、风险阈值或订单执行；{{ data.market.capabilities.snapshot_history?.reason ?? "观察历史未持久化" }}</span></div>
          </template>
          <StateBlock v-else state="empty" title="市场观察层不可用" :detail="data.marketDegradationReason ?? '当前后端未提供只读市场观察端点。'" />
        </article>

        <article class="panel orders-panel">
          <div class="panel-head"><div><span class="section-label">DECISION / EXECUTION AUDIT</span><h2>近期交易与决策审计</h2></div><div class="panel-status-stack"><span class="source-badge" :class="data.auditProvenance">{{ provenanceLabel(data.auditProvenance) }}</span><span>{{ data.audit.length }} 条记录</span></div></div>
          <div v-if="data.audit.length" class="trade-table-wrap">
            <table>
              <thead><tr><th>交易 / 策略</th><th>方向</th><th>信号来源</th><th>执行 / 退出</th><th>决策时间</th><th class="align-right">实际结果</th></tr></thead>
              <tbody>
                <tr v-for="record in data.audit" :key="record.id">
                  <td><strong>{{ record.pair }}</strong><small>{{ record.strategy }}</small></td>
                  <td><span class="side-tag" :class="{ short: record.side === 'short' }">{{ record.side.toUpperCase() }}</span></td>
                  <td :class="{ 'cell-unavailable': record.signalSource.status === 'unavailable' }">{{ record.signalSource.value ?? "待接入" }}</td>
                  <td><span>{{ record.executionStatus === "open_order" ? "持仓 · 有挂单" : record.executionStatus === "open" ? "持仓中" : "已退出" }}</span><small>{{ record.exitReason.value ?? record.exitReason.reason }}</small></td>
                  <td>{{ timestamp(record.decisionAt) }}</td>
                  <td v-if="auditProfit(record) !== null" class="align-right" :class="(auditProfit(record) ?? 0) < 0 ? 'loss' : 'profit'">{{ percent(auditProfit(record)) }}</td>
                  <td v-else class="align-right cell-unavailable">不可用</td>
                </tr>
              </tbody>
            </table>
            <div class="audit-gap"><span>预期结果 / 拒绝决策</span><strong>{{ rejectedSignalCapability?.reason ?? "当前 API 未提供，未做推断" }}</strong></div>
          </div>
          <StateBlock v-else-if="data.auditStatus === 'unavailable'" state="error" title="审计数据不可用" detail="当前持仓与历史成交端点均加载失败。" />
          <StateBlock v-else-if="data.auditStatus === 'partial'" state="empty" title="审计数据不完整" detail="当前持仓或历史成交端点加载失败，无法形成完整审计记录。" />
          <StateBlock v-else state="empty" title="暂无交易记录" detail="接口已连接，但当前没有可审计的持仓或成交。" />
        </article>

        <article class="panel system-panel">
          <div class="panel-head"><div><span class="section-label">SYSTEM OBSERVABILITY / READ ONLY</span><h2>系统健康与告警证据</h2></div><div class="panel-status-stack"><span class="source-badge" :class="data.observabilityProvenance">{{ provenanceLabel(data.observabilityProvenance) }}</span><span class="risk-level" :class="observabilityStatus.level">{{ observabilityStatus.label }}</span></div></div>
          <ul class="system-list">
            <li><span><i :class="{ ok: data.ping }"></i>API 服务</span><strong>{{ data.ping ? "在线" : "离线" }}</strong></li>
            <li><span><i :class="{ ok: data.observability?.heartbeat_age_ms.status === 'available' || healthFresh }"></i>交易引擎心跳</span><strong>{{ data.observability?.heartbeat_age_ms.value != null ? duration(data.observability.heartbeat_age_ms.value) : healthFresh ? elapsed(healthAge) : "不可用" }}</strong></li>
            <li><span><i :class="{ ok: data.observability?.database_status.status === 'available' }"></i>持久化诊断</span><strong>{{ data.observability?.database_status.status === "available" ? "可查询" : "不可用" }}</strong></li>
            <li><span><i :class="{ ok: !!data.observability || !!data.sysinfo }"></i>系统资源</span><strong>{{ data.observability ? `CPU ${data.observability.cpu_pct.value?.toFixed(0) ?? "—"}% · RAM ${data.observability.ram_pct.value?.toFixed(0) ?? "—"}%` : data.sysinfo ? `CPU ${data.sysinfo.cpu_avg.toFixed(0)}% · RAM ${data.sysinfo.ram_pct.toFixed(0)}%` : "接口不可用" }}</strong></li>
          </ul>
          <div v-if="data.observability" class="system-telemetry">
            <span>状态 {{ data.observability.runtime_state }}</span>
            <span>{{ data.observability.active_pair_count.value ?? "—" }} 活跃交易对</span>
            <span>{{ data.observability.open_trade_count.value ?? "—" }} 持仓</span>
            <span>{{ data.observability.active_lock_count.value ?? "—" }} 活动锁</span>
          </div>
          <div v-if="data.observability?.alerts.length" class="system-alerts">
            <div v-for="alert in data.observability.alerts" :key="alert.id" :class="alert.severity"><strong>{{ alert.title }}</strong><span>{{ alert.count }} 条 · {{ alert.event_timestamp ? timestamp(alert.event_timestamp) : "时间不可用" }}</span></div>
          </div>
          <div class="capability-note"><span>日志仅聚合级别计数，不返回消息或堆栈</span><strong>{{ data.observability?.capabilities.configured_alert_thresholds?.reason ?? data.observabilityDegradationReason ?? "原生聚合端点不可用" }}</strong></div>
        </article>

        <article class="panel capability-panel">
          <div class="panel-head"><div><span class="section-label">CONTROLLED EVOLUTION</span><h2>能力接入状态</h2></div><span>阶段 2</span></div>
          <div class="capability-grid">
            <div><span class="capability-state partial"></span><strong>市场认知</strong><small>OHLCV 观察已接入，状态分类保持关闭</small></div>
            <div><span class="capability-state partial"></span><strong>多维决策</strong><small>策略、入场标签与实际结果已接入</small></div>
            <div><span class="capability-state active"></span><strong>风险优先</strong><small>回撤、敞口、当日盈亏与交易锁已接入</small></div>
            <div><span class="capability-state active"></span><strong>专业执行</strong><small>费用、成交延迟、价格偏差与订单生命周期已接入</small></div>
            <div><span class="capability-state active"></span><strong>自我审计</strong><small>信号标签、执行状态与退出结果已接入</small></div>
            <div><span class="capability-state partial"></span><strong>受控进化</strong><small>验证证据只读接入，晋级与发布保持关闭</small></div>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>
