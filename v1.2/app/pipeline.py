"""The v1.2 enterprise orchestration pipeline.

DeepSeek supplies language understanding and evidence selection. Enterprise
configuration, lineage and deterministic validators own the executable plan.
"""
from __future__ import annotations

import time
import uuid
import re
from datetime import date

from . import database
from .compiler import compile_plan
from .enterprise import build_join_plan, load_enterprise_config
from .evidence import build_evidence, grounded_insight
from .models import AskRequest, QueryPlan
from .planner import decide, normalize, PlanError
from .semantic import CATALOG, metadata_for


class Trace:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, stage, detail, status="passed", actor="automation", evidence=None):
        self.items.append({
            "stage": stage,
            "status": status,
            "actor": actor,
            "detail": detail,
            "evidence": evidence or [],
        })


def query_plan_for(plan: QueryPlan, join_plan: dict) -> dict:
    """Create a typed, inspectable plan after model intent is validated."""
    if plan.metric == "receipts":
        steps = [
            "filter BKPF/BSEG to approved companies, currency and posting period",
            "select DZ customer credit lines only",
            "aggregate amount at requested dimension",
            "sort and limit after computing the full total",
        ]
    else:
        steps = [
            "select DR customer debit items posted by the requested cutoff",
            "aggregate ZAR_APPLICATION by invoice item and effective date",
            "subtract applied amount from invoice amount at invoice-item grain",
            "aggregate open items at requested dimension",
            "sort and limit after computing the full total",
        ]
    if plan.metric == "balance_change":
        steps.insert(3, "repeat the same calculation for compare_as_of and compute current minus previous")
    return {
        "metric": plan.metric,
        "group_by": plan.group_by,
        "time": {key: str(value) for key, value in {
            "as_of": plan.as_of, "start_date": plan.start_date,
            "end_date": plan.end_date, "compare_as_of": plan.compare_as_of,
        }.items() if value is not None},
        "scope": {"companies": plan.companies, "currency": plan.currency, "customer": plan.customer},
        "steps": steps,
        "join_plan": join_plan,
        "execution": {"read_only": True, "parameterized": True, "max_rows": 50},
    }


def out_of_coverage(question: str) -> bool:
    """Data coverage is a deterministic capability boundary, not an LLM choice."""
    calendar = CATALOG["calendar"]
    minimum = date.fromisoformat(calendar["start"])
    maximum = date.fromisoformat(calendar["end"])
    matches = re.findall(r"(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})日?", question)
    for year, month, day in matches:
        try:
            value = date(int(year), int(month), int(day))
        except ValueError:
            continue
        if value < minimum or value > maximum:
            return True
    return False


def run_plan(plan: QueryPlan, use_model=True, trace=None) -> dict:
    trace = trace or Trace()
    started = time.monotonic()
    enterprise = load_enterprise_config()

    plan = normalize(plan, database.customers())
    metric = CATALOG["metrics"][plan.metric]
    trace.add("② Business Semantic", f"已解析指标：{metric['name']}；语义版本 {enterprise['semantic_version']}",
              actor="model+automation", evidence=[enterprise["semantic_version"]])
    metadata = metadata_for(plan.metric)
    trace.add("③ Metadata Retrieval", f"召回 {len(metadata['tables'])} 张候选表；血缘快照 {metadata['lineage_snapshot']}",
              actor="automation+enterprise-config", evidence=metadata["lineage_ids"])
    trace.add("④ Schema Linking", "业务指标已绑定到目录中的物理表和字段；字段存在性由服务端校验",
              actor="automation", evidence=list(metadata["tables"]))

    join_plan = build_join_plan(plan.metric, CATALOG)
    trace.add("⑤ Join Planner", f"确定 {len(join_plan['joins'])} 条关联；1:N 核销路径先聚合",
              actor="automation+authoritative-lineage", evidence=join_plan["lineage_ids"])
    logical_plan = query_plan_for(plan, join_plan)
    trace.add("⑥ Query Planner", f"生成 {len(logical_plan['steps'])} 个只读步骤；粒度={join_plan['grain']}",
              actor="model+automation", evidence=["typed_query_plan"])

    query = compile_plan(plan)
    trace.add("⑦ SQL Compiler", "使用注册指标的确定性 SQL 编译器；未接受模型直接提供的 SQL",
              actor="automation", evidence=["registered_metric_template"])
    rows, checks = database.execute(query, plan)
    trace.add("⑧ SQL Validator / ⑨ Execute", f"只读查询通过校验并返回 {len(rows)} 个分组；{checks['elapsed_ms']} ms",
              actor="automation+read-only-database", evidence=["compiler_match", "read_only"])
    trace.add("⑩ Result Validation", "整数分精度、账套平衡、核销关联、非负未结金额和结果行数检查完成",
              actor="automation", evidence=["ledger_quality", "amount_type", "nonnegative_open_items"])

    query_id = uuid.uuid4().hex[:12]
    evidence, summary = build_evidence(rows, plan, query_id)
    statements, grounding = grounded_insight(evidence, use_model=True)
    trace.add("⑪ Insight LLM", f"模型仅选择已计算的 {len(statements)} 条类型化事实",
              actor="DeepSeek", evidence=[item["evidence_id"] for item in statements])
    trace.add("⑫ Grounding", f"{grounding['checked_statements']} 条表达已绑定查询证据",
              actor="automation", evidence=[item["evidence_id"] for item in statements])

    warnings = ["演示时钟为 2026-07-01；所有数据为虚构。",
                f"口径：公司 {'、'.join(plan.companies)}；{plan.currency} 凭证币；按过账日期；金额单位为元。"]
    if summary["truncated"]:
        warnings.append(f"共 {summary['group_count']} 个分组，显示 {summary['shown_groups']} 个；合计包含全部匹配分组。")
    if grounding["mode"] == "deterministic_fallback":
        warnings.append("模型解释选择不可用，已使用可核验的程序生成解释。")
    if plan.metric == "balance_change":
        warnings.append("余额变化为差额分解，不代表已确认业务原因。")
    for row in rows:
        row["delta_cents"] = row["amount_cents"] - row["previous_cents"]
    return {
        "status": "answered", "mode": "deepseek", "query_id": query_id,
        "plan": plan.model_dump(mode="json"), "logical_plan": logical_plan,
        "metric": metric, "metadata": metadata, "join_plan": join_plan,
        "sql": query.sql, "parameters": query.params, "rows": rows,
        "summary": summary, "statements": statements, "evidence": evidence,
        "checks": checks, "grounding": grounding, "warnings": warnings,
        "trace": trace.items, "config_version": enterprise["config_version"],
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def ask(request: AskRequest) -> dict:
    trace = Trace()
    decision, context, repaired = decide(request)
    trace.add("① Router", f"{decision.action}；结构修正次数：{int(repaired)}",
              actor="DeepSeek+automation", evidence=["validated_decision_schema"])
    if out_of_coverage(request.question):
        message = f"查询日期超出当前数据覆盖范围（{CATALOG['calendar']['start']} 至 {CATALOG['calendar']['end']}），暂不支持。"
        trace.add("① Router", message, "unsupported", "enterprise-config")
        return {"status": "unsupported", "message": message, "trace": trace.items}
    if decision.action == "explain":
        metric = CATALOG["metrics"].get(decision.concept)
        if not metric:
            trace.add("② Business Semantic", "指标代码不在企业目录", "needs_clarification", "automation")
            return {"status": "clarify", "message": "请选择应收余额、逾期应收、账龄、回款或余额变化。", "trace": trace.items}
        trace.add("② Business Semantic", "返回企业批准的指标定义", evidence=[decision.concept])
        return {"status": "explain", "message": metric["name"] + "：" + metric["definition"], "trace": trace.items}
    if decision.action != "query":
        status = "needs_clarification" if decision.action == "clarify" else "unsupported"
        trace.add("② Business Semantic", decision.message, status, "automation")
        return {"status": decision.action, "message": decision.message, "trace": trace.items}
    try:
        result = run_plan(decision.plan, use_model=True, trace=trace)
        result["retrieval"] = context["ranked_metrics"]
        return result
    except PlanError as error:
        trace.add("⑥ Query Planner", str(error), "needs_clarification", "automation")
        return {"status": "clarify", "message": str(error), "trace": trace.items}
    except ValueError as error:
        trace.add("⑤ Join Planner", str(error), "blocked_by_policy", "enterprise-config")
        return {"status": "blocked", "message": str(error), "trace": trace.items}
