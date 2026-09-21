# Stage 4 — Backtest Engine

## 1. 目标

提供本地回测引擎，在 OHLCV 历史数据上模拟策略表现，生成性能指标报告。

## 2. 安全约束

- `paper_trading=true` 强制要求；`LIVE_TRADING=false` 环境变量检查
- 无网络请求、无交易所连接、无真实订单
- 所有交易通过 PaperAccount/PaperExecutor 本地执行
- 模块 import 时检查 `LIVE_TRADING` 环境变量，为 `true` 则抛 RuntimeError

## 3. 模块结构

```
crypto_quant_ai/backend/backtest/
├── __init__.py          # 公开 API 导出
├── types.py             # 类型定义与枚举
├── equity_tracker.py    # 权益曲线与回撤跟踪
├── trade_ledger.py      # 交易记录与 FIFO 配对
├── metrics.py           # 性能指标计算
└── simulator.py         # 回测模拟器主引擎
```

## 4. 核心类型

### 4.1 BacktestConfig

回测配置（不可变）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| initial_cash | float | 100000.0 | 初始资金 |
| fee_bps | float | 10.0 | 手续费（基点） |
| slippage_bps | float | 5.0 | 滑点（基点） |
| start_time | datetime \| None | None | 回测起始时间 |
| end_time | datetime \| None | None | 回测结束时间 |
| paper_trading | bool | True | 必须为 True |

### 4.2 BacktestTrade

单笔交易记录（不可变）：trade_id、timestamp、symbol、action、quantity、price、fee、slippage_cost、cash_after、position_after、reason。

### 4.3 BacktestMetrics

性能指标（不可变）：total_return、max_drawdown、sharpe_ratio、sortino_ratio、win_rate、profit_factor 等完整指标集。

### 4.4 BacktestResult

回测结果（不可变）：run_id、config、status、trades、metrics、started_at、completed_at、error_message。

### 4.5 TradeAction 枚举

BUY、SELL、HOLD 三种动作。

### 4.6 BacktestStatus 枚举

PENDING、RUNNING、COMPLETED、FAILED、CANCELLED。

## 5. EquityTracker

权益曲线跟踪器：

- `record(timestamp, cash, position_value)`：记录权益点
- `peak_equity`：历史最高权益
- `max_drawdown`：最大回撤（绝对值）
- `max_drawdown_pct`：最大回撤百分比
- `equity_series()`：返回 (timestamp, equity) 列表
- `reset()`：清空所有数据

## 6. TradeLedger

交易账本，使用 FIFO 配对买卖：

- `record(trade)`：记录交易，自动 FIFO 配对
- `closed_trades`：已完成 round-trip 交易列表
- `win_rate`、`winning_trades`、`losing_trades`：胜负统计
- `avg_win`、`avg_loss`、`profit_factor`：盈亏分析
- `reset()`：清空

### FIFO 配对规则

卖出时从最早的买入 lot 开始匹配。部分卖出会拆分 lot。一个 lot 可以匹配多次卖出。

## 7. Metrics Calculator

`compute_metrics(config, equity_tracker, trade_ledger)` 计算所有性能指标：

- **总收益**：final_equity - initial_cash
- **最大回撤**：从 peak 到 trough 的最大跌幅
- **Sharpe Ratio**：(平均收益 - 无风险收益) / 收益标准差 × 年化因子
- **Sortino Ratio**：同 Sharpe 但仅用下行波动
- **胜率**：盈利交易数 / 总闭环交易数
- **盈利因子**：总盈利 / 总亏损（绝对值）

年化因子根据回测时间跨度和数据点数量自动估算。

## 8. BacktestSimulator

回测模拟器，主引擎：

### 初始化

```python
sim = BacktestSimulator(config=BacktestConfig(initial_cash=100000))
```

可选注入 `PaperRiskGate`（Stage 3.3），在交易前执行风控检查。

### 运行回测

```python
result = sim.run(
    candles=ohlcv_bars,
    signal_fn=my_strategy,  # callable(candle, account) -> CandleSignal | None
    symbol="BTC",
)
```

### 信号函数

`signal_fn` 接收当前 K 线和账户状态，返回 `CandleSignal` 或 `None`（表示 HOLD）。

`CandleSignal` 包含 timestamp、symbol、action、price、quantity、reason。

### 执行流程

1. 初始化 PaperAccount 和 PaperExecutor
2. 遍历每根 K 线：
   a. 调用 signal_fn 生成信号
   b. 记录权益点
   c. 若 BUY/SELL，计算手续费和滑点，通过 PaperAccount 执行
   d. 记录交易到 TradeLedger
3. 计算最终指标
4. 返回 BacktestResult

### 手续费与滑点

- 手续费 = 名义金额 × fee_rate
- 滑点调整买入价向上、卖出价向下
- 交易失败（资金不足/仓位不足）跳过不报错

## 9. 与前序 Stage 集成

| Stage | 集成点 |
|-------|--------|
| Stage 2.1 | OHLCVBar 数据结构用于回测输入 |
| Stage 3.1 | PaperAccount 执行买卖 |
| Stage 3.2 | PaperExecutor 封装执行 |
| Stage 3.3 | PaperRiskGate 可选注入风控 |
| Stage 3.4 | AuditLog 可选注入审计 |

## 10. 测试覆盖

`test_stage4_backtest.py` 包含以下测试类：

- `TestBacktestConfig`：配置验证（10 tests）
- `TestBacktestTrade`：交易记录验证（5 tests）
- `TestBacktestMetrics`：指标验证（3 tests）
- `TestEquityTracker`：权益跟踪（8 tests）
- `TestTradeLedger`：FIFO 配对（10 tests）
- `TestComputeMetrics`：指标计算（4 tests）
- `TestBacktestSimulator`：端到端模拟（10 tests）
- `TestSafetyGuards`：安全检查（5 tests）
- `TestBacktestResult`：结果验证（3 tests）
- `TestCandleSignal`：信号验证（4 tests）

## 11. 运行测试

```bash
PYTHONPATH=. python -m pytest crypto_quant_ai/backend/tests/test_stage4_backtest.py --noconftest -q
```

全量回归：

```bash
PYTHONPATH=. python -m pytest crypto_quant_ai/backend/tests --noconftest -q
```

## 12. 安全自检

源码与文档中不得出现以下小写禁用词字面量（测试文件使用 hex 编码间接表示）：

- 第三方交易客户端名称
- 下单方法名
- 真实订单关键词
- 自动交易关键词
- API 密钥字段名
- live_trading（小写）

`.env.example` 中 `LIVE_TRADING=false` 必须始终保持。
