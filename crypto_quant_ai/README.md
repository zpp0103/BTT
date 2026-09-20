# crypto_quant_ai

## Project status

This is the Stage 1 foundation for the Crypto Quant AI stack.

- No live trading is enabled.
- `LIVE_TRADING` defaults to `false`.
- The project is intentionally isolated from the existing BTT repo logic.

## Structure

```text
crypto_quant_ai/
├── backend/
│   ├── api/
│   ├── brains/
│   ├── core/
│   ├── database/
│   ├── decision/
│   ├── execution/
│   └── tests/
├── frontend/
├── docs/
├── requirements.txt
├── README.md
└── .env.example
```

## Install

```bash
pip install -r crypto_quant_ai/requirements.txt
```

## Run tests

```bash
PYTHONPATH=. pytest -q crypto_quant_ai/backend/tests/test_stage1.py
```

## Run FastAPI

```bash
PYTHONPATH=. uvicorn crypto_quant_ai.backend.api.app:app --reload
```

## Safety

The project is intentionally limited to a safe, no-trade foundation. No real order execution can happen before a future stage adds explicit live-trading protections and validated execution logic.
