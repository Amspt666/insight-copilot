/** 与后端 pipeline trace 对齐的类型定义 */

export interface GroundingInfo {
  total: number
  supported: number
  faithfulness: number
  unsupported: string[]
}

export interface ChartHint {
  type: 'number' | 'line' | 'bar' | 'table' | 'empty'
  x?: string
  y?: string[]
}

export interface StageRec {
  stage: string
  ok: boolean
  errors?: string[]
  error?: string
  reason?: string
  attempt?: number
}

export interface AskTrace {
  question: string
  status: 'ok' | 'clarify' | 'refuse' | 'error'
  category?: string
  gate?: { action: string; reason?: string; clarify_question?: string; options?: string[] }
  clarify_question?: string
  options?: string[]
  refuse_reason?: string
  error?: string
  sql?: string
  explanation?: string
  consistency?: { consistent: boolean; reason?: string; unknown?: boolean }
  columns?: string[]
  rows?: (string | number | null)[][]
  truncated?: boolean
  chart?: ChartHint
  insight?: string
  grounding?: GroundingInfo | null
  repairs?: number
  warning?: string | null
  latency_ms?: number
  model?: string
  stages?: StageRec[]
}

export interface ExampleMeta {
  id: string
  question: string
  category: string
}

export interface DatasetMeta {
  name: string
  orders: number
  order_items: number
  unique_customers: number
  products: number
  sellers: number
  categories: number
  states: number
  date_min: string
  date_max: string
  tables: number
}

export interface MetaInfo {
  mode: 'live' | 'replay'
  model: string | null
  dataset: DatasetMeta
}

/** 评测摘要（eval/run_eval.py 的 summarize 输出） */
export interface EvalSummary {
  config: string
  answerable: {
    n: number
    execution_accuracy: number | null
    answer_rate: number | null
    wrong_refusal_rate: number | null
    avg_repairs: number | null
    insight_faithfulness: number | null
  }
  clarify: { n: number; clarify_rate: number | null }
  refuse: { n: number; refuse_rate: number | null }
  avg_latency_s: number | null
}
