from datetime import UTC, datetime
from time import monotonic
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError


ProviderStatus = Literal["connected", "unconfigured", "error"]
FreshnessStatus = Literal["fresh", "stale", "unavailable"]
DecisionStatus = Literal["approved", "rejected", "unavailable"]


class IntelligenceProvider(Protocol):
    provider_id: str

    def collect(self) -> tuple[list["MarketEvent"], list["ProviderConnection"]]: ...


class ProviderConnection(BaseModel):
    provider_id: str
    label: str
    status: ProviderStatus
    message: str
    last_success_at: datetime | None = None
    latency_ms: int | None = None


class Freshness(BaseModel):
    status: FreshnessStatus
    age_seconds: int | None
    max_age_seconds: int = Field(ge=1)


class MarketEvent(BaseModel):
    event_id: str
    headline: str
    summary: str
    source: str
    source_url: str | None = None
    published_at: datetime
    received_at: datetime
    symbols: list[str]
    sentiment: Literal["positive", "neutral", "negative"]
    impact: Literal["low", "medium", "high", "critical"]


class EvidenceReference(BaseModel):
    event_id: str
    source: str
    headline: str


class RoundtableOpinion(BaseModel):
    role_id: str
    role: str
    status: Literal["ready", "unavailable"]
    thesis: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[EvidenceReference]
    valid_until: datetime | None
    simulated: bool = False


class RoundtableResult(BaseModel):
    status: Literal["ready", "unavailable"]
    consensus: str
    disagreements: list[str]
    suggested_action: Literal["observe", "hold", "reduce", "enter", "exit"]
    opinions: list[RoundtableOpinion]


class RiskConstraints(BaseModel):
    max_position_pct: float = Field(gt=0, le=1)
    max_drawdown_pct: float = Field(gt=0, le=1)
    max_daily_loss_pct: float = Field(gt=0, le=1)
    max_data_age_seconds: int = Field(ge=1)
    circuit_breaker_enabled: bool


class RiskDecision(BaseModel):
    status: DecisionStatus
    approved: bool
    veto_reasons: list[str]
    constraints: RiskConstraints


class ExecutionDecision(BaseModel):
    mode: Literal["observe_only"]
    status: Literal["disabled"]
    message: str


class MarketIntelligenceResponse(BaseModel):
    snapshot_id: str
    source_mode: Literal["live", "demo"]
    generated_at: datetime
    market_summary: str
    market_regime: Literal["risk_on", "neutral", "risk_off", "unavailable"]
    freshness: Freshness
    providers: list[ProviderConnection]
    events: list[MarketEvent]
    roundtable: RoundtableResult
    risk_decision: RiskDecision
    execution: ExecutionDecision


def evaluate_risk_gate(
    *,
    generated_at: datetime | None,
    now: datetime,
    max_age_seconds: int,
    intelligence_available: bool,
    ai_available: bool,
    circuit_breaker_triggered: bool = False,
    proposed_position_pct: float = 0,
    current_drawdown_pct: float = 0,
    daily_loss_pct: float = 0,
) -> tuple[Freshness, RiskDecision]:
    constraints = RiskConstraints(
        max_position_pct=0.1,
        max_drawdown_pct=0.12,
        max_daily_loss_pct=0.04,
        max_data_age_seconds=max_age_seconds,
        circuit_breaker_enabled=True,
    )
    veto_reasons: list[str] = []
    age_seconds: int | None = None
    if generated_at is None:
        freshness_status: FreshnessStatus = "unavailable"
        veto_reasons.append("market_data_unavailable")
    else:
        age_seconds = max(0, int((now - generated_at).total_seconds()))
        freshness_status = "fresh" if age_seconds <= max_age_seconds else "stale"
        if freshness_status == "stale":
            veto_reasons.append("market_data_stale")
    if not intelligence_available and "market_data_unavailable" not in veto_reasons:
        veto_reasons.append("market_data_unavailable")
    if not ai_available:
        veto_reasons.append("ai_service_unavailable")
    if circuit_breaker_triggered:
        veto_reasons.append("circuit_breaker_triggered")
    if proposed_position_pct > constraints.max_position_pct:
        veto_reasons.append("max_position_exceeded")
    if current_drawdown_pct > constraints.max_drawdown_pct:
        veto_reasons.append("max_drawdown_exceeded")
    if daily_loss_pct > constraints.max_daily_loss_pct:
        veto_reasons.append("max_daily_loss_exceeded")

    freshness = Freshness(
        status=freshness_status,
        age_seconds=age_seconds,
        max_age_seconds=max_age_seconds,
    )
    approved = not veto_reasons
    return freshness, RiskDecision(
        status="approved" if approved else "rejected",
        approved=approved,
        veto_reasons=veto_reasons,
        constraints=constraints,
    )


def _execution_decision() -> ExecutionDecision:
    return ExecutionDecision(
        mode="observe_only",
        status="disabled",
        message=(
            "第一版仅提供观察与建议；AI 不持有交易所密钥，也不能直接下单。"
        ),
    )


def build_unconfigured_intelligence(config: dict) -> MarketIntelligenceResponse:
    from freqtrade.rpc.api_server.market_intelligence_providers import unavailable_opinions

    now = datetime.now(UTC)
    intelligence_config = config.get("btt_market_intelligence", {})
    max_age_seconds = int(intelligence_config.get("max_age_seconds", 300))
    news_provider = intelligence_config.get("provider")
    ai_provider = config.get("btt_ai", {}).get("provider")
    freshness, risk_decision = evaluate_risk_gate(
        generated_at=None,
        now=now,
        max_age_seconds=max_age_seconds,
        intelligence_available=False,
        ai_available=False,
    )
    return MarketIntelligenceResponse(
        snapshot_id=f"unconfigured-{int(now.timestamp())}",
        source_mode="live",
        generated_at=now,
        market_summary=(
            "实时新闻数据源未配置，当前没有可供判断的市场情报快照。"
        ),
        market_regime="unavailable",
        freshness=freshness,
        providers=[
            ProviderConnection(
                provider_id=news_provider or "news",
                label="新闻 / 公告数据源",
                status="unconfigured",
                message=(
                    f"provider '{news_provider}' 尚未安装适配器。"
                    if news_provider
                    else "未配置 btt_market_intelligence.provider。"
                ),
            ),
            ProviderConnection(
                provider_id=ai_provider or "ai",
                label="AI 圆桌服务",
                status="unconfigured",
                message=(
                    f"provider '{ai_provider}' 尚未安装适配器。"
                    if ai_provider
                    else "未配置 btt_ai.provider。"
                ),
            ),
        ],
        events=[],
        roundtable=RoundtableResult(
            status="unavailable",
            consensus="AI 服务未配置，无法形成实时共识。",
            disagreements=[],
            suggested_action="observe",
            opinions=unavailable_opinions("AI 服务未配置，未生成观点。"),
        ),
        risk_decision=risk_decision,
        execution=_execution_decision(),
    )


def build_market_intelligence(config: dict) -> MarketIntelligenceResponse:
    from freqtrade.rpc.api_server.market_intelligence_providers import (
        OllamaProvider,
        OpenAICompatibleProvider,
        RSSIntelligenceProvider,
        build_roundtable_prompt,
        unavailable_opinions,
        validate_roundtable,
    )

    now = datetime.now(UTC)
    intelligence_config = config.get("btt_market_intelligence", {})
    ai_config = config.get("btt_ai", {})
    max_age_seconds = int(intelligence_config.get("max_age_seconds", 300))
    news_provider_name = str(intelligence_config.get("provider", "rss"))
    if news_provider_name == "rss":
        events, providers = RSSIntelligenceProvider(intelligence_config).collect()
    else:
        events = []
        providers = [
            ProviderConnection(
                provider_id=news_provider_name,
                label="新闻 / 公告数据源",
                status="error",
                message=f"不支持的市场情报 provider：{news_provider_name}",
            )
        ]

    snapshot_id = f"live-{int(now.timestamp())}"
    roundtable: RoundtableResult
    ai_available = False
    ai_provider_name = ai_config.get("provider")
    if not ai_provider_name:
        providers.append(
            ProviderConnection(
                provider_id="ai",
                label="AI 圆桌服务",
                status="unconfigured",
                message="未配置 btt_ai.provider。",
            )
        )
        roundtable = RoundtableResult(
            status="unavailable",
            consensus="AI 服务未配置，无法形成实时共识。",
            disagreements=[],
            suggested_action="observe",
            opinions=unavailable_opinions("AI 服务未配置，未生成观点。"),
        )
    elif not events:
        providers.append(
            ProviderConnection(
                provider_id=str(ai_provider_name),
                label="AI 圆桌服务",
                status="error",
                message="没有可用的市场事件，未调用 AI。",
            )
        )
        roundtable = RoundtableResult(
            status="unavailable",
            consensus="市场情报不可用，未调用 AI 服务。",
            disagreements=[],
            suggested_action="observe",
            opinions=unavailable_opinions("市场情报不可用，未生成观点。"),
        )
    else:
        started = monotonic()
        try:
            if ai_provider_name == "ollama":
                ai_provider = OllamaProvider(ai_config)
            elif ai_provider_name == "openai_compatible":
                ai_provider = OpenAICompatibleProvider(ai_config)
            else:
                raise ValueError(f"不支持的 AI provider：{ai_provider_name}")
            prompt = build_roundtable_prompt(snapshot_id, now, events)
            payload = ai_provider.analyze(prompt)
            roundtable = validate_roundtable(payload, events)
            ai_available = True
            providers.append(
                ProviderConnection(
                    provider_id=str(ai_provider_name),
                    label=f"AI 圆桌 · {ai_config.get('model', '未命名模型')}",
                    status="connected",
                    message="模型已基于当前情报快照返回结构化观点。",
                    last_success_at=datetime.now(UTC),
                    latency_ms=round((monotonic() - started) * 1000),
                )
            )
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            providers.append(
                ProviderConnection(
                    provider_id=str(ai_provider_name),
                    label="AI 圆桌服务",
                    status="error",
                    message=f"AI 不可用：{type(exc).__name__}",
                    latency_ms=round((monotonic() - started) * 1000),
                )
            )
            roundtable = RoundtableResult(
                status="unavailable",
                consensus="AI 服务调用或结构化校验失败，未形成共识。",
                disagreements=[],
                suggested_action="observe",
                opinions=unavailable_opinions("AI 服务不可用，未生成观点。"),
            )

    intelligence_available = bool(events) and any(
        provider.status == "connected" and provider.provider_id != ai_provider_name
        for provider in providers
    )
    freshness, risk_decision = evaluate_risk_gate(
        generated_at=now if intelligence_available else None,
        now=now,
        max_age_seconds=max_age_seconds,
        intelligence_available=intelligence_available,
        ai_available=ai_available,
    )
    connected_sources = sum(
        provider.status == "connected" and provider.provider_id != ai_provider_name
        for provider in providers
    )
    return MarketIntelligenceResponse(
        snapshot_id=snapshot_id,
        source_mode="live",
        generated_at=now,
        market_summary=(
            f"已从 {connected_sources} 个公开订阅源规范化 {len(events)} 条事件。"
            if events
            else "公开新闻订阅当前不可用，没有可供判断的市场情报快照。"
        ),
        market_regime="neutral" if events else "unavailable",
        freshness=freshness,
        providers=providers,
        events=events,
        roundtable=roundtable,
        risk_decision=risk_decision,
        execution=_execution_decision(),
    )
