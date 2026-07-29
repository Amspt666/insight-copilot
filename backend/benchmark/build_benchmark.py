"""构建 benchmark.json：100 道中英双语评测题。

五类：
  A 简单聚合（25）/ B 多表关联（25）/ C 时间对比（20）— 期望 answer，附 gold SQL
  D 歧义澄清（15）— 期望 clarify    / E 超纲拒答（15）— 期望 refuse

所有 gold SQL 在写入前都会在真实 DuckDB 上执行验证（见文件末尾）。
口径约定与语义层一致：经营指标默认排除 canceled/unavailable 订单。
"""
import json
import sys

sys.path.insert(0, "/mnt/agents/work/insight_copilot/backend")

ITEMS: list[dict] = []
_no = {}


def add(category: str, question: str, *, lang: str = "zh", expect: str = "answer",
         gold_sql: str | None = None, note: str = "") -> None:
    _no[category] = _no.get(category, 0) + 1
    ITEMS.append({
        "id": f"{category}{_no[category]:02d}",
        "category": category,
        "question": question,
        "lang": lang,
        "expect": expect,
        "gold_sql": gold_sql,
        "note": note,
    })


VALID = "o.order_status NOT IN ('canceled','unavailable')"

# ==================== A 简单聚合（25） ====================
add("A", "数据集中一共有多少笔有效订单？", gold_sql=f"""
SELECT COUNT(*) AS valid_orders FROM orders o WHERE {VALID}""")
add("A", "一共有多少位独立客户？", gold_sql="""
SELECT COUNT(DISTINCT customer_unique_id) AS unique_customers FROM customers""")
add("A", "平台在售商品总数是多少？", gold_sql="""
SELECT COUNT(*) AS products FROM products""")
add("A", "平台一共有多少个卖家？", gold_sql="""
SELECT COUNT(*) AS sellers FROM sellers""")
add("A", "全部评价的平均评分是多少？", gold_sql="""
SELECT ROUND(AVG(review_score), 2) AS avg_score FROM reviews""")
add("A", "有效订单的总销售额是多少？", gold_sql=f"""
SELECT ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE {VALID}""")
add("A", "有效订单的总运费是多少？", gold_sql=f"""
SELECT ROUND(SUM(oi.freight_value), 2) AS freight
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE {VALID}""")
add("A", "好评率是多少？", gold_sql="""
SELECT ROUND(COUNT(*) FILTER (review_score >= 4) * 1.0 / COUNT(*), 4) AS positive_rate
FROM reviews""")
add("A", "差评率是多少？", gold_sql="""
SELECT ROUND(COUNT(*) FILTER (review_score <= 2) * 1.0 / COUNT(*), 4) AS negative_rate
FROM reviews""")
add("A", "客单价是多少？", gold_sql=f"""
SELECT ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS aov
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE {VALID}""")
add("A", "已送达订单的平均配送时长是多少天？", gold_sql="""
SELECT ROUND(AVG(DATE_DIFF('day', order_purchase_timestamp, order_delivered_customer_date)), 2) AS avg_days
FROM orders WHERE order_status = 'delivered'""")
add("A", "平台商品覆盖多少个品类？", gold_sql="""
SELECT COUNT(*) AS categories FROM category_translation""")
add("A", "客户分布在多少个不同的州？", gold_sql="""
SELECT COUNT(DISTINCT customer_state) AS states FROM customers""")
add("A", "信用卡支付金额占全部支付金额的比例是多少？", gold_sql="""
SELECT ROUND(SUM(payment_value) FILTER (payment_type = 'credit_card') / SUM(payment_value), 4) AS credit_card_ratio
FROM payments""")
add("A", "信用卡支付的平均分期期数是多少？", gold_sql="""
SELECT ROUND(AVG(payment_installments), 2) AS avg_installments
FROM payments WHERE payment_type = 'credit_card'""")
add("A", "分期付款（期数大于1）的支付金额占比是多少？", gold_sql="""
SELECT ROUND(SUM(payment_value) FILTER (payment_installments > 1) / SUM(payment_value), 4) AS installment_ratio
FROM payments""")
add("A", "单笔支付的最大金额是多少？", gold_sql="""
SELECT ROUND(MAX(payment_value), 2) AS max_payment FROM payments""")
add("A", "售出商品中单件最高售价是多少？", gold_sql="""
SELECT ROUND(MAX(price), 2) AS max_price FROM order_items""")
add("A", "有效订单平均每单包含几件商品？", gold_sql=f"""
SELECT ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT o.order_id), 2) AS items_per_order
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE {VALID}""")
add("A", "数据集覆盖的下单时间范围是从哪天到哪天？", gold_sql="""
SELECT MIN(order_purchase_timestamp)::DATE AS first_order, MAX(order_purchase_timestamp)::DATE AS last_order
FROM orders""")
add("A", "How many delivered orders are there in the dataset?", lang="en", gold_sql="""
SELECT COUNT(*) AS delivered_orders FROM orders WHERE order_status = 'delivered'""")
add("A", "What is the average freight value per valid order?", lang="en", gold_sql=f"""
SELECT ROUND(SUM(oi.freight_value) / COUNT(DISTINCT o.order_id), 2) AS avg_freight_per_order
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id WHERE {VALID}""")
add("A", "被取消的订单有多少笔？", gold_sql="""
SELECT COUNT(*) AS canceled_orders FROM orders WHERE order_status = 'canceled'""")
add("A", "平台一共收到多少条评价？", gold_sql="""
SELECT COUNT(*) AS review_count FROM reviews""")
add("A", "How many distinct orders have at least one review?", lang="en", gold_sql="""
SELECT COUNT(DISTINCT order_id) AS orders_with_review FROM reviews""")

# ==================== B 多表关联（25） ====================
add("B", "销售额最高的前三个州是哪些？", gold_sql=f"""
SELECT c.customer_state, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
GROUP BY 1 ORDER BY revenue DESC LIMIT 3""")
add("B", "销售额最高的前五个品类是哪些？", gold_sql=f"""
SELECT ct.product_category_name_english AS category, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID}
GROUP BY 1 ORDER BY revenue DESC LIMIT 5""")
add("B", "售出商品件数最多的前五个品类是哪些？", gold_sql=f"""
SELECT ct.product_category_name_english AS category, COUNT(*) AS item_volume
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID}
GROUP BY 1 ORDER BY item_volume DESC LIMIT 5""")
add("B", "销售额最高的前五名卖家是谁？", gold_sql=f"""
SELECT oi.seller_id, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
GROUP BY 1 ORDER BY revenue DESC LIMIT 5""")
add("B", "独立客户数最多的前五个城市是哪些？", gold_sql="""
SELECT customer_city, COUNT(DISTINCT customer_unique_id) AS customers
FROM customers
GROUP BY 1 ORDER BY customers DESC LIMIT 5""")
add("B", "平均评分最低的前三个州是哪些（订单量超过100）？", gold_sql=f"""
SELECT c.customer_state, ROUND(AVG(r.review_score), 2) AS avg_score
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN reviews r ON r.order_id = o.order_id
WHERE {VALID}
GROUP BY 1 HAVING COUNT(DISTINCT o.order_id) > 100
ORDER BY avg_score ASC LIMIT 3""")
add("B", "差评率最高的前三个品类是哪些（评价数超过100）？", gold_sql=f"""
SELECT ct.product_category_name_english AS category,
       ROUND(COUNT(*) FILTER (r.review_score <= 2) * 1.0 / COUNT(*), 4) AS negative_rate
FROM reviews r
JOIN order_items oi ON oi.order_id = r.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
GROUP BY 1 HAVING COUNT(*) > 100
ORDER BY negative_rate DESC LIMIT 3""")
add("B", "各种支付方式的支付笔数和总金额分别是多少？", gold_sql="""
SELECT payment_type, COUNT(*) AS payment_count, ROUND(SUM(payment_value), 2) AS total_value
FROM payments
GROUP BY 1 ORDER BY total_value DESC""")
add("B", "平均配送时长最长的前五个州是哪些？", gold_sql="""
SELECT c.customer_state,
       ROUND(AVG(DATE_DIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 2) AS avg_days
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
GROUP BY 1 ORDER BY avg_days DESC LIMIT 5""")
add("B", "销售额前三的品类各自的平均评分是多少？", gold_sql=f"""
WITH top_cat AS (
  SELECT p.product_category_name
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  JOIN products p ON p.product_id = oi.product_id
  WHERE {VALID}
  GROUP BY 1 ORDER BY SUM(oi.price) DESC LIMIT 3
)
SELECT ct.product_category_name_english AS category, ROUND(AVG(r.review_score), 2) AS avg_score
FROM reviews r
JOIN order_items oi ON oi.order_id = r.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE p.product_category_name IN (SELECT product_category_name FROM top_cat)
GROUP BY 1 ORDER BY avg_score DESC""")
add("B", "圣保罗州（SP）销售额最高的前三个品类是哪些？", gold_sql=f"""
SELECT ct.product_category_name_english AS category, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID} AND c.customer_state = 'SP'
GROUP BY 1 ORDER BY revenue DESC LIMIT 3""")
add("B", "整体复购率是多少？", gold_sql=f"""
SELECT ROUND(COUNT(*) FILTER (cnt >= 2) * 1.0 / COUNT(*), 4) AS repeat_rate
FROM (
  SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS cnt
  FROM customers c JOIN orders o ON o.customer_id = c.customer_id
  WHERE {VALID}
  GROUP BY 1) t""")
add("B", "客单价最高的前三个品类是哪些？", gold_sql=f"""
SELECT ct.product_category_name_english AS category,
       ROUND(SUM(oi.price) / COUNT(DISTINCT o.order_id), 2) AS aov
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID}
GROUP BY 1 ORDER BY aov DESC LIMIT 3""")
add("B", "收到差评（评分不高于2）最多的前三名卖家是谁？", gold_sql=f"""
SELECT oi.seller_id, COUNT(*) FILTER (r.review_score <= 2) AS negative_reviews
FROM reviews r
JOIN order_items oi ON oi.order_id = r.order_id
GROUP BY 1 ORDER BY negative_reviews DESC LIMIT 3""")
add("B", "订单量最高的前五个州是哪些？", gold_sql=f"""
SELECT c.customer_state, COUNT(DISTINCT o.order_id) AS order_volume
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
WHERE {VALID}
GROUP BY 1 ORDER BY order_volume DESC LIMIT 5""")
add("B", "平均配送时长最短的前三个州是哪些（订单量超过100）？", gold_sql="""
SELECT c.customer_state,
       ROUND(AVG(DATE_DIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 2) AS avg_days
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
GROUP BY 1 HAVING COUNT(DISTINCT o.order_id) > 100
ORDER BY avg_days ASC LIMIT 3""")
add("B", "平均每单运费最高的前三个品类是哪些？", gold_sql=f"""
SELECT ct.product_category_name_english AS category,
       ROUND(SUM(oi.freight_value) / COUNT(DISTINCT o.order_id), 2) AS avg_freight_per_order
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID}
GROUP BY 1 ORDER BY avg_freight_per_order DESC LIMIT 3""")
add("B", "boleto 支付金额占比最高的前三个州是哪些？", gold_sql=f"""
SELECT c.customer_state,
       ROUND(SUM(p.payment_value) FILTER (p.payment_type = 'boleto') / SUM(p.payment_value), 4) AS boleto_ratio
FROM payments p
JOIN orders o ON o.order_id = p.order_id
JOIN customers c ON c.customer_id = o.customer_id
WHERE {VALID}
GROUP BY 1 ORDER BY boleto_ratio DESC LIMIT 3""")
add("B", "购买商品件数最多的前三位客户是谁？", gold_sql=f"""
SELECT c.customer_unique_id, COUNT(*) AS items_bought
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
GROUP BY 1 ORDER BY items_bought DESC LIMIT 3""")
add("B", "带文字评价比例最高的前三个品类是哪些（评价数超过100）？", gold_sql="""
SELECT ct.product_category_name_english AS category,
       ROUND(COUNT(*) FILTER (r.review_comment_message IS NOT NULL AND LENGTH(r.review_comment_message) > 0) * 1.0 / COUNT(*), 4) AS comment_ratio
FROM reviews r
JOIN order_items oi ON oi.order_id = r.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
GROUP BY 1 HAVING COUNT(*) > 100
ORDER BY comment_ratio DESC LIMIT 3""")
add("B", "Which five product categories generated the most revenue in 2018?", lang="en", gold_sql=f"""
SELECT ct.product_category_name_english AS category, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID}
  AND o.order_purchase_timestamp >= DATE '2018-01-01'
  AND o.order_purchase_timestamp < DATE '2019-01-01'
GROUP BY 1 ORDER BY revenue DESC LIMIT 5""")
add("B", "Which three sellers have the highest average review score with at least 50 reviews?", lang="en", gold_sql="""
SELECT oi.seller_id, ROUND(AVG(r.review_score), 2) AS avg_score
FROM reviews r JOIN order_items oi ON oi.order_id = r.order_id
GROUP BY 1 HAVING COUNT(*) >= 50
ORDER BY avg_score DESC, COUNT(*) DESC LIMIT 3""")
add("B", "运费占商品金额比例最高的前三个品类是哪些？", gold_sql=f"""
SELECT ct.product_category_name_english AS category,
       ROUND(SUM(oi.freight_value) / SUM(oi.price), 4) AS freight_ratio
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p ON p.product_id = oi.product_id
JOIN category_translation ct ON ct.product_category_name = p.product_category_name
WHERE {VALID}
GROUP BY 1 ORDER BY freight_ratio DESC LIMIT 3""")
add("B", "每个州最常用的支付方式（按支付金额）是什么？", gold_sql=f"""
SELECT customer_state, payment_type, total_value FROM (
  SELECT c.customer_state, p.payment_type, SUM(p.payment_value) AS total_value,
         ROW_NUMBER() OVER (PARTITION BY c.customer_state ORDER BY SUM(p.payment_value) DESC) AS rn
  FROM payments p
  JOIN orders o ON o.order_id = p.order_id
  JOIN customers c ON c.customer_id = o.customer_id
  WHERE {VALID}
  GROUP BY 1, 2) t
WHERE rn = 1 ORDER BY customer_state""")
add("B", "Which five customer states have the longest average delivery time for delivered orders?", lang="en", gold_sql="""
SELECT c.customer_state,
       ROUND(AVG(DATE_DIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 2) AS avg_days
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
GROUP BY 1 ORDER BY avg_days DESC LIMIT 5""")

# ==================== C 时间对比（20） ====================
add("C", "2018 年各月的销售额是多少？", gold_sql=f"""
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
  AND o.order_purchase_timestamp >= DATE '2018-01-01'
  AND o.order_purchase_timestamp < DATE '2019-01-01'
GROUP BY 1 ORDER BY 1""")
add("C", "2017 年和 2018 年各自的销售额是多少？", gold_sql=f"""
SELECT strftime(o.order_purchase_timestamp, '%Y') AS year, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID} AND strftime(o.order_purchase_timestamp, '%Y') IN ('2017', '2018')
GROUP BY 1 ORDER BY 1""")
add("C", "2018 年各月的有效订单量是多少？", gold_sql=f"""
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month, COUNT(DISTINCT o.order_id) AS order_volume
FROM orders o
WHERE {VALID}
  AND o.order_purchase_timestamp >= DATE '2018-01-01'
  AND o.order_purchase_timestamp < DATE '2019-01-01'
GROUP BY 1 ORDER BY 1""")
add("C", "2017 年至 2018 年各月的平均评分是怎么变化的？", gold_sql="""
SELECT DATE_TRUNC('month', r.review_creation_date)::DATE AS month, ROUND(AVG(r.review_score), 2) AS avg_score
FROM reviews r
GROUP BY 1 ORDER BY 1""")
add("C", "最近 12 个月（以数据最新日期为准）各月销售额是多少？", gold_sql=f"""
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
  AND o.order_purchase_timestamp >= (SELECT MAX(order_purchase_timestamp)::DATE FROM orders) - INTERVAL 12 MONTH
GROUP BY 1 ORDER BY 1""")
add("C", "最近 3 个月（以数据最新日期为准）的有效订单量是多少？", gold_sql=f"""
SELECT COUNT(DISTINCT o.order_id) AS order_volume
FROM orders o
WHERE {VALID}
  AND o.order_purchase_timestamp >= (SELECT MAX(order_purchase_timestamp)::DATE FROM orders) - INTERVAL 3 MONTH""")
add("C", "各个年份的销售额分别是多少？", gold_sql=f"""
SELECT strftime(o.order_purchase_timestamp, '%Y') AS year, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
GROUP BY 1 ORDER BY 1""")
add("C", "2018 年第一季度和第二季度的销售额分别是多少？", gold_sql=f"""
SELECT quarter_label, ROUND(SUM(price), 2) AS revenue FROM (
  SELECT CASE WHEN o.order_purchase_timestamp < DATE '2018-04-01' THEN '2018Q1' ELSE '2018Q2' END AS quarter_label,
         oi.price
  FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
  WHERE {VALID}
    AND o.order_purchase_timestamp >= DATE '2018-01-01'
    AND o.order_purchase_timestamp < DATE '2018-07-01') t
GROUP BY 1 ORDER BY 1""")
add("C", "2018 年各月的新客户数（当月首次下单）是多少？", gold_sql=f"""
WITH first_order AS (
  SELECT c.customer_unique_id, MIN(DATE_TRUNC('month', o.order_purchase_timestamp)) AS first_month
  FROM customers c JOIN orders o ON o.customer_id = c.customer_id
  WHERE {VALID}
  GROUP BY 1)
SELECT first_month::DATE AS month, COUNT(*) AS new_customers
FROM first_order
WHERE first_month >= DATE '2018-01-01' AND first_month < DATE '2019-01-01'
GROUP BY 1 ORDER BY 1""")
add("C", "2018 年销售额相比 2017 年的增长率是多少？", gold_sql=f"""
WITH yearly AS (
  SELECT strftime(o.order_purchase_timestamp, '%Y') AS year, SUM(oi.price) AS revenue
  FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
  WHERE {VALID} AND strftime(o.order_purchase_timestamp, '%Y') IN ('2017', '2018')
  GROUP BY 1)
SELECT ROUND((MAX(revenue) FILTER (year = '2018') - MAX(revenue) FILTER (year = '2017'))
       / MAX(revenue) FILTER (year = '2017'), 4) AS growth_rate
FROM yearly""")
add("C", "What is the monthly valid order volume for the last 6 months of available data?", lang="en", gold_sql=f"""
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month, COUNT(DISTINCT o.order_id) AS order_volume
FROM orders o
WHERE {VALID}
  AND o.order_purchase_timestamp >= (SELECT MAX(order_purchase_timestamp)::DATE FROM orders) - INTERVAL 6 MONTH
GROUP BY 1 ORDER BY 1""")
add("C", "各个季度的销售额分别是多少？", gold_sql=f"""
SELECT strftime(o.order_purchase_timestamp, '%Y') AS year,
       QUARTER(o.order_purchase_timestamp) AS quarter,
       ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
GROUP BY 1, 2 ORDER BY 1, 2""")
add("C", "2018 年 9 月的销售额相比 8 月变化了百分之几？", gold_sql=f"""
WITH monthly AS (
  SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month, SUM(oi.price) AS revenue
  FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
  WHERE {VALID}
    AND o.order_purchase_timestamp >= DATE '2018-08-01'
    AND o.order_purchase_timestamp < DATE '2018-10-01'
  GROUP BY 1)
SELECT ROUND((MAX(revenue) FILTER (month = DATE '2018-09-01') - MAX(revenue) FILTER (month = DATE '2018-08-01'))
       / MAX(revenue) FILTER (month = DATE '2018-08-01'), 4) AS mom_change
FROM monthly""")
add("C", "一周之中哪一天的订单量最高？", gold_sql=f"""
SELECT dayname(o.order_purchase_timestamp) AS weekday, COUNT(DISTINCT o.order_id) AS order_volume
FROM orders o
WHERE {VALID}
GROUP BY 1 ORDER BY order_volume DESC""")
add("C", "一天之中哪个小时的下单量最高？", gold_sql=f"""
SELECT HOUR(o.order_purchase_timestamp) AS hour_of_day, COUNT(*) AS orders
FROM orders o
WHERE {VALID}
GROUP BY 1 ORDER BY orders DESC LIMIT 1""")
add("C", "2018 年各月的平均配送时长是多少天？", gold_sql="""
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month,
       ROUND(AVG(DATE_DIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 2) AS avg_days
FROM orders o
WHERE o.order_status = 'delivered'
  AND o.order_purchase_timestamp >= DATE '2018-01-01'
  AND o.order_purchase_timestamp < DATE '2019-01-01'
GROUP BY 1 ORDER BY 1""")
add("C", "2017 年销售额最高的是哪个月份？", gold_sql=f"""
SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS month, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
  AND o.order_purchase_timestamp >= DATE '2017-01-01'
  AND o.order_purchase_timestamp < DATE '2018-01-01'
GROUP BY 1 ORDER BY revenue DESC LIMIT 1""")
add("C", "最近一年的好评率与再之前一年的好评率分别是多少？", gold_sql="""
SELECT CASE WHEN r.review_creation_date >= (SELECT MAX(review_creation_date)::DATE FROM reviews) - INTERVAL 12 MONTH
            THEN '最近一年' ELSE '再前一年' END AS period,
       ROUND(COUNT(*) FILTER (r.review_score >= 4) * 1.0 / COUNT(*), 4) AS positive_rate
FROM reviews r
WHERE r.review_creation_date >= (SELECT MAX(review_creation_date)::DATE FROM reviews) - INTERVAL 24 MONTH
GROUP BY 1 ORDER BY 1 DESC""")
add("C", "What was the revenue by quarter in 2017?", lang="en", gold_sql=f"""
SELECT QUARTER(o.order_purchase_timestamp) AS quarter, ROUND(SUM(oi.price), 2) AS revenue
FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
WHERE {VALID}
  AND o.order_purchase_timestamp >= DATE '2017-01-01'
  AND o.order_purchase_timestamp < DATE '2018-01-01'
GROUP BY 1 ORDER BY 1""")
add("C", "2017 年和 2018 年各自销售额前三的品类分别是什么？", gold_sql=f"""
SELECT year, category, revenue, rn FROM (
  SELECT strftime(o.order_purchase_timestamp, '%Y') AS year,
         ct.product_category_name_english AS category,
         ROUND(SUM(oi.price), 2) AS revenue,
         ROW_NUMBER() OVER (PARTITION BY strftime(o.order_purchase_timestamp, '%Y') ORDER BY SUM(oi.price) DESC) AS rn
  FROM orders o
  JOIN order_items oi ON oi.order_id = o.order_id
  JOIN products p ON p.product_id = oi.product_id
  JOIN category_translation ct ON ct.product_category_name = p.product_category_name
  WHERE {VALID} AND strftime(o.order_purchase_timestamp, '%Y') IN ('2017', '2018')
  GROUP BY 1, 2) t
WHERE rn <= 3 ORDER BY year, rn""")

# ==================== D 歧义澄清（15） ====================
add("D", "销量最好的品类是哪个？", expect="clarify", note="“销量”口径歧义：件数/订单数/销售额")
add("D", "哪些商品的销量比较差？", expect="clarify", note="“销量”口径歧义")
add("D", "卖家销量排名是怎样的？", expect="clarify", note="“销量”口径歧义")
add("D", "2018 年销量怎么样？", expect="clarify", note="“销量”口径歧义")
add("D", "哪个品类卖得最好？", expect="clarify", note="“卖得好”无明确口径")
add("D", "大客户贡献了多少钱？", expect="clarify", note="“大客户”无定义")
add("D", "优质卖家的平均评分是多少？", expect="clarify", note="“优质卖家”无定义")
add("D", "热卖商品有哪些？", expect="clarify", note="“热卖”无阈值与口径")
add("D", "忠实客户有多少？", expect="clarify", note="“忠实客户”无定义")
add("D", "大订单的平均金额是多少？", expect="clarify", note="“大订单”无阈值")
add("D", "平台业绩怎么样？", expect="clarify", note="“业绩”无明确指标")
add("D", "哪些品类表现不好？", expect="clarify", note="“表现”无明确指标")
add("D", "新用户的购买情况如何？", expect="clarify", note="“新用户”时间窗无定义")
add("D", "畅销品有多少个？", expect="clarify", note="“畅销”无阈值")
add("D", "How many VIP customers does the platform have?", lang="en", expect="clarify", note="“VIP”无定义")

# ==================== E 超纲拒答（15） ====================
add("E", "今天天气怎么样？", expect="refuse", note="与数据无关")
add("E", "帮我写一段 Python 快速排序", expect="refuse", note="编程求助")
add("E", "苹果公司的股价是多少？", expect="refuse", note="实时外部数据")
add("E", "平台的广告投放 ROI 是多少？", expect="refuse", note="无广告数据")
add("E", "现在仓库里还剩多少库存？", expect="refuse", note="无库存数据")
add("E", "帮我查一下某个订单的物流单号", expect="refuse", note="无物流单号数据")
add("E", "客户张三的手机号是多少？", expect="refuse", note="无个人隐私数据")
add("E", "预测一下 2025 年的销售额会是多少？", expect="refuse", note="不做外推预测")
add("E", "Olist 和亚马逊谁的销售额更高？", expect="refuse", note="外部对比数据")
add("E", "把总销售额按当前汇率换算成美元", expect="refuse", note="需要实时汇率")
add("E", "平台的退货率是多少？", expect="refuse", note="无退货数据")
add("E", "平台的利润率是多少？", expect="refuse", note="无成本数据")
add("E", "客服的平均响应时间是多少？", expect="refuse", note="无客服数据")
add("E", "网站的日均访问量是多少？", expect="refuse", note="无流量数据")
add("E", "What is Olist's market share in Brazil?", lang="en", expect="refuse", note="外部市场数据")


# ==================== 验证 gold SQL 并落盘 ====================
if __name__ == "__main__":
    from app import executor

    ok_count, fail = 0, []
    for item in ITEMS:
        if item["expect"] != "answer":
            continue
        r = executor.execute(item["gold_sql"])
        if not r.ok or not r.rows:
            fail.append((item["id"], r.error[:120] if r.error else "空结果"))
            continue
        item["gold_result"] = {
            "columns": r.columns,
            "rows": [[str(c) for c in row] for row in r.rows[:50]],
        }
        ok_count += 1

    from collections import Counter
    dist = Counter(i["category"] for i in ITEMS)
    print("题目分布:", dict(dist), "| 总数:", len(ITEMS))
    print("gold SQL 验证:", ok_count, "通过;", len(fail), "失败")
    for f in fail:
        print("  FAIL:", f)
    if not fail:
        with open("/mnt/agents/work/insight_copilot/backend/benchmark/benchmark.json", "w", encoding="utf-8") as fp:
            json.dump(ITEMS, fp, ensure_ascii=False, indent=1)
        print("benchmark.json 已写入")
