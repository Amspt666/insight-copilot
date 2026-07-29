"""全局配置：从环境变量读取，.env 仅作本地开发便利，不要提交真实 key。"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv  # 可选依赖；未安装时静默跳过
    load_dotenv()
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[2]  # 项目根目录（backend/ 的上一级）
DATA_DIR = ROOT / "data"
DB_PATH = os.environ.get("IC_DB_PATH", str(DATA_DIR / "olist.duckdb"))
SEMANTIC_PATH = os.environ.get("IC_SEMANTIC_PATH", str(DATA_DIR / "semantic" / "semantic_layer.yaml"))

# LLM（OpenAI 兼容接口）
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-pro")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "120"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))

# 生成与执行参数
SQL_MAX_REPAIR = int(os.environ.get("IC_SQL_MAX_REPAIR", "3"))      # 自我修正最大轮数
SQL_ROW_LIMIT = int(os.environ.get("IC_SQL_ROW_LIMIT", "500"))      # 结果行数上限
SQL_TIMEOUT_S = float(os.environ.get("IC_SQL_TIMEOUT_S", "10"))     # 单条 SQL 执行超时（秒）
INSIGHT_MAX_TOKENS = int(os.environ.get("IC_INSIGHT_MAX_TOKENS", "3000"))
SQLGEN_MAX_TOKENS = int(os.environ.get("IC_SQLGEN_MAX_TOKENS", "4000"))


def llm_available() -> bool:
    """是否配置了可用的 LLM 凭证（否则系统进入回放/降级模式）。"""
    return bool(LLM_API_KEY)
