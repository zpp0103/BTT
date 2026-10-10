<script setup lang="ts">
import type { DashboardData } from "@/api/types";
import Icon from "@/components/Icon.vue";
import StateBlock from "@/components/StateBlock.vue";

defineProps<{ module: string; data: DashboardData | null }>();

const ratio = (value: number | null | undefined) => value == null ? "—" : `${(value * 100).toFixed(2)}%`;
const governanceStatus = (value: string) => value === "available" ? "已记录" : value === "partial" ? "部分记录" : value === "not_recorded" ? "未记录" : "不可用";
const shortFingerprint = (value: string | null | undefined) => value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "不可用";

const moduleInfo: Record<string, { kicker: string; title: string; desc: string; icon: string }> = {
  live: { kicker: "EXECUTION", title: "实时交易", desc: "观察策略执行、市场状态与交易信号", icon: "live" },
  strategies: { kicker: "STRATEGIES", title: "策略管理", desc: "管理策略版本、参数与运行实例", icon: "strategy" },
  backtest: { kicker: "RESEARCH", title: "回测分析", desc: "验证策略表现并比较关键指标", icon: "backtest" },
  positions: { kicker: "PORTFOLIO", title: "持仓与订单", desc: "统一追踪仓位、委托与历史成交", icon: "orders" },
  risk: { kicker: "RISK CONTROL", title: "风险控制", desc: "监控回撤、风险敞口与保护状态", icon: "risk" },
};
</script>

<template>
  <section class="view module-view">
    <header class="view-header">
      <div><div class="header-kicker">{{ moduleInfo[module].kicker }}</div><h1>{{ moduleInfo[module].title }}</h1><p>{{ moduleInfo[module].desc }}</p></div>
    </header>
    <div class="module-hero panel">
      <div class="module-icon"><Icon :name="moduleInfo[module].icon" :size="26" /></div>
      <div>
        <span class="section-label">FOUNDATION · V0.1</span>
        <h2>{{ moduleInfo[module].title }}工作区</h2>
        <p>当前版本已完成统一信息架构与实时 API 数据上下文，后续功能可在此基础上逐步接入。</p>
      </div>
    </div>
    <div v-if="module === 'live'" class="module-grid">
      <article class="panel"><span class="section-label">ENGINE</span><h2>执行引擎</h2><dl class="data-list"><div><dt>状态</dt><dd>{{ data?.config?.state ?? "未知" }}</dd></div><div><dt>交易所</dt><dd>{{ data?.config?.exchange ?? "—" }}</dd></div><div><dt>运行模式</dt><dd>{{ data?.config?.runmode ?? "—" }}</dd></div></dl></article>
      <article class="panel"><span class="section-label">SIGNALS</span><h2>实时信号</h2><StateBlock state="empty" title="等待策略信号" detail="信号流接入后将在此展示入场、出场与拒绝原因。" /></article>
    </div>
    <div v-else-if="module === 'strategies'" class="module-grid">
      <article class="panel"><span class="section-label">ACTIVE / READ ONLY</span><h2>当前策略</h2><div class="large-value">{{ data?.governance?.strategy.identifier ?? data?.config?.strategy ?? "未加载" }}</div><p class="muted">{{ data?.config?.trading_mode ?? "—" }} · {{ data?.config?.exchange ?? "—" }}</p></article>
      <article class="panel"><span class="section-label">IDENTITY</span><h2>版本与指纹</h2><dl v-if="data?.governance" class="data-list"><div><dt>类名</dt><dd>{{ data.governance.strategy.class_name }}</dd></div><div><dt>策略版本</dt><dd>{{ data.governance.strategy.version ?? "未记录" }}</dd></div><div><dt>SHA-256</dt><dd class="mono">{{ shortFingerprint(data.governance.strategy.fingerprint) }}</dd></div></dl><StateBlock v-else state="empty" title="治理数据不可用" :detail="data?.governanceDegradationReason ?? '当前后端未提供策略治理端点。'" /></article>
    </div>
    <div v-else-if="module === 'backtest'" class="module-grid">
      <article class="panel"><span class="section-label">LATEST EVIDENCE</span><h2>最近回测证据</h2><dl v-if="data?.governance && ['available', 'partial'].includes(data.governance.latest_backtest.status)" class="data-list"><div><dt>证据状态</dt><dd>{{ governanceStatus(data.governance.latest_backtest.status) }}</dd></div><div><dt>样本交易</dt><dd>{{ data.governance.latest_backtest.trade_count.value ?? "—" }}</dd></div><div><dt>收益</dt><dd>{{ ratio(data.governance.latest_backtest.profit_ratio.value) }}</dd></div><div><dt>最大回撤</dt><dd>{{ ratio(data.governance.latest_backtest.max_drawdown.value) }}</dd></div><div><dt>胜率</dt><dd>{{ ratio(data.governance.latest_backtest.win_rate.value) }}</dd></div></dl><StateBlock v-else state="empty" title="没有活动策略的回测证据" :detail="data?.governance?.latest_backtest.reason ?? data?.governanceDegradationReason ?? '当前后端未提供策略治理端点。'" /></article>
      <article class="panel"><span class="section-label">INTERPRETATION</span><h2>证据边界</h2><StateBlock state="empty" title="不自动判定上线资格" :detail="data?.governance?.capabilities.performance_interpretation?.reason ?? '单次回测不能替代样本外、压力与实盘前验证。'" /></article>
    </div>
    <article v-if="module === 'strategies' || module === 'backtest'" class="panel governance-panel">
      <div class="panel-head"><div><span class="section-label">VALIDATION / PROMOTION GOVERNANCE</span><h2>验证与晋级治理</h2></div><span class="source-badge" :class="data?.governanceProvenance ?? 'unavailable'">{{ data?.governance ? "READ ONLY" : "UNAVAILABLE" }}</span></div>
      <template v-if="data?.governance">
        <div class="governance-gates">
          <div v-for="gate in data.governance.gates" :key="gate.id" :class="gate.status">
            <span>{{ gate.label }}</span>
            <strong>{{ governanceStatus(gate.status) }}</strong>
            <small>{{ gate.reason ?? gate.source }}</small>
          </div>
        </div>
        <div class="observe-only-note"><strong>NO PROMOTION</strong><span>只读取策略身份与已有回测证据，不运行回测、不批准、不发布、不切换策略；{{ data.governance.capabilities.automatic_promotion?.reason }}</span></div>
      </template>
      <StateBlock v-else state="empty" title="验证治理不可用" :detail="data?.governanceDegradationReason ?? '当前后端未提供只读治理端点。'" />
    </article>
    <div v-else-if="module === 'positions'" class="panel">
      <div class="panel-head"><div><span class="section-label">OPEN POSITIONS</span><h2>未平仓仓位</h2></div><span>{{ data?.openTrades.length ?? 0 }} 个</span></div>
      <div v-if="data?.openTrades.length" class="trade-table-wrap"><table><thead><tr><th>交易对</th><th>方向</th><th>策略</th><th>名义金额</th><th class="align-right">浮动盈亏</th></tr></thead><tbody><tr v-for="trade in data.openTrades" :key="trade.trade_id"><td><strong>{{ trade.pair }}</strong></td><td>{{ trade.is_short ? "SHORT" : "LONG" }}</td><td>{{ trade.strategy }}</td><td>{{ trade.stake_amount.toFixed(2) }}</td><td class="align-right" :class="(trade.total_profit_ratio ?? 0) < 0 ? 'loss' : 'profit'">{{ ((trade.total_profit_ratio ?? 0) * 100).toFixed(2) }}%</td></tr></tbody></table></div>
      <StateBlock v-else state="empty" title="当前无持仓" detail="实时持仓将通过 /status API 自动同步。" />
    </div>
    <div v-else class="module-grid">
      <article class="panel"><span class="section-label">DRAWDOWN</span><h2>回撤监控</h2><div class="large-value">{{ data?.profit ? `${(data.profit.current_drawdown * 100).toFixed(2)}%` : "—" }}</div><p class="muted">历史最大 {{ data?.profit ? `${(data.profit.max_drawdown * 100).toFixed(2)}%` : "—" }}</p></article>
      <article class="panel"><span class="section-label">PROTECTION</span><h2>保护机制</h2><StateBlock state="empty" title="尚未读取保护配置" detail="后续接入交易锁与保护策略状态。" /></article>
    </div>
  </section>
</template>
