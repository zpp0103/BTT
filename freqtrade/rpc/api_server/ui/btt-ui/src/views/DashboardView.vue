<script setup lang="ts">
import { computed } from "vue";
import EquityChart from "@/components/EquityChart.vue";
import Icon from "@/components/Icon.vue";
import StateBlock from "@/components/StateBlock.vue";
import type { DashboardData, LoadState, Trade } from "@/api/types";

const props = defineProps<{ data: DashboardData | null; state: LoadState; demo: boolean }>();
const emit = defineEmits<{ refresh: []; "toggle-demo": []; navigate: [path: string] }>();

const currency = computed(() => props.data?.config?.stake_currency ?? props.data?.balances?.stake ?? "USDT");
const equity = computed(() => props.data?.balances?.total_bot ?? props.data?.balances?.total ?? 0);
const todayProfit = computed(() => {
  const points = props.data?.equity ?? [];
  if (points.length < 2) return null;
  const last = points.at(-1)!.value;
  const cutoff = Date.now() - 86_400_000;
  const base = points.findLast((point) => point.timestamp <= cutoff)?.value ?? points.at(-2)!.value;
  return { abs: last - base, pct: base ? ((last / base) - 1) * 100 : 0 };
});
const recentTrades = computed(() => [...(props.data?.openTrades ?? []), ...(props.data?.closedTrades ?? [])].sort((a, b) => (b.close_timestamp ?? b.open_timestamp) - (a.close_timestamp ?? a.open_timestamp)).slice(0, 6));
const healthFresh = computed(() => !!props.data?.health?.last_process_ts && Date.now() - normalizedTs(props.data.health.last_process_ts) < 60_000);
const errorSummary = computed(() => props.data?.errors.map((error) => `${error.endpoint}: ${error.message}`).join("；") ?? "");

function normalizedTs(value: number): number {
  return value < 10_000_000_000 ? value * 1000 : value;
}
const money = (value: number, digits = 2) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
const percent = (value: number | null | undefined) => `${(value ?? 0) >= 0 ? "+" : ""}${(value ?? 0).toFixed(2)}%`;
const tradeProfit = (trade: Trade) => trade.total_profit_ratio != null ? trade.total_profit_ratio * 100 : (trade.profit_pct ?? 0);
const timestamp = (value: number | null) => value ? new Date(normalizedTs(value)).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "进行中";
</script>

<template>
  <section class="view dashboard-view">
    <header class="view-header">
      <div>
        <div class="header-kicker"><span>工作台</span><span>/</span><span>总览</span></div>
        <h1>交易总览</h1>
        <p>组合、策略与风险的实时运行视图</p>
      </div>
      <div class="header-actions">
        <button class="mode-toggle" :class="{ demo }" type="button" @click="emit('toggle-demo')">
          <span class="status-dot"></span>{{ demo ? "DEMO 演示数据" : "LIVE 实时数据" }}
        </button>
        <button class="icon-button" type="button" aria-label="刷新数据" :disabled="state === 'loading'" @click="emit('refresh')"><Icon name="refresh" /></button>
      </div>
    </header>

    <StateBlock v-if="state === 'loading' && !data" state="loading" detail="正在连接 Freqtrade API 并加载账户数据" />
    <StateBlock v-else-if="state === 'error' && !data" state="error" title="无法加载总览" detail="请在系统设置中检查 API 地址和登录状态。" />
    <template v-else-if="data">
      <div v-if="data.errors.length" class="inline-alert" role="alert">
        <Icon name="alert" /><div><strong>部分实时数据加载失败</strong><span>{{ errorSummary }}</span></div>
      </div>

      <div class="metric-strip">
        <article class="metric-primary">
          <span class="metric-label">资产净值 <em>{{ currency }}</em></span>
          <strong>{{ money(equity) }}</strong>
          <span class="metric-caption">机器人管理资产</span>
        </article>
        <article>
          <span class="metric-label">今日收益</span>
          <strong v-if="todayProfit" :class="todayProfit.abs < 0 ? 'loss' : 'profit'">{{ todayProfit.abs >= 0 ? "+" : "" }}{{ money(todayProfit.abs) }}</strong>
          <strong v-else>—</strong>
          <span class="metric-caption" :class="todayProfit && todayProfit.pct < 0 ? 'loss' : 'profit'">{{ todayProfit ? percent(todayProfit.pct) : "权益历史不足" }}</span>
        </article>
        <article>
          <span class="metric-label">累计收益</span>
          <strong :class="(data.profit?.profit_all_coin ?? 0) < 0 ? 'loss' : 'profit'">{{ data.profit ? `${data.profit.profit_all_coin >= 0 ? "+" : ""}${money(data.profit.profit_all_coin)}` : "—" }}</strong>
          <span class="metric-caption">{{ data.profit ? percent(data.profit.profit_all_percent) : "接口不可用" }}</span>
        </article>
        <article>
          <span class="metric-label">当前持仓</span>
          <strong>{{ data.openTrades.length }} <small>/ {{ data.config?.max_open_trades ?? "—" }}</small></strong>
          <span class="metric-caption">已用策略仓位</span>
        </article>
      </div>

      <div class="dashboard-grid">
        <article class="panel equity-panel">
          <div class="panel-head">
            <div><span class="section-label">PERFORMANCE</span><h2>权益曲线</h2></div>
            <span class="period-label">历史全量</span>
          </div>
          <EquityChart v-if="data.equity.length > 1" :points="data.equity" :currency="currency" />
          <StateBlock v-else state="empty" title="暂无权益历史" detail="Freqtrade 记录两个以上钱包快照后将显示曲线。" />
        </article>

        <article class="panel strategy-panel">
          <div class="panel-head"><div><span class="section-label">STRATEGY</span><h2>策略运行</h2></div><span class="status-pill" :class="data.config?.state === 'running' ? 'ok' : 'warn'">{{ data.config?.state ?? "未知" }}</span></div>
          <div class="strategy-name">
            <span class="strategy-mark">B</span>
            <div><strong>{{ data.config?.strategy ?? "未加载策略" }}</strong><span>{{ data.config?.exchange ?? "—" }} · {{ data.config?.trading_mode ?? "—" }}</span></div>
          </div>
          <dl class="data-list">
            <div><dt>运行模式</dt><dd><span class="status-dot"></span>{{ data.config?.dry_run ? "模拟交易" : "实盘交易" }}</dd></div>
            <div><dt>已完成交易</dt><dd>{{ data.profit?.closed_trade_count ?? "—" }}</dd></div>
            <div><dt>胜率</dt><dd>{{ data.profit ? `${(data.profit.winrate * 100).toFixed(1)}%` : "—" }}</dd></div>
            <div><dt>Profit Factor</dt><dd>{{ data.profit?.profit_factor?.toFixed(2) ?? "—" }}</dd></div>
          </dl>
        </article>

        <article class="panel positions-panel">
          <div class="panel-head"><div><span class="section-label">POSITIONS</span><h2>当前持仓</h2></div><a href="/positions" @click.prevent="emit('navigate', '/positions')">查看全部</a></div>
          <div v-if="data.openTrades.length" class="positions-list">
            <div v-for="trade in data.openTrades.slice(0, 4)" :key="trade.trade_id" class="position-row">
              <div><strong>{{ trade.pair }}</strong><span>{{ trade.is_short ? "SHORT" : "LONG" }} · {{ money(trade.stake_amount, 0) }} {{ currency }}</span></div>
              <div class="position-price"><span>{{ money(trade.current_rate ?? trade.open_rate, 4) }}</span><strong :class="tradeProfit(trade) < 0 ? 'loss' : 'profit'">{{ percent(tradeProfit(trade)) }}</strong></div>
            </div>
          </div>
          <StateBlock v-else state="empty" title="当前无持仓" detail="策略产生有效入场信号后，仓位会显示在这里。" />
        </article>

        <article class="panel risk-panel">
          <div class="panel-head"><div><span class="section-label">RISK</span><h2>风险概览</h2></div><span class="risk-level" :class="{ elevated: (data.profit?.current_drawdown ?? 0) > .1 }">风险正常</span></div>
          <div class="risk-gauge">
            <div><span>当前回撤</span><strong>{{ data.profit ? `${(data.profit.current_drawdown * 100).toFixed(2)}%` : "—" }}</strong></div>
            <div class="gauge-track"><span :style="{ width: `${Math.min((data.profit?.current_drawdown ?? 0) * 500, 100)}%` }"></span></div>
          </div>
          <dl class="risk-stats">
            <div><dt>最大回撤</dt><dd>{{ data.profit ? `${(data.profit.max_drawdown * 100).toFixed(2)}%` : "—" }}</dd></div>
            <div><dt>Sharpe</dt><dd>{{ data.profit?.sharpe?.toFixed(2) ?? "—" }}</dd></div>
            <div><dt>Sortino</dt><dd>{{ data.profit?.sortino?.toFixed(2) ?? "—" }}</dd></div>
          </dl>
        </article>

        <article class="panel orders-panel">
          <div class="panel-head"><div><span class="section-label">ACTIVITY</span><h2>近期订单与成交</h2></div><span>{{ recentTrades.length }} 条记录</span></div>
          <div v-if="recentTrades.length" class="trade-table-wrap">
            <table>
              <thead><tr><th>交易对</th><th>方向</th><th>状态</th><th>时间</th><th class="align-right">盈亏</th></tr></thead>
              <tbody>
                <tr v-for="trade in recentTrades" :key="trade.trade_id">
                  <td><strong>{{ trade.pair }}</strong></td>
                  <td><span class="side-tag" :class="{ short: trade.is_short }">{{ trade.is_short ? "SHORT" : "LONG" }}</span></td>
                  <td>{{ trade.is_open ? "持仓中" : trade.exit_reason ?? "已成交" }}</td>
                  <td>{{ timestamp(trade.close_timestamp ?? trade.open_timestamp) }}</td>
                  <td class="align-right" :class="tradeProfit(trade) < 0 ? 'loss' : 'profit'">{{ percent(tradeProfit(trade)) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <StateBlock v-else state="empty" title="暂无交易记录" detail="已完成和进行中的交易会显示在这里。" />
        </article>

        <article class="panel system-panel">
          <div class="panel-head"><div><span class="section-label">INFRASTRUCTURE</span><h2>系统状态</h2></div><Icon name="server" /></div>
          <ul class="system-list">
            <li><span><i :class="{ ok: data.ping }"></i>API 服务</span><strong>{{ data.ping ? "在线" : "离线" }}</strong></li>
            <li><span><i :class="{ ok: healthFresh }"></i>交易引擎</span><strong>{{ healthFresh ? "运行正常" : "心跳异常" }}</strong></li>
            <li><span><i :class="{ ok: !!data.config?.exchange }"></i>交易所连接</span><strong>{{ data.config?.exchange ?? "未知" }}</strong></li>
            <li><span><i class="ok"></i>系统资源</span><strong>{{ data.sysinfo ? `CPU ${data.sysinfo.cpu_avg.toFixed(0)}% · RAM ${data.sysinfo.ram_pct.toFixed(0)}%` : "不可用" }}</strong></li>
          </ul>
        </article>
      </div>
    </template>
  </section>
</template>
