import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { createDemoDashboard } from "@/api/demo";
import ModuleView from "./ModuleView.vue";

describe("ModuleView strategy governance", () => {
  it("shows recorded evidence and explicit governance gaps without promotion claims", () => {
    const wrapper = mount(ModuleView, {
      props: { module: "backtest", data: createDemoDashboard() },
    });

    expect(wrapper.text()).toContain("验证与晋级治理");
    expect(wrapper.text()).toContain("历史回测");
    expect(wrapper.text()).toContain("样本外验证");
    expect(wrapper.text()).toContain("未记录");
    expect(wrapper.text()).toContain("NO PROMOTION");
    expect(wrapper.text()).toContain("不运行回测、不批准、不发布、不切换策略");
    expect(wrapper.text()).not.toMatch(/自动晋级|已批准|通过验证/);
  });

  it("shows old-backend governance as unavailable", () => {
    const data = createDemoDashboard();
    data.governance = null;
    data.governanceProvenance = "unavailable";
    data.governanceDegradationReason = "当前后端版本不提供原生端点（404）";
    const wrapper = mount(ModuleView, {
      props: { module: "strategies", data },
    });

    expect(wrapper.find(".governance-panel").text()).toContain("验证治理不可用");
    expect(wrapper.find(".governance-panel").text()).toContain("当前后端版本不提供原生端点（404）");
    expect(wrapper.find(".governance-panel .source-badge").text()).toBe("UNAVAILABLE");
  });

  it("preserves real zero backtest metrics", () => {
    const data = createDemoDashboard();
    data.governance!.latest_backtest.trade_count.value = 0;
    data.governance!.latest_backtest.profit_ratio.value = 0;
    data.governance!.latest_backtest.max_drawdown.value = 0;
    const wrapper = mount(ModuleView, {
      props: { module: "backtest", data },
    });

    expect(wrapper.text()).toContain("样本交易0");
    expect(wrapper.text()).toContain("收益0.00%");
    expect(wrapper.text()).toContain("最大回撤0.00%");
  });
});
