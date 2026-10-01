import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EquityChart from "./EquityChart.vue";

describe("EquityChart", () => {
  it("shows a finite change when the first equity value is zero", () => {
    const wrapper = mount(EquityChart, {
      props: {
        currency: "USDT",
        points: [
          { timestamp: 1_700_000_000_000, value: 0 },
          { timestamp: 1_700_000_100_000, value: 100 },
        ],
      },
    });

    expect(wrapper.find(".metric-delta").text()).toBe("+0.00%");
    expect(wrapper.text()).not.toContain("Infinity");
  });
});
