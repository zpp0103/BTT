from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Any

import fcntl

from crypto_quant_ai.backend.gateway import GatewayConfig
from crypto_quant_ai.backend.paper.account import PaperAccount
from crypto_quant_ai.backend.paper.audit import AuditLog
from crypto_quant_ai.backend.paper.order_event import OrderEvent
from crypto_quant_ai.backend.paper.snapshot import PortfolioSnapshot
from crypto_quant_ai.backend.gateway.venue import SimulatedVenueLedger, VenueFill

from .session_types import (
    Stage14AuditSummary,
    Stage14ReconciliationSnapshot,
    Stage14RunRecord,
    Stage14SessionState,
)


class LocalSessionStore:
    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = root_dir or os.path.join(
            tempfile.gettempdir(), "crypto_quant_ai_stage14_sessions"
        )
        os.makedirs(self.root_dir, exist_ok=True)

    @staticmethod
    def session_id_for_config(config: GatewayConfig) -> str:
        def _clean(value: str) -> str:
            return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())

        return "__".join(
            [
                _clean(config.account_id),
                _clean(config.strategy_id),
                _clean(config.symbol),
                _clean(config.timeframe),
            ]
        )

    def path_for(self, session_id: str) -> str:
        return os.path.join(self.root_dir, "sessions.json")

    def _lock_path(self) -> str:
        return os.path.join(self.root_dir, ".sessions.lock")

    def exists(self, session_id: str) -> bool:
        safe_id = self._sanitize_session_id(session_id)
        return safe_id in self._load_all()

    @staticmethod
    def _sanitize_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("invalid session_id")
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id.strip())
        if safe_id != session_id.strip():
            raise ValueError("invalid session_id")
        return safe_id

    def save(self, state: Stage14SessionState) -> str:
        safe_id = self._sanitize_session_id(state.session_id)
        path = self.path_for(safe_id)
        with self._exclusive_lock():
            payload = self._load_all()
            payload[safe_id] = self._state_to_dict(state)
            fd, tmp_path = tempfile.mkstemp(
                dir=self.root_dir,
                prefix="sessions.",
                suffix=".tmp",
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False, indent=2)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        return path

    def load(self, session_id: str) -> Stage14SessionState:
        safe_id = self._sanitize_session_id(session_id)
        try:
            payload = self._load_all()
            if safe_id not in payload:
                raise FileNotFoundError(session_id)
            return self._state_from_dict(payload[safe_id])
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ValueError(f"invalid session state for {session_id}: {exc}") from exc

    def create_empty_state(
        self,
        config: GatewayConfig,
        *,
        gateway_hash: str,
    ) -> Stage14SessionState:
        return Stage14SessionState(
            session_id=self.session_id_for_config(config),
            gateway_hash=gateway_hash,
            gateway_config=config,
            account=PaperAccount(cash=config.initial_cash),
            audit_summary=Stage14AuditSummary(0, 0, 0, 0, 0),
            reconciliation=Stage14ReconciliationSnapshot(True, 0, 0),
        )

    def _load_all(self) -> dict[str, Any]:
        path = self.path_for("sessions")
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError("session store root must be a JSON object")
        return payload

    @contextmanager
    def _exclusive_lock(self):
        lock_path = self._lock_path()
        with open(lock_path, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def build_audit_log(events: list[dict[str, Any]]) -> AuditLog:
        log = AuditLog()
        for item in events:
            snapshot = None
            if item.get("snapshot") is not None:
                snapshot = PortfolioSnapshot(
                    timestamp=datetime.fromisoformat(item["snapshot"]["timestamp"]),
                    cash=float(item["snapshot"]["cash"]),
                    positions={
                        str(k): float(v)
                        for k, v in dict(item["snapshot"].get("positions", {})).items()
                    },
                    total_equity=float(item["snapshot"].get("total_equity", 0.0)),
                    total_exposure=float(item["snapshot"].get("total_exposure", 0.0)),
                    exposure_pct=float(item["snapshot"].get("exposure_pct", 0.0)),
                    source=str(item["snapshot"].get("source", "")),
                )
            log.append(
                OrderEvent(
                    event_id=str(item["event_id"]),
                    order_id=str(item["order_id"]),
                    event_type=item["event_type"],
                    symbol=str(item["symbol"]),
                    side=str(item.get("side", "")),
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    quantity=float(item.get("quantity", 0.0)),
                    price=float(item.get("price", 0.0)),
                    status=str(item.get("status", "")),
                    reasons=[str(r) for r in item.get("reasons", [])],
                    source=item.get("source", "audit_log"),
                    snapshot=snapshot,
                )
            )
        return log

    @staticmethod
    def build_ledger(fills: list[dict[str, Any]]) -> SimulatedVenueLedger:
        ledger = SimulatedVenueLedger()
        for item in fills:
            ledger.record(
                VenueFill(
                    order_id=str(item["order_id"]),
                    symbol=str(item["symbol"]),
                    side=str(item["side"]),
                    quantity=float(item["quantity"]),
                    price=float(item["price"]),
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    venue=str(item.get("venue", "simulated")),
                )
            )
        return ledger

    def _state_to_dict(self, state: Stage14SessionState) -> dict[str, Any]:
        payload = asdict(state)
        payload["gateway_config"] = state.gateway_config.model_dump(mode="json")
        payload["account"] = state.account.model_dump(mode="json")
        return payload

    def _state_from_dict(self, payload: dict[str, Any]) -> Stage14SessionState:
        gateway_config = GatewayConfig.model_validate(payload["gateway_config"])
        account = PaperAccount.model_validate(payload["account"])
        audit_summary = Stage14AuditSummary(**payload["audit_summary"])
        reconciliation = Stage14ReconciliationSnapshot(**payload["reconciliation"])
        history = [Stage14RunRecord(**item) for item in payload.get("history", [])]
        return Stage14SessionState(
            session_id=str(payload["session_id"]),
            gateway_hash=str(payload["gateway_hash"]),
            gateway_config=gateway_config,
            account=account,
            audit_summary=audit_summary,
            reconciliation=reconciliation,
            latest_report_hash=str(payload.get("latest_report_hash", "")),
            latest_report_generated_at=str(payload.get("latest_report_generated_at", "")),
            latest_result=dict(payload.get("latest_result", {})),
            history=history,
            breaker_state=dict(payload.get("breaker_state", {})),
            order_seq=int(payload.get("order_seq", 0)),
            audit_events=list(payload.get("audit_events", [])),
            venue_fills=list(payload.get("venue_fills", [])),
            updated_at=str(payload.get("updated_at", "")),
        )
