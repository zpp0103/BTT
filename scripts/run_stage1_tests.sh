#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."
PYTHONPATH=. python -m pytest -q crypto_quant_ai/backend/tests/test_stage1.py
