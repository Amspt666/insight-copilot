"""Independent reference calculations for the v1.2 evaluation set.

This intentionally does not call the production compiler. It reads the same
generated ledger through a read-only connection and computes expected totals
from event rows, so the experiment can detect a compiler regression.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from app import database


def _customer_id(con, value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        value = value.zfill(10)
    row = con.execute("SELECT KUNNR FROM KNA1 WHERE KUNNR=? OR NAME1=? OR SORTL=? LIMIT 1", (value, value, value)).fetchone()
    return row[0] if row else value


def _facts(item: dict, cutoff: str) -> list[dict]:
    companies = item.get("companies", ["1000", "2000"])
    currency = item.get("currency", "CNY")
    placeholders = ",".join("?" for _ in companies)
    params: list = ["800", *companies, currency, cutoff]
    customer = None
    with database.connection() as con:
        customer = _customer_id(con, item.get("customer"))
        sql = f"""
        SELECT b.KUNNR AS customer_id, b.BUKRS AS company_id,
               b.WRBTR - COALESCE((SELECT SUM(a.AMOUNT)
                 FROM ZAR_APPLICATION a
                 WHERE a.MANDT=b.MANDT AND a.BUKRS=b.BUKRS
                   AND a.INV_GJAHR=b.GJAHR AND a.INV_BELNR=b.BELNR AND a.INV_BUZEI=b.BUZEI
                   AND a.APPLIED_ON<=?),0) AS remaining,
               julianday(?) - julianday(b.ZFBDT, printf('+%d days',b.ZBD1T)) AS overdue_days,
               h.BUDAT AS posting_date
        FROM BSEG b JOIN BKPF h
          ON h.MANDT=b.MANDT AND h.BUKRS=b.BUKRS AND h.GJAHR=b.GJAHR AND h.BELNR=b.BELNR
        WHERE b.MANDT=? AND b.BUKRS IN ({placeholders}) AND h.WAERS=?
          AND h.BLART='DR' AND b.KOART='D' AND b.SHKZG='S' AND h.BUDAT<=?"""
        # The correlated subquery cutoff and the outer date cutoff are both the same value.
        bind = [cutoff, cutoff, "800", *companies, currency, cutoff]
        if customer:
            sql += " AND b.KUNNR=?"
            bind.append(customer)
        return [dict(row) for row in con.execute(sql, bind).fetchall()]


def _receipts(item: dict) -> list[dict]:
    companies = item.get("companies", ["1000", "2000"])
    placeholders = ",".join("?" for _ in companies)
    with database.connection() as con:
        sql = f"""
        SELECT b.BUKRS AS company_id, b.KUNNR AS customer_id, b.WRBTR AS amount,
               substr(h.BUDAT,1,7) AS month
        FROM BSEG b JOIN BKPF h
          ON h.MANDT=b.MANDT AND h.BUKRS=b.BUKRS AND h.GJAHR=b.GJAHR AND h.BELNR=b.BELNR
        WHERE b.MANDT='800' AND b.BUKRS IN ({placeholders}) AND h.WAERS=?
          AND h.BLART='DZ' AND b.KOART='D' AND b.SHKZG='H'
          AND h.BUDAT BETWEEN ? AND ?"""
        bind = [*companies, item.get("currency", "CNY"), item["start_date"], item["end_date"]]
        customer = _customer_id(con, item.get("customer"))
        if customer:
            sql += " AND b.KUNNR=?"
            bind.append(customer)
        return [dict(row) for row in con.execute(sql, bind).fetchall()]


def _bucket(days: float) -> str:
    if days <= 0:
        return "0 未到期"
    if days <= 30:
        return "1 逾期1–30天"
    if days <= 60:
        return "2 逾期31–60天"
    if days <= 90:
        return "3 逾期61–90天"
    return "4 逾期90天以上"


def expected(item: dict) -> dict | None:
    if item.get("category") != "answer":
        return None
    metric = item["expected_metric"]
    group_by = item["expected_group"]
    if metric == "receipts":
        rows = _receipts(item)
        grouped = defaultdict(int)
        for row in rows:
            key = {"total": "total", "month": row["month"], "customer": row["customer_id"], "company": row["company_id"]}[group_by]
            grouped[key] += row["amount"]
        return {"total_cents": sum(grouped.values()), "group_count": len(grouped), "metric": metric, "group_by": group_by}

    def snapshot(cutoff: str):
        rows = _facts(item, cutoff)
        if metric == "overdue_ar":
            threshold = item.get("overdue_days", 0)
            rows = [row for row in rows if row["overdue_days"] > threshold]
        grouped = defaultdict(int)
        for row in rows:
            key = "total" if group_by == "total" else row["customer_id"] if group_by == "customer" else row["company_id"] if group_by == "company" else _bucket(row["overdue_days"])
            grouped[key] += row["remaining"]
        return grouped

    current = snapshot(item["as_of"])
    if metric == "balance_change":
        previous = snapshot(item["compare_as_of"])
        keys = set(current) | set(previous)
        grouped = {key: current.get(key, 0) - previous.get(key, 0) for key in keys}
        return {"total_cents": sum(current.values()), "previous_cents": sum(previous.values()),
                "delta_cents": sum(grouped.values()), "group_count": len(grouped),
                "metric": metric, "group_by": group_by}
    else:
        grouped = current
    return {"total_cents": sum(grouped.values()), "group_count": len(grouped), "metric": metric, "group_by": group_by}
