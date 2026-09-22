from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from crypto_quant_ai.backend.orchestration import (
    Stage13ApiRequest,
    Stage13Orchestrator,
    Stage14SessionManager,
    Stage14SessionOpenRequest,
    Stage14SessionRunRequest,
    report_to_dict,
)

app = FastAPI(title="crypto-quant-ai", version="0.1.0")


@lru_cache
def get_stage14_manager() -> Stage14SessionManager:
    return Stage14SessionManager()


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "crypto-quant-ai"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "crypto-quant-ai"}


@app.post("/stage13/run")
def run_stage13(request: Stage13ApiRequest) -> dict:
    try:
        report = Stage13Orchestrator().run(request.to_request())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report_to_dict(report)


@app.post("/stage14/sessions")
def open_stage14_session(request: Stage14SessionOpenRequest) -> dict:
    view = get_stage14_manager().open_session(request.to_gateway_config())
    return report_to_dict(view)


@app.get("/stage14/sessions/{session_id}")
def get_stage14_session(session_id: str) -> dict:
    try:
        view = get_stage14_manager().get_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report_to_dict(view)


@app.post("/stage14/sessions/{session_id}/run")
def run_stage14_session(session_id: str, request: Stage14SessionRunRequest) -> dict:
    try:
        report = get_stage14_manager().run_session(session_id, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report_to_dict(report)


@app.get("/stage14/sessions/{session_id}/history")
def get_stage14_history(session_id: str, format: str = "json"):
    manager = get_stage14_manager()
    try:
        if format == "csv":
            return PlainTextResponse(manager.export_history_csv(session_id), media_type="text/csv")
        if format != "json":
            raise HTTPException(status_code=400, detail="format must be 'json' or 'csv'")
        return {"history": manager.get_history(session_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
