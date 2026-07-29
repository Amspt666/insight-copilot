"""把真实运行产物编译为前端内置数据（src/lib/demoData.ts）：

- examples/replay/*.json   → DEMO_TRACES / DEMO_EXAMPLES
- backend/eval/results/*.json → DEMO_EVAL（每个配置取最新一次）
- 数据集统计               → DEMO_META（构建时从 DuckDB 实读）

运行：python3 scripts/gen_demo_data.py <frontend_src_dir>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "examples" / "replay"
EVAL_RESULTS = ROOT / "backend" / "eval" / "results"

CONFIG_ORDER = ["full", "baseline", "no_clarify", "no_semantic", "no_repair",
                "no_backtranslate", "no_grounding"]


def latest_summaries() -> list[dict]:
    best: dict[str, tuple[str, dict]] = {}
    if not EVAL_RESULTS.exists():
        return []
    for f in sorted(EVAL_RESULTS.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cfg = data["config"]
            if cfg not in best or f.name > best[cfg][0]:
                best[cfg] = (f.name, data["summary"] | {"config": cfg})
        except Exception:
            continue
    return [best[c][1] for c in CONFIG_ORDER if c in best]


def main() -> None:
    src_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "frontend" / "src" / "lib"
    src_dir.mkdir(parents=True, exist_ok=True)

    traces = {}
    examples = []
    for f in sorted(REPLAY.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        traces[f.stem] = data
        examples.append({"id": f.stem, "question": data.get("question", f.stem),
                         "category": data.get("category", "示例")})

    sys.path.insert(0, str(ROOT / "backend"))
    from app import db  # noqa
    con = db.get_conn()
    q = lambda s: con.execute(s).fetchone()
    meta = {
        "mode": "replay", "model": None,
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

    summaries = latest_summaries()
    demo_eval = {"benchmarkSize": 100, "summaries": summaries}

    ts = (
        "/** 本文件由 scripts/gen_demo_data.py 自动生成，内容为真实运行数据，请勿手改 */\n"
        "import type { AskTrace, ExampleMeta, MetaInfo, EvalSummary } from './types'\n\n"
        f"export const DEMO_META: MetaInfo = {json.dumps(meta, ensure_ascii=False)}\n\n"
        f"export const DEMO_EXAMPLES: ExampleMeta[] = {json.dumps(examples, ensure_ascii=False)}\n\n"
        f"export const DEMO_TRACES: Record<string, AskTrace> = {json.dumps(traces, ensure_ascii=False)}\n\n"
        f"export const DEMO_EVAL: {{ benchmarkSize: number; summaries: EvalSummary[] }} = "
        f"{json.dumps(demo_eval, ensure_ascii=False)}\n"
    )
    (src_dir / "demoData.ts").write_text(ts, encoding="utf-8")
    print(f"demoData.ts written: {len(traces)} traces, {len(summaries)} eval configs → {src_dir}")


if __name__ == "__main__":
    main()
