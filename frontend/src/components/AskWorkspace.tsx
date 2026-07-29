import { useEffect, useRef, useState } from 'react'
import { ask, getExample, getExamples } from '../lib/api'
import type { AskTrace, ExampleMeta, MetaInfo } from '../lib/types'
import ResultView from './ResultView'

interface Turn {
  question: string
  trace: AskTrace | null
  loading: boolean
}

/** 空状态引导问题：有对应真实运行样例的直接回放样例，没有的走自由提问 */
const SUGGESTIONS: { q: string; id?: string }[] = [
  { q: '2018 年各月的销售额是多少？', id: 'monthly_revenue_2018' },
  { q: '差评率最高的品类是哪些？' },
  { q: '整体复购率是多少？', id: 'repeat_rate' },
]

export default function AskWorkspace({ demo, meta }: { demo: boolean; meta: MetaInfo | null }) {
  const [examples, setExamples] = useState<ExampleMeta[]>([])
  const [input, setInput] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getExamples().then(setExamples)
  }, [])

  useEffect(() => {
    // 只滚动对话容器自身，避免 scrollIntoView 带动整页跳动
    const el = listRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [turns])

  async function run(question: string, exampleId?: string, fromInput = false) {
    if (!question.trim() || busy) return
    if (fromInput) setInput('') // 仅输入框提交时立即清空；请求期间用户新打的字不受影响
    setBusy(true)
    setTurns((t) => [...t, { question, trace: null, loading: true }])
    const trace = exampleId ? await getExample(exampleId) : await ask(question)
    setTurns((t) => {
      const next = [...t]
      next[next.length - 1] = {
        question,
        trace: trace ?? { question, status: 'error', error: '样例加载失败' },
        loading: false,
      }
      return next
    })
    setBusy(false)
  }

  return (
    <div className="border border-hairline rounded-2xl bg-card shadow-card overflow-hidden flex flex-col">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 md:px-5 py-3 border-b border-hairline">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-full bg-teal shrink-0" />
          <span className="text-sm font-medium truncate">问数台</span>
        </div>
        {demo && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-teal-soft text-teal whitespace-nowrap">
            演示数据 · 真实运行记录
          </span>
        )}
      </div>

      {/* 对话区 */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 md:px-5 py-4 space-y-5 min-h-[380px] max-h-[62vh]">
        {turns.length === 0 && (
          <div className="text-sm text-ink-soft space-y-2 pt-2">
            <p>用一句自然语言开始，例如：</p>
            <ul className="space-y-1.5">
              {SUGGESTIONS.map(({ q, id }) => (
                <li key={q}>
                  <button onClick={() => run(q, id)} className="text-teal hover:underline text-left">
                    {q} →
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-xs pt-1">也可以从下方示例库中挑选——其中包括“该反问”“该拒答”的可信机制演示。</p>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="space-y-2.5">
            <div className="flex justify-end">
              <div className="max-w-[85%] bg-teal text-on-teal text-sm rounded-2xl rounded-br-md px-4 py-2 break-words">
                {t.question}
              </div>
            </div>
            <div className="max-w-full">
              {t.loading ? (
                <div className="text-sm text-ink-soft flex items-center gap-2 py-2">
                  <span className="inline-block w-3.5 h-3.5 border-2 border-teal border-t-transparent rounded-full animate-spin" />
                  正在执行四层可信管线（澄清判断 → 生成校验 → 沙箱执行 → 数字溯源）…
                </div>
              ) : (
                t.trace && <ResultView trace={t.trace} onOption={(q) => run(q)} />
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 示例库 */}
      {examples.length > 0 && (
        <div className="px-4 md:px-5 py-2.5 border-t border-hairline overflow-x-auto">
          <div className="flex gap-2 w-max">
            {examples.map((e) => (
              <button
                key={e.id}
                onClick={() => run(e.question, e.id)}
                disabled={busy}
                className="text-xs px-3 py-1.5 rounded-full border border-hairline bg-paper hover:border-teal hover:text-teal transition-colors whitespace-nowrap disabled:opacity-50"
                title={e.category}
              >
                {e.question.length > 22 ? e.question.slice(0, 22) + '…' : e.question}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 输入区 */}
      <form
        className="flex items-center gap-2 px-4 md:px-5 py-3 border-t border-hairline"
        onSubmit={(e) => {
          e.preventDefault()
          run(input, undefined, true)
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
          placeholder={`向 ${meta ? meta.dataset.orders.toLocaleString() : '…'} 笔真实订单提问…`}
          className="flex-1 min-w-0 bg-transparent text-sm outline-none placeholder:text-ink-soft/70 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="shrink-0 text-sm px-4 py-2 rounded-lg bg-teal text-on-teal hover:bg-teal-strong transition-colors disabled:opacity-40 whitespace-nowrap"
        >
          提问
        </button>
      </form>
    </div>
  )
}
