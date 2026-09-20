# 圆桌会议回测阶段

当前先完成**历史数据回测**，不启动 Paper Trading，更不接入实盘。

## 1. 安装与检查

在仓库根目录执行：

```bash
python -m compileall user_data/roundtable user_data/strategies/RoundTableStrategy.py
freqtrade list-strategies --config config_examples/config_roundtable_backtest.json
```

输出中应包含 `RoundTableStrategy`。

## 2. 下载历史数据

只下载 BTC 和 ETH 的 15 分钟合约数据。示例时间范围需要根据 Binance 数据可用性调整：

```bash
freqtrade download-data \
  --config config_examples/config_roundtable_backtest.json \
  --timerange 20250101-20260101 \
  --timeframes 15m
```

如果交易所数据不可用，先缩短时间范围，不要修改策略代码。

## 3. 执行回测

```bash
freqtrade backtesting \
  --config config_examples/config_roundtable_backtest.json \
  --strategy RoundTableStrategy \
  --timerange 20250101-20260101 \
  --export signals
```

查看最近一次结果：

```bash
freqtrade backtesting-show --config config_examples/config_roundtable_backtest.json
```

## 4. 生成图表

```bash
freqtrade plot-dataframe \
  --config config_examples/config_roundtable_backtest.json \
  --strategy RoundTableStrategy \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --timerange 20250101-20260101
```

FreqUI 可以作为后续的可视化入口；本阶段先保证回测结果、交易信号和风控否决逻辑正确，再制作圆桌专用的深色渐变仪表盘。这样不会为了视觉效果掩盖回测逻辑问题。

## 安全边界

- 配置保持 `dry_run: true`。
- 配置没有 API key 或 secret。
- 以上命令不会下单。
- 不要把 `.env`、数据库、回测结果或真实凭据提交到仓库。
- 回测收益不代表未来收益，进入 Testnet 前必须先检查交易数、最大回撤、收益曲线和异常信号。
