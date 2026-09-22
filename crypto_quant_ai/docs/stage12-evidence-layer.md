# Stage 12 — Evidence / Self-Verification Layer

Stage 12 在 Stage 11 committee 之后增加证据采集、矛盾检测、fail-closed 验证和可审计报告导出层。该层保持 **paper-only / local-only / offline**。

## 组件

- `backend/evidence/types.py`
  - `EvidenceItem` / `EvidenceSet` / `VerificationResult` / `EvidenceReport`
  - `math.isfinite` 校验关键数值，拒绝 NaN/Inf
  - `evidence_hash` 对规范化输入稳定；忽略 `generated_at`、`started_at`、`stopped_at`
- `backend/evidence/collector.py`
  - 汇总 intelligence、committee、model contributions、replay 指标
  - 低稳定性或 overfit 自动生成 opposition（`max(0.5, 1.0 - stability + penalty)`）
  - replay 稳定性低于阈值时生成独立 risk opposition，并记录阈值到 details
- `backend/evidence/contradiction.py`
  - 使用 evidence 内记录的阈值检测矛盾（不硬编码 0.5）
  - active committee + unstable research/replay/overfit 必触发矛盾
- `backend/evidence/verifier.py`
  - 对证据不足、矛盾、低稳定性、overfit、非 finite 一律 fail-closed 为 `NO_TRADE`
  - 仅在证据充分且无矛盾时返回 `PAPER_TRADE`
- `backend/evidence/report.py`
  - Markdown / JSON / CSV（`csv.writer`）导出
  - 对敏感键值做脱敏，避免泄露凭据

## 安全边界

- `LIVE_TRADING=true` 在导入或构造时抛 `RuntimeError`。
- 不访问网络、不连接真实交易所、不下真实订单。

## 离线流程

`committee verdict -> evidence collect -> contradiction detect -> verify -> export report`

当出现不稳定研究或回测风险时，系统应退化为 `NO_TRADE`。
