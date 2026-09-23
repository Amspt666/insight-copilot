from contextlib import contextmanager
import sqlite3
import time

import sqlglot
from sqlglot import exp

from . import config
from .compiler import CompiledQuery, compile_plan
from .models import QueryPlan
from .quality import ledger_checks
from .semantic import CATALOG


class DataError(RuntimeError):
    pass


@contextmanager
def connection():
    if not config.DB_PATH.exists():
        raise DataError('尚未生成数据，请在 v1.1 目录执行 python scripts/generate_data.py。')
    con = sqlite3.connect(config.DB_PATH.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    try:
        yield con
    finally:
        con.close()


def customers() -> list[dict]:
    marks = ','.join('?' for _ in config.ALLOWED_COMPANIES)
    with connection() as con:
        return [dict(row) for row in con.execute(f'''SELECT DISTINCT k.KUNNR,k.NAME1,k.SORTL
        FROM KNA1 k JOIN KNB1 b ON k.MANDT=b.MANDT AND k.KUNNR=b.KUNNR
        WHERE k.MANDT='800' AND b.BUKRS IN ({marks}) ORDER BY k.KUNNR''', config.ALLOWED_COMPANIES)]


def validate(query: CompiledQuery, plan: QueryPlan) -> dict:
    if query != compile_plan(plan):
        raise DataError('查询与已批准计划不一致。')
    if not plan.companies or any(c not in config.ALLOWED_COMPANIES for c in plan.companies):
        raise DataError('查询缺少有效公司范围。')
    try:
        trees = sqlglot.parse(query.sql, read='sqlite')
    except sqlglot.errors.ParseError:
        raise DataError('SQL 解析失败，查询未执行。') from None
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise DataError('仅允许单条只读 SELECT。')
    tree = trees[0]
    ctes = {node.alias_or_name.lower() for node in tree.find_all(exp.CTE)}
    allowed = {name.lower() for name in CATALOG['tables']}
    for table in tree.find_all(exp.Table):
        if table.db or table.catalog or table.name.lower() not in allowed | ctes:
            raise DataError('查询包含未授权表。')
    return {'single_select': True, 'registered_tables': True,
            'compiler_match': True, 'company_scope': list(plan.companies),
            'join_policy': '固定复合键；核销先聚合后关联', 'parameters_bound': True}


def execute(query: CompiledQuery, plan: QueryPlan) -> tuple[list[dict], dict]:
    checks = validate(query, plan)
    allowed_tables = {name.lower() for name in CATALOG['tables']}
    functions = {'sum','coalesce','count','substr','julianday','printf','typeof'}

    def authorize(action, arg1, arg2, db, trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and arg1.lower() in allowed_tables:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or arg1 or '').lower() in functions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    started = time.monotonic()
    try:
        with connection() as con:
            con.set_authorizer(authorize)
            con.set_progress_handler(lambda: int(time.monotonic()-started > config.SQL_TIMEOUT), 1000)
            quality = ledger_checks(con, query.params)
            if any(quality.values()):
                raise DataError('账套一致性检查未通过（借贷平衡、核销分配或核销关联），已停止查询。')
            explain = con.execute('EXPLAIN QUERY PLAN ' + query.sql, query.params).fetchall()
            rows = [dict(row) for row in con.execute(query.sql, query.params).fetchmany(51)]
    except sqlite3.Error:
        raise DataError('数据库拒绝了查询或执行超时；请检查数据文件及服务端日志配置。') from None
    if len(rows) > 50:
        raise DataError('结果超出行数预算。')
    if any(row['invalid_items'] for row in rows):
        raise DataError('核销金额超过发票金额，数据检查未通过，已停止生成业务解释。')
    if any(not isinstance(row['amount_cents'], int) or not isinstance(row['previous_cents'], int) for row in rows):
        raise DataError('金额精度检查未通过；数据库金额必须为整数分。')
    checks.update({'schema_prepared': True, 'read_only': True, 'amount_type': 'integer cents', 'ledger_quality': quality,
                   'nonnegative_open_items': True, 'elapsed_ms': round((time.monotonic()-started)*1000),
                   'query_plan': [dict(row) for row in explain]})
    return rows, checks
