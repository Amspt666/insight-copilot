"""InsightCopilot FastAPI 服务。

两种模式：
- 实时模式：配置了 LLM_API_KEY，问题走完整四层管线
- 回放模式：未配置 key，返回预录的真实运行样例（演示/开发用，页面会有明确标识）

启动：uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPLAY_DIR = ROOT / "examples" / "replay"
DIST_DIR = ROOT / "frontend" / "dist"

app = FastAPI(title="InsightCopilot", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] | None = None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": "live" if config.llm_available() else "replay",
            "model": config.LLM_MODEL if config.llm_available() else None}


@app.get("/api/meta")
def meta() -> dict:
    """数据集真实统计（页面展示用，全部来自数据库实测）。"""
    con = db.get_conn()
    q = lambda s: con.execute(s).fetchone()
    return {
        "mode": "live" if config.llm_available() else "replay",
        "model": config.LLM_MODEL if config.llm_available() else None,
        "dataset": {
            "name": "Olist 巴西电商公开数据集",
            "orders": q("SELECT COUNT(*) FROM orders")[0],
            "order_items": q("SELECT COUNT(*) FROM order_items")[0],
            "unique_customers": q("SELECT COUNT(DISTINCT customer_unique_id) FROM customers")[0],
            "products": q("SELECT COUNT(*) FROM products")[0],
            "sellers": q("SELECT COUNT(*) FROM sellers")[0],
            "categories": q("SELECT COUNT(*) FROM category_translation")[0],
            "states": q("SELECT COUNT(DISTINCT customer_state) FROM customers")[0],
            "date_min": str(q("SELECT MIN(order_purchase_timestamp)::DATE FROM orders")[0]),
            "date_max": str(q("SELECT MAX(order_purchase_timestamp)::DATE FROM orders")[0]),
            "tables": 8,
        },
    }


@app.get("/api/examples")
def examples() -> dict:
    """回放样例列表（真实运行的完整 trace）。"""
    out = []
    if REPLAY_DIR.exists():
        for f in sorted(REPLAY_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                out.append({"id": f.stem, "question": data.get("question", f.stem),
                            "category": data.get("category", "示例")})
            except Exception:
                continue
    return {"examples": out}


@app.get("/api/examples/{example_id}")
def example_detail(example_id: str) -> dict:
    f = REPLAY_DIR / f"{example_id}.json"
    if not f.exists():
        raise HTTPException(404, "样例不存在")
    return json.loads(f.read_text(encoding="utf-8"))


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    if not req.question.strip():
        raise HTTPException(400, "问题不能为空")
    if not config.llm_available():
        raise HTTPException(
            503, "当前为回放模式：未配置 LLM_API_KEY。请从示例中选择问题，或配置 key 后使用实时问答。")
    return pipeline.ask(req.question.strip(), req.history)


# ---------- 前端静态资源（生产模式：直接服务构建产物） ----------
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    """SPA 托管：dist 内文件直出，其余回退 index.html（前端路由）；dist 未构建时 404。"""
    if not DIST_DIR.exists():
        raise HTTPException(404, "前端未构建")
    # 防目录穿越：%2e%2e%2f 等编码变体解码后含 ../，resolve 后会逃逸 DIST_DIR
    dist_root = DIST_DIR.resolve()
    target = (DIST_DIR / full_path).resolve()
    if full_path and target.is_relative_to(dist_root) and target.is_file():
        return FileResponse(target)
    return FileResponse(DIST_DIR / "index.html")
