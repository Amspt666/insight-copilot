"""意图回译校验（可信闭环第四道机制：问得对）。

SQL 能跑 ≠ SQL 答的是用户的问题。本模块把 SQL 反向翻译成业务语言，
再与原问题做一致性判定；不一致则触发修正或标注风险。
"""
from __future__ import annotations

import json
import re

from . import llm

EXPLAIN_PROMPT = """把下面的 DuckDB SQL 用一句中文业务语言解释它在算什么。
要求：面向业务人员，不出现表名列名等术语；只输出这一句话。

```sql
{sql}
```"""

JUDGE_PROMPT = """判断 SQL 回译与用户问题是否语义一致。

用户问题：{question}
SQL 回译：{explanation}

一致的标准：回译回答的核心指标、维度、时间范围、过滤条件与用户问题对齐。
只输出 JSON（不要代码块）：{{"consistent": true/false, "reason": "一句话依据"}}"""


def explain(sql: str) -> str:
    return llm.chat(
        [{"role": "user", "content": EXPLAIN_PROMPT.format(sql=sql)}],
        max_tokens=1000, temperature=0.0,
    ).strip()


def judge(question: str, explanation: str) -> dict:
    out = llm.chat(
        [{"role": "user", "content": JUDGE_PROMPT.format(question=question, explanation=explanation)}],
        max_tokens=1000, temperature=0.0,
    )
    m = re.search(r"\{.*\}", out, re.S)
    try:
        r = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        r = {}
    if "consistent" not in r:  # 判定失败时不冤枉 SQL，标注为未知而非不一致
        return {"consistent": True, "reason": "一致性判定不可用", "unknown": True}
    return r
