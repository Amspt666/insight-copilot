"""评测跑分器：在 100 题基准上评估可信管线，支持消融配置。

用法：
  python3 -m eval.run_eval --config full
  python3 -m eval.run_eval --config baseline --limit 20 --concurrency 8

指标：
  可答题（A/B/C 70 题）：执行准确率 EX（结果集与 gold 一致）、可答率、平均修正轮数
  歧义题（D 15 题）：澄清率（该反问的有没有反问）
  超纲题（E 15 题）：拒答率（该拒的有没有拒）
  附带：洞察忠实度（数字溯源）、误拒/误澄清率
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import pipeline  # noqa: E402

BENCH_PATH = Path(__file__).resolve().parent.parent / "benchmark" / "benchmark.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

CONFIGS: dict[str, dict[str, bool]] = {
    "full":             {},
    "baseline":         {"clarify": False, "semantic": False, "repair": False,
                         "backtranslate": False, "grounding": False},
    "no_clarify":       {"clarify": False},
    "no_semantic":      {"semantic": False},
    "no_repair":        {"repair": False},
    "no_backtranslate": {"backtranslate": False},
    "no_grounding":     {"grounding": False},
}


def _norm_cell(x) -> str:
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return str(x)


def result_match(actual_rows: list[list], gold_rows: list[list]) -> bool:
    """结果集多重集合比较（数值归一到两位小数，行序不敏感）。"""
    a = sorted(tuple(_norm_cell(c) for c in row) for row in actual_rows)
    g = sorted(tuple(_norm_cell(c) for c in row) for row in gold_rows)
    return a == g


def run_item(item: dict, enable: dict[str, bool], skip_insight: bool) -> dict:
    t0 = time.time()
    try:
        tr = pipeline.ask(item["question"], enable=enable, skip_insight=skip_insight)
    except Exception as e:
        return {"id": item["id"], "category": item["category"], "expect": item["expect"],
                "status": "exception", "error": str(e)[:300],
                "latency_s": round(time.time() - t0, 1)}
    rec = {
        "id": item["id"], "category": item["category"], "expect": item["expect"],
        "status": tr["status"], "latency_s": round(time.time() - t0, 1),
        "repairs": tr.get("repairs"),
    }
    if item["expect"] == "answer":
        if tr["status"] == "ok":
            rec["sql"] = tr["sql"]
            rec["ex_match"] = result_match(tr.get("rows", []),
                                           item.get("gold_result", {}).get("rows", []))
            if tr.get("grounding"):
                rec["faithfulness"] = tr["grounding"]["faithfulness"]
            # backtranslate 被消融时 pipeline 返回占位 {"consistent": True, "reason": "未启用"}，
            # 不能计入一致性统计，否则消融配置的一致性虚高
            if enable.get("backtranslate", True):
                rec["consistent"] = (tr.get("consistency") or {}).get("consistent")
        else:
            rec["ex_match"] = False
            rec["blocked_as"] = tr["status"]  # refuse/clarify/error → 误拒统计
    else:
        rec["correct"] = tr["status"] == item["expect"]
        if tr["status"] == "ok":
            rec["blocked_as"] = "answered_anyway"
    return rec


def summarize(records: list[dict]) -> dict:
    ans = [r for r in records if r["expect"] == "answer"]
    clar = [r for r in records if r["expect"] == "clarify"]
    ref = [r for r in records if r["expect"] == "refuse"]
    ok_ans = [r for r in ans if r["status"] == "ok"]
    faith = [r["faithfulness"] for r in ok_ans if "faithfulness" in r]
    cons = [r["consistent"] for r in ok_ans if r.get("consistent") is not None]

    def rate(xs, pred):
        xs = list(xs)
        return round(sum(1 for x in xs if pred(x)) / len(xs), 4) if xs else None

    return {
        "total": len(records),
        "answerable": {
            "n": len(ans),
            "execution_accuracy": rate(ans, lambda r: r.get("ex_match")),
            "answer_rate": rate(ans, lambda r: r["status"] == "ok"),
            # 误拒与误澄清分开统计（此前混在一个字段里）
            "wrong_refusal_rate": rate(ans, lambda r: r["status"] == "refuse"),
            "wrong_clarify_rate": rate(ans, lambda r: r["status"] == "clarify"),
            "avg_repairs": round(sum(r.get("repairs") or 0 for r in ok_ans) / len(ok_ans), 2) if ok_ans else None,
            "insight_faithfulness": round(sum(faith) / len(faith), 4) if faith else None,
            # 仅统计 backtranslate 实际启用的记录（None=该配置未启用回译）
            "backtranslate_consistency": round(sum(1 for c in cons if c) / len(cons), 4) if cons else None,
        },
        "clarify": {"n": len(clar), "clarify_rate": rate(clar, lambda r: r.get("correct"))},
        "refuse": {"n": len(ref), "refuse_rate": rate(ref, lambda r: r.get("correct"))},
        "avg_latency_s": round(sum(r["latency_s"] for r in records) / len(records), 1) if records else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="full", choices=list(CONFIGS))
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（调试用）")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--tag", default="", help="结果文件名后缀")
    ap.add_argument("--skip-insight", action="store_true",
                    help="跳过洞察生成（只测执行准确率/澄清/拒答，速度更快）")
    ap.add_argument("--categories", default="", help="只跑指定类别，如 A,B,C")
    args = ap.parse_args()

    items = json.loads(BENCH_PATH.read_text(encoding="utf-8"))
    if args.categories:
        keep = {c.strip() for c in args.categories.split(",")}
        items = [i for i in items if i["category"] in keep]
    if args.limit:
        items = items[: args.limit]
    enable = CONFIGS[args.config]

    # ---------- 断点续跑：JSONL 增量落盘，已完成题目自动跳过 ----------
    RESULTS_DIR.mkdir(exist_ok=True)
    cats = f"_{args.categories.replace(',', '')}" if args.categories else ""
    tag = f"_{args.tag}" if args.tag else ""
    jsonl = RESULTS_DIR / f"{args.config}{cats}{tag}.jsonl"
    done: dict[str, dict] = {}
    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                done[rec["id"]] = rec
            except Exception:
                continue
    todo = [it for it in items if it["id"] not in done]
    print(f"[run_eval] config={args.config} items={len(items)} 已完成={len(done)} "
          f"待跑={len(todo)} concurrency={args.concurrency} skip_insight={args.skip_insight}")

    records: list[dict] = list(done.values())
    lock = threading.Lock()
    with open(jsonl, "a", encoding="utf-8") as fp:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futs = {pool.submit(run_item, it, enable, args.skip_insight): it for it in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                with lock:
                    records.append(rec)
                    fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fp.flush()
                flag = "✓" if rec.get("ex_match") or rec.get("correct") else "✗"
                print(f"  [{len(done)+i}/{len(items)}] {rec['id']} {rec['expect']}->{rec['status']} {flag} "
                      f"({rec['latency_s']}s)")

    summary = summarize(records)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"{args.config}{tag}_{ts}.json"
    out.write_text(json.dumps({"config": args.config, "enable": enable,
                               "summary": summary, "records": records},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"[run_eval] 结果已写入 {out}")


if __name__ == "__main__":
    main()
