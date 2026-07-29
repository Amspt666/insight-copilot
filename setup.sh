#!/usr/bin/env bash
# InsightCopilot 一键配置：安装依赖 + 构建数据库 + 准备环境
set -e
cd "$(dirname "$0")"

echo "==> 1/5 检查 Python"
command -v python3 >/dev/null || { echo "未找到 python3（需要 3.10+）"; exit 1; }
python3 -c "import sys; assert sys.version_info >= (3, 10), '需要 Python 3.10+'"

echo "==> 2/5 创建虚拟环境并安装依赖"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r backend/requirements.txt

echo "==> 3/5 构建 DuckDB 数据库"
python3 scripts/build_db.py

echo "==> 4/5 检查前端产物"
if [ -f frontend/dist/index.html ]; then
  echo "  前端已预构建（frontend/dist），无需 Node 环境"
elif command -v npm >/dev/null; then
  echo "  未发现预构建产物，使用 npm 构建…"
  cd frontend && npm install && npm run build && cd ..
else
  echo "  警告：无 frontend/dist 且无 npm，将只启动 API（无网页界面）"
fi

echo "==> 5/5 准备 .env"
if [ ! -f .env ]; then cp .env.example .env; echo "  已生成 .env（请编辑填入你的模型 Key）"; fi

echo ""
echo "配置完成。下一步："
echo "  1) 编辑 .env 填入 LLM_API_KEY（不填也能跑，进入示例回放模式）"
echo "  2) bash start.sh 启动，浏览器打开 http://localhost:8000"
