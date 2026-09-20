from fastapi import FastAPI

app = FastAPI(title="crypto-quant-ai", version="0.1.0")


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "crypto-quant-ai"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "crypto-quant-ai"}
