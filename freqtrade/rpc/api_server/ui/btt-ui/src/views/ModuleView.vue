<script setup lang="ts">
import type { DashboardData } from "@/api/types";
import Icon from "@/components/Icon.vue";
import StateBlock from "@/components/StateBlock.vue";

defineProps<{ module: string; data: DashboardData | null }>();

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
      <article class="panel"><span class="section-label">ACTIVE</span><h2>当前策略</h2><div class="large-value">{{ data?.config?.strategy ?? "未加载" }}</div><p class="muted">{{ data?.config?.trading_mode ?? "—" }} · {{ data?.config?.exchange ?? "—" }}</p></article>
      <article class="panel"><span class="section-label">LIFECYCLE</span><h2>策略版本</h2><StateBlock state="empty" title="暂无版本记录" detail="后续可接入策略列表与参数版本对比。" /></article>
    </div>
    <div v-else-if="module === 'backtest'" class="module-grid">
      <article class="panel"><span class="section-label">LATEST RESULT</span><h2>最近回测</h2><StateBlock state="empty" title="暂无回测结果" detail="可通过现有 /backtest API 接入任务创建、进度与结果分析。" /></article>
      <article class="panel"><span class="section-label">COMPARE</span><h2>策略对比</h2><StateBlock state="empty" title="等待对比样本" detail="选择多个回测结果后比较收益、回撤和稳定性。" /></article>
    </div>
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
