"""SQL 静态校验器（可信闭环第二层的第一道闸）。

在执行前拦截四类问题：
1. 语法错误（按 DuckDB 方言解析）
2. 非只读语句（INSERT/UPDATE/DELETE/DDL/ATTACH/PRAGMA 等一律拒绝）
3. 幻觉表 / 幻觉列（标识符必须存在于真实 schema）
4. 危险函数（read_csv/read_parquet/INSTALL/LOAD 等可触达文件系统或扩展的能力）
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from . import db

DIALECT = "duckdb"

# 文件/网络/扩展类危险能力：按谓词规则拒绝（前缀/子串），而非逐一枚举函数名。
# 教训：纯枚举黑名单曾被 read_json_objects / parquet_schema / csv_metadata 等
# 同族变体绕过；httpfs 是扩展名而非函数名，属无效条目，已删除。
_EXPLICIT_DENIED = {
    "sqlitescan", "postgrescan", "mysqlscan", "jsonscan", "stread", "streadosm",
    "install", "load", "exportdatabase", "importdatabase", "glob",
    "query", "querytable",
}


def _is_denied_function(name: str) -> bool:
    """归一化（小写、去下划线）后按谓词规则判定。函数名与节点类名都过此闸。"""
    n = name.lower().replace("_", "")
    if not n:
        return False
    return (
        n in _EXPLICIT_DENIED
        or n.startswith(("read", "parquet", "csv", "sniff"))
        or "metadata" in n
        or n.endswith("schema")
    )

# 允许出现的顶层语句
ALLOWED_STATEMENTS = (exp.Select, exp.Union, exp.With, exp.Subquery)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # 便于 if result:
        return self.ok


def _check_single_select(tree: exp.Expression) -> list[str]:
    errors: list[str] = []
    # 顶层必须是查询
    root = tree
    if isinstance(root, exp.With):
        root = root.this
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        errors.append(f"只允许只读 SELECT 查询，检测到：{tree.key.upper() if hasattr(tree, 'key') else type(tree).__name__}")
        return errors
    # 全树扫描：禁止任何写操作/管理命令节点（按 sqlglot 版本实际存在的节点名动态取用）
    banned_names = (
        "Insert", "Update", "Delete", "Merge", "Drop", "Create",
        "Alter", "TruncateTable", "Attach", "Detach", "Copy",
        "Pragma", "Set", "Use", "Grant", "Commit", "Rollback",
        "Vacuum", "Describe", "Kill", "LoadData", "Transaction",
    )
    banned = tuple(
        t for t in (getattr(exp, n, None) for n in banned_names) if t is not None
    )
    for node in tree.walk():
        if isinstance(node, banned):
            errors.append(f"检测到禁止的语句类型：{type(node).__name__}")
    return errors


def _select_output_names(node: exp.Expression) -> set[str] | None:
    """SELECT/UNION 的输出列名集合；含 * 无法静态确定时返回 None（回退扁平白名单）。"""
    while isinstance(node, (exp.Union, exp.Subquery)):  # UNION 取左支输出名
        node = node.this
    if not isinstance(node, exp.Select):
        return None
    names: set[str] = set()
    for e in node.expressions:
        if isinstance(e, exp.Star) or (isinstance(e, exp.Column) and e.is_star):
            return None
        if isinstance(e, exp.Alias):
            if e.alias:
                names.add(e.alias.lower())
        elif isinstance(e, exp.Column):
            names.add(e.name.lower())
    return names


def _check_identifiers(tree: exp.Expression, schema: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    schema_l = {t.lower(): {c.lower() for c in cols} for t, cols in schema.items()}

    # ---- 表：FROM 中的表值函数一律拒绝（range/duckdb_tables 等可绕过表名白名单） ----
    used_tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        if isinstance(table.this, exp.Func):
            errors.append(f"禁止 FROM 中的表值函数：{table.sql(dialect=DIALECT)[:80]}")
            continue
        name = table.name.lower()
        # CTE 名不在 schema 中，收集后放行
        used_tables.add(name)
    cte_names = {c.alias.lower() for c in tree.find_all(exp.CTE) if c.alias}
    for name in sorted(used_tables):
        if name and name not in schema_l and name not in cte_names:
            errors.append(f"表不存在（疑似幻觉表）：{name}")

    # ---- 别名 → 可用列集合（真实表 / CTE 输出列 / FROM 派生子查询输出列） ----
    alias_cols: dict[str, set[str]] = {}
    for table in tree.find_all(exp.Table):
        tname = table.name.lower()
        key = (table.alias_or_name or "").lower()
        if key and tname in schema_l:
            alias_cols[key] = schema_l[tname]
    for cte in tree.find_all(exp.CTE):
        key = cte.alias.lower()
        if not key:
            continue
        alias_expr = cte.args.get("alias")  # exp.TableAlias，可带显式列清单 t(a,b)
        explicit = alias_expr.args.get("columns") if alias_expr else None
        if explicit:
            alias_cols[key] = {c.name.lower() for c in explicit}
        else:
            cols = _select_output_names(cte.this)
            if cols:
                alias_cols[key] = cols
    for sq in tree.find_all(exp.Subquery):
        key = (sq.alias or "").lower()
        if key and isinstance(sq.this, (exp.Select, exp.Union)):
            cols = _select_output_names(sq.this)
            if cols:
                alias_cols[key] = cols

    # ---- 列：限定列（t.c）必须属于该表/别名；非限定列走扁平白名单 ----
    known_cols: set[str] = set()
    for cols in schema_l.values():
        known_cols.update(cols)
    known_cols |= {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    for col in tree.find_all(exp.Column):
        cname = col.name.lower()
        if not cname or cname == "*":
            continue
        qualifier = (col.table or "").lower()
        if qualifier and qualifier in alias_cols:
            if cname not in alias_cols[qualifier]:
                errors.append(
                    f"列 {col.sql(dialect=DIALECT)} 不存在于 {qualifier} 对应的表中（疑似幻觉列）")
            continue
        if cname not in known_cols:
            errors.append(f"列不存在（疑似幻觉列）：{col.sql(dialect=DIALECT)}")
    return errors


def _check_functions(tree: exp.Expression) -> list[str]:
    errors: list[str] = []
    for func in tree.find_all(exp.Func):
        # 函数名可能藏在 .name（Anonymous），也可能体现为专用类名（ReadParquet）
        candidates = {
            getattr(func, "name", "") or "",
            type(func).__name__,
        }
        if any(_is_denied_function(c) for c in candidates):
            errors.append(f"检测到危险函数：{func.sql(dialect=DIALECT)[:80]}")
    return errors


def validate(sql: str) -> ValidationResult:
    """对单条 SQL 做静态校验；返回结构化结果供自我修正使用。"""
    errors: list[str] = []
    sql_clean = sql.strip().rstrip(";")
    if not sql_clean:
        return ValidationResult(False, ["SQL 为空"])
    try:
        statements = sqlglot.parse(sql_clean, read=DIALECT)
    except Exception as e:
        return ValidationResult(False, [f"语法解析失败：{e}"])
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return ValidationResult(False, ["只允许单条语句"])
    tree = statements[0]
    errors += _check_single_select(tree)
    errors += _check_identifiers(tree, db.table_columns())
    errors += _check_functions(tree)
    return ValidationResult(not errors, errors)
