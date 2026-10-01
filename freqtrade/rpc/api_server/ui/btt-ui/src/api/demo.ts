import type { DashboardData, Trade } from "./types";

const now = Date.now();

const trade = (id: number, pair: string, pct: number, open: boolean, short = false): Trade => ({
  trade_id: id,
  pair,
  is_open: open,
  is_short: short,
  stake_amount: 1200 + id * 85,
  strategy: "MomentumGridV2",
  open_timestamp: now - id * 3_600_000,
  close_timestamp: open ? null : now - id * 1_800_000,
  open_rate: 100 + id * 12,
  close_rate: open ? null : 100 + id * 12 + pct,
  profit_ratio: pct / 100,
  profit_pct: pct,
  profit_abs: (1200 + id * 85) * (pct / 100),
  current_rate: 100 + id * 12 + pct,
  total_profit_abs: (1200 + id * 85) * (pct / 100),
  total_profit_ratio: pct / 100,
  exit_reason: open ? null : pct > 0 ? "roi" : "stop_loss",
  has_open_orders: false,
  orders: [],
});

export function createDemoDashboard(): DashboardData {
  const equity = Array.from({ length: 32 }, (_, i) => {
    const trend = i * 58;
    const wave = Math.sin(i / 2.7) * 420 + Math.cos(i / 5) * 190;
    return { timestamp: now - (31 - i) * 86_400_000, value: 100_000 + trend + wave };
  });
  const openTrades = [trade(1, "BTC/USDT", 2.84, true), trade(2, "ETH/USDT", -0.72, true), trade(3, "SOL/USDT", 1.46, true, true)];
  const closedTrades = [trade(4, "BNB/USDT", 3.12, false), trade(5, "XRP/USDT", -1.04, false), trade(6, "LINK/USDT", 2.28, false)];
  return {
    config: {
      version: "demo",
      api_version: 2.5,
      dry_run: true,
      demo_trading: true,
      stake_currency: "USDT",
      exchange: "Binance",
      strategy: "MomentumGridV2",
      bot_name: "BTT Alpha",
      state: "running",
      runmode: "dry_run",
      max_open_trades: 8,
      trading_mode: "futures",
    },
    balances: {
      total: equity.at(-1)?.value ?? 0,
      total_bot: equity.at(-1)?.value ?? 0,
      symbol: "USDT",
      value: equity.at(-1)?.value ?? 0,
      value_bot: equity.at(-1)?.value ?? 0,
      stake: "USDT",
      starting_capital: 100_000,
      starting_capital_pct: 1.73,
    },
    profit: {
      profit_all_coin: 1732.48,
      profit_all_percent: 1.73,
      profit_all_fiat: 1732.48,
      trade_count: 184,
      closed_trade_count: 181,
      winrate: 0.642,
      profit_factor: 1.86,
      sharpe: 1.72,
      sortino: 2.18,
      max_drawdown: 0.047,
      max_drawdown_abs: 4715.4,
      current_drawdown: 0.012,
    },
    openTrades,
    closedTrades,
    equity,
    health: { last_process: new Date(now - 2800).toISOString(), last_process_ts: now - 2800, bot_start: new Date(now - 12 * 3_600_000).toISOString(), bot_start_ts: now - 12 * 3_600_000 },
    sysinfo: { cpu_avg: 18.4, cpu_count: 8, ram_pct: 42.7 },
    ping: true,
    errors: [],
    updatedAt: now,
    source: "demo",
  };
}
