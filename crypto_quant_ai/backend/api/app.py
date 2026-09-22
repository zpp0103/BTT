from fastapi import FastAPI, HTTPException

from crypto_quant_ai.backend.orchestration import (
    Stage13ApiRequest,
    Stage13Orchestrator,
    report_to_dict,
)

app = FastAPI(title="crypto-quant-ai", version="0.1.0")


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
