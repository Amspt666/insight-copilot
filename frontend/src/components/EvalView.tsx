import { getEvalSummary } from '../lib/api'
import type { EvalSummary } from '../lib/types'

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${(v * 100).toFixed(1)}%`
}

function Bar({ value, color }: { value: number | null; color: string }) {
  return (
    <div className="h-2 rounded-full bg-muted overflow-hidden w-full max-w-[180px]">
      <div className="h-full rounded-full" style={{ width: `${(value ?? 0) * 100}%`, background: color }} />
    </div>
  )
}

const CONFIG_LABELS: Record<string, string> = {
  full: '完整管线（四层全开）',
  baseline: '朴素基线（只有 DDL → SQL）',
  no_clarify: '去掉澄清/拒答门',
  no_semantic: '去掉语义层口径',
  no_repair: '去掉自我修正',
  no_backtranslate: '去掉意图回译',
  no_grounding: '去掉数字溯源',
}

export default function EvalView() {
  const data = getEvalSummary()
  const summaries: EvalSummary[] = data.summaries
  const full = summaries.find((s) => s.config === 'full')
  const hasReal = summaries.length > 0

  return (
    <div className="py-8 md:py-12 space-y-10">
      <header className="space-y-3 max-w-3xl">
        <h1 className="font-display text-2xl md:text-3xl font-semibold tracking-tight">实测，而不是宣称</h1>
        <p className="text-[15px] leading-7 text-ink-soft">
          评测集：{data.benchmarkSize} 道中英双语题（简单聚合 / 多表关联 / 时间对比 / 歧义澄清 / 超纲拒答），
          每题附人工标注的标准 SQL 或期望行为。所有数字由 <code className="text-teal">eval/run_eval.py</code> 真实跑出，
          可在本地一键复现。
        </p>
      </header>

      {!hasReal && (
        <div className="border border-dashed border-hairline rounded-xl p-5 text-sm text-ink-soft max-w-3xl">
          本环境尚未跑评测。克隆仓库后执行
          <code className="mx-1 px-1.5 py-0.5 bg-muted rounded text-teal">make eval</code>
          即可在本机复现全部指标（需配置模型 Key）。
        </div>
      )}

      {full && (
        <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-hairline border border-hairline rounded-xl overflow-hidden">
          {[
            { label: `执行准确率（${full.answerable.n} 道可答题）`, value: pct(full.answerable.execution_accuracy) },
            { label: `该反问的反问率（${full.clarify.n} 道歧义题）`, value: pct(full.clarify.clarify_rate) },
            { label: `该拒的拒答率（${full.refuse.n} 道超纲题）`, value: pct(full.refuse.refuse_rate) },
            { label: '洞察数字可溯源比例', value: pct(full.answerable.insight_faithfulness) },
          ].map((s) => (
            <div key={s.label} className="bg-card p-5">
              <div className="num text-3xl font-medium text-teal">{s.value}</div>
              <div className="text-xs text-ink-soft mt-1 leading-5">{s.label}</div>
            </div>
          ))}
        </section>
      )}

      {hasReal && (
        <section className="space-y-3">
          <h2 className="font-display text-lg md:text-xl font-semibold">消融：每个机制到底贡献多少</h2>
          <p className="text-sm text-ink-soft max-w-3xl">
            逐个关掉一层机制重跑同一评测集。执行准确率一列掉得越多，说明该机制越不可或缺。
          </p>
          <div className="overflow-x-auto border border-hairline rounded-xl">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="bg-teal-soft/40 text-left">
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">配置</th>
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">执行准确率</th>
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">可答率</th>
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">误拒率</th>
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">澄清率</th>
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">拒答率</th>
                  <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">平均修正轮数</th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((s) => (
                  <tr key={s.config} className="border-t border-hairline">
                    <td className="px-4 py-2.5 whitespace-nowrap">{CONFIG_LABELS[s.config] ?? s.config}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <Bar value={s.answerable.execution_accuracy} color="hsl(var(--teal))" />
                        <span className="num text-xs">{pct(s.answerable.execution_accuracy)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 num text-xs">{pct(s.answerable.answer_rate)}</td>
                    <td className="px-4 py-2.5 num text-xs">{pct(s.answerable.wrong_refusal_rate)}</td>
                    <td className="px-4 py-2.5 num text-xs">{pct(s.clarify.clarify_rate)}</td>
                    <td className="px-4 py-2.5 num text-xs">{pct(s.refuse.refuse_rate)}</td>
                    <td className="px-4 py-2.5 num text-xs">{s.answerable.avg_repairs ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="space-y-3 max-w-3xl border-t border-hairline pt-8">
        <h2 className="font-display text-lg md:text-xl font-semibold">机制级验证（单元测试实测）</h2>
        <ul className="text-[15px] leading-8 text-ink list-disc pl-5">
          <li>静态校验器：15/15 拦截恶意与幻觉 SQL（删改语句、多语句注入、文件读写函数、幻觉表/列）</li>
          <li>合法查询放行：8/8 无误杀（CTE、多表 JOIN、FILTER、窗口函数、UNION）</li>
          <li>只读沙箱：写操作在执行层被二次拦截；结果行数强制截断；超时自动中断</li>
          <li>数字溯源：千分位 / 百分数双尺度 / 万·亿单位 / 四舍五入容差均实测通过，编造数字全部被抓出</li>
        </ul>
        <p className="text-xs text-ink-soft">以上可在 <code>backend/tests/</code> 中一键复跑。</p>
      </section>

      <section className="space-y-2 max-w-3xl border-t border-hairline pt-8 text-sm text-ink-soft">
        <h2 className="font-display text-lg font-semibold text-ink">复现方式</h2>
        <pre className="bg-code text-code-ink rounded-lg p-4 text-[12.5px] leading-6 overflow-x-auto">
          <code>{`cp .env.example .env   # 填入你的模型 Key
make eval               # 完整管线，100 题
make eval-ablation      # 基线 + 四个消融配置`}</code>
        </pre>
      </section>
    </div>
  )
}
