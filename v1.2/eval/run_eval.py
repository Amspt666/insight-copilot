"""Evaluate the v1.2 trusted pipeline against a raw-model baseline.

Both systems use the configured DeepSeek endpoint. The baseline receives only
the physical schema and prompt; v1.2 additionally uses the approved semantic
catalog, lineage planner, typed plan, validators and evidence grounding.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import database, pipeline  # noqa: E402
from app.compiler import compile_plan  # noqa: E402
from app.llm import chat_json  # noqa: E402
from app.models import AskRequest, Decision  # noqa: E402
from app.planner import normalize  # noqa: E402
from app.semantic import CATALOG  # noqa: E402
from eval.oracle import expected as independent_expected  # noqa: E402

BENCH = Path(__file__).resolve().parent / "benchmark.json"
RESULTS = Path(__file__).resolve().parent / "results"

BASELINE_SYSTEM = """你是一个简单的财务 Text-to-SQL 模型。只输出 JSON。
支持的指标是 ar_balance, overdue_ar, aging, receipts, balance_change；
只使用 SAP 风格表 BKPF、BSEG、KNA1、T001、ZAR_APPLICATION。
如果问题缺少日期、包含多个指标、涉及利润/预测/写操作或工资，输出
{\"action\":\"clarify\",\"message\":\"...\"} 或
{\"action\":\"unsupported\",\"message\":\"...\"}。
否则输出符合给定 Schema 的 query plan。不要输出 SQL。"""

CATALOG_BASELINE_SYSTEM = BASELINE_SYSTEM + """
你可以参考下面的业务指标名称和定义，但没有权威血缘规划器；自行判断表关系。
业务目录：""" + json.dumps(CATALOG["metrics"], ensure_ascii=False)


def expected_plan(item: dict):
    values = {"metric": item["expected_metric"], "group_by": item["expected_group"],
              "currency": item.get("currency", "CNY"), "limit": item.get("limit", 10), "order": item.get("order", "desc"),
              "companies": item.get("companies", ["1000", "2000"])}
    for key in ("as_of", "start_date", "end_date", "compare_as_of"):
        if key in item:
            values[key] = date.fromisoformat(item[key])
    if "overdue_days" in item:
        values["overdue_days"] = item["overdue_days"]
    if "customer" in item:
        values["customer"] = item["customer"]
    return Decision(action="query", plan=__import__("app.models", fromlist=["QueryPlan"]).QueryPlan(**values))


def oracle(item: dict) -> dict | None:
    """Reference result from independent event-row calculations."""
    return independent_expected(item)


def run_trusted(item: dict) -> dict:
    started = time.monotonic()
    try:
        response = pipeline.ask(AskRequest(question=item["question"]))
        return {"status": response.get("status"), "elapsed_ms": round((time.monotonic() - started) * 1000),
                "response": response}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:300], "elapsed_ms": round((time.monotonic() - started) * 1000)}


def run_baseline(item: dict) -> dict:
    return run_model_plan(item, BASELINE_SYSTEM)


def run_catalog_baseline(item: dict) -> dict:
    return run_model_plan(item, CATALOG_BASELINE_SYSTEM)


def run_model_plan(item: dict, system_prompt: str) -> dict:
    started = time.monotonic()
    try:
        raw = chat_json([
            {"role": "system", "content": system_prompt + "\nSchema: " + json.dumps(Decision.model_json_schema(), ensure_ascii=False)},
            {"role": "user", "content": item["question"]},
        ], max_tokens=1200)
        decision = Decision.model_validate(raw)
        if decision.action != "query":
            return {"status": decision.action, "elapsed_ms": round((time.monotonic() - started) * 1000), "raw": raw}
        plan = normalize(decision.plan, database.customers())
        rows, checks = database.execute(compile_plan(plan), plan)
        return {"status": "answered", "elapsed_ms": round((time.monotonic() - started) * 1000),
                "summary": {"total_cents": rows[0]["full_total_cents"] if rows else 0,
                            "group_count": rows[0]["group_count"] if rows else 0},
                "checks": checks, "raw": raw}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:300], "elapsed_ms": round((time.monotonic() - started) * 1000)}


def score(item: dict, result: dict, expected: dict | None) -> dict:
    target_status = item.get("expected_action", "answered" if item["category"] == "answer" else item["category"])
    status = result.get("status")
    status_ok = status == target_status
    numeric_ok = None
    if expected is not None and status == "answered":
        actual = result.get("response", result).get("summary", {})
        numeric_ok = actual.get("total_cents") == expected["total_cents"]
    trace_ok = None
    response = result.get("response")
    if response is not None:
        stages = {item.get("stage") for item in response.get("trace", [])}
        required = {"① Router", "② Business Semantic", "③ Metadata Retrieval", "④ Schema Linking",
                    "⑤ Join Planner", "⑥ Query Planner", "⑦ SQL Compiler", "⑧ SQL Validator / ⑨ Execute",
                    "⑩ Result Validation", "⑪ Insight LLM", "⑫ Grounding"}
        trace_ok = required.issubset(stages) if status == "answered" else True
        if status == "answered":
            trace_ok = trace_ok and bool(response.get("join_plan", {}).get("lineage_ids")) and bool(response.get("checks", {}).get("read_only"))
    return {"status_ok": status_ok, "numeric_ok": numeric_ok, "trace_ok": trace_ok,
            "passed": status_ok and (numeric_ok is not False) and (trace_ok is not False)}


def summarize(records: list[dict]) -> dict:
    out = {}
    for system in ("trusted", "catalog_baseline", "baseline"):
        subset = [r for r in records if r["system"] == system]
        numeric = [r["score"]["numeric_ok"] for r in subset if r["score"]["numeric_ok"] is not None]
        trace = [r["score"]["trace_ok"] for r in subset if r["score"]["trace_ok"] is not None]
        out[system] = {
            "n": len(subset),
            "pass_rate": round(sum(r["score"]["passed"] for r in subset) / len(subset), 4) if subset else 0,
            "status_accuracy": round(sum(r["score"]["status_ok"] for r in subset) / len(subset), 4) if subset else 0,
            "numeric_accuracy": round(sum(x is True for x in numeric) / max(1, len(numeric)), 4),
            "trace_completeness": round(sum(x is True for x in trace) / max(1, len(trace)), 4) if trace else None,
            "avg_latency_ms": round(sum(r["elapsed_ms"] for r in subset) / len(subset)) if subset else 0,
        }
        for category in ("answer", "clarify", "unsupported", "security", "explain"):
            group = [r for r in subset if r["category"] == category]
            if group:
                out[system][f"{category}_pass_rate"] = round(sum(r["score"]["passed"] for r in group) / len(group), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--baseline-only", action="store_true")
    ap.add_argument("--repeat", type=int, default=1, help="每个系统重复运行次数")
    args = ap.parse_args()
    items = json.loads(BENCH.read_text(encoding="utf-8"))
    if args.limit:
        items = items[:args.limit]
    RESULTS.mkdir(exist_ok=True)
    records = []
    for repeat in range(1, max(1, args.repeat) + 1):
        for index, item in enumerate(items, 1):
            expected = oracle(item)
            if not args.baseline_only:
                result = run_trusted(item)
                rec = {"id": item["id"], "repeat": repeat, "category": item["category"], "system": "trusted", "elapsed_ms": result["elapsed_ms"],
                       "status": result.get("status"), "score": score(item, result, expected),
                       "response": result.get("response"), "error": result.get("error")}
                records.append(rec)
                print(f"[{repeat}/{args.repeat}] [{index}/{len(items)}] trusted {item['id']} {rec['status']} {rec['score']['passed']}")
            result = run_catalog_baseline(item)
            rec = {"id": item["id"], "repeat": repeat, "category": item["category"], "system": "catalog_baseline", "elapsed_ms": result["elapsed_ms"],
                   "status": result.get("status"), "score": score(item, result, expected),
                   "summary": result.get("summary"), "error": result.get("error")}
            records.append(rec)
            print(f"[{repeat}/{args.repeat}] [{index}/{len(items)}] catalog_baseline {item['id']} {rec['status']} {rec['score']['passed']}")
            result = run_baseline(item)
            rec = {"id": item["id"], "repeat": repeat, "category": item["category"], "system": "baseline", "elapsed_ms": result["elapsed_ms"],
                   "status": result.get("status"), "score": score(item, result, expected),
                   "summary": result.get("summary"), "error": result.get("error")}
            records.append(rec)
            print(f"[{repeat}/{args.repeat}] [{index}/{len(items)}] baseline {item['id']} {rec['status']} {rec['score']['passed']}")
    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": os.getenv("LLM_MODEL", "from-env-file"), "items": len(items), "repeats": max(1, args.repeat),
              "summary": summarize(records), "records": records}
    path = RESULTS / f"report_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(path)


if __name__ == "__main__":
    main()
