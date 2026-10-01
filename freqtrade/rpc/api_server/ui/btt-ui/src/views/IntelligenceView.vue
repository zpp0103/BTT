<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { isIntelligenceStale, loadMarketIntelligence } from "@/api/intelligence";
import type { MarketIntelligence } from "@/api/intelligence";
import Icon from "@/components/Icon.vue";
import StateBlock from "@/components/StateBlock.vue";

const props = defineProps<{ demo: boolean }>();
const emit = defineEmits<{ "toggle-demo": [] }>();
const data = ref<MarketIntelligence | null>(null);
const state = ref<"loading" | "ready" | "error">("loading");
const errorMessage = ref("");
const clock = ref(Date.now());
let clockTimer: number | undefined;
let refreshTimer: number | undefined;

const stale = computed(() => data.value ? isIntelligenceStale(data.value, clock.value) : true);
const decisionBlocked = computed(() => !data.value?.risk_decision.approved || stale.value);
const freshnessLabel = computed(() => {
  if (!data.value || data.value.freshness.status === "unavailable") return "无可用快照";
  if (stale.value) return "数据已过期";
  const age = Math.max(data.value.freshness.age_seconds ?? 0, Math.floor((clock.value - Date.parse(data.value.generated_at)) / 1000));
  return age < 60 ? `${age} 秒前` : `${Math.floor(age / 60)} 分钟前`;
});
const sourceTime = (value: string) => new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
const confidence = (value: number | null) => value == null ? "—" : `${Math.round(value * 100)}%`;
const providerState = (status: "connected" | "unconfigured" | "error", latency: number | null) => {
  if (status === "connected") return `${latency ?? "—"} ms`;
  return status === "unconfigured" ? "未配置" : "连接失败";
};
const sentimentLabel = { positive: "正向", neutral: "中性", negative: "负向" } as const;
const impactLabel = { low: "低", medium: "中", high: "高", critical: "极高" } as const;
const regimeLabel = { risk_on: "风险偏好", neutral: "中性", risk_off: "风险规避", unavailable: "不可用" } as const;
const vetoLabel: Record<string, string> = {
  market_data_unavailable: "市场数据不可用",
  market_data_stale: "市场数据已过期",
  ai_service_unavailable: "AI 服务未配置",
  circuit_breaker_triggered: "熔断器已触发",
  max_position_exceeded: "超过最大仓位",
  max_drawdown_exceeded: "超过最大回撤",
  max_daily_loss_exceeded: "超过单日亏损限制",
};

async function refresh() {
  state.value = "loading";
  errorMessage.value = "";
  try {
    data.value = await loadMarketIntelligence(props.demo);
    state.value = "ready";
  } catch (error) {
    data.value = null;
    state.value = "error";
    errorMessage.value = error instanceof Error ? error.message : "无法加载市场情报";
  }
}

watch(() => props.demo, () => void refresh());
onMounted(() => {
  void refresh();
  clockTimer = window.setInterval(() => {
    clock.value = Date.now();
  }, 10_000);
  refreshTimer = window.setInterval(() => {
    if (!props.demo && document.visibilityState === "visible") void refresh();
  }, 30_000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <section class="view intelligence-view">
    <header class="view-header">
      <div>
        <div class="header-kicker"><span>INTELLIGENCE</span><span>/</span><span>市场情报</span></div>
        <h1>新闻与市场动态</h1>
        <p>统一情报快照、AI 圆桌观点与确定性风险审批</p>
      </div>
      <div class="header-actions">
        <button class="mode-toggle" :class="{ demo }" type="button" @click="emit('toggle-demo')">
          <span class="status-dot"></span>{{ demo ? "DEMO 模拟情报" : "LIVE 实时情报" }}
        </button>
        <button class="icon-button" type="button" aria-label="刷新市场情报" :disabled="state === 'loading'" @click="refresh"><Icon name="refresh" /></button>
      </div>
    </header>

    <StateBlock v-if="state === 'loading' && !data" state="loading" detail="正在读取新闻数据源、情报快照与 AI 服务状态" />
    <div v-else-if="state === 'error'" class="panel terminal-error">
      <StateBlock state="error" title="市场情报接口不可用" :detail="`${errorMessage}。当前不会生成 AI 建议或执行动作。`" />
      <div class="state-actions"><button class="primary-button" type="button" @click="refresh">重新加载</button></div>
    </div>

    <template v-else-if="data">
      <div v-if="demo" class="demo-disclosure" role="status">
        <Icon name="alert" /><strong>模拟数据</strong><span>新闻、来源与 AI 观点均为产品演示，不代表实时市场事实。</span>
      </div>

      <section class="intelligence-summary">
        <article class="panel market-brief">
          <div class="panel-head">
            <div><span class="section-label">MARKET SNAPSHOT</span><h2>市场状态摘要</h2></div>
            <span class="status-pill" :class="{ ok: !stale && data.market_regime !== 'unavailable', warn: stale }">{{ freshnessLabel }}</span>
          </div>
          <p class="brief-copy">{{ data.market_summary }}</p>
          <div class="snapshot-meta">
            <span>市场状态 {{ regimeLabel[data.market_regime] }}</span>
            <span>快照 {{ data.snapshot_id }}</span>
            <span>生成 {{ sourceTime(data.generated_at) }}</span>
            <span>最大延迟 {{ data.freshness.max_age_seconds }} 秒</span>
          </div>
        </article>
        <article class="panel provider-panel">
          <div class="panel-head"><div><span class="section-label">CONNECTIONS</span><h2>数据源连接</h2></div></div>
          <ul class="provider-list">
            <li v-for="provider in data.providers" :key="provider.provider_id">
              <i :class="{ ok: provider.status === 'connected' }"></i>
              <div><strong>{{ provider.label }}</strong><span>{{ provider.message }}</span></div>
              <em>{{ providerState(provider.status, provider.latency_ms) }}</em>
            </li>
          </ul>
        </article>
      </section>

      <section class="intelligence-layout">
        <article class="panel event-panel">
          <div class="panel-head">
            <div><span class="section-label">NEWS & EVENTS</span><h2>新闻 / 公告事件流</h2></div>
            <span>{{ data.events.length }} 条</span>
          </div>
          <div v-if="data.events.length" class="event-stream">
            <article v-for="event in data.events" :key="event.event_id" class="event-item">
              <div class="event-time"><strong>{{ sourceTime(event.published_at).slice(-8) }}</strong><span>接收延迟 {{ Math.max(0, Math.round((Date.parse(event.received_at) - Date.parse(event.published_at)) / 1000)) }}s</span></div>
              <div class="event-copy">
                <div class="event-tags">
                  <span class="impact-tag" :class="event.impact">{{ impactLabel[event.impact] }}影响</span>
                  <span class="sentiment-tag" :class="event.sentiment">{{ sentimentLabel[event.sentiment] }}</span>
                  <span v-for="symbol in event.symbols" :key="symbol" class="symbol-tag">{{ symbol }}</span>
                </div>
                <h3>{{ event.headline }}</h3>
                <p>{{ event.summary }}</p>
                <span class="event-source">{{ event.source }} · {{ sourceTime(event.published_at) }}</span>
              </div>
            </article>
          </div>
          <StateBlock v-else state="empty" title="没有可用的实时事件" detail="新闻 provider 未配置或当前没有返回事件。LIVE 模式不会使用演示数据补位。" />
        </article>

        <article class="panel decision-chain">
          <div class="panel-head"><div><span class="section-label">SAFETY PIPELINE</span><h2>安全决策链</h2></div><span class="risk-level" :class="{ elevated: decisionBlocked }">{{ decisionBlocked ? "已阻断" : "待人工复核" }}</span></div>
          <ol>
            <li :class="{ complete: data.roundtable.status === 'ready' }"><span>01</span><div><strong>AI 提议</strong><p>{{ data.roundtable.status === "ready" ? "基于同一时间戳快照形成建议" : "AI 服务未配置，无提议" }}</p></div></li>
            <li :class="{ complete: data.risk_decision.approved, blocked: decisionBlocked }"><span>02</span><div><strong>确定性风险引擎</strong><p>{{ decisionBlocked ? "硬约束否决或数据不满足新鲜度" : "硬约束通过，仍需人工复核" }}</p></div></li>
            <li class="blocked"><span>03</span><div><strong>执行器</strong><p>观察模式固定禁用，不发送真实订单</p></div></li>
          </ol>
          <div v-if="decisionBlocked" class="veto-box">
            <span class="section-label">VETO REASONS</span>
            <strong v-for="reason in data.risk_decision.veto_reasons" :key="reason">{{ vetoLabel[reason] ?? reason }}</strong>
            <strong v-if="stale && !data.risk_decision.veto_reasons.includes('market_data_stale')">市场数据已超过有效期</strong>
          </div>
          <dl class="constraint-grid">
            <div><dt>最大仓位</dt><dd>{{ (data.risk_decision.constraints.max_position_pct * 100).toFixed(0) }}%</dd></div>
            <div><dt>最大回撤</dt><dd>{{ (data.risk_decision.constraints.max_drawdown_pct * 100).toFixed(0) }}%</dd></div>
            <div><dt>单日亏损</dt><dd>{{ (data.risk_decision.constraints.max_daily_loss_pct * 100).toFixed(0) }}%</dd></div>
            <div><dt>熔断保护</dt><dd>{{ data.risk_decision.constraints.circuit_breaker_enabled ? "启用" : "禁用" }}</dd></div>
          </dl>
        </article>
      </section>

      <section class="panel roundtable-panel">
        <div class="panel-head">
          <div><span class="section-label">AI ROUNDTABLE</span><h2>圆桌交易员观点</h2></div>
          <span class="status-pill" :class="{ ok: data.roundtable.status === 'ready' }">{{ data.roundtable.status === "ready" ? "同快照完成" : "AI 未配置" }}</span>
        </div>
        <div class="consensus">
          <div><span class="section-label">COORDINATOR</span><strong>协调者共识</strong><p>{{ data.roundtable.consensus }}</p></div>
          <span class="action-chip">{{ data.roundtable.suggested_action.toUpperCase() }}</span>
        </div>
        <div class="role-grid">
          <article v-for="opinion in data.roundtable.opinions" :key="opinion.role_id" class="role-card">
            <div><span class="role-mark">{{ opinion.role.slice(0, 1) }}</span><div><strong>{{ opinion.role }}</strong><small>{{ opinion.simulated ? "DEMO · 模拟观点" : opinion.status === "ready" ? "AI 实时观点" : "AI 服务未配置" }}</small></div><em>{{ confidence(opinion.confidence) }}</em></div>
            <p>{{ opinion.thesis }}</p>
            <ul v-if="opinion.evidence.length"><li v-for="item in opinion.evidence" :key="item.event_id">{{ item.source }} · {{ item.headline }}</li></ul>
            <span class="validity">有效期 {{ opinion.valid_until ? sourceTime(opinion.valid_until) : "—" }}</span>
          </article>
        </div>
        <div v-if="data.roundtable.disagreements.length" class="disagreement"><strong>分歧</strong><span v-for="item in data.roundtable.disagreements" :key="item">{{ item }}</span></div>
      </section>
    </template>
  </section>
</template>
