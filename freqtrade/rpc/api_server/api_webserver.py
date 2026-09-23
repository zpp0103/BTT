import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

import rapidjson
from fastapi import APIRouter, Depends, HTTPException

from freqtrade.data.history.datahandlers import get_datahandler
from freqtrade.enums import CandleType, TradingMode
from freqtrade.rpc.api_server.api_schemas import (
    AIAssistantBootstrapResponse,
    AIAssistantEndpointInfo,
    AIAssistantExtensionPoint,
    AIContextResponse,
    AIRoundtableConfigPayload,
    AIRoundtableConfigResponse,
    AIRoundtableHistoryResponse,
    AIRoundtableRollbackPayload,
    AvailablePairs,
    ExchangeListResponse,
    FreqAIModelListResponse,
    HyperoptLossListResponse,
    StrategyListResponse,
)
from freqtrade.rpc.api_server.deps import get_config


logger = logging.getLogger(__name__)
ROUNDTABLE_CONFIG_PATH = Path("ai") / "roundtable_config.json"
ROUNDTABLE_HISTORY_PATH = Path("ai") / "roundtable_history.json"
ROUNDTABLE_HISTORY_LIMIT = 30
ROUNDTABLE_HISTORY_LOCK = threading.Lock()

# Private API, protected by authentication and webserver_mode dependency
router = APIRouter()


def _default_roundtable_config() -> dict:
    return {
        "version": 1,
        "layers": [
            {
                "layer_id": "signal_research",
                "title": "Signal Research Layer",
                "description": "Generates candidate directional or market-state hypotheses.",
                "agents": [
                    {
                        "agent_id": "market_observer",
                        "name": "Market Observer",
                        "prompt": (
                            "Analyze recent market structure and describe key directional "
                            "signals and uncertainty."
                        ),
                        "editable": True,
                    },
                    {
                        "agent_id": "feature_analyst",
                        "name": "Feature Analyst",
                        "prompt": (
                            "Review available indicators/features and summarize the strongest "
                            "predictive candidates."
                        ),
                        "editable": True,
                    },
                ],
            },
            {
                "layer_id": "risk_discussion",
                "title": "Risk Discussion Layer",
                "description": "Challenges assumptions and estimates downside risk.",
                "agents": [
                    {
                        "agent_id": "risk_guardian",
                        "name": "Risk Guardian",
                        "prompt": (
                            "Identify failure modes, overfitting risks, and conditions where "
                            "signals should be rejected."
                        ),
                        "editable": True,
                    },
                    {
                        "agent_id": "liquidity_checker",
                        "name": "Liquidity Checker",
                        "prompt": (
                            "Assess liquidity, spread, and execution risk impacts on the idea."
                        ),
                        "editable": True,
                    },
                ],
            },
            {
                "layer_id": "decision_synthesis",
                "title": "Decision Synthesis Layer",
                "description": "Produces a consolidated recommendation with guardrails.",
                "agents": [
                    {
                        "agent_id": "moderator",
                        "name": "Roundtable Moderator",
                        "prompt": (
                            "Synthesize all layer outputs into a clear recommendation and list "
                            "required safeguards before action."
                        ),
                        "editable": True,
                    }
                ],
            },
        ],
    }


def _roundtable_config_file(config) -> Path:
    user_data_root = Path(config["user_data_dir"]).resolve()
    config_file = (user_data_root / ROUNDTABLE_CONFIG_PATH).resolve()
    if not config_file.is_relative_to(user_data_root):
        raise HTTPException(status_code=400, detail="Invalid roundtable config path.")
    return config_file


def _roundtable_history_file(config) -> Path:
    user_data_root = Path(config["user_data_dir"]).resolve()
    history_file = (user_data_root / ROUNDTABLE_HISTORY_PATH).resolve()
    if not history_file.is_relative_to(user_data_root):
        raise HTTPException(status_code=400, detail="Invalid roundtable history path.")
    return history_file


def _normalize_roundtable_config(raw_config: dict) -> dict:
    cfg = AIRoundtableConfigPayload(config=raw_config).config.model_dump()
    for layer in cfg.get("layers", []):
        layer["enabled"] = bool(layer.get("enabled", True))
        for agent in layer.get("agents", []):
            agent["enabled"] = bool(agent.get("enabled", True))
            agent["editable"] = True
    return cfg


def _load_roundtable_history(config) -> list[dict]:
    history_file = _roundtable_history_file(config)
    if not history_file.is_file():
        return []
    try:
        payload = rapidjson.loads(history_file.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to parse roundtable history from %s", history_file)
        return []
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    valid_entries = []
    for entry in entries:
        try:
            version_id = entry.get("version_id")
            saved_at = entry.get("saved_at")
            if not version_id or not saved_at:
                continue
            cfg = _normalize_roundtable_config(entry.get("config", {}))
            source = entry.get("source", "save")
            if source not in ("save", "rollback"):
                source = "save"
            valid_entries.append(
                {
                    "version_id": str(version_id),
                    "saved_at": str(saved_at),
                    "source": source,
                    "config": cfg,
                }
            )
        except Exception:
            logger.exception("Skipping invalid roundtable history entry.")
            continue
    return valid_entries


def _save_roundtable_history(config, entries: list[dict]) -> None:
    history_file = _roundtable_history_file(config)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        rapidjson.dumps({"entries": entries}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _append_roundtable_history_entry_unlocked(config, cfg: dict, source: str) -> None:
    entries = _load_roundtable_history(config)
    now = datetime.now(UTC)
    entry = {
        "version_id": now.strftime("%Y%m%dT%H%M%S%fZ"),
        "saved_at": now.isoformat().replace("+00:00", "Z"),
        "source": source,
        "config": cfg,
    }
    entries.append(entry)
    entries = entries[-ROUNDTABLE_HISTORY_LIMIT:]
    _save_roundtable_history(config, entries)


def _append_roundtable_history_entry(config, cfg: dict, source: str) -> None:
    with ROUNDTABLE_HISTORY_LOCK:
        _append_roundtable_history_entry_unlocked(config, cfg, source)


def _load_roundtable_config(config) -> tuple[str, dict]:
    config_file = _roundtable_config_file(config)
    if not config_file.is_file():
        return "default", _default_roundtable_config()
    try:
        file_content = config_file.read_text(encoding="utf-8")
        user_cfg = rapidjson.loads(file_content)
    except Exception:
        logger.exception("Failed to load user roundtable config from %s", config_file)
        invalid_file = config_file.with_suffix(f"{config_file.suffix}.invalid")
        try:
            config_file.replace(invalid_file)
            logger.warning("Moved invalid roundtable config to %s", invalid_file)
        except Exception:
            logger.exception("Failed to quarantine invalid roundtable config file %s", config_file)
        return "default", _default_roundtable_config()
    try:
        return "user_override", _normalize_roundtable_config(user_cfg)
    except Exception:
        logger.exception(
            "Roundtable config in %s failed schema validation. Falling back to default.",
            config_file,
        )
        return "default", _default_roundtable_config()


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
        "roundtable_config_endpoint": "/ai/assistant/roundtable-config",
        "roundtable_history_endpoint": "/ai/assistant/roundtable-config/history",
        "roundtable_rollback_endpoint": "/ai/assistant/roundtable-config/rollback",
    }


@router.get(
    "/ai/assistant/roundtable-config", response_model=AIRoundtableConfigResponse, tags=["FreqAI"]
)
def get_ai_assistant_roundtable_config(config=Depends(get_config)):
    """
    Read authenticated roundtable prompt configuration (user-scoped, read endpoint).
    """
    source, cfg = _load_roundtable_config(config)
    return {"source": source, "config": cfg}


@router.post(
    "/ai/assistant/roundtable-config", response_model=AIRoundtableConfigResponse, tags=["FreqAI"]
)
def save_ai_assistant_roundtable_config(
    payload: AIRoundtableConfigPayload,
    config=Depends(get_config),
):
    """
    Save authenticated roundtable prompt configuration override under user_data_dir.
    """
    config_file = _roundtable_config_file(config)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_roundtable_config(payload.model_dump()["config"])
    with ROUNDTABLE_HISTORY_LOCK:
        config_file.write_text(
            rapidjson.dumps(normalized, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _append_roundtable_history_entry_unlocked(config, normalized, source="save")
    return {"source": "user_override", "config": normalized}


@router.get(
    "/ai/assistant/roundtable-config/history",
    response_model=AIRoundtableHistoryResponse,
    tags=["FreqAI"],
)
def get_ai_assistant_roundtable_history(config=Depends(get_config)):
    return {"entries": list(reversed(_load_roundtable_history(config)))}


@router.post(
    "/ai/assistant/roundtable-config/rollback",
    response_model=AIRoundtableConfigResponse,
    tags=["FreqAI"],
)
def rollback_ai_assistant_roundtable_config(
    payload: AIRoundtableRollbackPayload,
    config=Depends(get_config),
):
    with ROUNDTABLE_HISTORY_LOCK:
        entries = _load_roundtable_history(config)
        selected = next((e for e in entries if e["version_id"] == payload.version_id), None)
        if not selected:
            raise HTTPException(status_code=404, detail="Roundtable history version not found.")

        config_file = _roundtable_config_file(config)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            rapidjson.dumps(selected["config"], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _append_roundtable_history_entry_unlocked(config, selected["config"], source="rollback")
        return {"source": "user_override", "config": selected["config"]}


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
