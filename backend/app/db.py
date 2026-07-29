"""DuckDB 访问与 schema 自省。

所有查询一律以只读模式打开连接；写库只发生在 scripts/build_db.py。
"""
from __future__ import annotations

import re
import threading
from typing import Any

import duckdb

from . import config

_local = threading.local()

_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


def strip_line_comments(sql: str) -> str:
    """剥掉 -- 行注释（跳过单引号字符串内的伪注释）。

    行注释会把 LIMIT 包装层的闭括号吞掉（`... -- 注释` 与 `) AS _ic_sub` 同行），
    执行器与 run_readonly 包装前都先过一遍。
    """
    parts = re.split(r"('(?:[^'\\]|\\.|'')*')", sql)
    for i in range(0, len(parts), 2):  # 偶数段是引号外的 SQL
        parts[i] = _LINE_COMMENT_RE.sub("", parts[i])
    return "".join(parts)


def get_conn() -> duckdb.DuckDBPyConnection:
    """线程内复用的只读连接。"""
    con = getattr(_local, "con", None)
    if con is None:
        con = duckdb.connect(config.DB_PATH, read_only=True)
        _local.con = con
    return con


def schema_ddl() -> str:
    """导出全部表的 DDL 摘要，供 Text-to-SQL prompt 与校验器使用。"""
    con = get_conn()
    tables = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
    ]
    chunks: list[str] = []
    for t in tables:
        cols = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name=? ORDER BY ordinal_position",
            [t],
        ).fetchall()
        col_txt = ", ".join(f"{name} {dtype}" for name, dtype in cols)
        chunks.append(f"CREATE TABLE {t} ({col_txt});")
    return "\n".join(chunks)


def table_columns() -> dict[str, list[str]]:
    """{表名: [列名, ...]}，供静态校验器核对标识符合法性。"""
    con = get_conn()
    rows = con.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='main'"
    ).fetchall()
    out: dict[str, list[str]] = {}
    for t, c in rows:
        out.setdefault(t, []).append(c)
    return out


def run_readonly(sql: str, row_limit: int | None = None) -> tuple[list[str], list[tuple[Any, ...]]]:
    """在只读连接上执行查询，返回 (列名, 行)。行数超出上限会被截断。

    调用方必须保证 sql 已通过 validator 检查；此处再做一层连接级隔离兜底。
    """
    con = get_conn()
    limit = config.SQL_ROW_LIMIT if row_limit is None else row_limit
    wrapped = f"SELECT * FROM ({strip_line_comments(sql.strip().rstrip(';'))}) AS _ic_sub LIMIT {int(limit)}"
    cur = con.execute(wrapped)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()
