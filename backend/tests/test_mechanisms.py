"""机制级单元测试：静态校验器 / 沙箱执行器 / 数字溯源校验器。

不依赖 LLM，直接运行：cd backend && python3 -m pytest tests/ -q
（无 pytest 时也可 python3 tests/test_mechanisms.py）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import executor, grounding, validator  # noqa: E402


# ---------------- 静态校验器 ----------------
MALICIOUS = {
    "删表": "DROP TABLE orders",
    "删除数据": "DELETE FROM orders WHERE order_status='canceled'",
    "改数据": "UPDATE orders SET order_status='x'",
    "建表": "CREATE TABLE hack AS SELECT * FROM orders",
    "多语句注入": "SELECT 1; DROP TABLE orders",
    "附加数据库": "ATTACH DATABASE '/tmp/x.db' AS x",
    "读文件函数": "SELECT * FROM read_csv_auto('/etc/passwd')",
    "读对象存储": "SELECT * FROM read_parquet('s3://b/x.parquet')",
    "导出数据库": "EXPORT DATABASE '/tmp/dump'",
    "PRAGMA": "PRAGMA database_list",
    "幻觉表": "SELECT COUNT(*) FROM order_items_extra",
    "幻觉列": "SELECT order_total_amount FROM orders",
    "安装扩展": "INSTALL httpfs",
    "COPY导出": "COPY orders TO '/tmp/o.csv'",
    "空SQL": "   ",
    # B1 回归：同族变体不得绕过谓词规则
    "读文件变体_objects": "SELECT * FROM read_json_objects('/tmp/x.json')",
    "读文件变体_ndjson": "SELECT * FROM read_ndjson_objects('/tmp/x.json')",
    "parquet_schema": "SELECT * FROM parquet_schema('/tmp/x.parquet')",
    "parquet_metadata": "SELECT * FROM parquet_metadata('/tmp/x.parquet')",
    "csv_metadata": "SELECT * FROM csv_metadata('/tmp/x.csv')",
    "sniff_csv": "SELECT * FROM sniff_csv('/tmp/x.csv')",
    "空间扩展读文件": "SELECT * FROM st_read('/tmp/x.shp')",
    # S3 回归：FROM 中的表值函数
    "表值函数range": "SELECT * FROM range(1000)",
    "表值函数元数据": "SELECT * FROM duckdb_tables()",
    # S4 回归：限定列必须属于其表
    "跨表错配限定列": "SELECT oi.customer_id FROM order_items oi",
}

LEGIT = {
    "简单聚合": "SELECT COUNT(*) FROM orders",
    "CTE": "WITH t AS (SELECT order_id FROM orders) SELECT COUNT(*) FROM t",
    "多表JOIN+别名": """SELECT c.customer_state, SUM(oi.price) s FROM orders o
        JOIN order_items oi ON oi.order_id=o.order_id
        JOIN customers c ON c.customer_id=o.customer_id
        GROUP BY 1 ORDER BY s DESC LIMIT 5""",
    "子查询": "SELECT * FROM (SELECT order_id FROM orders LIMIT 3) x",
    "UNION": "SELECT 'a' k, COUNT(*) v FROM orders UNION ALL SELECT 'b', COUNT(*) FROM reviews",
    "FILTER语法": "SELECT COUNT(*) FILTER (review_score>=4)*1.0/COUNT(*) FROM reviews",
    "日期截断": "SELECT DATE_TRUNC('month', order_purchase_timestamp) m, COUNT(*) FROM orders GROUP BY 1",
    "窗口函数": "SELECT customer_state, ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) rn FROM orders GROUP BY 1",
}


def test_validator_blocks_all_malicious():
    leaked = [n for n, sql in MALICIOUS.items() if validator.validate(sql).ok]
    assert not leaked, f"漏网: {leaked}"


def test_validator_passes_all_legit():
    killed = {n: validator.validate(sql).errors for n, sql in LEGIT.items()
              if not validator.validate(sql).ok}
    assert not killed, f"误杀: {killed}"


def test_validator_qualified_column_ownership():
    """S4：限定列归属校验——t.c 中 c 必须属于 t（含 CTE 输出列/派生子查询）。"""
    must_pass = [
        "SELECT o.order_id, oi.price FROM orders o JOIN order_items oi ON oi.order_id=o.order_id",
        "WITH t AS (SELECT order_id AS oid, price FROM orders) SELECT t.oid FROM t",
        "WITH t(a, b) AS (SELECT order_id, price FROM orders) SELECT t.a FROM t",
        "SELECT s.cnt FROM (SELECT customer_id, COUNT(*) AS cnt FROM orders GROUP BY 1) s",
    ]
    must_block = [
        "SELECT oi.customer_id FROM order_items oi",               # 列属于别的表
        "WITH t(a, b) AS (SELECT order_id, price FROM orders) SELECT t.c FROM t",
        "SELECT s.nope FROM (SELECT customer_id, COUNT(*) AS cnt FROM orders GROUP BY 1) s",
    ]
    leaked = [s for s in must_block if validator.validate(s).ok]
    killed = {s: validator.validate(s).errors for s in must_pass if not validator.validate(s).ok}
    assert not leaked, f"漏网: {leaked}"
    assert not killed, f"误杀: {killed}"


def test_gold_sql_all_pass_validator():
    """benchmark 全部 gold SQL 必须过静态校验（validator 过严会直接拖累问答通过率）。"""
    import json
    bench = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark.json"
    items = json.loads(bench.read_text(encoding="utf-8"))
    fails = {it["id"]: validator.validate(it["gold_sql"]).errors
             for it in items if it.get("gold_sql") and not validator.validate(it["gold_sql"]).ok}
    assert not fails, f"gold SQL 误杀: {fails}"


# ---------------- 沙箱执行器 ----------------
def test_executor_runs_readonly_query():
    r = executor.execute("SELECT COUNT(*) FROM orders")
    assert r.ok and r.rows[0][0] == 99441


def test_executor_double_guards_dangerous_sql():
    assert not executor.execute("SELECT * FROM read_csv_auto('/etc/passwd')").ok
    assert not executor.execute("DROP TABLE orders").ok


def test_executor_truncates_rows():
    r = executor.execute("SELECT customer_state FROM customers", row_limit=5)
    assert r.ok and len(r.rows) == 5 and r.truncated


def test_executor_handles_trailing_line_comment():
    """行尾 -- 注释曾吞掉 LIMIT 包装的闭括号导致必报语法错误。"""
    r = executor.execute("SELECT COUNT(*) FROM orders -- 统计订单数")
    assert r.ok and r.rows[0][0] == 99441
    # 字符串字面量中的 -- 不得被误剥
    r2 = executor.execute("SELECT 'a--b' AS x")
    assert r2.ok and r2.rows[0][0] == "a--b"


# ---------------- 数字溯源校验器 ----------------
def test_grounding_accepts_traceable_numbers():
    rows = [(2017, 45101, 3587782.42), (2018, 54011, 8665535.10)]
    text = "2017 年订单 45,101 单；2018 年增至 54,011 单、866.55万 BRL。"
    g = grounding.check(text, rows, extra_whitelist=[2017, 2018])
    assert g.faithfulness == 1.0


def test_grounding_catches_fabricated_numbers():
    rows = [(2018, 8665535.10)]
    text = "2018 年销售额 8665535.10 BRL，同比增长 142%，SP 州贡献 320万。"
    g = grounding.check(text, rows, extra_whitelist=[2018])
    assert g.faithfulness < 1.0
    assert "142%" in g.unsupported_raws and "320万" in g.unsupported_raws


def test_grounding_percentage_dual_scale():
    g = grounding.check("好评率约 41%。", [(0.4092,)])
    assert g.claims[0].supported


def test_grounding_same_row_derivation():
    # 同年两列之差属合法派生：revenue_2018 - revenue_2017
    rows = [("2018Q1", 100.0, 160.0)]
    g = grounding.check("环比增加 60。", rows)
    assert g.claims[0].supported


def test_redaction_uses_spans_not_content():
    rows = [(2018, 8665535.10)]
    text = "2018 年销售额 8665535.10，增长 142%。"
    g = grounding.check(text, rows, extra_whitelist=[2018])
    out = grounding.redact_unsupported(text, g)
    assert "2018 年销售额" in out and "[未溯源:142%]" in out


# ---------------- API 层 ----------------
def test_spa_route_blocks_path_traversal(tmp_path=None):
    """S1：SPA 托管不得因 %2e%2e%2f 编码变体逃逸 dist 目录。"""
    import tempfile

    from fastapi.testclient import TestClient

    import api.main as m

    with tempfile.TemporaryDirectory() as td:
        dist = Path(td) / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("index")
        secret = Path(td) / "secret.txt"
        secret.write_text("TOPSECRET")
        old = m.DIST_DIR
        m.DIST_DIR = dist
        try:
            c = TestClient(m.app)
            for p in ("/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt"):
                r = c.get(p)
                assert r.status_code == 200 and "TOPSECRET" not in r.text, f"穿越成功: {p}"
            assert c.get("/index.html").text == "index"
        finally:
            m.DIST_DIR = old


def test_pipeline_error_trace_when_llm_unavailable():
    """S5：LLM 不可用时 pipeline 返回结构化 error trace，而非裸抛异常。"""
    from app import config, pipeline
    old = config.LLM_API_KEY
    config.LLM_API_KEY = ""
    try:
        tr = pipeline.ask("销售额是多少？")
    finally:
        config.LLM_API_KEY = old
    assert tr["status"] == "error"
    assert "模型服务" in tr["error"]
    assert "latency_ms" in tr and "repairs" in tr


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
    print(f"全部 {len(fns)} 项机制测试通过")
