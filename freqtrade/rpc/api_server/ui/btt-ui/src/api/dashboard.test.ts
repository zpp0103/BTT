import { describe, expect, it } from "vitest";
import { parseEquity } from "./dashboard";

describe("parseEquity", () => {
  it("maps wallet history columns without assuming their order", () => {
    const result = parseEquity({
      columns: ["bot_managed", "total_quote", "__date_ts"],
      data: [[true, 1024.5, 1_700_000_000]],
      length: 1,
      capture_start_ts: null,
    });
    expect(result).toEqual([{ timestamp: 1_700_000_000_000, value: 1024.5 }]);
  });

  it("returns an empty series for unsupported payloads", () => {
    expect(parseEquity({ columns: ["x"], data: [[1]], length: 1, capture_start_ts: null })).toEqual([]);
  });

  it("sorts wallet history chronologically", () => {
    const result = parseEquity({
      columns: ["__date_ts", "total"],
      data: [[1_700_000_100, 101], [1_700_000_000, 100]],
      length: 2,
      capture_start_ts: null,
    });
    expect(result.map((point) => point.value)).toEqual([100, 101]);
  });
});
