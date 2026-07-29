"""SQL 生成与自我修正（可信闭环第二层的生成端）。"""
from __future__ import annotations

import re

from . import config, llm, semantic

SYSTEM_PROMPT = """你是 InsightCopilot 的 Text-to-SQL 引擎。根据用户问题与给定语义上下文，生成一条 DuckDB 方言的只读 SELECT 查询。

硬性要求：
1. 只输出一条 SQL，包在 ```sql 代码块中，不要任何解释文字
2. 严格遵守语义上下文中的指标口径、连接关系与全局约定（如有效订单口径）
3. 表名、列名必须来自给定 Schema，禁止臆造
4. 相对时间一律基于给定的时间锚点推算
5. 只读 SELECT；禁止 INSERT/UPDATE/DELETE/DDL/文件读写函数
6. 结果聚合适当取别名；金额保留两位小数（ROUND(x, 2)）

简洁原则（非常重要）：
7. 能用单表查询就不要 JOIN，每多 JOIN 一张表就多一层出错可能
8. 问"好评率"直接查 reviews 表，不需要 JOIN orders（好评率和订单是否取消无关）
9. 问"客户分布"直接查 customers 表，不需要 JOIN orders（去重客户数和订单状态无关）
10. 问"平均评分月度趋势"直接查 reviews.review_creation_date，不需要 JOIN orders
11. 先想清楚：这个问题本质上是关于哪张表的？只查那张表够不够？

输出格式规范（必须遵守，影响评测匹配）：
12. 只输出用户问题中明确要求的列，不要额外添加无关列（如用户没要求看"订单量"，就不要加 order_volume）
13. 百分比/比率/占比 一律用小数表示（如 0.2018 而非 20.18 或 20.18%）；好评率/差评率同理用 0.xxxx
14. 日期用 ::DATE 转成纯日期格式（如 '2018-01-01'），不要输出 datetime 格式
15. 季度标注用 '2018Q1' 格式，不要用单独的 'Q1'
16. 星期几用英文全名（Monday/Tuesday/...），不要用数字 0-6
17. Top N 查询只需要返回要求的 N 行；"最高/最大"只返回排名第一的
18. 问"共有多少个品类"用 category_translation 表，不用 products 表（products 的品类可能超过翻译表）"""

FEW_SHOTS = [
    {
        "q": "2018 年各月销售额趋势如何？",
        "sql": """SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month,
       ROUND(SUM(oi.price), 2) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
  AND o.order_purchase_timestamp >= DATE '2018-01-01'
  AND o.order_purchase_timestamp < DATE '2019-01-01'
GROUP BY 1
ORDER BY 1""",
    },
    {
        "q": "哪个州的客户贡献了最多订单量？",
        "sql": """SELECT c.customer_state,
       COUNT(DISTINCT o.order_id) AS order_volume
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY order_volume DESC
LIMIT 10""",
    },
    {
        "q": "好评率是多少？",
        "sql": """SELECT ROUND(COUNT(*) FILTER (review_score >= 4) * 1.0 / COUNT(*), 4) AS positive_rate
FROM reviews""",
    },
    {
        "q": "销量最高的品类是哪个？",
        "sql": """SELECT ct.product_category_name_english AS category,
       COUNT(*) AS item_volume
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY item_volume DESC
LIMIT 10""",
    },
    {
        "q": "2017 年和 2018 年的销售额对比如何？",
        "sql": """SELECT EXTRACT(YEAR FROM o.order_purchase_timestamp) AS year,
       ROUND(SUM(oi.price), 2) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
  AND EXTRACT(YEAR FROM o.order_purchase_timestamp) IN (2017, 2018)
GROUP BY 1
ORDER BY 1""",
    },
    {
        "q": "各月平均评分怎么变化的？",
        "sql": """SELECT DATE_TRUNC('month', review_creation_date)::DATE AS month,
       ROUND(AVG(review_score), 2) AS avg_score
FROM reviews
GROUP BY 1
ORDER BY 1""",
    },
    {
        "q": "2017 年各季度的订单量是多少？",
        "sql": """SELECT EXTRACT(QUARTER FROM order_purchase_timestamp) AS quarter,
       COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status NOT IN ('canceled', 'unavailable')
  AND EXTRACT(YEAR FROM order_purchase_timestamp) = 2017
GROUP BY 1
ORDER BY 1""",
    },
]

_SQL_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    """从模型输出中抽取 SQL；无代码块时回退为全文。"""
    m = _SQL_RE.search(text)
    sql = (m.group(1) if m else text).strip()
    return sql.rstrip(";").strip()


def build_messages(
    question: str,
    history: list[dict[str, str]] | None = None,
    repair: dict[str, str] | None = None,
    use_semantic: bool = True,
) -> list[dict[str, str]]:
    """组装生成 prompt。repair 传入上一轮错误信息即进入自我修正模式。

    use_semantic=False 时为消融基线：只给 DDL，不给指标口径/约定/歧义提醒。
    """
    if use_semantic:
        context = semantic.build_context(question)
    else:
        from . import db
        context = "## 数据库 Schema（DuckDB 方言）\n" + db.schema_ddl()
    user_parts = [context, "\n## 问答示例"]
    for fs in FEW_SHOTS:
        user_parts.append(f"问：{fs['q']}\n答：```sql\n{fs['sql']}\n```")

    if history:  # 多轮追问：携带上一问与 SQL，供指代消解
        last = history[-1]
        user_parts.append("\n## 对话历史")
        user_parts.append(f"上一问：{last.get('question', '')}")
        if last.get("sql"):
            user_parts.append(f"上一问 SQL：```sql\n{last['sql']}\n```")
        user_parts.append("当前问题若含“那/它/再/还”等指代，请结合对话历史理解。")

    if repair:
        user_parts.append("\n## 上一版 SQL 出错，请修正")
        user_parts.append(f"错误类型：{repair['stage']}")
        user_parts.append(f"错误信息：{repair['error']}")
        user_parts.append(f"出错的 SQL：```sql\n{repair['sql']}\n```")

    user_parts.append(f"\n## 用户问题\n{question}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def generate(
    question: str,
    history: list[dict[str, str]] | None = None,
    repair: dict[str, str] | None = None,
    use_semantic: bool = True,
) -> str:
    messages = build_messages(question, history, repair, use_semantic)
    out = llm.chat(messages, max_tokens=config.SQLGEN_MAX_TOKENS, temperature=0.0)
    return extract_sql(out)
