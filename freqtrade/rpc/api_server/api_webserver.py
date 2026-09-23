import logging

from fastapi import APIRouter, Depends

from freqtrade.data.history.datahandlers import get_datahandler
from freqtrade.enums import CandleType, TradingMode
from freqtrade.rpc.api_server.api_schemas import (
    AIAssistantBootstrapResponse,
    AIAssistantEndpointInfo,
    AIAssistantExtensionPoint,
    AIContextResponse,
    AvailablePairs,
    ExchangeListResponse,
    FreqAIModelListResponse,
    HyperoptLossListResponse,
    StrategyListResponse,
)
from freqtrade.rpc.api_server.deps import get_config


logger = logging.getLogger(__name__)

# Private API, protected by authentication and webserver_mode dependency
router = APIRouter()


@router.get("/strategies", response_model=StrategyListResponse, tags=["Strategy"])
def list_strategies(config=Depends(get_config)):
    from freqtrade.resolvers.strategy_resolver import StrategyResolver

    strategies = StrategyResolver.search_all_objects(
        config, False, config.get("recursive_strategy_search", False)
    )
    strategies = sorted(strategies, key=lambda x: x["name"])

    return {"strategies": [x["name"] for x in strategies]}


@router.get("/exchanges", response_model=ExchangeListResponse, tags=[])
def list_exchanges(config=Depends(get_config)):
    from freqtrade.exchange import list_available_exchanges

    exchanges = list_available_exchanges(config)
    return {
        "exchanges": exchanges,
    }


@router.get("/hyperoptloss", response_model=HyperoptLossListResponse, tags=["Hyperopt"])
def list_hyperoptloss(
    config=Depends(get_config),
):
    import textwrap

    from freqtrade.resolvers.hyperopt_resolver import HyperOptLossResolver

    loss_functions = HyperOptLossResolver.search_all_objects(config, False)
    loss_functions = sorted(loss_functions, key=lambda x: x["name"])

    return {
        "loss_functions": [
            {
                "name": x["name"],
                "description": textwrap.dedent((x["class"].__doc__ or "").strip()),
            }
            for x in loss_functions
        ]
    }


@router.get("/freqaimodels", response_model=FreqAIModelListResponse, tags=["FreqAI"])
def list_freqaimodels(config=Depends(get_config)):
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver

    models = FreqaiModelResolver.search_all_objects(config, False)
    models = sorted(models, key=lambda x: x["name"])

    return {"freqaimodels": [x["name"] for x in models]}


@router.get("/ai/context", response_model=AIContextResponse, tags=["FreqAI"])
def get_ai_context(config=Depends(get_config)):
    from freqtrade.resolvers.freqaimodel_resolver import FreqaiModelResolver
    from freqtrade.resolvers.strategy_resolver import StrategyResolver

    strategies = StrategyResolver.search_all_objects(
        config, False, config.get("recursive_strategy_search", False)
    )
    strategies = sorted(strategies, key=lambda x: x["name"])

    models = FreqaiModelResolver.search_all_objects(config, False)
    models = sorted(models, key=lambda x: x["name"])

    return {
        "ai_enabled": bool(config.get("freqai", {}).get("enabled", False)),
        "has_freqai_config": bool(config.get("freqai")),
        "configured_strategy": config.get("strategy"),
        "configured_freqaimodel": config.get("freqaimodel"),
        "strategies": [x["name"] for x in strategies],
        "freqaimodels": [x["name"] for x in models],
        "recommended_readonly_endpoints": [
            "/show_config",
            "/status",
            "/logs",
            "/entries",
            "/exits",
            "/mix_tags",
            "/strategies",
            "/freqaimodels",
            "/sysinfo",
            "/health",
        ],
    }


@router.get("/ai/assistant/bootstrap", response_model=AIAssistantBootstrapResponse, tags=["FreqAI"])
def get_ai_assistant_bootstrap(config=Depends(get_config)):
    ai_context = get_ai_context(config=config)

    extension_points = [
        AIAssistantExtensionPoint(
            key="freqai_model_interface",
            title="FreqAI model interface",
            docs_path="docs/freqai-developers.md",
            summary=(
                "Use IFreqaiModel fit/train/predict and model resolver integration "
                "for external model providers."
            ),
        ),
        AIAssistantExtensionPoint(
            key="strategy_callbacks",
            title="Strategy callbacks",
            docs_path="docs/strategy-callbacks.md",
            summary="Use callbacks for bounded, deterministic AI-assisted filters and checks.",
        ),
        AIAssistantExtensionPoint(
            key="custom_pipelines",
            title="Custom feature pipelines",
            docs_path="docs/freqai-feature-engineering.md",
            summary=(
                "Extend define_data_pipeline/define_label_pipeline for external "
                "AI-derived features."
            ),
        ),
        AIAssistantExtensionPoint(
            key="rest_api",
            title="REST API discovery",
            docs_path="docs/rest-api.md",
            summary="Use read-only API endpoints first before any automated actions.",
        ),
    ]
    endpoint_details = [
        AIAssistantEndpointInfo(path="/show_config", purpose="Runtime configuration snapshot."),
        AIAssistantEndpointInfo(path="/status", purpose="Open trade status."),
        AIAssistantEndpointInfo(path="/logs", purpose="Recent bot log lines."),
        AIAssistantEndpointInfo(path="/entries", purpose="Entry-tag performance summary."),
        AIAssistantEndpointInfo(path="/exits", purpose="Exit-reason performance summary."),
        AIAssistantEndpointInfo(path="/mix_tags", purpose="Entry/exit combination stats."),
        AIAssistantEndpointInfo(path="/strategies", purpose="Discover available strategies."),
        AIAssistantEndpointInfo(path="/freqaimodels", purpose="Discover available FreqAI models."),
        AIAssistantEndpointInfo(path="/sysinfo", purpose="System load and health context."),
        AIAssistantEndpointInfo(path="/health", purpose="Bot loop freshness in trade mode."),
    ]

    return {
        "ai_context": ai_context,
        "extension_points": extension_points,
        "readonly_endpoint_details": endpoint_details,
        "safe_workflow": [
            "Start with read-only endpoints and validate assumptions.",
            "Test strategy/model changes in backtesting and dry-run first.",
            "Keep deterministic fallback behavior if external AI is unavailable.",
            "Promote to live only after stable repeated results.",
        ],
    }


@router.get(
    "/available_pairs", response_model=AvailablePairs, tags=["Candle data", "Download-data"]
)
def list_available_pairs(
    timeframe: str | None = None,
    stake_currency: str | None = None,
    candletype: CandleType | None = None,
    config=Depends(get_config),
):
    dh = get_datahandler(config["datadir"], config.get("dataformat_ohlcv"))
    trading_mode: TradingMode = config.get("trading_mode", TradingMode.SPOT)
    pair_interval = dh.ohlcv_get_available_data(config["datadir"], trading_mode)

    if timeframe:
        pair_interval = [pair for pair in pair_interval if pair[1] == timeframe]
    if stake_currency:
        pair_interval = [pair for pair in pair_interval if pair[0].endswith(stake_currency)]
    if candletype:
        pair_interval = [pair for pair in pair_interval if pair[2] == candletype]
    else:
        candle_type = CandleType.get_default(trading_mode)
        pair_interval = [pair for pair in pair_interval if pair[2] == candle_type]

    pair_interval = sorted(pair_interval, key=lambda x: x[0])

    pairs = list({x[0] for x in pair_interval})
    pairs.sort()
    result = {
        "length": len(pairs),
        "pairs": pairs,
        "pair_interval": pair_interval,
    }
    return result
