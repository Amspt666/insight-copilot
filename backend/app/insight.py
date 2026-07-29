"""洞察生成 + 数字溯源（可信闭环第三层：说得对）。"""
from __future__ import annotations

from typing import Any

from . import config, grounding, llm

PROMPT = """你是 InsightCopilot 的商业分析师。基于查询结果为用户问题写一段 2-4 句的中文洞察。

铁律：
1. 文中出现的每个数字都必须来自下方查询结果表，禁止任何编造、估算、外推
2. 直接引用结果表中的数值写法，禁止单位换算（不要把 993592.98 写成“99 万”）
3. 不要给结果表中没有的对比（如结果只有 2018 年数据，就不要谈同比）
4. 先直接回答问题，再指出最值得注意的一个发现
5. 金额保留两位小数；比例用百分数表示（如 41.09%）

用户问题：{question}
SQL 业务含义：{explanation}
查询结果（共 {n_rows} 行{truncated}）：
{table}"""


def _md_cell(x: Any) -> str:
    """单元格转义：| 会破坏 markdown 表格结构（数据中的竖线/换行先压平）。"""
    return str(x).replace("|", "\\|").replace("\n", " ")


def _to_markdown(columns: list[str], rows: list[tuple[Any, ...]], max_rows: int = 30) -> str:
    head = "| " + " | ".join(_md_cell(c) for c in columns) + " |"
    sep = "|" + "---|" * len(columns)
    body = ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in rows[:max_rows]]
    return "\n".join([head, sep, *body])


def _whitelist(question: str) -> list[float]:
    """问题中出现的数字（如“Top 5”“2018 年”）视为可引用。"""
    import re
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", question)]


def generate(
    question: str,
    explanation: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
    truncated: bool,
) -> dict:
    """返回 {"text": 原文, "text_verified": 溯源后文本, "grounding": 报告}。"""
    table = _to_markdown(columns, rows)
    text = llm.chat(
        [{"role": "user", "content": PROMPT.format(
            question=question, explanation=explanation,
            n_rows=len(rows), truncated="，结果已截断" if truncated else "", table=table)}],
        max_tokens=config.INSIGHT_MAX_TOKENS, temperature=0.0,
    ).strip()

    report = grounding.check(text, rows, extra_whitelist=_whitelist(question))
    verified = text if report.faithfulness >= 1.0 else grounding.redact_unsupported(text, report)
    return {
        "text": text,
        "text_verified": verified,
        "grounding": {
            "total": report.total,
            "supported": report.supported,
            "faithfulness": round(report.faithfulness, 4),
            "unsupported": report.unsupported_raws,
        },
    }
