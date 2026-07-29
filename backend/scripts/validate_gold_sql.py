"""回归脚本：benchmark.json 中全部 gold SQL 必须通过静态校验器。

用法：cd backend && python3 scripts/validate_gold_sql.py
退出码非 0 表示有误杀（validator 过严，会拖累真实问答的通过率）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import validator  # noqa: E402

BENCH = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark.json"


def main() -> int:
    items = json.loads(BENCH.read_text(encoding="utf-8"))
    golds = [(it["id"], it["gold_sql"]) for it in items if it.get("gold_sql")]
    fails = []
    for qid, sql in golds:
        v = validator.validate(sql)
        status = "PASS" if v.ok else "FAIL"
        print(f"{status} {qid}")
        if not v.ok:
            fails.append((qid, v.errors))
    print(f"\n共 {len(golds)} 条 gold SQL：{len(golds) - len(fails)} PASS，{len(fails)} FAIL")
    for qid, errs in fails:
        print(f"  {qid}: {errs}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
