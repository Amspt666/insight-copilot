/** API 客户端：优先调用后端；静态预览（无后端）时回退到内置的真实运行数据。
 * 回退模式下页面会明确标注“演示数据”，不作任何隐瞒。
 */
import { DEMO_EXAMPLES, DEMO_META, DEMO_TRACES, DEMO_EVAL } from './demoData'
import type { AskTrace, ExampleMeta, MetaInfo } from './types'

const API_TIMEOUT = 4000

async function tryFetch<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), init ? 120000 : API_TIMEOUT)
    const r = await fetch(path, { ...init, signal: ctrl.signal })
    clearTimeout(t)
    if (!r.ok) return null
    return (await r.json()) as T
  } catch {
    return null
  }
}

let backendAlive: boolean | null = null
/** 后端探测只进行一次，所有后续请求共享同一 promise，
 *  避免子组件 effect 先于 getMeta 执行时拿到错误的 backendAlive。 */
let metaPromise: Promise<{ meta: MetaInfo; demo: boolean }> | null = null

export function getMeta(): Promise<{ meta: MetaInfo; demo: boolean }> {
  if (!metaPromise) {
    metaPromise = tryFetch<MetaInfo>('/api/meta').then((meta) => {
      if (meta) {
        backendAlive = true
        return { meta, demo: false }
      }
      backendAlive = false
      return { meta: DEMO_META, demo: true }
    })
  }
  return metaPromise
}

export async function getExamples(): Promise<ExampleMeta[]> {
  await getMeta() // 等待后端探测完成再决定走哪条数据通路
  if (backendAlive) {
    const r = await tryFetch<{ examples: ExampleMeta[] }>('/api/examples')
    if (r) return r.examples
  }
  return DEMO_EXAMPLES
}

export async function getExample(id: string): Promise<AskTrace | null> {
  await getMeta()
  if (backendAlive) {
    const r = await tryFetch<AskTrace>(`/api/examples/${id}`)
    if (r) return r
  }
  return DEMO_TRACES[id] ?? null
}

export async function ask(question: string): Promise<AskTrace> {
  await getMeta()
  if (backendAlive) {
    const r = await tryFetch<AskTrace>('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
    if (r) return r
    return {
      question, status: 'error',
      error: '后端未配置 LLM Key（回放模式）。请从右侧示例中选择问题体验完整流程。',
    }
  }
  // 静态演示：自由提问时给出诚实指引
  return {
    question, status: 'error',
    error: '当前为静态演示环境，自由问答未启用。本地一键启动并配置模型 Key 后即可实时问答——下方示例均为真实运行的完整记录，可直接查看。',
  }
}

export function getEvalSummary() {
  return DEMO_EVAL
}
