# Stage 13 — Execution Orchestration Layer

Stage 13 将 Stage 9 intelligence、Stage 11 committee、Stage 12 evidence、Stage 7 gateway 串成一个 **end-to-end / paper-only / offline** 的单次执行编排层。

## 目标

- 输入从本地 OHLCV candles 开始。
- 输出一个可审计的单次执行结果，包含：
  - market context
  - intelligence report
  - committee verdict
  - evidence set + verification
  - final decision
  - gateway execution / block reason
- 任何验证失败都默认 fail-closed，不进入 gateway 执行。

## 流程

```text
local candles
  -> IntelligenceOrchestrator.analyze()
  -> ModelCommittee.evaluate()
  -> EvidenceCollector.collect()
  -> ContradictionDetector.detect()
  -> EvidenceVerifier.verify()
  -> gateway submit or block
  -> Stage 13 report export
```

## 关键规则

- `LIVE_TRADING=true` 时导入、构造、运行都会抛出 `RuntimeError`。
- committee 负责生成可执行方向；intelligence 提供研究和风险上下文。
- evidence verification 是 gateway 前的硬闸门：
  - 证据不足
  - 矛盾
  - 低稳定性 / overfit
  - 非 finite 值
  都会返回 `NO_TRADE` 或直接阻断执行。
- gateway 仅在 verification 通过后才会收到最终 `FinalDecision`。

## 新增组件

`crypto_quant_ai/backend/orchestration/`

- `types.py` — Stage 13 request / result / report types, API request model, stable hash helper.
- `orchestrator.py` — pipeline orchestration, final decision synthesis, gateway submit-or-block flow.
- `formatters.py` — Markdown / JSON / CSV export with sensitive-value redaction.
- `__init__.py` — paper-only guard and public exports.

## API 入口

保留现有 `/` 与 `/health` 不变，并新增同步本地入口：

- `POST /stage13/run`

该入口只接受本地 candles 输入并同步返回 Stage 13 报告，不创建后台守护进程，不触发真实交易。

## 输出

- `Stage13Report`
- `stage13_execution_report.md`
- `stage13_execution_report.json`
- `stage13_execution_report.csv`

## 验收

- verification 失败时不会进入 gateway。
- verification 通过时可生成可审计的 paper execution result。
- 输出包含 block reason / verification reason / gateway result / report hash。
- 无网络、无真实凭据、无真实订单、无 `LIVE_TRADING` 放开路径。
