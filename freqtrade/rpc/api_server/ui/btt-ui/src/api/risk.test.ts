import { describe, expect, it } from "vitest";
import type { Profit, ShowConfig, Trade, TradeResponse } from "./types";
import {
  buildAuditRecords,
  buildRiskSnapshot,
  mapNativeDecisionJournal,
  mapNativeRiskSnapshot,
} from "./risk";

const config = { max_open_trades: 5 } as ShowConfig;
const profit = {
  current_drawdown: 0,
  max_drawdown: 0,
  max_drawdown_abs: 0,
} as Profit;

function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    trade_id: 1,
    pair: "BTC/USDT",
    is_open: false,
    is_short: false,
    amount: 0.5,
    stake_amount: 1000,
    strategy: "AuditStrategy",
    enter_tag: "breakout",
    open_timestamp: 1_700_000_000_000,
    open_fill_timestamp: 1_700_000_001_000,
    close_timestamp: 1_700_003_600_000,
    open_rate: 20_000,
    close_rate: 20_100,
    profit_ratio: 0,
    profit_pct: 0,
    profit_abs: 0,
    exit_reason: "roi",
    has_open_orders: false,
    orders: [],
    ...overrides,
  };
}

function tradeResponse(trades: Trade[], total = trades.length): TradeResponse {
  return { trades, trades_count: trades.length, offset: 0, total_trades: total };
}

describe("buildRiskSnapshot", () => {
  it("preserves real zero values instead of marking them unavailable", () => {
    const snapshot = buildRiskSnapshot({
      asOf: 1_700_000_000_000,
      config,
      profit,
      openTrades: [],
      closedTrades: tradeResponse([]),
      daily: {
        data: [{ date: "2026-10-11", abs_profit: 0, rel_profit: 0, starting_balance: 1000, fiat_value: 0, trade_count: 0 }],
        fiat_display_currency: "USD",
        stake_currency: "USDT",
      },
      locks: { lock_count: 0, locks: [] },
    });

    expect(snapshot.currentDrawdown).toMatchObject({ status: "available", value: 0 });
    expect(snapshot.nominalExposure).toMatchObject({ status: "available", value: 0 });
    expect(snapshot.todayProfit).toMatchObject({ status: "available", value: 0 });
    expect(snapshot.consecutiveLosses).toMatchObject({ status: "available", value: 0 });
    expect(snapshot.tradeLocks.value).toEqual({ count: 0, locks: [] });
  });

  it("marks only failed endpoint metrics unavailable during partial failure", () => {
    const snapshot = buildRiskSnapshot({
      asOf: 1_700_000_000_000,
      config,
      profit,
      openTrades: [],
      closedTrades: tradeResponse([]),
      daily: null,
      locks: null,
    });

    expect(snapshot.currentDrawdown.status).toBe("available");
    expect(snapshot.positionCapacity.status).toBe("available");
    expect(snapshot.todayProfit).toMatchObject({ status: "unavailable", value: null });
    expect(snapshot.tradeLocks).toMatchObject({ status: "unavailable", value: null });
    expect(snapshot.riskBudget).toMatchObject({ status: "unconfigured", value: null });
  });

  it("reports a consecutive loss count only when fetched history proves the boundary", () => {
    const bounded = buildRiskSnapshot({
      asOf: 1,
      config,
      profit,
      openTrades: [],
      closedTrades: tradeResponse([
        makeTrade({ trade_id: 3, close_timestamp: 300, profit_abs: -3 }),
        makeTrade({ trade_id: 2, close_timestamp: 200, profit_abs: -2 }),
        makeTrade({ trade_id: 1, close_timestamp: 100, profit_abs: 1 }),
      ]),
      daily: null,
      locks: null,
    });
    const truncated = buildRiskSnapshot({
      asOf: 1,
      config,
      profit,
      openTrades: [],
      closedTrades: tradeResponse([
        makeTrade({ trade_id: 2, close_timestamp: 200, profit_abs: -2 }),
        makeTrade({ trade_id: 1, close_timestamp: 100, profit_abs: -1 }),
      ], 10),
      daily: null,
      locks: null,
    });

    expect(bounded.consecutiveLosses).toMatchObject({ status: "available", value: 2 });
    expect(truncated.consecutiveLosses).toMatchObject({ status: "unavailable", value: null });
  });
});

describe("buildAuditRecords", () => {
  it("maps real decision and execution fields while leaving expected outcome unavailable", () => {
    const [record] = buildAuditRecords([], tradeResponse([makeTrade()]));

    expect(record).toMatchObject({
      strategy: "AuditStrategy",
      pair: "BTC/USDT",
      side: "long",
      decisionAt: 1_700_000_000_000,
      executionAt: 1_700_000_001_000,
      executionStatus: "closed",
      signalSource: { status: "available", value: "breakout" },
      exitReason: { status: "available", value: "roi" },
      actualProfitRatio: { status: "available", value: 0 },
      actualProfitAbs: { status: "available", value: 0 },
      expectedOutcome: { status: "unavailable", value: null },
    });
  });

  describe("server-native mappings", () => {
    it("preserves server timestamps, zero values, and provenance", () => {
      const snapshot = mapNativeRiskSnapshot({
        generated_timestamp: 2_000,
        event_timestamp: 1_500,
        status: "available",
        current_drawdown: { value: 0, status: "available", source: "server.dd" },
        max_drawdown: { value: 0.1, status: "available", source: "server.max_dd" },
        max_drawdown_abs: { value: 100, status: "available", source: "server.max_dd_abs" },
        position_capacity: { used: 0, limit: 5, utilization_pct: 0, status: "available", source: "server.capacity" },
        nominal_exposure: { value: 0, status: "available", source: "server.exposure" },
        today_realized_profit: { value: 0, status: "available", source: "server.today" },
        consecutive_losses: { value: 0, status: "available", source: "server.losses" },
        active_locks: [],
        locks_status: { status: "available", source: "server.locks" },
        risk_limit: { status: "unconfigured", source: "server.config", reason: "not configured" },
      });

      expect(snapshot).toMatchObject({
        asOf: 2_000,
        eventAt: 1_500,
        provenance: "server-native",
        currentDrawdown: { value: 0, status: "available" },
        riskBudget: { value: null, status: "unconfigured" },
      });
    });

    it("maps stable native journal IDs and capability-backed unavailable fields", () => {
      const records = mapNativeDecisionJournal({
        generated_timestamp: 2_000,
        offset: 0,
        count: 1,
        capabilities: {},
        events: [{
          id: "trade:42",
          event_timestamp: 1_500,
          strategy: "NativeStrategy",
          pair: "ETH/USDT",
          side: "short",
          stage: "exit",
          result: "stop_loss",
          enter_tag: "breakdown",
          signal_source: "breakdown",
          decision_reason: "stop_loss",
          rejection_reason: null,
          trade_id: 42,
          order_id: "order-1",
          order_status: "closed",
          order_side: "buy",
          open_rate: 100,
          close_rate: 102,
          profit_ratio: 0,
          profit_abs: 0,
          source: "trade_persistence",
        }],
      });

      expect(records[0]).toMatchObject({
        id: "trade:42",
        provenance: "server-native",
        signalSource: { value: "breakdown", status: "available" },
        actualProfitRatio: { value: 0, status: "available" },
        expectedOutcome: { value: null, status: "unavailable" },
      });
    });
  });
});
