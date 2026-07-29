#!/usr/bin/env bash
# InsightCopilot 一键启动
set -e
cd "$(dirname "$0")"
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || { echo "请先运行 bash setup.sh"; exit 1; }
cd backend
echo "InsightCopilot 启动中 → http://localhost:8000"
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
