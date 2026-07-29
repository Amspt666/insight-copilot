"""生成回放样例：用真实模型跑 10 个代表性问题，完整 trace 落盘。

这些样例同时服务于：
- 未配置 key 时的回放模式（本地一键体验）
- 在线静态演示（前端内置真实运行数据）
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, "/mnt/agents/work/insight_copilot/backend")
from app import pipeline

OUT = Path("/mnt/agents/work/insight_copilot/examples/replay")
OUT.mkdir(parents=True, exist_ok=True)

EXAMPLES = [
    ("monthly_revenue_2018", "2018 年各月的销售额是多少？", "趋势分析"),
    ("top_categories", "销售额最高的前五个品类是哪些？", "品类洞察"),
    ("repeat_rate", "整体复购率是多少？", "客户经营"),
    ("delivery_by_state", "平均配送时长最长的前五个州是哪些？", "物流体验"),
    ("yoy_growth", "2018 年销售额相比 2017 年的增长率是多少？", "增长分析"),
    ("worst_categories_review", "差评率最高的前三个品类是哪些（评价数超过100）？", "体验治理"),
    ("ambiguous_sales", "销量最高的三个品类是哪些？", "可信机制·澄清"),
    ("vague_performance", "平台业绩怎么样？", "可信机制·澄清"),
    ("out_of_scope", "今天天气怎么样？", "可信机制·拒答"),
    ("en_top_categories_2018", "Which five product categories generated the most revenue in 2018?", "English QA"),
]


def run_one(slug: str, q: str, cat: str) -> None:
    if (OUT / f"{slug}.json").exists():
        print(f"[skip] {slug} 已存在")
        return
    tr = pipeline.ask(q)
    tr["category"] = cat
    (OUT / f"{slug}.json").write_text(
        json.dumps(tr, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[done] {slug}: status={tr['status']} repairs={tr.get('repairs')} "
          f"latency={tr.get('latency_ms')}ms faith={(tr.get('grounding') or {}).get('faithfulness')}")


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda a: run_one(*a), EXAMPLES))
    print("all examples saved to", OUT)
