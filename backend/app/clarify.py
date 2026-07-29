"""澄清与拒答门（可信闭环第一层的前置判断）。

三种出口：
- answer：问题明确，进入 SQL 生成
- clarify：问题有歧义（如“销量”口径不明），反问用户
- refuse：问题与本数据集无关，明确拒答而不是硬编
"""
from __future__ import annotations

import json
import re

from . import llm, semantic

PROMPT = """你是 InsightCopilot 的问题分流器。判断用户对电商数据集的提问应如何处理。

分流规则（按优先级执行）：

1. **refuse — 必须拒答**：满足以下任一条件就 refuse
   - 问题与电商经营数据完全无关（闲聊、编程求助、实时信息、个人隐私）
   - 问题涉及数据集中明确不存在的字段（如退货、退款、广告投放、库存、利润/成本），歧义规则中有 `note: ...必须拒答` 的也走这里
   - 问题要求数据修改/删除/预测/机器学习建模

2. **clarify — 需要反问**：同时满足两个条件才反问
   - 问题中的关键词命中下方"歧义规则"中的 trigger_terms
   - 不同的口径/定义会导致 SQL 查询结果不同
   如果 trigger_terms 命中的规则只有 note（口径说明）没有 clarify_question，不需要反问，直接 answer

3. **answer — 直接回答**：不属于上述两类就直接 answer，包括：
   - 问题明确、关键词不在歧义规则中
   - 问题是简单的聚合查询（求平均、求和、计数、比例），语义层已有明确口径
   - 未指定时间范围 → 默认全量统计即可，不反问
   - 像"平均分期数""分期占比"这类直接 SQL 能算的问题，不属于歧义

歧义规则：
{rules}

输出要求：只输出一行 JSON，不要代码块，不要任何其他文字：
{{"action": "answer|clarify|refuse", "reason": "一句话判断依据", "clarify_question": "（仅 clarify 时）反问用户的完整问题", "options": ["选项1", "选项2"]}}

用户问题：{question}"""


def _rules_text() -> str:
    lines = []
    for r in semantic.layer().get("ambiguity_rules", []):
        terms = "、".join(r.get("trigger_terms", []))
        if "clarify_question" in r:
            opts = " / ".join(o["label"] for o in r.get("options", []))
            lines.append(f"- 触发词「{terms}」：{r['clarify_question']}（候选：{opts}）")
        else:
            lines.append(f"- 触发词「{terms}」：{r.get('note', '')}（此为口径说明，不需反问）")
    return "\n".join(lines) or "（无）"


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"action": "answer", "reason": "分流输出无法解析，默认放行"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"action": "answer", "reason": "分流输出无法解析，默认放行"}


def classify(question: str) -> dict:
    """返回 {"action": ..., ...}；任何异常都降级为 answer，宁可放行进后续校验。"""
    try:
        out = llm.chat(
            [{"role": "user", "content": PROMPT.format(rules=_rules_text(), question=question)}],
            max_tokens=1500, temperature=0.0,
        )
        result = _parse_json(out)
        if result.get("action") not in ("answer", "clarify", "refuse"):
            result["action"] = "answer"
        return result
    except Exception as e:  # 分流失败不应阻塞主流程
        return {"action": "answer", "reason": f"分流器异常（{e}），默认放行"}
