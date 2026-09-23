from dataclasses import dataclass

from .models import QueryPlan


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: dict


def compile_plan(plan: QueryPlan) -> CompiledQuery:
    """Only fixed SQL fragments are composed; business values are bound parameters."""
    params = {'currency': plan.currency, 'limit': plan.limit,
              **{f'company{i}': code for i, code in enumerate(plan.companies)}}
    placeholders = ','.join(f':company{i}' for i in range(len(plan.companies)))
    scope = f"b.MANDT='800' AND b.KOART='D' AND b.BUKRS IN ({placeholders}) AND h.WAERS=:currency"
    if plan.customer:
        scope += ' AND b.KUNNR=:customer'
        params['customer'] = plan.customer
    joins = '''JOIN BKPF h ON b.MANDT=h.MANDT AND b.BUKRS=h.BUKRS AND b.GJAHR=h.GJAHR AND b.BELNR=h.BELNR
 JOIN KNA1 k ON b.MANDT=k.MANDT AND b.KUNNR=k.KUNNR
 JOIN T001 c ON b.MANDT=c.MANDT AND b.BUKRS=c.BUKRS'''
    if plan.metric == 'receipts':
        params.update(start=plan.start_date.isoformat(), end=plan.end_date.isoformat())
        ctes = f'''WITH facts AS (
 SELECT b.KUNNR AS customer_id,k.NAME1 AS customer_name,b.BUKRS AS company_id,c.BUTXT AS company_name,
 substr(h.BUDAT,1,7) AS month, b.WRBTR AS amount, 0 AS previous
 FROM BSEG b {joins}
 WHERE {scope} AND h.BLART='DZ' AND b.SHKZG='H' AND h.BUDAT BETWEEN :start AND :end
 )'''
    else:
        params['as_of'] = plan.as_of.isoformat()
        snapshots = "SELECT 'current' AS slot, :as_of AS cutoff"
        if plan.metric == 'balance_change':
            snapshots += " UNION ALL SELECT 'previous', :compare_as_of"
            params['compare_as_of'] = plan.compare_as_of.isoformat()
        condition = ''
        if plan.metric == 'overdue_ar':
            condition = ' AND julianday(s.cutoff)-julianday(b.ZFBDT, printf(\'+%d days\',b.ZBD1T))>:overdue_days'
            params['overdue_days'] = plan.overdue_days
        ctes = f'''WITH snapshots AS ({snapshots}), applied AS (
 SELECT s.slot,a.MANDT,a.BUKRS,a.INV_GJAHR,a.INV_BELNR,a.INV_BUZEI,SUM(a.AMOUNT) AS allocated
 FROM ZAR_APPLICATION a JOIN snapshots s ON a.APPLIED_ON<=s.cutoff
 GROUP BY s.slot,a.MANDT,a.BUKRS,a.INV_GJAHR,a.INV_BELNR,a.INV_BUZEI
 ), open_items AS (
 SELECT s.slot,b.KUNNR AS customer_id,k.NAME1 AS customer_name,b.BUKRS AS company_id,c.BUTXT AS company_name,
 b.WRBTR-COALESCE(a.allocated,0) AS remaining,
 julianday(s.cutoff)-julianday(b.ZFBDT,printf('+%d days',b.ZBD1T)) AS days_overdue
 FROM BSEG b {joins}
 JOIN snapshots s ON h.BUDAT<=s.cutoff
 LEFT JOIN applied a ON a.slot=s.slot AND a.MANDT=b.MANDT AND a.BUKRS=b.BUKRS
 AND a.INV_GJAHR=b.GJAHR AND a.INV_BELNR=b.BELNR AND a.INV_BUZEI=b.BUZEI
 WHERE {scope} AND h.BLART='DR' AND b.SHKZG='S'{condition}
 ), facts AS (
 SELECT customer_id,customer_name,company_id,company_name,
 CASE WHEN days_overdue<=0 THEN '0 未到期' WHEN days_overdue<=30 THEN '1 逾期1–30天'
 WHEN days_overdue<=60 THEN '2 逾期31–60天' WHEN days_overdue<=90 THEN '3 逾期61–90天' ELSE '4 逾期90天以上' END AS aging,
 CASE WHEN slot='current' THEN remaining ELSE 0 END AS amount,
 CASE WHEN slot='previous' THEN remaining ELSE 0 END AS previous
 FROM open_items
 )'''
    dimension, label = {
        'total': ("'total'", "'全部匹配记录'"),
        'customer': ('customer_id', 'customer_name'),
        'company': ('company_id', 'company_name'),
        'month': ('month', 'month'),
        'aging': ('aging', 'aging'),
    }[plan.group_by]
    group = '' if plan.group_by == 'total' else f'GROUP BY {dimension},{label}'
    # Do not discard negative remaining values: validation must detect corruption.
    ctes += f''', grouped AS (
 SELECT {dimension} AS dimension_id, {label} AS label,
 COALESCE(SUM(amount),0) AS amount_cents, COALESCE(SUM(previous),0) AS previous_cents,
 COALESCE(SUM(CASE WHEN amount<0 OR previous<0 THEN 1 ELSE 0 END),0) AS invalid_items,
 COUNT(*) AS source_items
 FROM facts {group}
 )'''
    order_value = 'amount_cents-previous_cents' if plan.metric == 'balance_change' else 'amount_cents'
    direction = 'DESC' if plan.order == 'desc' else 'ASC'
    order = 'dimension_id ASC' if plan.group_by in ('month','aging') else f'{order_value} {direction},dimension_id ASC'
    sql = ctes + f'''
 SELECT dimension_id,label,amount_cents,previous_cents,source_items,
 SUM(amount_cents) OVER () AS full_total_cents,
 SUM(previous_cents) OVER () AS full_previous_cents,
 SUM(invalid_items) OVER () AS invalid_items,
 COUNT(*) OVER () AS group_count
 FROM grouped ORDER BY {order} LIMIT :limit'''
    return CompiledQuery(sql=sql, params=params)
