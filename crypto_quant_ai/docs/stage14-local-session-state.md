# Stage 14 — Local Session State & Continuous Execution Layer

Stage 14 在 Stage 13 之上增加可持续复用的本地 paper session，使多次运行之间能够保留账户、持仓、审计、venue ledger、以及 circuit-breaker 状态。

## 目标

- 保持 **paper-only / local-only / offline / fail-closed**。
- 按 `account_id / strategy_id / symbol / timeframe` 识别本地 session。
- 支持在已有 session 上重复执行 Stage 13，而不是每次都从空白账户开始。

## 持久化内容

- `PaperAccount`
- audit summary 与完整 audit events
- venue ledger fills
- circuit-breaker state
- latest report hash / latest result summary
- run history
- reconciliation snapshot

## 入口

保留现有 `POST /stage13/run`，并新增本地接口：

- `POST /stage14/sessions` — create/load session
- `GET /stage14/sessions/{session_id}` — 查看当前 paper state 摘要
- `POST /stage14/sessions/{session_id}/run` — 在已有 session 上执行一次 Stage 13 pipeline
- `GET /stage14/sessions/{session_id}/history` — 导出 session history（JSON）
- `GET /stage14/sessions/{session_id}/history?format=csv` — 导出 session history（CSV）

## 执行语义

- Stage 12 verification 仍是 gateway 前的硬闸门。
- 只有 verification 通过后，已有 session 才会推进到 gateway 执行。
- 已有持仓会被后续 `SELL` 使用。
- breaker / drawdown / reconciliation 基于已恢复的真实本地 paper state 生效。

## 存储

默认使用本地 JSON store，按 session key 写入临时目录下的本地 session 文件。该存储不连接网络、不读取真实凭据、不创建真实订单。

## 测试覆盖

- BUY → SELL 跨运行连续执行
- session 恢复
- breaker 状态延续
- invalid restore failure
- session history export
- Stage 14 API endpoints
