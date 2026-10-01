import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DashboardView from "./DashboardView.vue";
import type { DashboardData } from "@/api/types";

const unavailableData: DashboardData = {
  config: null,
  balances: null,
  profit: null,
  openTrades: [],
  closedTrades: [],
  equity: [],
  health: null,
  sysinfo: null,
  ping: false,
  errors: Array.from({ length: 9 }, (_, index) => ({ endpoint: `API ${index + 1}`, message: "不可用" })),
  updatedAt: Date.now(),
  source: "live",
};

describe("DashboardView", () => {
  it("hides misleading metrics when every endpoint fails", () => {
    const wrapper = mount(DashboardView, {
      props: { data: unavailableData, state: "error", demo: false },
    });

    expect(wrapper.text()).toContain("无法加载实时数据");
    expect(wrapper.text()).toContain("数据面板已暂停展示");
    expect(wrapper.find(".metric-strip").exists()).toBe(false);
    expect(wrapper.find(".state-actions").exists()).toBe(true);
  });

  it("reports unavailable risk and system status without positive indicators", () => {
    const wrapper = mount(DashboardView, {
      props: { data: unavailableData, state: "ready", demo: false },
    });

    expect(wrapper.find(".risk-level").text()).toBe("数据不可用");
    const resourceRow = wrapper.findAll(".system-list li").at(-1)!;
    expect(resourceRow.text()).toContain("不可用");
    expect(resourceRow.find("i").classes()).not.toContain("ok");
    expect(wrapper.find(".strategy-panel").text()).toContain("运行模式未知");
  });
});
