from decimal import Decimal, ROUND_HALF_UP

from .models import QueryPlan, EvidenceSelection
from .llm import chat_json, ModelError
from .semantic import CATALOG


def money(cents: int) -> str:
    return format(Decimal(cents) / 100, ',.2f')


def rate(current: int, previous: int) -> str | None:
    if not previous:
        return None
    return str((Decimal(current-previous) * 100 / Decimal(previous)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) + '%'


def build_evidence(rows: list[dict], plan: QueryPlan, query_id: str) -> tuple[list[dict], dict]:
    total = rows[0]['full_total_cents'] if rows else 0
    prior = rows[0]['full_previous_cents'] if rows else 0
    groups = rows[0]['group_count'] if rows else 0
    scope = {'companies': plan.companies, 'currency': plan.currency, 'customer': plan.customer,
             'as_of': str(plan.as_of) if plan.as_of else None,
             'start_date': str(plan.start_date) if plan.start_date else None,
             'end_date': str(plan.end_date) if plan.end_date else None,
             'compare_as_of': str(plan.compare_as_of) if plan.compare_as_of else None}
    metric_name = CATALOG['metrics'][plan.metric]['name']
    period = f'{plan.start_date} 至 {plan.end_date}' if plan.metric == 'receipts' else f'截至 {plan.as_of}'
    if plan.metric == 'overdue_ar':
        metric_name = f'逾期超过 {plan.overdue_days} 天的应收'
    evidence = []

    def add(text, values, source):
        evidence.append({'id': f'{query_id}:E{len(evidence)+1}', 'text': text,
                         'values': values, 'scope': scope, 'source': source})

    if plan.metric == 'balance_change':
        add(f'所选范围应收余额从 {plan.compare_as_of} 的 {money(prior)} {plan.currency}，变为 {plan.as_of} 的 {money(total)} {plan.currency}；净变化 {money(total-prior)} {plan.currency}。',
            {'current_cents': total, 'previous_cents': prior, 'delta_cents': total-prior},
            {'result': 'window totals over all matching groups', 'formula': 'current - previous'})
        percentage = rate(total, prior)
        add(f'余额变化率为 {percentage}。' if percentage is not None else '比较期余额为零，变化率不定义。',
            {'rate': percentage, 'current_cents': total, 'previous_cents': prior},
            {'result': 'window totals', 'formula': '(current - previous) / previous * 100; zero => null'})
    else:
        add(f'{period}，所选范围{metric_name}合计 {money(total)} {plan.currency}。',
            {'amount_cents': total}, {'result': 'full_total_cents over all matching groups; empty => 0'})
    if plan.group_by != 'total':
        for index, row in enumerate(rows[:5]):
            label = row['label']
            if plan.group_by == 'aging':
                label = label[2:]
            if plan.metric == 'balance_change':
                sentence = f'{label}的应收余额净变化 {money(row["amount_cents"]-row["previous_cents"])} {plan.currency}。'
            else:
                sentence = f'{label}：{money(row["amount_cents"])} {plan.currency}。'
            add(sentence, {'amount_cents': row['amount_cents'], 'previous_cents': row['previous_cents'], 'dimension_id': row['dimension_id']},
                {'row': index, 'columns': ['dimension_id', 'label', 'amount_cents', 'previous_cents']})
    if not rows or (plan.group_by == 'total' and rows[0]['source_items'] == 0):
        add('该范围没有匹配的业务记录；零值不代表数据范围以外没有业务。', {'matched_rows': 0}, {'result': 'empty set or source_items=0'})
    summary = {'total_cents': total, 'previous_cents': prior,
               'delta_cents': total-prior if plan.metric == 'balance_change' else None,
               'change_rate': rate(total, prior) if plan.metric == 'balance_change' else None,
               'currency': plan.currency, 'group_count': groups, 'shown_groups': len(rows),
               'truncated': groups > len(rows), 'total_formatted': money(total),
               'previous_formatted': money(prior), 'delta_formatted': money(total-prior)}
    return evidence, summary


def grounded_insight(evidence: list[dict], use_model: bool) -> tuple[list[dict], dict]:
    """The model may select facts, but cannot insert numbers or causal assertions."""
    selected = [e['id'] for e in evidence[:5]]
    mode = 'deterministic'
    if use_model:
        try:
            selection = EvidenceSelection.model_validate(chat_json([
                {'role': 'system', 'content': '你是财务分析编辑。只从给定证据中选择最有用的最多5条，输出 {"evidence_ids":["id"]}。首条必须是给定第一条总体证据。不得输出新文字或新ID。'},
                {'role': 'user', 'content': __import__('json').dumps(evidence, ensure_ascii=False)},
            ], max_tokens=600))
            known = {e['id'] for e in evidence}
            if any(key not in known for key in selection.evidence_ids):
                raise ValueError('unknown evidence')
            selected = list(dict.fromkeys([evidence[0]['id'], *selection.evidence_ids]))[:5]
            mode = 'deepseek_selected_verified_evidence'
        except (ModelError, ValueError):
            mode = 'deterministic_fallback'
    mapping = {e['id']: e for e in evidence}
    statements = [{'text': mapping[key]['text'], 'evidence_id': key} for key in selected]
    return statements, {'passed': True, 'method': 'evidence-bound rendering', 'mode': mode,
                        'checked_statements': len(statements),
                        'scope': '数值、维度、时间和表达来自确定性证据；不证明用户意图识别一定正确。'}
