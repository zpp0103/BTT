from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Sequence

from crypto_quant_ai.backend.backtest.simulator import BacktestSimulator
from crypto_quant_ai.backend.backtest.types import BacktestConfig
from crypto_quant_ai.backend.decision.brain_orchestrator import MultiBrainOrchestrator
from crypto_quant_ai.backend.paper.audit import AuditLog
from crypto_quant_ai.backend.paper.executor import PaperExecutor
from crypto_quant_ai.backend.paper.risk_gate import PaperRiskGate

from .registry import build_brains
from .strategy import build_signal_fn
from .types import (
    ReplayConfig,
    StrategySpec,
    StrategyReport,
    SummarySection,
    PerformanceSection,
    AuditSection,
    EquitySection,
    canonical_hash,
)


class StrategyReplayer:
    def __init__(self, config: ReplayConfig, strategy: StrategySpec):
        self.config = config
        self.strategy = strategy
        self.audit_log = AuditLog()
        self.backtest_config = config.to_backtest_config()

    def _input_hash(self, candles: Sequence[Any]) -> str:
        normalized = []
        for candle in candles:
            normalized.append(
                {
                    "timestamp": (
                        getattr(candle, "timestamp", None).isoformat()
                        if getattr(candle, "timestamp", None) is not None
                        else None
                    ),
                    "open": float(getattr(candle, "open", 0.0)),
                    "high": float(getattr(candle, "high", 0.0)),
                    "low": float(getattr(candle, "low", 0.0)),
                    "close": float(getattr(candle, "close", 0.0)),
                    "volume": float(getattr(candle, "volume", 0.0)),
                }
            )
        payload = {
            "strategy": {
                "id": self.strategy.id,
                "name": self.strategy.name,
                "version": self.strategy.version,
                "brains": list(self.strategy.brains),
                "position_fraction": self.strategy.position_fraction,
                "timeframe": self.strategy.timeframe,
            },
            "config": {
                "initial_cash": self.config.initial_cash,
                "fee_bps": self.config.fee_bps,
                "slippage_bps": self.config.slippage_bps,
                "symbol": self.config.symbol,
                "start_time": (
                    self.config.start_time.isoformat() if self.config.start_time else None
                ),
                "end_time": (
                    self.config.end_time.isoformat() if self.config.end_time else None
                ),
            },
            "candles": normalized,
        }
        return canonical_hash(payload)

    def run(self, candles: Sequence[Any]) -> dict:
        # Apply time filter if configured.
        filtered = list(candles)
        if self.config.start_time is not None:
            filtered = [
                c
                for c in filtered
                if getattr(c, "timestamp", None) is not None
                and c.timestamp >= self.config.start_time
            ]
        if self.config.end_time is not None:
            filtered = [
                c
                for c in filtered
                if getattr(c, "timestamp", None) is not None
                and c.timestamp <= self.config.end_time
            ]

        if not filtered:
            raise ValueError("no candles available in replay window")

        brains = build_brains(self.strategy.brains)
        orchestrator = MultiBrainOrchestrator(brains, max_workers=max(1, len(brains)))

        sim = BacktestSimulator(
            self.backtest_config, risk_gate=None, audit_log=self.audit_log
        )

        # Inject the risk gate so the executor enforces it and the audit log
        # captures validated/rejected events (Stage 3.3 + Stage 3.4 pipeline).
        risk_gate = PaperRiskGate(
            account=sim.account,
            executor=sim._executor,
            min_confidence=self.strategy.risk_gate.min_confidence,
            max_position_fraction=self.strategy.risk_gate.max_position_fraction,
            min_risk_reward=self.strategy.risk_gate.min_risk_reward,
            min_stop_loss_pct=self.strategy.risk_gate.min_stop_loss_pct,
        )
        sim._risk_gate = risk_gate
        sim._executor = PaperExecutor(
            account=sim.account,
            audit_log=self.audit_log,
            risk_gate=risk_gate,
        )

        signal_fn = build_signal_fn(orchestrator, self.strategy, self.config)
        result = sim.run(filtered, signal_fn=signal_fn, symbol=self.config.symbol)

        input_hash = self._input_hash(filtered)

        metrics = getattr(result, "metrics", None)
        summary = SummarySection(
            total_return=getattr(metrics, "total_return", 0.0),
            total_return_pct=getattr(metrics, "total_return_pct", 0.0),
            max_drawdown_pct=getattr(metrics, "max_drawdown_pct", 0.0),
            sharpe_ratio=getattr(metrics, "sharpe_ratio", 0.0),
            sortino_ratio=getattr(metrics, "sortino_ratio", 0.0),
            win_rate_pct=getattr(metrics, "win_rate_pct", 0.0),
            profit_factor=getattr(metrics, "profit_factor", 0.0),
            final_equity=getattr(metrics, "final_equity", 0.0),
            initial_cash=getattr(metrics, "initial_cash", self.config.initial_cash),
        )

        perf = PerformanceSection(
            total_return=summary.total_return,
            total_return_pct=summary.total_return_pct,
            max_drawdown_pct=summary.max_drawdown_pct,
            sharpe_ratio=summary.sharpe_ratio,
            sortino_ratio=summary.sortino_ratio,
            win_rate_pct=summary.win_rate_pct,
            profit_factor=summary.profit_factor,
            final_equity=summary.final_equity,
            initial_cash=summary.initial_cash,
        )

        eq_points = sim.equity_tracker.equity_series()
        equity = EquitySection(
            initial=sim.equity_tracker.initial_equity,
            peak=sim.equity_tracker.peak_equity,
            final=sim.equity_tracker.final_equity,
            points=[(ts, eq) for ts, eq in eq_points],
        )

        trace_sample = []
        for ev in list(self.audit_log.all_events())[:10]:
            trace_sample.append(
                {
                    "order_id": getattr(ev, "order_id", None),
                    "event_type": getattr(ev, "event_type", None),
                    "status": getattr(ev, "status", None),
                    "timestamp": (
                        getattr(ev, "timestamp", None).isoformat()
                        if getattr(ev, "timestamp", None) is not None
                        else None
                    ),
                }
            )

        audit = AuditSection(
            total_orders=getattr(self.audit_log, "total_orders", 0),
            executed=getattr(self.audit_log, "executed_count", 0),
            rejected=getattr(self.audit_log, "rejected_count", 0),
            skipped=getattr(self.audit_log, "skipped_count", 0),
            trace_sample=trace_sample,
        )

        report = StrategyReport(
            title=f"Strategy Replay: {self.strategy.name}",
            generated_at=datetime.utcnow(),
            input_hash=input_hash,
            strategy={
                "id": self.strategy.id,
                "name": self.strategy.name,
                "version": self.strategy.version,
                "brains": list(self.strategy.brains),
                "timeframe": self.strategy.timeframe,
            },
            config={
                "initial_cash": self.config.initial_cash,
                "fee_bps": self.config.fee_bps,
                "slippage_bps": self.config.slippage_bps,
                "start_time": (
                    self.config.start_time.isoformat()
                    if self.config.start_time
                    else None
                ),
                "end_time": (
                    self.config.end_time.isoformat() if self.config.end_time else None
                ),
                "symbol": self.config.symbol,
            },
            summary=summary,
            performance=perf,
            audit=audit,
            equity=equity,
            trades=[
                {
                    "trade_id": getattr(t, "trade_id", None),
                    "timestamp": (
                        getattr(t, "timestamp", None).isoformat()
                        if getattr(t, "timestamp", None) is not None
                        else None
                    ),
                    "symbol": getattr(t, "symbol", None),
                    "action": (
                        getattr(t, "action", None).value
                        if getattr(t, "action", None) is not None
                        else None
                    ),
                    "quantity": getattr(t, "quantity", 0.0),
                    "price": getattr(t, "price", 0.0),
                    "fee": getattr(t, "fee", 0.0),
                    "slippage_cost": getattr(t, "slippage_cost", 0.0),
                    "cash_after": getattr(t, "cash_after", 0.0),
                    "position_after": getattr(t, "position_after", 0.0),
                }
                for t in getattr(result, "trades", tuple())
            ],
        )

        return {
            "result": result,
            "report": report,
            "input_hash": input_hash,
            "audit_log": self.audit_log,
            "equity_series": eq_points,
        }
