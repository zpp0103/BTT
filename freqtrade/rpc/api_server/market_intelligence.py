from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field


ProviderStatus = Literal["connected", "unconfigured", "error"]
FreshnessStatus = Literal["fresh", "stale", "unavailable"]
DecisionStatus = Literal["approved", "rejected", "unavailable"]


class IntelligenceProvider(Protocol):
    provider_id: str

    def collect(self) -> list["MarketEvent"]: ...


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


def build_unconfigured_intelligence(config: dict) -> MarketIntelligenceResponse:
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
    unavailable_opinions = [
        RoundtableOpinion(
            role_id=role_id,
            role=role,
            status="unavailable",
            thesis="AI 服务未配置，未生成观点。",
            evidence=[],
            valid_until=None,
        )
        for role_id, role in [
            ("macro_news", "宏观 / 新闻"),
            ("technical", "技术面"),
            ("risk", "风险"),
            ("execution", "执行"),
        ]
    ]
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
            opinions=unavailable_opinions,
        ),
        risk_decision=risk_decision,
        execution=ExecutionDecision(
            mode="observe_only",
            status="disabled",
            message=(
                "第一版仅提供观察与建议；AI 不持有交易所密钥，也不能直接下单。"
            ),
        ),
    )
