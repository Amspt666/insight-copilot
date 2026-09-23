'use strict';
const $ = id => document.getElementById(id);
let history = [], lastResult = null, busy = false;
const amount = cents => (cents / 100).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
const pretty = value => JSON.stringify(value, null, 2);
function node(tag, text, className) { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (className) item.className = className; return item; }
function message(role, text, isError = false) {
  const welcome = document.querySelector('.welcome'); if (welcome) welcome.remove();
  const item = node('div', undefined, `message ${role}${isError ? ' error' : ''}`);
  item.append(node('span', role === 'user' ? '你' : '问数', 'speaker'), node('span', text, 'body'));
  $('chat-log').append(item); $('chat-log').scrollTop = $('chat-log').scrollHeight;
}
function setBusy(value) {
  busy = value;
  document.querySelectorAll('#ask-form button, .suggestions button, #new-chat').forEach(b => b.disabled = value);
  $('send').textContent = value ? '查询中…' : '查询';
  $('result-state').textContent = value ? '正在处理，模型调用可能需要稍候' : lastResult ? '已生成结果' : '等待查询';
}
async function api(url, body) {
  const response = await fetch(url, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(x => `${x.loc.join('.')}: ${x.msg}`).join('；') : data.detail;
    throw new Error(data.message || detail || '请求失败，请稍后重试。');
  }
  return data;
}
function clearResult() {
  lastResult = null;
  $('result-content').hidden = true;
  $('empty-result').hidden = false;
}
function activateTab(name, focus = false) {
  for (const tab of document.querySelectorAll('[data-tab]')) {
    const selected = tab.dataset.tab === name;
    tab.classList.toggle('active', selected); tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $('panel-' + tab.dataset.tab).hidden = !selected;
    if (selected && focus) tab.focus();
  }
}
document.querySelectorAll('[data-tab]').forEach(tab => {
  tab.addEventListener('click', () => activateTab(tab.dataset.tab));
  tab.addEventListener('keydown', e => {
    const names = ['chart','table','evidence']; let index = names.indexOf(tab.dataset.tab);
    if (e.key === 'ArrowRight') index = (index + 1) % 3;
    else if (e.key === 'ArrowLeft') index = (index + 2) % 3;
    else if (e.key === 'Home') index = 0;
    else if (e.key === 'End') index = 2;
    else return;
    e.preventDefault(); activateTab(names[index], true);
  });
});
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b === button));
  $('workspace-view').hidden = button.dataset.view !== 'workspace'; $('catalog-view').hidden = button.dataset.view !== 'catalog';
}));
function render(result) {
  lastResult = result; $('empty-result').hidden = true; $('result-content').hidden = false;
  const p = result.plan, s = result.summary, change = p.metric === 'balance_change';
  const period = p.metric === 'receipts' ? `${p.start_date} 至 ${p.end_date}` : `截至 ${p.as_of}`;
  $('scope').textContent = `${period}  /  公司 ${p.companies.join('、')}  /  ${p.currency}  /  DeepSeek 自然语言查询`;
  $('total-label').textContent = change ? '所选范围余额净变化' : `${result.metric.name} · 全部匹配记录`;
  $('total-value').textContent = `${amount(change ? s.delta_cents : s.total_cents)} ${s.currency}`;
  $('comparison').hidden = !change;
  $('comparison').textContent = change ? `比较期 ${amount(s.previous_cents)}\n本期 ${amount(s.total_cents)}\n变化率 ${s.change_rate ?? '不定义（比较期为零）'}` : '';
  $('insights').replaceChildren();
  for (const statement of result.statements) {
    const line = node('div', undefined, 'insight');
    const citation = node('button', statement.evidence_id.split(':')[1], 'citation');
    citation.setAttribute('aria-label', '查看证据 ' + citation.textContent);
    citation.addEventListener('click', () => { activateTab('evidence'); const target = document.getElementById(statement.evidence_id); target?.scrollIntoView({block:'nearest'}); target?.focus(); });
    line.append(citation, node('span', statement.text)); $('insights').append(line);
  }
  $('warnings').replaceChildren(...result.warnings.map(text => node('p', text)));
  renderChart(result); renderTable(result); renderEvidence(result);
  $('trace').replaceChildren(...result.trace.map(stage => { const item = node('li', stage.stage); item.append(node('span', stage.detail)); return item; }));
  $('definition').textContent = result.metric.definition;
  $('plan-json').textContent = pretty(p); $('sql').textContent = result.sql; $('params').textContent = pretty(result.parameters);
  $('metadata').textContent = pretty(result.metadata); $('checks').textContent = pretty({execution:result.checks, grounding:result.grounding});
  activateTab('chart');
}
function renderChart(result) {
  const change = result.plan.metric === 'balance_change'; const rows = result.rows;
  $('chart').replaceChildren();
  const max = Math.max(1, ...rows.map(row => Math.abs(change ? row.delta_cents : row.amount_cents)));
  for (const row of rows) {
    const value = change ? row.delta_cents : row.amount_cents;
    const bar = node('div', undefined, 'bar-row'), label = node('span', row.label, 'bar-label'); label.title = row.label;
    const track = node('div', undefined, 'bar-track' + (change ? ' diverging' : ''));
    const fill = node('div', undefined, 'bar-fill' + (value < 0 ? ' negative' : ''));
    const width = Math.abs(value) / max * (change ? 50 : 100);
    fill.style.width = width + '%'; fill.style.left = (change ? value < 0 ? 50 - width : 50 : 0) + '%';
    track.append(fill); track.setAttribute('aria-hidden', 'true');
    bar.append(label, track, node('span', amount(value), 'bar-value')); $('chart').append(bar);
  }
  if (!rows.length) $('chart').append(node('p', '没有匹配记录，请调整筛选条件。', 'muted'));
  $('chart-note').textContent = `单位：${result.plan.currency} 元。显示 ${rows.length} / ${result.summary.group_count} 个分组。` + (change ? ' 蓝色为增加，橙色为减少。' : '');
}
function renderTable(result) {
  const change = result.plan.metric === 'balance_change';
  const headers = ['编号 / 分组','名称', ...(change ? ['比较期金额','本期金额','净变化'] : ['金额']), '币种'];
  const head = node('thead'), headRow = node('tr');
  headers.forEach((name, i) => {const cell = node('th', name, i >= 2 && i < headers.length-1 ? 'numeric' : ''); cell.scope='col'; headRow.append(cell);}); head.append(headRow);
  const body = node('tbody');
  result.rows.forEach(row => {
    const tr = node('tr'); const values = [row.dimension_id,row.label,...(change ? [amount(row.previous_cents),amount(row.amount_cents),amount(row.delta_cents)] : [amount(row.amount_cents)]),result.plan.currency];
    values.forEach((v,i) => tr.append(node('td',v,i >= 2 && i < values.length-1 ? 'numeric' : ''))); body.append(tr);
  });
  $('result-table').replaceChildren(head,body);
}
function renderEvidence(result) {
  $('evidence-list').replaceChildren();
  for (const evidence of result.evidence) {
    const card = node('article', undefined, 'evidence-item'); card.id = evidence.id; card.tabIndex = -1;
    card.append(node('strong', evidence.id), node('p', evidence.text));
    const detail = node('details'); detail.append(node('summary','来源、金额与适用范围'),node('pre',pretty({values:evidence.values, scope:evidence.scope, source:evidence.source})));
    card.append(detail); $('evidence-list').append(card);
  }
}
async function submitQuestion(question) {
  if (busy || !question.trim()) return;
  setBusy(true); message('user',question); $('question').value='';
  try {
    const result = await api('/api/ask',{question,history:history.slice(-12)});
    let answer;
    if (result.status === 'answered') { render(result); answer = result.statements.map(x=>x.text).join('\n'); }
    else answer = result.message;
    message('assistant',answer);
    history.push({role:'user',content:question},{role:'assistant',content: (answer + (result.plan ? '\n已执行计划：' + JSON.stringify(result.plan) : '')).slice(0,2000)});
    history=history.slice(-12);
    if (result.status !== 'answered') { $('result-content').hidden=true; $('empty-result').hidden=false; lastResult=null; }
  } catch(error) {clearResult();message('assistant',error.message,true);}
  finally {setBusy(false);}
}
$('ask-form').addEventListener('submit', e => {e.preventDefault();submitQuestion($('question').value.trim());});
$('question').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('ask-form').requestSubmit();}});
document.querySelectorAll('[data-question]').forEach(button=>button.addEventListener('click',()=>submitQuestion(button.dataset.question)));
$('new-chat').addEventListener('click',()=>{history=[];lastResult=null;$('chat-log').replaceChildren();message('assistant','已开始新对话，请输入指标和日期。');$('result-content').hidden=true;$('empty-result').hidden=false;$('result-state').textContent='等待查询';$('question').focus();});
function updateMetric() {
  const metric=$('metric').value;
  $('asof-field').hidden=metric==='receipts'; $('start-field').hidden=metric!=='receipts'; $('end-field').hidden=metric!=='receipts';
  $('compare-field').hidden=metric!=='balance_change';$('overdue-field').hidden=metric!=='overdue_ar';
  const options = metric==='aging' ? [['aging','账龄区间']] : [['customer','客户'],['total','合计'],['company','公司'],...(metric==='receipts'?[['month','月份']]:[])];
  $('group').replaceChildren(...options.map(([value,label])=>{const o=node('option',label);o.value=value;return o;}));
}
function download(name,text,type) {const url=URL.createObjectURL(new Blob([text],{type}));const link=node('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csvCell(value) {let s=String(value??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
$('export-csv').addEventListener('click',()=>{if(!lastResult)return;const r=lastResult;const rows=[['分组编号','名称','金额_元','比较金额_元','净变化_元','币种','当前日期或期间','比较截止日','公司范围'],...r.rows.map(x=>[x.dimension_id,x.label,(x.amount_cents/100).toFixed(2),(x.previous_cents/100).toFixed(2),r.plan.metric==='balance_change'?(x.delta_cents/100).toFixed(2):'',r.plan.currency,r.plan.as_of||`${r.plan.start_date}..${r.plan.end_date}`,r.plan.compare_as_of||'',r.plan.companies.join('|')])];download(`finance-${r.query_id}.csv`,'\uFEFF'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n'),'text/csv;charset=utf-8');});
$('export-json').addEventListener('click',()=>{if(lastResult)download(`evidence-${lastResult.query_id}.json`,pretty(lastResult),'application/json');});
function renderCatalog(catalog) {
  const content=$('catalog-content');content.replaceChildren();
  const metrics=node('section',undefined,'catalog-section');metrics.append(node('h2','已支持的业务指标'));
  Object.entries(catalog.metrics).forEach(([code,m])=>{const d=node('div',undefined,'metric-definition');d.append(node('strong',m.name),node('p',m.definition),node('span',`${code} · 常见表达：${m.synonyms.join('、')}`,'muted'));metrics.append(d);});
  const rules=node('section',undefined,'catalog-section');rules.append(node('h2','时间与计算约定'));const list=node('ul');catalog.conventions.forEach(text=>list.append(node('li',text)));rules.append(list);
  const tables=node('section',undefined,'catalog-section');tables.append(node('h2','SAP 风格字段目录'),node('p','采用常见 FI 字段命名。ZAR_APPLICATION 是自定义核销事件；金额按整数分存储。该模型不是完整 SAP S/4HANA 数据字典，也不是 HANA 连接器。'));
  Object.entries(catalog.tables).forEach(([code,table])=>{const d=node('details');d.append(node('summary',`${code} / ${table.name}`),node('p','主键：'+table.key.join(' + ')));const t=node('table');Object.entries(table.fields).forEach(([field,label])=>{const tr=node('tr');tr.append(node('td',field),node('td',label));t.append(tr);});d.append(t);tables.append(d);});
  content.append(metrics,rules,tables);
}
async function initialize() {
  const results=await Promise.allSettled([api('/api/health'),api('/api/catalog'),api('/api/customers')]);
  if(results[0].status==='fulfilled'){const h=results[0].value;$('connection').textContent=!h.database_ready?'数据尚未初始化':h.model_configured?`${h.model} 已配置 · 连接待调用确认`:'未配置有效模型密钥';}
  else $('connection').textContent='服务不可用，请检查启动终端';
  if(results[1].status==='fulfilled'){const c=results[1].value;renderCatalog(c);}
  else $('catalog-content').textContent='业务目录读取失败，请刷新页面。';
  if(results[2].status==='fulfilled')results[2].value.forEach(c=>{const o=node('option',c.KUNNR);o.value=c.NAME1;$('customers').append(o);});
  activateTab('chart');
}
initialize();

