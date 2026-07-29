"""SQL 沙箱执行器（可信闭环第二层的第二道闸）。

三道隔离：
1. 连接级：只读模式打开 DuckDB，物理上无法写库
2. 语句级：执行前必须已过 validator（此处再强制校验一次，双保险）
3. 资源级：独立线程执行 + 超时 interrupt + 结果行数截断
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import duckdb

from . import config, validator
from .db import strip_line_comments


@dataclass
class ExecutionResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    error: str = ""
    truncated: bool = False

    def __bool__(self) -> bool:
        return self.ok


def execute(sql: str, row_limit: int | None = None, timeout_s: float | None = None) -> ExecutionResult:
    # 双保险：未通过静态校验的 SQL 不允许进入执行阶段
    v = validator.validate(sql)
    if not v.ok:
        return ExecutionResult(False, error="静态校验未通过：" + "；".join(v.errors))

    limit = config.SQL_ROW_LIMIT if row_limit is None else row_limit
    timeout = config.SQL_TIMEOUT_S if timeout_s is None else timeout_s
    # 每次执行开独立只读连接，避免污染会话状态
    con = duckdb.connect(config.DB_PATH, read_only=True)
    result = ExecutionResult(False)
    done = threading.Event()

    def _run() -> None:
        try:
            inner = strip_line_comments(sql.strip().rstrip(";"))
            wrapped = f"SELECT * FROM ({inner}) AS _ic_sub LIMIT {int(limit) + 1}"
            cur = con.execute(wrapped)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            result.columns = cols
            if len(rows) > limit:
                result.rows = rows[:limit]
                result.truncated = True
            else:
                result.rows = rows
            result.ok = True
        except Exception as e:  # DuckDB 错误信息对自我修正很有价值，原样保留
            result.error = str(e)[:500]
        finally:
            done.set()
            # 连接由工作线程自行关闭：主线程在超时路径上不再跨线程 close
            # （活跃查询期间跨线程 close 行为未定义，可能抛错或崩溃）
            try:
                con.close()
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    if not done.wait(timeout):
        con.interrupt()
        # interrupt 后再等一个短窗口让查询干净收尾；仍不结束就直接返回超时结果，
        # 悬挂的 daemon 线程会在查询结束后自行关闭连接并退出
        done.wait(min(5.0, timeout))
        result.error = f"执行超时（>{timeout}s），已中断"
    return result
