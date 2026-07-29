"""数字溯源校验器（可信闭环第三层）。

大模型写“解读”时最常见的幻觉不是 SQL 错，而是**文字里的数字对不上结果表**。
本模块把洞察文本中的每个数字抽取出来，与查询结果集做可溯源核验：
命中（允许四舍五入与容差）→ 保留；未命中 → 标记/剔除，并计入忠实度指标。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# 支持 12,345.67 / 12.3% / 约 4.09 / 2018年 等写法
_NUM_RE = re.compile(
    r"(?<![\w.])(?:约|~)?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(%|％|万|亿)?(?![\w%])"
)


@dataclass
class NumberClaim:
    raw: str            # 原文片段
    value: float        # 归一化后的数值（百分数已除 100，万/亿已展开）
    supported: bool
    nearest: float | None = None  # 结果集中最接近的值（供人工排查）
    span: tuple[int, int] = (0, 0)  # 在原文中的位置（剔除时按区间替换，避免误伤）


@dataclass
class GroundingReport:
    total: int
    supported: int
    claims: list[NumberClaim] = field(default_factory=list)

    @property
    def faithfulness(self) -> float:
        return self.supported / self.total if self.total else 1.0

    @property
    def unsupported_raws(self) -> list[str]:
        return [c.raw for c in self.claims if not c.supported]


def _normalize(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    if unit in ("%", "％"):
        return v / 100.0
    if unit == "万":
        return v * 1e4
    if unit == "亿":
        return v * 1e8
    return v


def _candidate_values(rows: list[tuple[Any, ...]]) -> list[float]:
    """结果集中的全部可引用数值：
    - 数值单元格（比例同时提供 0.41 / 41 两种尺度）
    - 日期/日期字符串单元格拆出的年、月、日（“4 月最高”属合法引用）
    - 结果行数
    """
    import datetime

    vals: set[float] = set()

    def _add_date_parts(d: datetime.date) -> None:
        vals.update({float(d.year), float(d.month), float(d.day)})

    for row in rows:
        nums_in_row = [float(c) for c in row if isinstance(c, (int, float)) and not isinstance(c, bool)]
        # 同行两两差值/和值：支持“第一名领先 2.16 天”这类行内派生表述
        for i in range(len(nums_in_row)):
            for j in range(i + 1, len(nums_in_row)):
                vals.add(abs(nums_in_row[i] - nums_in_row[j]))
                vals.add(nums_in_row[i] + nums_in_row[j])
        for cell in row:
            if isinstance(cell, bool):
                continue
            if isinstance(cell, (int, float)):
                vals.add(float(cell))
                if 0.0 <= float(cell) <= 1.0:      # 比例 ↔ 百分数双尺度
                    vals.add(float(cell) * 100.0)
                elif 0.0 <= float(cell) <= 100.0:
                    vals.add(float(cell) / 100.0)
            elif isinstance(cell, (datetime.date, datetime.datetime)):
                _add_date_parts(cell)
            elif isinstance(cell, str):
                m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", cell)
                if m:
                    vals.update({float(m.group(1)), float(m.group(2)), float(m.group(3))})
    vals.add(float(len(rows)))                      # 行数也视为可引用
    return sorted(vals)


def check(
    text: str,
    rows: list[tuple[Any, ...]],
    *,
    extra_whitelist: list[float] | None = None,
    rel_tol: float = 0.01,
    abs_tol: float = 0.005,
) -> GroundingReport:
    """核验文本中的数字是否都能追溯到结果集。

    容差规则：相对误差 ≤1% 或绝对误差 ≤0.005（兼容四舍五入到两位小数）。
    """
    candidates = _candidate_values(rows)
    if extra_whitelist:
        candidates = sorted(set(candidates) | set(extra_whitelist))
    claims: list[NumberClaim] = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(0)
        try:
            v = _normalize(m.group(1), m.group(2))
        except ValueError:
            continue
        nearest, ok = None, False
        for c in candidates:
            if abs(c - v) <= max(abs_tol, abs(c) * rel_tol):
                ok, nearest = True, c
                break
            if nearest is None or abs(c - v) < abs(nearest - v):
                nearest = c
        claims.append(NumberClaim(raw=raw, value=v, supported=ok, nearest=nearest,
                                  span=(m.start(), m.end())))
    return GroundingReport(
        total=len(claims),
        supported=sum(1 for c in claims if c.supported),
        claims=claims,
    )


def redact_unsupported(text: str, report: GroundingReport) -> str:
    """把未溯源的数字替换为显式标记，绝不让可疑数字静默流出。
    按位置区间从后往前替换，避免误伤同内容片段（如 "2018" 中的 "1"）。"""
    out = text
    for c in sorted((c for c in report.claims if not c.supported),
                    key=lambda x: x.span[0], reverse=True):
        s, e = c.span
        out = out[:s] + f"[未溯源:{c.raw}]" + out[e:]
    return out
