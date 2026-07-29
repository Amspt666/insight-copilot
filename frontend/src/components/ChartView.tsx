import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Cell,
} from 'recharts'
import type { AskTrace } from '../lib/types'

/* recharts 只接受颜色字符串，无法走 Tailwind 类名；这里统一引用 index.css 中的命名 token */
const TEAL = 'hsl(var(--teal))'
const TEAL_MID = 'hsl(var(--teal-mid))'
const INK_SOFT = 'hsl(var(--ink-soft))'
const HAIRLINE = 'hsl(var(--hairline))'

function fmt(v: unknown): string {
  if (typeof v === 'number') {
    return Math.abs(v) >= 1000
      ? v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
      : String(v)
  }
  return String(v ?? '')
}

/** 数值单元格智能解析：字符串数字也能参与画图 */
function num(v: unknown): number | null {
  if (typeof v === 'number') return v
  const n = parseFloat(String(v))
  return Number.isFinite(n) ? n : null
}

export default function ChartView({ trace }: { trace: AskTrace }) {
  const { chart, columns = [], rows = [] } = trace
  if (!chart || chart.type === 'empty' || rows.length === 0) return null

  if (chart.type === 'number') {
    const valueRow = rows[0] ?? []
    return (
      <div className="flex flex-wrap items-end gap-x-10 gap-y-4 py-2">
        {columns.map((c, i) => (
          <div key={c}>
            <div className="text-xs text-ink-soft mb-1">{c}</div>
            <div className="num text-4xl md:text-5xl font-medium text-teal tracking-tight">
              {fmt(valueRow[i])}
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (chart.type === 'line' || chart.type === 'bar') {
    const xKey = chart.x ?? columns[0]
    const yKeys = (chart.y ?? columns.slice(1)).filter((c) => c !== xKey)
    const data = rows.slice(0, 60).map((r) => {
      const obj: Record<string, unknown> = {}
      columns.forEach((c, i) => {
        obj[c] = i === 0 ? String(r[i] ?? '') : num(r[i]) ?? r[i]
      })
      return obj
    })
    const isLine = chart.type === 'line'
    const ChartTag = isLine ? LineChart : BarChart
    return (
      <div className="w-full min-w-0" style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ChartTag data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={HAIRLINE} vertical={false} />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 11, fill: INK_SOFT }}
              tickLine={false}
              axisLine={{ stroke: HAIRLINE }}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis
              tick={{ fontSize: 11, fill: INK_SOFT }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) =>
                Math.abs(v) >= 10000 ? `${(v / 10000).toFixed(0)}万` : String(v)
              }
              width={48}
            />
            <Tooltip
              formatter={(v: unknown) => [fmt(v), undefined]}
              contentStyle={{
                fontSize: 12, border: `1px solid ${HAIRLINE}`,
                borderRadius: 8, background: 'hsl(var(--card))',
              }}
            />
            {yKeys.map((k, i) =>
              isLine ? (
                <Line key={k} type="monotone" dataKey={k} stroke={i === 0 ? TEAL : TEAL_MID}
                  strokeWidth={2} dot={false} />
              ) : (
                <Bar key={k} dataKey={k} radius={[4, 4, 0, 0]} maxBarSize={48}>
                  {data.map((_, idx) => (
                    <Cell key={idx} fill={i === 0 ? TEAL : TEAL_MID} />
                  ))}
                </Bar>
              ),
            )}
          </ChartTag>
        </ResponsiveContainer>
      </div>
    )
  }

  // table
  return (
    <div className="overflow-x-auto border border-hairline rounded-lg">
      <table className="w-full text-sm min-w-[480px]">
        <thead>
          <tr className="bg-teal-soft/40">
            {columns.map((c) => (
              <th key={c} className="text-left px-3 py-2 font-medium text-xs text-ink-soft whitespace-nowrap">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((r, i) => (
            <tr key={i} className="border-t border-hairline">
              {r.map((cell, j) => (
                <td key={j} className="px-3 py-1.5 num whitespace-nowrap">{fmt(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
