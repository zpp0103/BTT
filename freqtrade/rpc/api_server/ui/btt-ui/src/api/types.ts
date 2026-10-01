export type LoadState = "idle" | "loading" | "ready" | "error";

export interface ApiConfig {
  baseUrl: string;
  accessToken: string;
  refreshToken: string;
}

export interface ShowConfig {
  version: string;
  api_version: number;
  dry_run: boolean;
  demo_trading: boolean;
  stake_currency: string;
  exchange: string;
  strategy: string | null;
  bot_name: string;
  state: string;
  runmode: string;
  max_open_trades: number | string;
  trading_mode: string;
}

export interface Balances {
  total: number;
  total_bot: number;
  symbol: string;
  value: number;
  value_bot: number;
  stake: string;
  starting_capital: number;
  starting_capital_pct: number;
}

export interface Profit {
  profit_all_coin: number;
  profit_all_percent: number;
  profit_all_fiat: number;
  trade_count: number;
  closed_trade_count: number;
  winrate: number;
  profit_factor: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  max_drawdown_abs: number;
  current_drawdown: number;
}

export interface Order {
  order_id: string;
  status: string;
  amount: number;
  safe_price: number;
  cost: number;
  ft_order_side: string;
  order_type: string;
  order_timestamp: number | null;
}

export interface Trade {
  trade_id: number;
  pair: string;
  is_open: boolean;
  is_short: boolean;
  stake_amount: number;
  strategy: string;
  open_timestamp: number;
  close_timestamp: number | null;
  open_rate: number;
  close_rate: number | null;
  profit_ratio: number | null;
  profit_pct: number | null;
  profit_abs: number | null;
  current_rate?: number;
  total_profit_abs?: number;
  total_profit_ratio?: number | null;
  exit_reason: string | null;
  has_open_orders: boolean;
  orders: Order[];
}

export interface TradeResponse {
  trades: Trade[];
  total_trades: number;
}

export interface WalletHistory {
  columns: string[];
  data: unknown[][];
  length: number;
  capture_start_ts: number | null;
}

export interface Health {
  last_process: string | null;
  last_process_ts: number | null;
  bot_start: string | null;
  bot_start_ts: number | null;
}

export interface SysInfo {
  cpu_avg: number;
  cpu_count: number;
  ram_pct: number;
}

export interface EquityPoint {
  timestamp: number;
  value: number;
}

export interface EndpointError {
  endpoint: string;
  message: string;
}

export interface DashboardData {
  config: ShowConfig | null;
  balances: Balances | null;
  profit: Profit | null;
  openTrades: Trade[];
  closedTrades: Trade[];
  equity: EquityPoint[];
  health: Health | null;
  sysinfo: SysInfo | null;
  ping: boolean;
  errors: EndpointError[];
  updatedAt: number;
  source: "live" | "demo";
}
