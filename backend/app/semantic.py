"""语义层加载与上下文构建（可信闭环第一层）。

职责：把 YAML 中的表结构、指标口径、歧义规则、全局约定渲染成
供 LLM 使用的确定性上下文；并计算“相对时间锚点”等动态信息。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from . import config, db


@lru_cache(maxsize=1)
def layer() -> dict[str, Any]:
    with open(config.SEMANTIC_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def time_anchor() -> str:
    """相对时间锚点：数据快照中的最大下单日期。数据为静态快照，进程内只算一次。"""
    sql = layer()["dataset"]["time_anchor_sql"]
    _, rows = db.run_readonly(sql, row_limit=1)
    return str(rows[0][0])


def match_ambiguity_rules(question: str) -> list[dict[str, Any]]:
    """按 trigger_terms 命中歧义规则，供澄清判断与 prompt 强调使用。"""
    hits = []
    for rule in layer().get("ambiguity_rules", []):
        for term in rule.get("trigger_terms", []):
            if term in question:
                hits.append(rule)
                break
    return hits


def build_context(question: str = "") -> str:
    """渲染完整语义上下文（8 张表规模下全量注入是最优解；
    术语→口径映射同时服务于澄清判断与口径强调）。"""
    ly = layer()
    parts: list[str] = []

    parts.append("## 数据库 Schema（DuckDB 方言）")
    parts.append(db.schema_ddl())

    parts.append("\n## 表业务含义")
    for t, meta in ly["tables"].items():
        parts.append(f"- {t}：{meta['description']}")
        for c, desc in meta.get("columns", {}).items():
            parts.append(f"  - {c}：{desc}")

    parts.append("\n## 连接关系")
    for j in ly.get("join_graph", []):
        parts.append(f"- {j}")

    parts.append("\n## 指标口径（必须使用，不得自行发明）")
    for key, m in ly.get("metrics", {}).items():
        terms = "、".join(m.get("zh_terms", []))
        desc = m.get("description", "")
        parts.append(f"- {m['name']}（{terms}）：{m['sql']}" + (f"  —— {desc}" if desc else ""))

    parts.append("\n## 全局口径约定")
    for c in ly.get("conventions", []):
        parts.append(f"- {c}")

    parts.append(f"\n## 时间锚点\n数据为静态历史快照，最大下单日期 = {time_anchor()}。"
                 "所有相对时间（最近/今年/去年等）以此日期推算。")

    hits = match_ambiguity_rules(question) if question else []
    if hits:
        parts.append("\n## 本问题触发的歧义提醒")
        for h in hits:
            if "clarify_question" in h:
                parts.append(f"- {h['clarify_question']}")
            if "note" in h:
                parts.append(f"- {h['note']}")
    return "\n".join(parts)
