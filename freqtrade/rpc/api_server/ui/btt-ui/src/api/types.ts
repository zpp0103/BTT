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
  current_drawdown_abs?: number;
  latest_trade_timestamp?: number;
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
  order_filled_timestamp?: number | null;
  is_open?: boolean;
  ft_order_tag?: string | null;
}

export interface Trade {
  trade_id: number;
  pair: string;
  is_open: boolean;
  is_short: boolean;
  amount?: number;
  stake_amount: number;
  strategy: string;
  enter_tag?: string | null;
  open_timestamp: number;
  open_fill_timestamp?: number | null;
  close_timestamp: number | null;
  open_rate: number;
  close_rate: number | null;
  profit_ratio: number | null;
  profit_pct: number | null;
  profit_abs: number | null;
  current_rate?: number;
  total_profit_abs?: number;
  total_profit_ratio?: number | null;
  realized_profit?: number;
  exit_reason: string | null;
  exit_order_status?: string | null;
  has_open_orders: boolean;
  leverage?: number | null;
  liquidation_price?: number | null;
  stop_loss_abs?: number | null;
  orders: Order[];
}

export interface TradeResponse {
  trades: Trade[];
  trades_count: number;
  offset: number;
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

export interface DailyProfitRecord {
  date: string;
  abs_profit: number;
  rel_profit: number;
  starting_balance: number;
  fiat_value: number;
  trade_count: number;
}

export interface DailyProfitResponse {
  data: DailyProfitRecord[];
  fiat_display_currency: string;
  stake_currency: string;
}

export interface PairLock {
  id: number;
  active: boolean;
  lock_end_time: string;
  lock_end_timestamp: number;
  lock_time: string;
  lock_timestamp: number;
  pair: string;
  side: string;
  reason: string | null;
}

export interface LocksResponse {
  lock_count: number;
  locks: PairLock[];
}

export type AvailabilityStatus = "available" | "partial" | "unavailable" | "unconfigured";
export type AuditAvailabilityStatus = AvailabilityStatus | "partial";
export type DataProvenance = "server-native" | "client-derived" | "demo" | "unavailable";

export interface DataMetric<T> {
  value: T | null;
  status: AvailabilityStatus;
  source: string;
  reason?: string;
}

export interface PositionCapacity {
  used: number;
  limit: number | null;
  utilizationPct: number | null;
}

export interface LockSnapshot {
  count: number;
  locks: PairLock[];
}

export interface RiskSnapshot {
  asOf: number;
  eventAt: number | null;
  staleAfterMs: number;
  provenance: DataProvenance;
  degradationReason?: string;
  currentDrawdown: DataMetric<number>;
  maxDrawdown: DataMetric<number>;
  maxDrawdownAbs: DataMetric<number>;
  positionCapacity: DataMetric<PositionCapacity>;
  nominalExposure: DataMetric<number>;
  todayProfit: DataMetric<number>;
  todayLoss: DataMetric<number>;
  consecutiveLosses: DataMetric<number>;
  tradeLocks: DataMetric<LockSnapshot>;
  riskBudget: DataMetric<number>;
}

export type AuditExecutionStatus = "open" | "open_order" | "closed";

export interface AuditRecord {
  id: string;
  strategy: string;
  pair: string;
  side: "long" | "short";
  decisionAt: number;
  executionAt: number | null;
  completedAt: number | null;
  executionStatus: AuditExecutionStatus;
  signalSource: DataMetric<string>;
  exitReason: DataMetric<string>;
  expectedOutcome: DataMetric<number>;
  actualProfitRatio: DataMetric<number>;
  actualProfitAbs: DataMetric<number>;
  provenance: DataProvenance;
}

export interface ReadOnlyCapability {
  status: AvailabilityStatus;
  source: string;
  reason?: string | null;
}

export interface NativeReadOnlyMetric {
  value: number | null;
  status: AvailabilityStatus;
  source: string;
  reason?: string | null;
}

export interface NativePositionCapacity {
  used: number;
  limit: number | null;
  utilization_pct: number | null;
  status: AvailabilityStatus;
  source: string;
  reason?: string | null;
}

export interface NativeRiskSnapshot {
  generated_timestamp: number;
  event_timestamp: number | null;
  status: AvailabilityStatus;
  current_drawdown: NativeReadOnlyMetric;
  max_drawdown: NativeReadOnlyMetric;
  max_drawdown_abs: NativeReadOnlyMetric;
  position_capacity: NativePositionCapacity;
  nominal_exposure: NativeReadOnlyMetric;
  today_realized_profit: NativeReadOnlyMetric;
  consecutive_losses: NativeReadOnlyMetric;
  active_locks: PairLock[];
  locks_status: ReadOnlyCapability;
  risk_limit: ReadOnlyCapability;
}

export interface NativeDecisionEvent {
  id: string;
  event_timestamp: number;
  strategy: string;
  pair: string;
  side: "long" | "short";
  stage: "entry" | "position" | "exit";
  result: string;
  enter_tag: string | null;
  signal_source: string | null;
  decision_reason: string | null;
  rejection_reason: string | null;
  trade_id: number;
  order_id: string | null;
  order_status: string | null;
  order_side: string | null;
  open_rate: number;
  close_rate: number | null;
  profit_ratio: number | null;
  profit_abs: number | null;
  source: "trade_persistence";
}

export interface NativeDecisionJournal {
  generated_timestamp: number;
  events: NativeDecisionEvent[];
  offset: number;
  count: number;
  capabilities: Record<string, ReadOnlyCapability>;
}

export interface MarketPairObservation {
  pair: string;
  timeframe: string;
  status: "available" | "unavailable";
  freshness: "fresh" | "stale" | "unavailable";
  event_timestamp: number | null;
  sample_count: number;
  close: number | null;
  change_pct: number | null;
  range_pct: number | null;
  volume: number | null;
  volume_ratio: number | null;
  source: string;
  reason?: string | null;
}

export interface MarketTimeframeSummary {
  timeframe: string;
  requested_pairs: number;
  available: number;
  fresh: number;
  stale: number;
  unavailable: number;
  coverage_pct: number;
  breadth: {
    observed: number;
    advancing: number;
    declining: number;
    unchanged: number;
    unavailable: number;
  };
}

export interface MarketObserverSnapshot {
  mode: "observe_only";
  affects_trading: false;
  generated_timestamp: number;
  event_timestamp: number | null;
  status: "available" | "partial" | "unavailable";
  timeframe: string;
  lookback_candles: number;
  pairs: MarketPairObservation[];
  breadth: {
    observed: number;
    advancing: number;
    declining: number;
    unchanged: number;
    unavailable: number;
  };
  timeframes: MarketTimeframeSummary[];
  health: {
    requested_timestamp: number;
    generated_timestamp: number;
    generation_duration_ms: number;
    requested_observations: number;
    available: number;
    fresh: number;
    stale: number;
    unavailable: number;
    coverage_pct: number;
  };
  capabilities: Record<string, ReadOnlyCapability>;
}

export interface ExecutionQualitySnapshot {
  mode: "read_only";
  affects_trading: false;
  generated_timestamp: number;
  event_timestamp: number | null;
  status: "available" | "partial" | "unavailable";
  fee_totals: Array<{ currency: string; value: number; source: string }>;
  fee_status: ReadOnlyCapability;
  average_fill_latency_ms: DataMetric<number>;
  p95_fill_latency_ms: DataMetric<number>;
  average_price_deviation_bps: DataMetric<number>;
  lifecycle: { total: number; open: number; filled: number; cancelled: number; other: number };
  coverage: {
    sampled_trades: number;
    sampled_orders: number;
    fee_records: number;
    latency_records: number;
    price_deviation_records: number;
  };
  recent_orders: Array<{
    id: string;
    event_timestamp: number;
    trade_id: number;
    order_id: string | null;
    pair: string;
    side: string;
    lifecycle: "open" | "filled" | "cancelled" | "other";
    created_timestamp: number | null;
    filled_timestamp: number | null;
    fill_latency_ms: number | null;
    requested_price: number | null;
    average_price: number | null;
    price_deviation_bps: number | null;
    source: "order_persistence";
  }>;
  capabilities: Record<string, ReadOnlyCapability>;
}

export type GovernanceEvidenceStatus = "available" | "partial" | "unavailable" | "not_recorded";

export interface StrategyGovernanceSnapshot {
  mode: "read_only";
  affects_trading: false;
  promotion_allowed: false;
  generated_timestamp: number;
  status: "available" | "partial" | "unavailable";
  strategy: {
    identifier: string;
    class_name: string;
    version: string | null;
    fingerprint: string | null;
    fingerprint_algorithm: "sha256" | null;
    fingerprint_status: ReadOnlyCapability;
  };
  latest_backtest: {
    status: GovernanceEvidenceStatus;
    source: string;
    reason?: string | null;
    result_file?: string | null;
    run_id?: string | null;
    run_timestamp?: number | null;
    sample_start_timestamp?: number | null;
    sample_end_timestamp?: number | null;
    timeframe?: string | null;
    trade_count: DataMetric<number>;
    profit_ratio: DataMetric<number>;
    max_drawdown: DataMetric<number>;
    win_rate: DataMetric<number>;
  };
  gates: Array<{
    id: "backtest" | "out_of_sample" | "stress_test" | "paper_trading" | "limited_capital" | "human_approval" | "rollback_point";
    label: string;
    status: GovernanceEvidenceStatus;
    source: string;
    reason?: string | null;
  }>;
  capabilities: Record<string, ReadOnlyCapability>;
}

export interface SystemObservabilitySnapshot {
  mode: "read_only";
  affects_trading: false;
  generated_timestamp: number;
  status: "available" | "partial" | "unavailable";
  runtime_state: string;
  heartbeat_age_ms: DataMetric<number>;
  uptime_ms: DataMetric<number>;
  database_status: ReadOnlyCapability;
  open_trade_count: DataMetric<number>;
  active_lock_count: DataMetric<number>;
  active_pair_count: DataMetric<number>;
  cpu_pct: DataMetric<number>;
  ram_pct: DataMetric<number>;
  log_window: {
    requested_limit: number;
    record_count: number;
    oldest_timestamp: number | null;
    newest_timestamp: number | null;
  };
  log_levels: Record<string, number>;
  alerts: Array<{
    id: string;
    severity: "warning" | "error";
    title: string;
    count: number;
    event_timestamp: number | null;
    source: string;
  }>;
  capabilities: Record<string, ReadOnlyCapability>;
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
  risk: RiskSnapshot;
  audit: AuditRecord[];
  auditStatus: AuditAvailabilityStatus;
  auditProvenance: DataProvenance;
  auditCapabilities: Record<string, ReadOnlyCapability>;
  market: MarketObserverSnapshot | null;
  marketProvenance: DataProvenance;
  marketDegradationReason?: string;
  executionQuality: ExecutionQualitySnapshot | null;
  executionQualityProvenance: DataProvenance;
  executionQualityDegradationReason?: string;
  governance: StrategyGovernanceSnapshot | null;
  governanceProvenance: DataProvenance;
  governanceDegradationReason?: string;
  observability: SystemObservabilitySnapshot | null;
  observabilityProvenance: DataProvenance;
  observabilityDegradationReason?: string;
  errors: EndpointError[];
  updatedAt: number;
  source: "live" | "demo";
}
