from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Sequence

from crypto_quant_ai.backend.brains.llm_stub import LLMStubBrain
from crypto_quant_ai.backend.committee import ModelCommittee
from crypto_quant_ai.backend.committee.types import ModelCommitteeConfig
from crypto_quant_ai.backend.core.models import BrainAnalysis, FinalDecision, MarketData
from crypto_quant_ai.backend.data.ohlcv import OHLCVBar, validate_ohlcv
from crypto_quant_ai.backend.evidence import (
    ContradictionDetector,
    EvidenceCollector,
    EvidenceSet,
    EvidenceVerifier,
)
from crypto_quant_ai.backend.gateway import (
    GatewayConfig,
    GatewayReportGenerator,
    LiveTradingSession,
    compute_gateway_hash,
)
from crypto_quant_ai.backend.intelligence import IntelligenceOrchestrator, IntelligenceReport
from crypto_quant_ai.backend.replay.registry import build_brains

from .formatters import report_to_dict
from .types import (
    Stage13ExecutionResult,
    Stage13MarketContext,
    Stage13Report,
    Stage13Request,
    Stage13RequestSummary,
    default_stage13_committee_config,
    stage13_hash,
)


def _live_guard() -> None:
    if os.environ.get("LIVE_TRADING", "false").lower() == "true":
        raise RuntimeError("Stage 13 orchestration requires LIVE_TRADING=false (paper only).")


_DEFAULT_BRAINS = ("quant", "market_structure", "risk", "devil_advocate")


class Stage13Orchestrator:
    def __init__(
        self,
        *,
        models: Sequence[Any] | None = None,
        intelligence_orchestrator: Any | None = None,
        evidence_collector: EvidenceCollector | None = None,
        evidence_verifier: EvidenceVerifier | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        _live_guard()
        self._models = list(models) if models is not None else None
        self._intelligence_orchestrator = intelligence_orchestrator
        self._collector = evidence_collector or EvidenceCollector()
        self._verifier = evidence_verifier or EvidenceVerifier(min_items=2)
        self._detector = contradiction_detector or ContradictionDetector()

    def run(self, request: Stage13Request) -> Stage13Report:
        _live_guard()
        candles = validate_ohlcv(request.candles)
        if not candles:
            raise ValueError("Stage13Request requires at least one candle")
        gateway_config = request.gateway_config.model_copy(
            update={
                "symbol": request.symbol,
                "timeframe": request.timeframe,
            }
        )

        intelligence = self._analyze_intelligence(request, candles)
        market_data = self._to_market_data(candles[-1], request.symbol, request.timeframe)
        committee_cfg = request.committee_config or default_stage13_committee_config()
        verdict = ModelCommittee(self._build_models(), committee_cfg).evaluate(
            market_data, intelligence.market_state
        )

        gateway_hash = compute_gateway_hash(gateway_config)
        session = LiveTradingSession(gateway_config)
        session.start()
        try:
            final_decision = self._build_final_decision(
                market_data, verdict, intelligence, gateway_config, session
            )
            evidence = self._collector.collect(
                intelligence_report=self._research_payload(intelligence, verdict),
                committee_verdict=verdict,
                model_contributions=verdict.contributions,
                replay_metrics=self._replay_payload(intelligence),
            )
            contradictions = self._detector.detect(evidence)
            verification = self._verifier.verify(evidence)

            gateway_result = None
            gateway_allowed = False
            block_reason = ""
            if not verification.approved:
                block_reason = "; ".join(verification.reasons) or "verification failed"
            elif final_decision.decision not in ("BUY", "SELL"):
                block_reason = final_decision.reasoning or "committee did not produce active decision"
            elif final_decision.decision == "SELL" and not self._has_position(session, final_decision.symbol):
                block_reason = f"no paper position available for SELL execution: {final_decision.symbol}"
            else:
                gateway_allowed = True
                gateway_result = session.submit_decision(
                    final_decision, reference_price=market_data.close
                )
                if not gateway_result.executed:
                    block_reason = gateway_result.reason

            reconciliation = session.reconcile()
            gateway_report = GatewayReportGenerator().build(
                session, gateway_hash=gateway_hash, reconciliation=reconciliation
            )
        finally:
            session.stop()

        request_summary = Stage13RequestSummary(
            symbol=request.symbol,
            timeframe=request.timeframe,
            candles_count=len(candles),
            timeframes=list(request.timeframes),
            committee_fusion=committee_cfg.fusion.value,
            gateway_hash=gateway_hash,
        )
        market_context = Stage13MarketContext(
            symbol=request.symbol,
            timeframe=request.timeframe,
            candles_count=len(candles),
            first_timestamp=self._ts(candles[0]),
            last_timestamp=self._ts(candles[-1]),
            last_close=float(candles[-1].close),
        )
        result = Stage13ExecutionResult(
            verification_passed=verification.approved,
            gateway_allowed=gateway_allowed,
            executed=bool(gateway_result and gateway_result.executed),
            blocked=not bool(gateway_result and gateway_result.executed),
            block_reason=block_reason,
            final_decision=final_decision,
            gateway_result=gateway_result,
        )
        report = Stage13Report(
            request=request_summary,
            market_context=market_context,
            intelligence=intelligence,
            committee_verdict=verdict,
            evidence=evidence,
            verification=verification,
            contradictions=contradictions,
            result=result,
            gateway_report=gateway_report,
        )
        report.report_hash = stage13_hash(report_to_dict(report))
        return report

    def _analyze_intelligence(
        self, request: Stage13Request, candles: list[OHLCVBar]
    ) -> IntelligenceReport:
        orchestrator = self._intelligence_orchestrator
        if orchestrator is None:
            orchestrator = IntelligenceOrchestrator(default_timeframe=request.timeframe)
        return orchestrator.analyze(
            candles,
            symbol=request.symbol,
            timeframes=request.timeframes,
            space=request.space,
            search=request.search,
            wf=request.wf,
            replay_config=request.replay_config,
        )

    def _build_models(self) -> list[Any]:
        if self._models is not None:
            return list(self._models)
        return build_brains(list(_DEFAULT_BRAINS)) + [LLMStubBrain()]

    def _build_final_decision(
        self,
        market_data: MarketData,
        verdict,
        intelligence: IntelligenceReport,
        gateway_config: GatewayConfig,
        session: LiveTradingSession,
    ) -> FinalDecision:
        action = verdict.final_decision if verdict.final_decision in ("BUY", "SELL") else "NO_TRADE"
        confidence = min(
            1.0,
            max(0.0, min(float(verdict.confidence), float(intelligence.decision.confidence))),
        )
        reasoning = (
            f"stage13 pipeline; committee={verdict.reasoning}; "
            f"recommendation={intelligence.recommendation}"
        )
        if action == "NO_TRADE":
            return FinalDecision(
                symbol=market_data.symbol,
                timeframe=market_data.timeframe,
                decision="NO_TRADE",
                confidence=0.0,
                entry=None,
                stop_loss=None,
                take_profit=None,
                position_size=0.0,
                risk_reward=0.0,
                veto=False,
                reasoning=reasoning,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        entry = float(market_data.close)
        sl_pct = max(gateway_config.risk_manager.min_stop_loss_pct, 0.005)
        rr = max(gateway_config.risk_manager.min_risk_reward, 1.5)
        max_notional = min(
            session.account.cash * gateway_config.risk_manager.max_position_fraction,
            gateway_config.circuit_breaker.max_order_notional,
        )
        scaled_notional = max_notional * max(confidence, gateway_config.risk_manager.min_confidence)

        if action == "SELL":
            position = session.account.positions.get(market_data.symbol.upper())
            if position is None:
                return FinalDecision(
                    symbol=market_data.symbol,
                    timeframe=market_data.timeframe,
                    decision="NO_TRADE",
                    confidence=0.0,
                    entry=None,
                    stop_loss=None,
                    take_profit=None,
                    position_size=0.0,
                    risk_reward=0.0,
                    veto=False,
                    reasoning=f"{reasoning}; no paper position available for SELL execution",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            position_notional = position.quantity * entry
            position_size = min(position_notional, scaled_notional)
            stop_loss = round(entry * (1.0 + sl_pct), 8)
            take_profit = round(max(0.0, entry - (stop_loss - entry) * rr), 8)
        else:
            position_size = scaled_notional
            stop_loss = round(entry * (1.0 - sl_pct), 8)
            take_profit = round(entry + (entry - stop_loss) * rr, 8)

        return FinalDecision(
            symbol=market_data.symbol,
            timeframe=market_data.timeframe,
            decision=action,
            confidence=confidence,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=round(position_size, 8),
            risk_reward=rr,
            veto=False,
            reasoning=reasoning,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _research_payload(intelligence: IntelligenceReport, verdict) -> dict[str, Any]:
        return {
            "decision": verdict.final_decision,
            "stability": float(intelligence.research.stability_score),
            "overfit_flags": list(intelligence.research.overfit_flags),
        }

    @staticmethod
    def _replay_payload(intelligence: IntelligenceReport) -> dict[str, Any]:
        metrics = intelligence.research.best_metrics
        pnl = metrics.get("total_return_pct")
        if pnl is None:
            pnl = metrics.get("total_return")
        if pnl is None:
            pnl = metrics.get(intelligence.research.objective, 0.0)
        drawdown = metrics.get("max_drawdown_pct")
        if drawdown is None:
            drawdown = metrics.get("max_drawdown", 0.0)
        return {
            "stability": float(intelligence.research.stability_score),
            "pnl": float(pnl or 0.0),
            "drawdown": float(drawdown or 0.0),
        }

    @staticmethod
    def _to_market_data(candle: OHLCVBar, symbol: str, timeframe: str) -> MarketData:
        ts = candle.timestamp.isoformat() if hasattr(candle.timestamp, "isoformat") else str(candle.timestamp)
        return MarketData(
            symbol=symbol,
            timestamp=ts,
            open=float(candle.open),
            high=float(candle.high),
            low=float(candle.low),
            close=float(candle.close),
            volume=float(candle.volume),
            timeframe=timeframe,
        )

    @staticmethod
    def _has_position(session: LiveTradingSession, symbol: str) -> bool:
        return symbol.upper() in session.account.positions

    @staticmethod
    def _ts(candle: OHLCVBar) -> str:
        return candle.timestamp.isoformat() if hasattr(candle.timestamp, "isoformat") else str(candle.timestamp)
