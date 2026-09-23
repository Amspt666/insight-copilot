#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then FIN_PY=.venv/bin/python; elif [ -x ../.venv/bin/python ]; then FIN_PY=../.venv/bin/python; else FIN_PY=python3; fi
if [ ! -f data/finance.sqlite ]; then "$FIN_PY" scripts/generate_data.py; fi
exec "$FIN_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8112
