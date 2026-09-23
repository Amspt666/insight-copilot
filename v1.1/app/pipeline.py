import time
import uuid

from . import database
from .compiler import compile_plan
from .evidence import build_evidence, grounded_insight
from .models import AskRequest, QueryPlan
from .planner import decide, normalize, PlanError
from .semantic import CATALOG, metadata_for


class Trace:
    def __init__(self):
        self.items = []

    def add(self, stage, detail, status='passed'):
        self.items.append({'stage': stage, 'status': status, 'detail': detail})


def run_plan(plan: QueryPlan, use_model=False, trace=None) -> dict:
    trace = trace or Trace()
    started = time.monotonic()
    plan = normalize(plan, database.customers())
    trace.add('业务语义与元数据', f'指标：{CATALOG["metrics"][plan.metric]["name"]}；按业务映射解析字段')
    trace.add('查询计划', '日期、指标维度、客户、公司范围校验完成')
    query = compile_plan(plan)
    trace.add('关联与 SQL 编译', '固定复合键关联，核销按发票行预聚合，过滤值参数化')
    rows, checks = database.execute(query, plan)
    trace.add('SQL 校验与执行', f'只读查询返回 {len(rows)} 个分组；{checks["elapsed_ms"]} ms')
    trace.add('结果校验', '整数分精度及未结金额非负检查完成；不将前 N 名之和作为总体')
    query_id = uuid.uuid4().hex[:12]
    evidence, summary = build_evidence(rows, plan, query_id)
    statements, grounding = grounded_insight(evidence, use_model)
    trace.add('解释与 Grounding', f'{grounding["checked_statements"]} 条表达绑定查询证据')
    warnings = ['演示时钟为 2026-07-01；所有数据为虚构。',
                f'口径：公司 {"、".join(plan.companies)}；{plan.currency} 凭证币；按过账日期；金额单位为元。']
    if summary['truncated']:
        warnings.append(f'共 {summary["group_count"]} 个分组，显示 {summary["shown_groups"]} 个；合计包含全部匹配分组。')
    if grounding['mode'] == 'deterministic_fallback':
        warnings.append('模型解释选择不可用，已使用可核验的程序生成解释。')
    if plan.metric == 'balance_change':
        warnings.append('余额变化为差额分解，不代表已确认业务原因。')
    for row in rows:
        row['delta_cents'] = row['amount_cents'] - row['previous_cents']
    return {'status': 'answered', 'mode': 'deepseek' if use_model else 'structured',
            'query_id': query_id, 'plan': plan.model_dump(mode='json'),
            'metric': CATALOG['metrics'][plan.metric], 'metadata': metadata_for(plan.metric),
            'sql': query.sql, 'parameters': query.params, 'rows': rows,
            'summary': summary, 'statements': statements, 'evidence': evidence,
            'checks': checks, 'grounding': grounding, 'warnings': warnings,
            'trace': trace.items, 'elapsed_ms': round((time.monotonic()-started)*1000)}


def ask(request: AskRequest) -> dict:
    trace = Trace()
    decision, context, repaired = decide(request)
    trace.add('意图识别与路由', f'{decision.action}；结构修正次数：{int(repaired)}')
    if decision.action == 'explain':
        metric = CATALOG['metrics'].get(decision.concept)
        if not metric:
            return {'status': 'clarify', 'message': '请选择应收余额、逾期应收、账龄、回款或余额变化。', 'trace': trace.items}
        return {'status': 'explain', 'message': metric['name'] + '：' + metric['definition'], 'trace': trace.items}
    if decision.action != 'query':
        return {'status': decision.action, 'message': decision.message, 'trace': trace.items}
    try:
        result = run_plan(decision.plan, use_model=True, trace=trace)
        result['retrieval'] = context['ranked_metrics']
        return result
    except PlanError as error:
        trace.add('查询计划', str(error), 'needs_input')
        return {'status': 'clarify', 'message': str(error), 'trace': trace.items}
