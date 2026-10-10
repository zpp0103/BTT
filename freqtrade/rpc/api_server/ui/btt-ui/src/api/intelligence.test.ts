import { describe, expect, it } from "vitest";
import { createDemoIntelligence, isIntelligenceStale } from "./intelligence";

describe("market intelligence", () => {
  it("labels every demo surface and simulated opinion", () => {
    const data = createDemoIntelligence();

    expect(data.source_mode).toBe("demo");
    expect(data.providers.every((provider) => provider.provider_id.startsWith("demo-"))).toBe(true);
    expect(data.roundtable.opinions.every((opinion) => opinion.simulated)).toBe(true);
    expect(data.execution.mode).toBe("observe_only");
    expect(data.execution.status).toBe("disabled");
  });

  it("blocks snapshots that have aged beyond the freshness contract", () => {
    const data = createDemoIntelligence();
    const expiredAt = Date.parse(data.generated_at) + (data.freshness.max_age_seconds + 1) * 1000;

    expect(isIntelligenceStale(data, expiredAt)).toBe(true);
  });
});
