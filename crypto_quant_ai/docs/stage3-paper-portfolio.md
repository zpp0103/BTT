# Stage 3.1 — Local Paper Portfolio

## 概述

Stage 3.1 在 `crypto_quant_ai/backend/paper/` 模块中实现本地纸面账户系统，支持虚拟持仓和虚拟订单操作，**不连接任何交易所，不使用真实 API Key，不产生真实订单**。

## 安全约束

| 约束 | 状态 |
|------|------|
| `LIVE_TRADING=false` | ✅ enforced |
| `PAPER_TRADING=true` | ✅ enforced |
| 无交易所连接 | ✅ 无第三方交易库 |
| 无真实 API Key | ✅ 无密钥字段 |
| 无真实订单 | ✅ 虚拟订单仅内存 |
| 仅修改白名单路径 | ✅ |

## 模块结构

```
crypto_quant_ai/backend/paper/
├── __init__.py       # 公共 API 导出
└── account.py        # PaperAccount / PaperPosition / PaperOrder + buy() / sell()
```

## 数据模型

### PaperPosition
| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | `str` | 交易对，如 `BTC` |
| `quantity` | `float` | 持仓数量，`> 0` |
| `avg_cost` | `float` | 平均成本价，`> 0` |

### PaperOrder
| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | `str` | 交易对 |
| `side` | `Literal["buy","sell"]` | 买卖方向 |
| `quantity` | `float` | 数量 |
| `price` | `float` | 执行价格 |
| `timestamp` | `datetime` | UTC 时间戳 |

### PaperAccount
| 字段 | 类型 | 说明 |
|------|------|------|
| `cash` | `float` | 可用资金，默认 100,000 |
| `positions` | `dict[str, PaperPosition]` | 当前持仓 |
| `orders` | `list[PaperOrder]` | 历史订单 |

## 核心函数

### `buy(account, symbol, quantity, price) -> (new_account, order)`
- 扣除现金，更新持仓（支持加仓均化成本）
- 抛出 `ValueError` 当现金不足

### `sell(account, symbol, quantity, price) -> (new_account, order)`
- 平仓或减仓，增加现金
- 抛出 `ValueError` 当无持仓或数量超限

## 范围限制

- ❌ 无交易所连接
- ❌ 无 API Key / Secret
- ❌ 无 BTT / Freqtrade core 修改
- ✅ 仅 `crypto_quant_ai/` / `docs/` / `scripts/` / `.env.example`
