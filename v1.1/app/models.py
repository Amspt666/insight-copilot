from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class QueryPlan(StrictModel):
    metric: Literal['ar_balance', 'overdue_ar', 'aging', 'receipts', 'balance_change']
    group_by: Literal['total', 'customer', 'company', 'month', 'aging'] = 'total'
    as_of: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    compare_as_of: date | None = None
    companies: list[Literal['1000', '2000']] = Field(default_factory=list, max_length=2)
    currency: Literal['CNY', 'USD'] = 'CNY'
    customer: str | None = Field(default=None, max_length=80)
    overdue_days: int = Field(default=0, ge=0, le=3650)
    limit: int = Field(default=10, ge=1, le=50)
    order: Literal['desc', 'asc'] = 'desc'

    @model_validator(mode='after')
    def check_shape(self):
        if self.metric == 'receipts':
            if not self.start_date or not self.end_date or self.start_date > self.end_date:
                raise ValueError('回款需提供有序的 start_date / end_date')
            if self.as_of or self.compare_as_of or self.overdue_days:
                raise ValueError('回款不接受时点比较或逾期过滤')
        else:
            if not self.as_of:
                raise ValueError('余额和账龄需提供 as_of')
            if self.start_date or self.end_date:
                raise ValueError('时点指标不接受期间字段')
            if self.group_by == 'month':
                raise ValueError('月度维度仅支持回款')
        if self.metric == 'balance_change':
            if not self.compare_as_of or self.compare_as_of >= self.as_of:
                raise ValueError('余额比较需提供早于 as_of 的 compare_as_of')
        elif self.compare_as_of:
            raise ValueError('compare_as_of 仅用于 balance_change')
        if self.metric == 'aging' and self.group_by != 'aging':
            raise ValueError('账龄指标须按 aging 分组')
        if self.group_by == 'aging' and self.metric != 'aging':
            raise ValueError('aging 维度仅用于账龄指标')
        if self.overdue_days and self.metric != 'overdue_ar':
            raise ValueError('逾期天数只适用于 overdue_ar')
        return self


class Decision(StrictModel):
    action: Literal['query', 'clarify', 'unsupported', 'explain']
    message: str = Field(default='', max_length=600)
    concept: str | None = Field(default=None, max_length=40)
    plan: QueryPlan | None = None

    @model_validator(mode='after')
    def check_plan(self):
        if (self.action == 'query') != (self.plan is not None):
            raise ValueError('query 必须有 plan，其他 action 不接受 plan')
        if self.action in ('clarify', 'unsupported') and not self.message:
            raise ValueError('请提供需要澄清或不支持的原因')
        return self


class Turn(StrictModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=2000)


class AskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=1200)
    history: list[Turn] = Field(default_factory=list, max_length=12)


class EvidenceSelection(StrictModel):
    evidence_ids: list[str] = Field(min_length=1, max_length=5)
