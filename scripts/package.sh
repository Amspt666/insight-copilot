#!/usr/bin/env bash
# 打包交付：生成 insight-copilot.zip（排除虚拟环境/缓存/日志）
set -e
cd "$(dirname "$0")/.."
OUT=${1:-/mnt/agents/output/insight-copilot.zip}
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
zip -r "$OUT" . \
  -x ".venv/*" "*/__pycache__/*" "*.pyc" ".git/*" \
  -x "backend/eval/eval_run.log" "data/olist.duckdb" \
  -x "frontend/node_modules/*" "nohup.out"
echo "packed → $OUT ($(du -h "$OUT" | cut -f1))"
