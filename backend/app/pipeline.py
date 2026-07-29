"""可信问答管线编排。

四层闭环：
  1. 问得对：语义层口径约束 + 澄清/拒答门 + 意图回译校验
  2. 算得对：静态校验 → 沙箱执行 → 出错自我修正
  3. 说得对：洞察数字逐条溯源核验
  4. 拿不准就明说：任何一环不过，宁可反问/拒答/标注，绝不硬编

enable 开关用于消融实验（eval/run_eval.py 调用）。
"""
from __future__ import annotations

import time
from typing import Any

from . import backtranslate, clarify, config, executor, insight, llm, sqlgen, validator


def _chart_hint(columns: list[str], rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    """根据结果形状给前端一个图表建议（数字卡/折线/柱状/表格）。"""
    if not rows or not columns:
        return {"type": "empty"}
    if len(rows) == 1 and len(columns) <= 2:
        return {"type": "number"}
    first = rows[0][0]
    import datetime
    date_like = isinstance(first, (datetime.date, datetime.datetime)) or (
        isinstance(first, str) and len(first) >= 7 and first[:4].isdigit() and "-" in first
    )
    numeric_tail = all(isinstance(r[-1], (int, float)) for r in rows[:10])
    if date_like and numeric_tail:
        return {"type": "line", "x": columns[0], "y": columns[1:]}
    if isinstance(first, str) and numeric_tail:
        return {"type": "bar", "x": columns[0], "y": columns[1:]}
    return {"type": "table"}


def ask(
    question: str,
    history: list[dict[str, Any]] | None = None,
    *,
    enable: dict[str, bool] | None = None,
    skip_insight: bool = False,
) -> dict[str, Any]:
    """端到端问答。enable 键：clarify/semantic/repair/backtranslate/grounding。

    skip_insight=True 时跳过洞察生成与数字溯源（评测执行准确率时提速）。
    """
    en = {"clarify": True, "semantic": True, "repair": True, "backtranslate": True, "grounding": True}
    if enable:
        en.update(enable)
    t0 = time.time()
    trace: dict[str, Any] = {"question": question, "status": "ok", "stages": []}

    # ---------- 第一层：澄清/拒答门 ----------
    if en["clarify"]:
        gate = clarify.classify(question)
        trace["gate"] = gate
        if gate["action"] == "clarify":
            trace.update(status="clarify",
                         clarify_question=gate.get("clarify_question", "能否补充说明您的口径？"),
                         options=gate.get("options", []),
                         latency_ms=int((time.time() - t0) * 1000))
            return trace
        if gate["action"] == "refuse":
            trace.update(status="refuse",
                         refuse_reason=gate.get("reason", "该问题超出本数据集可回答范围。"),
                         latency_ms=int((time.time() - t0) * 1000))
            return trace

    # ---------- 第二层：生成 → 校验 → 沙箱执行 → 自我修正 ----------
    sql, repairs = "", 0
    repair_ctx = None
    max_repair = config.SQL_MAX_REPAIR if en["repair"] else 0
    try:
        for attempt in range(max_repair + 1):
            sql = sqlgen.generate(question, history, repair=repair_ctx, use_semantic=en["semantic"])

            # 静态校验是安全底线，任何消融配置下都不关闭
            v = validator.validate(sql)
            if not v.ok:
                trace["stages"].append({"stage": "validate", "ok": False, "errors": v.errors})
                repair_ctx = {"stage": "静态校验", "error": "；".join(v.errors), "sql": sql}
                repairs += 1
                continue

            r = executor.execute(sql)
            if r.ok:
                trace["stages"].append({"stage": "execute", "ok": True, "attempt": attempt})
                break
            trace["stages"].append({"stage": "execute", "ok": False, "error": r.error})
            repair_ctx = {"stage": "沙箱执行", "error": r.error, "sql": sql}
            repairs += 1
        else:
            trace.update(status="error",
                         error="多轮修正后仍无法得到可执行 SQL，请换个问法或缩小范围。",
                         last_sql=sql, repairs=repairs,
                         latency_ms=int((time.time() - t0) * 1000))
            return trace
    except llm.LLMError as e:
        # LLM 故障（重试耗尽）不应裸抛 500：与其它 error 路径同构的结构化 trace
        trace.update(status="error",
                     error=f"模型服务暂时不可用：{e}",
                     last_sql=sql or None, repairs=repairs,
                     latency_ms=int((time.time() - t0) * 1000))
        return trace

    # ---------- 意图回译：SQL 答的是不是用户问的 ----------
    explanation, consistent = "", {"consistent": True, "reason": "未启用"}
    if en["backtranslate"]:
        try:
            explanation = backtranslate.explain(sql)
            consistent = backtranslate.judge(question, explanation)
        except Exception as e:
            consistent = {"consistent": True, "reason": f"回译校验不可用：{e}", "unknown": True}
        trace["stages"].append({"stage": "backtranslate", "ok": consistent.get("consistent", True),
                                "reason": consistent.get("reason", "")})

    # ---------- 第三层：洞察生成 + 数字溯源 ----------
    ins = {"text": "", "text_verified": "", "grounding": None}
    if not skip_insight:
        try:
            ins = insight.generate(question, explanation or "（未生成回译）",
                                   r.columns, r.rows, r.truncated)
            if not en["grounding"]:
                ins["text_verified"], ins["grounding"] = ins["text"], None
        except Exception as e:
            ins = {"text": f"（洞察生成失败：{e}）", "text_verified": "", "grounding": None}

    warning = None
    if en["backtranslate"] and not consistent.get("consistent", True):
        warning = f"意图一致性存疑：{consistent.get('reason', '')}；结果仅供参考。"
    if en["grounding"] and ins.get("grounding") and ins["grounding"]["faithfulness"] < 1.0:
        bad = ins["grounding"]["unsupported"]
        warning = (warning + " " if warning else "") + f"洞察中有 {len(bad)} 个数字未能溯源，已标记。"

    trace.update(
        sql=sql,
        explanation=explanation,
        consistency=consistent,
        columns=r.columns,
        rows=[list(row) for row in r.rows],
        truncated=r.truncated,
        chart=_chart_hint(r.columns, r.rows),
        insight=ins["text_verified"] or ins["text"],
        grounding=ins["grounding"],
        repairs=repairs,
        warning=warning,
        latency_ms=int((time.time() - t0) * 1000),
        model=config.LLM_MODEL,
    )
    return trace
