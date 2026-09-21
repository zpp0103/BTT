# Stage 3.4 — Local Paper Portfolio Audit Trail

## 1. 目标 (Goal)

为本地 paper trading 增加**不可变、可查询、可导出**的审计账本，使每一笔
纸面订单的完整生命周期（创建 → 风险校验 → 接受 → 执行 → 关闭 / 拒绝 / 跳过）
都被本地记录，用于事后追溯与合规核验。

## 2. 范围 (Scope)

仅涉及本地 paper 模块：

- `crypto_quant_ai/backend/paper/order_event.py` （新增）
- `crypto_quant_ai/backend/paper/snapshot.py` （新增）
- `crypto_quant_ai/backend/paper/execution_trace.py` （新增）
- `crypto_quant_ai/backend/paper/audit.py` （新增）
- `crypto_quant_ai/backend/paper/executor.py` （在 `execute()` 中注入审计点，向后兼容）
- `crypto_quant_ai/backend/paper/__init__.py` （导出新增符号）
- `crypto_quant_ai/backend/tests/test_stage3_4_audit.py` （新增）
- 本文档

不修改 BTT / Freqtrade 核心，不修改 `requirements.txt` / `pyproject.toml`，
不执行真实下单、不连接交易所、不发起任何网络请求。

## 3. 安全保证 (Safety Guarantees)

- `LIVE_TRADING=true` 时，上述模块在 import 阶段即抛出 `RuntimeError`，
  杜绝任何真实交易风险。
- 审计账本**只记录、不执行**：`AuditLog` 不提供 `buy` / `sell` / `execute` 方法。
- 拒绝的订单**不会**改变 `cash` / `positions`，也**不会**生成 `executed` 事件。
- 不引入任何第三方交易客户端，不保存任何密钥类字段。
- 估值（如有）仅使用调用方显式传入的本地价格；**绝不**联网获取行情。

## 4. 设计 (Design)

```
OrderEvent ──▶ ExecutionTrace (单笔订单生命周期)
     │
     ▼
  AuditLog (全局账本, 按 order_id 聚合 trace, 可查询/导出)
```

- `OrderEvent`：单条不可变状态事件，含 `order_id` / `event_type` / `symbol` /
  `side` / `quantity` / `price` / `timestamp` / `status` / `reasons` / `source` /
  `snapshot`。
- `ExecutionTrace`：同一 `order_id` 的事件序列，含 `snapshot_before` /
  `snapshot_after` / `final_status`，内置状态机校验。
- `AuditLog`：追加式账本，提供 `append` / `append_trace` / `query_by_order` /
  `query_recent` / `all_events` / `clear`，以及 `to_csv` / `to_json` 导出。

## 5. PortfolioSnapshot

`PortfolioSnapshot`：某一时刻的本地账户视图。

| 字段 | 含义 |
| --- | --- |
| `timestamp` | 采集时间 |
| `cash` | 空闲现金（计价币） |
| `positions` | `symbol -> quantity` |
| `total_equity` | `cash + 估值敞口` |
| `total_exposure` | 估值敞口（无价格时为 0） |
| `exposure_pct` | `total_exposure / total_equity` |
| `source` | 采集方 |

`snapshot_from_account(account, source, *, prices=None)` 在不传入价格时
保守地令敞口为 0，**不**访问网络。

## 6. OrderEvent

合法 `event_type`：`created` / `validated` / `accepted` / `rejected` /
`executed` / `closed` / `skipped`。

校验规则：

- `order_id`、`symbol` 非空；
- `timestamp` 必须为合法 `datetime`；
- `side` ∈ {`buy`, `sell`, `""`}（`""` 表示尚未决定方向）；
- `quantity` / `price` 必须有限且非负；
- `rejected` 事件**必须**携带至少一条 `reasons`；
- `status` 缺省时与 `event_type` 一致。

## 7. ExecutionTrace

合法状态机：

```
created -> validated -> accepted -> executed -> closed
                              \-> rejected
                              \-> skipped
```

非法跃迁（如 `validated -> executed` 跳过 `accepted`）会抛出 `ValueError`。
`from_events(events)` 可用于从已存储事件重建 trace；`is_executed` 在曾经进入
`EXECUTED` 后保持为真（即使后续进入 `CLOSED`）。

## 8. AuditLog

方法（命名遵循规范）：

- `append(event)`：追加单条事件并路由到对应 trace。
- `append_trace(trace)`：追加整条 trace 的全部事件。
- `query_by_order(order_id)`：返回该订单全部事件（确定性排序）。
- `query_recent(limit)`：返回最近 `limit` 条全局事件。
- `all_events()`：返回全部事件（确定性排序）。
- `clear()`：清空全部事件与 trace。

附带视图：`total_orders` / `executed_count` / `rejected_count` /
`skipped_count` / `traces_by_symbol` / `traces_by_state`，以及
`to_csv` / `to_json` 导出。

确定性排序键：`(timestamp, 生命周期序位, event_id)`。

## 9. 与 Executor 的集成 (Stage 3.2)

`PaperExecutor(account, *, default_fraction, audit_log=None, risk_gate=None)`。

当注入 `audit_log` 时，`execute()` 会在每个状态转换追加 `OrderEvent` 并携带
前后 `PortfolioSnapshot`：

- `created`（下单前快照）
- `validated`（风险校验结果，来自 `risk_gate`）
- `accepted`（执行前快照）
- `executed`（执行后快照）
- `closed`
- 或在 `veto` / `NO_TRADE` / 无有效价格 / 现金不足 / 超量时追加 `skipped` / `rejected`。

**向后兼容**：不传 `audit_log` / `risk_gate` 时，行为与 Stage 3.2 完全一致。

## 10. 与 Stage 3.3 的集成

当注入 `risk_gate` 时，Stage 3.3 风险闸门**始终在** `buy` / `sell` 之前执行：

- 闸门通过 → 继续正常流程；
- 闸门拒绝 → 记录 `validated` + `rejected` 事件，直接返回，
  **不**修改 `cash` / `positions`，**不**生成 `executed` 事件。

由此保证「风险不通过的订单必须被拒绝，且不得改变账户状态」。

## 11. 测试覆盖 (Test Coverage)

`test_stage3_4_audit.py` 覆盖：

- `OrderEvent` 校验（必填字段、非法 `event_type`、非法 `side`、缺 `timestamp`、
  `rejected` 必须带原因、负数量拒绝、默认 `status`）。
- `ExecutionTrace` 正常生命周期、拒绝分支、非法跃迁拒绝、`from_events` 重建。
- `PortfolioSnapshot` 从账户构建、显式价格估值正确。
- `AuditLog` 的 `append` / `append_trace` / `query_by_order` / `query_recent` /
  `all_events` / `clear` / `to_csv` / `to_json` / 重复 `order_id` 累积。
- Executor 集成：完整生命周期事件与快照、拒绝不改账户且无 `executed`、
  Stage 3.3 闸门先于执行、向后兼容、执行前后快照与账户一致。
- 安全属性：事件/导出不含密钥、账本不执行订单、模块不含交易所/网络代码、
  `LIVE_TRADING=true` 时 import 抛 `RuntimeError`。

## 12. 验收结论 (Acceptance)

- Stage 3.4 测试：**全部通过**（33 passed）。
- 全量回归：Stage 1 / 2.1 / 3.1 / 3.2 / 3.3 / 3.4 全绿。
- 安全扫描：无第三方交易客户端、无密钥类字段、无下单类关键字符号命中。
- Git 范围：仅 `crypto_quant_ai/**` 与 `docs/**`，未触碰核心与依赖清单。
- `LIVE_TRADING=false`：`true` 时所有审计模块拒绝加载。

**FINAL DECISION: STAGE 3.4 PASS。**
