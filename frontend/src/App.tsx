import { useEffect, useState } from 'react'
import { getMeta } from './lib/api'
import type { MetaInfo } from './lib/types'
import HomeView from './components/HomeView'
import EvalView from './components/EvalView'
import MethodView from './components/MethodView'
import DataView from './components/DataView'

type View = 'home' | 'eval' | 'method' | 'data'

const NAV: { key: View; label: string }[] = [
  { key: 'home', label: '问数' },
  { key: 'method', label: '可信怎么炼成' },
  { key: 'eval', label: '实测' },
  { key: 'data', label: '数据与语义层' },
]

export default function App() {
  const [view, setView] = useState<View>('home')
  const [meta, setMeta] = useState<MetaInfo | null>(null)
  const [demo, setDemo] = useState(false)

  useEffect(() => {
    getMeta().then(({ meta, demo }) => {
      setMeta(meta)
      setDemo(demo)
    })
  }, [])

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col">
      <header className="sticky top-0 z-20 bg-paper/90 backdrop-blur border-b border-hairline">
        <div className="max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between gap-4">
          <button onClick={() => setView('home')} className="flex items-baseline gap-2 min-w-0">
            <span className="font-display text-lg font-semibold tracking-tight whitespace-nowrap">问数</span>
            <span className="text-xs text-ink-soft whitespace-nowrap hidden sm:inline">InsightCopilot · 可信对话式 BI</span>
          </button>
          <nav className="flex items-center gap-1 md:gap-2 overflow-x-auto">
            {NAV.map((n) => (
              <button
                key={n.key}
                onClick={() => setView(n.key)}
                className={`text-sm px-2.5 md:px-3 py-1.5 rounded-full transition-colors whitespace-nowrap ${
                  view === n.key ? 'bg-teal text-on-teal' : 'text-ink-soft hover:text-ink'
                }`}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-4 md:px-6">
        {view === 'home' && <HomeView meta={meta} demo={demo} />}
        {view === 'method' && <MethodView />}
        {view === 'eval' && <EvalView />}
        {view === 'data' && <DataView meta={meta} />}
      </main>

      <footer className="border-t border-hairline mt-16">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-2 text-xs text-ink-soft">
          <span>InsightCopilot 问数 · 个人技术作品 · 数据：Olist 巴西电商公开数据集</span>
          <span>页面上所有数字均来自真实数据与真实运行，未作虚构</span>
        </div>
      </footer>
    </div>
  )
}
