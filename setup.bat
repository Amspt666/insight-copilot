@echo off
REM InsightCopilot 一键配置（Windows）
setlocal
cd /d "%~dp0"

echo ==^> 1/4 创建虚拟环境并安装依赖
if not exist .venv (
  python -m venv .venv || (echo 未找到 python（需要 3.10+） & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r backend\requirements.txt || exit /b 1

echo ==^> 2/4 构建 DuckDB 数据库
python scripts\build_db.py || exit /b 1

echo ==^> 3/4 检查前端产物
if exist frontend\dist\index.html (
  echo   前端已预构建，无需 Node 环境
) else (
  where npm >nul 2>nul && (cd frontend && call npm install && call npm run build && cd ..) || echo   警告：无预构建前端且无 npm，将只启动 API
)

echo ==^> 4/4 准备 .env
if not exist .env (copy .env.example .env >nul & echo   已生成 .env（请编辑填入你的模型 Key）)

echo.
echo 配置完成。下一步：
echo   1) 编辑 .env 填入 LLM_API_KEY（不填也能跑，进入示例回放模式）
echo   2) start.bat 启动，浏览器打开 http://localhost:8000
