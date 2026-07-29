#!/usr/bin/env bash
# 完整评测：主配置 + 基线 + 消融（沙箱实测用，按顺序跑避免并发拥塞）
set -u
cd "$(dirname "$0")/.."
export LLM_TRANSPORT=${LLM_TRANSPORT:-auto}

echo "== 1/6 full（100 题，跳过洞察） =="
python3 -u -m eval.run_eval --config full --skip-insight --concurrency 3
echo "== 2/6 baseline（100 题） =="
python3 -u -m eval.run_eval --config baseline --skip-insight --concurrency 3
echo "== 3/6 no_semantic（70 可答题） =="
python3 -u -m eval.run_eval --config no_semantic --categories A,B,C --skip-insight --concurrency 3
echo "== 4/6 no_repair（70 可答题） =="
python3 -u -m eval.run_eval --config no_repair --categories A,B,C --skip-insight --concurrency 3
echo "== 5/6 no_clarify（30 歧义+超纲题） =="
python3 -u -m eval.run_eval --config no_clarify --categories D,E --skip-insight --concurrency 3
echo "== 6/6 full + 洞察（30 题子集，测忠实度与回译） =="
python3 -u -m eval.run_eval --config full --categories A,B,C --limit 30 --tag with_insight --concurrency 3
echo "ALL DONE"
