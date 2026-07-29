import { useState } from 'react'
import type { AskTrace } from '../lib/types'
import ChartView from './ChartView'

/** 把洞察文本中的 [未溯源:xx] 标记渲染为醒目的琥珀色标签 */
function InsightText({ text }: { text: string }) {
  const parts = text.split(/(\[未溯源:[^\]]+\])/g)
  return (
    <p className="text-[15px] leading-7 text-ink break-words">
      {parts.map((p, i) =>
        p.startsWith('[未溯源:') ? (
          <mark key={i} className="bg-transparent text-warn border border-dashed border-current rounded px-1 mx-0.5 text-[13px]">
            {p.slice(5, -1)}·未溯源
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </p>
  )
}

function SqlBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="rounded-lg overflow-hidden border border-hairline">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-muted/60 text-xs text-ink-soft hover:bg-muted transition-colors"
      >
        <span className="font-mono">SQL · 透明可验</span>
        <span>{open ? '收起' : '展开'}</span>
      </button>
      {open && (
        <pre className="bg-code text-code-ink text-[13px] leading-6 p-4 overflow-x-auto">
          <code>{sql}</code>
        </pre>
      )}
    </div>
  )
}

function Evidence({ trace }: { trace: AskTrace }) {
  const [open, setOpen] = useState(false)
  const g = trace.grounding
  return (
    <div className="border border-hairline rounded-lg">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-ink-soft hover:bg-muted/50 transition-colors rounded-lg"
      >
        <span>证据面板 · 这次回答是怎么炼成的</span>
        <span>{open ? '收起' : '展开'}</span>
      </button>
      {open && (
        <dl className="px-4 pb-4 pt-1 space-y-3 text-[13px]">
          {trace.explanation && (
            <div>
              <dt className="text-ink-soft mb-0.5">意图回译（SQL 在算什么）</dt>
              <dd className="text-ink">{trace.explanation}</dd>
            </div>
          )}
          {trace.consistency && (
            <div>
              <dt className="text-ink-soft mb-0.5">意图一致性校验</dt>
              <dd className={trace.consistency.consistent ? 'text-ok' : 'text-warn'}>
                {trace.consistency.consistent ? '通过' : '存疑'} — {trace.consistency.reason}
              </dd>
            </div>
          )}
          {g && (
            <div>
              <dt className="text-ink-soft mb-0.5">数字溯源</dt>
              <dd>
                <span className={g.faithfulness >= 1 ? 'text-ok' : 'text-warn'}>
                  {g.supported}/{g.total} 个数字可追溯到结果集
                </span>
                {g.unsupported.length > 0 && (
                  <span className="text-warn">（未溯源：{g.unsupported.join('、')}）</span>
                )}
              </dd>
            </div>
          )}
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-ink-soft">
            <span>自我修正 {trace.repairs ?? 0} 轮</span>
            {trace.truncated && <span>结果已截断（超过行数上限）</span>}
            {trace.latency_ms != null && <span>耗时 {(trace.latency_ms / 1000).toFixed(1)}s</span>}
            {trace.model && <span>模型 {trace.model}</span>}
          </div>
        </dl>
      )}
    </div>
  )
}

export default function ResultView({
  trace, onOption,
}: { trace: AskTrace; onOption?: (q: string) => void }) {
  if (trace.status === 'clarify') {
    return (
      <div className="border border-dashed border-[hsl(var(--amber-warn)/0.5)] rounded-xl p-4 bg-[hsl(var(--amber-warn)/0.05)]">
        <div className="text-xs text-warn mb-1.5">可信机制 · 反问澄清（宁可多问一句，不可猜错口径）</div>
        <p className="text-[15px] text-ink mb-3">{trace.clarify_question}</p>
        <div className="flex flex-wrap gap-2">
          {(trace.options ?? []).map((o) => (
            <button key={o} onClick={() => onOption?.(`${trace.question}（按${o}口径）`)}
              className="text-sm px-3 py-1.5 rounded-full border border-hairline bg-card hover:border-teal hover:text-teal transition-colors whitespace-nowrap">
              {o}
            </button>
          ))}
        </div>
      </div>
    )
  }

  if (trace.status === 'refuse') {
    return (
      <div className="border border-hairline rounded-xl p-4 bg-muted/40">
        <div className="text-xs text-no mb-1.5">可信机制 · 主动拒答（答不了的明说，绝不硬编）</div>
        <p className="text-[15px] text-ink">{trace.refuse_reason}</p>
      </div>
    )
  }

  if (trace.status === 'error') {
    return (
      <div className="border border-hairline rounded-xl p-4 bg-muted/40">
        <div className="text-xs text-warn mb-1.5">无法完成这次回答</div>
        <p className="text-[15px] text-ink">{trace.error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {trace.warning && (
        <div className="text-xs text-warn border border-dashed border-[hsl(var(--amber-warn)/0.4)] rounded-lg px-3 py-2 bg-[hsl(var(--amber-warn)/0.05)]">
          {trace.warning}
        </div>
      )}
      {trace.insight && (
        <div>
          <div className="text-xs text-ink-soft mb-1.5">洞察（每个数字都可核验）</div>
          <InsightText text={trace.insight} />
        </div>
      )}
      <ChartView trace={trace} />
      {trace.sql && <SqlBlock sql={trace.sql} />}
      <Evidence trace={trace} />
    </div>
  )
}
