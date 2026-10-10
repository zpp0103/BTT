import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createDemoDashboard } from "@/api/demo";
import { buildRiskSnapshot } from "@/api/risk";
import DashboardView from "./DashboardView.vue";

describe("DashboardView", () => {
  it("presents supported institutional context without inventing unavailable capabilities", () => {
    const wrapper = mount(DashboardView, {
      props: {
        data: createDemoDashboard(),
        state: "ready",
        demo: true,
      },
    });

    expect(wrapper.text()).toContain("策略与决策上下文");
    expect(wrapper.text()).toContain("回撤、敞口、当日盈亏与交易锁已接入");
    expect(wrapper.text()).toContain("市场观察层在线 · 不做状态分类");
    expect(wrapper.text()).toContain("OBSERVE ONLY");
    expect(wrapper.find(".execution-quality-panel").text()).toContain("READ ONLY");
    expect(wrapper.find(".execution-quality-panel").text()).toContain("平均成交延迟");
    expect(wrapper.find(".execution-quality-panel").text()).toContain("requested 与 average 的绝对差");
    expect(wrapper.find(".system-panel").text()).toContain("SYSTEM OBSERVABILITY / READ ONLY");
    expect(wrapper.find(".system-panel").text()).toContain("日志仅聚合级别计数");
    expect(wrapper.find(".system-panel").text()).not.toContain("warning detail");
    expect(wrapper.text()).toContain("本区域不参与策略选择、风险阈值或订单执行");
    expect(wrapper.text()).toContain("完整决策理由API 未提供");
    expect(wrapper.text()).toContain("验证证据只读接入，晋级与发布保持关闭");
    wrapper.unmount();
  });

  it("marks missing risk data as unavailable instead of healthy", () => {
    const data = createDemoDashboard();
    data.profit = null;
    data.balances = null;
    data.risk = buildRiskSnapshot({
      asOf: Date.now(),
      config: data.config,
      profit: null,
      openTrades: data.openTrades,
      closedTrades: null,
      daily: null,
      locks: null,
    });

    const wrapper = mount(DashboardView, {
      props: {
        data,
        state: "ready",
        demo: false,
      },
    });

    expect(wrapper.find(".risk-level").text()).toBe("风险数据不可用");
    expect(wrapper.find(".risk-level").classes()).toContain("unavailable");
    expect(wrapper.text()).toContain("收益接口不可用");
    expect(wrapper.text()).toContain("账户余额接口不可用");
    wrapper.unmount();
  });

  it("hides stale values when every core dashboard request fails", async () => {
    const wrapper = mount(DashboardView, {
      props: {
        data: createDemoDashboard(),
        state: "error",
        demo: false,
      },
    });

    expect(wrapper.text()).toContain("无法加载实时数据");
    expect(wrapper.text()).not.toContain("BTT Alpha");
    await wrapper.get(".primary-button").trigger("click");
    await wrapper.get(".secondary-button").trigger("click");
    expect(wrapper.emitted("refresh")).toHaveLength(1);
    expect(wrapper.emitted("navigate")).toEqual([["/settings"]]);
    wrapper.unmount();
  });

  it("warns when the risk snapshot is stale", () => {
    const data = createDemoDashboard();
    data.risk.asOf = Date.now() - data.risk.staleAfterMs - 1;

    const wrapper = mount(DashboardView, {
      props: {
        data,
        state: "ready",
        demo: false,
      },
    });

    expect(wrapper.find(".risk-level").text()).toBe("风险快照过期");
    expect(wrapper.find(".risk-level").classes()).toContain("warn");
    wrapper.unmount();
  });

  it("shows an honest unavailable state when the market observer endpoint is absent", () => {
    const data = createDemoDashboard();
    data.market = null;
    data.marketProvenance = "unavailable";
    data.marketDegradationReason = "当前后端版本不提供原生端点（404）";

    const wrapper = mount(DashboardView, {
      props: {
        data,
        state: "ready",
        demo: false,
      },
    });

    expect(wrapper.find(".market-panel").text()).toContain("市场观察层不可用");
    expect(wrapper.find(".market-panel").text()).toContain("当前后端版本不提供原生端点（404）");
    expect(wrapper.find(".market-panel .source-badge").text()).toBe("UNAVAILABLE");
    wrapper.unmount();
  });

  it("surfaces stale multi-timeframe coverage without predictive language", () => {
    const data = createDemoDashboard();
    const staleAt = Date.now() - 4 * 60 * 60_000;
    data.market!.event_timestamp = staleAt;
    data.market!.health.stale = 2;
    data.market!.health.fresh = 4;
    data.market!.timeframes[1].stale = 2;
    data.market!.timeframes[1].fresh = 1;

    const wrapper = mount(DashboardView, {
      props: {
        data,
        state: "ready",
        demo: true,
      },
    });

    expect(wrapper.find(".market-panel").text()).toContain("市场数据过期");
    expect(wrapper.find(".market-panel").text()).toContain("5m");
    expect(wrapper.find(".market-panel").text()).toContain("1h");
    expect(wrapper.find(".market-panel").text()).toContain("stale");
    expect(wrapper.find(".market-panel").text()).not.toMatch(/买入|卖出|置信度|预测/);
    wrapper.unmount();
  });

  it("shows execution quality as unavailable instead of fabricating zero metrics", () => {
    const data = createDemoDashboard();
    data.executionQuality = null;
    data.executionQualityProvenance = "unavailable";
    data.executionQualityDegradationReason = "当前后端版本不提供原生端点（404）";

    const wrapper = mount(DashboardView, {
      props: {
        data,
        state: "ready",
        demo: false,
      },
    });

    expect(wrapper.find(".execution-quality-panel").text()).toContain("执行质量分析不可用");
    expect(wrapper.find(".execution-quality-panel").text()).toContain("当前后端版本不提供原生端点（404）");
    expect(wrapper.find(".execution-quality-panel").text()).not.toContain("0ms");
    wrapper.unmount();
  });

  it("keeps system observability fallback explicit on old backends", () => {
    const data = createDemoDashboard();
    data.observability = null;
    data.observabilityProvenance = "unavailable";
    data.observabilityDegradationReason = "当前后端版本不提供原生端点（404）";

    const wrapper = mount(DashboardView, {
      props: {
        data,
        state: "ready",
        demo: false,
      },
    });

    expect(wrapper.find(".system-panel .source-badge").text()).toBe("UNAVAILABLE");
    expect(wrapper.find(".system-panel").text()).toContain("当前后端版本不提供原生端点（404）");
    expect(wrapper.find(".system-panel").text()).not.toContain("遥测在线");
    wrapper.unmount();
  });

  it("preserves dashboard controls and navigation events", async () => {
    const wrapper = mount(DashboardView, {
      props: {
        data: createDemoDashboard(),
        state: "ready",
        demo: true,
      },
    });

    await wrapper.get(".mode-toggle").trigger("click");
    await wrapper.get(".positions-panel a").trigger("click");

    expect(wrapper.emitted("toggle-demo")).toHaveLength(1);
    expect(wrapper.emitted("navigate")).toEqual([["/positions"]]);
    wrapper.unmount();
  });
});
