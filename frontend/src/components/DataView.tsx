import type { MetaInfo } from '../lib/types'

const METRICS = [
  { name: '销售额', terms: '销售额 / 成交金额 / 营收 / GMV', def: '有效订单商品金额合计（不含运费）' },
  { name: '订单量', terms: '订单量 / 订单数 / 单量', def: '有效订单数（去重）' },
  { name: '客单价', terms: '客单价 / 平均订单金额 / AOV', def: '销售额 ÷ 订单量' },
  { name: '复购率', terms: '复购率 / 回头客比例', def: '有效订单 ≥2 的独立客户数 ÷ 独立客户总数' },
  { name: '好评率', terms: '好评率 / 满意率', def: '评分 ≥4 的评价占比' },
  { name: '差评率', terms: '差评率', def: '评分 ≤2 的评价占比' },
  { name: '平均配送时长', terms: '配送时长 / 送达时长', def: '已送达订单从下单到签收的天数' },
  { name: '运费占比', terms: '运费占比 / 运费率', def: '运费合计 ÷ 商品金额合计' },
  { name: '分期使用率', terms: '分期率', def: '分期期数 >1 的支付金额占比' },
]

/** metaKey 指向 /api/meta 的 dataset 字段（真实行数唯一事实源）；
 *  meta 未覆盖的表（payments/reviews/customers/category_translation）用 fallback 常量兜底。 */
const TABLES: { name: string; desc: string; metaKey?: keyof MetaInfo['dataset']; fallback: string }[] = [
  { name: 'orders', desc: '订单主表：状态、下单/送达时间', metaKey: 'orders', fallback: '99,441' },
  { name: 'order_items', desc: '订单商品明细：商品、卖家、金额、运费', metaKey: 'order_items', fallback: '112,650' },
  { name: 'payments', desc: '支付流水：方式、分期、金额', fallback: '103,886' },
  { name: 'reviews', desc: '评价：1–5 分与评论', fallback: '99,224' },
  { name: 'customers', desc: '客户：唯一标识、城市、州', fallback: '99,441' },
  { name: 'products', desc: '商品：品类、尺寸重量', metaKey: 'products', fallback: '32,951' },
  { name: 'sellers', desc: '卖家：城市、州', metaKey: 'sellers', fallback: '3,095' },
  { name: 'category_translation', desc: '品类葡英对照', fallback: '71' },
]

export default function DataView({ meta }: { meta: MetaInfo | null }) {
  return (
    <div className="py-8 md:py-12 space-y-12 max-w-4xl">
      <header className="space-y-3">
        <h1 className="font-display text-2xl md:text-3xl font-semibold tracking-tight">数据与语义层</h1>
        <p className="text-[15px] leading-7 text-ink-soft">
          真实公开数据集 + 显式的业务口径定义。语义层是整个系统的地基：
          它让“销售额”“复购率”这些词有且仅有一种算法。
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="font-display text-lg md:text-xl font-semibold">Olist 巴西电商公开数据集</h2>
        <p className="text-[15px] leading-7 text-ink">
          巴西电商平台 Olist 发布的真实脱敏交易数据
          {meta ? `（${meta.dataset.date_min} 至 ${meta.dataset.date_max}）` : ''}，
          覆盖 {meta?.dataset.states ?? 27} 个州、{meta?.dataset.categories ?? 71} 个品类。
          数据为静态历史快照：所有“最近 / 今年 / 去年”等相对时间，系统一律以数据最大日期为锚点推算。
        </p>
        <div className="overflow-x-auto border border-hairline rounded-xl">
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="bg-teal-soft/40 text-left">
                <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">表</th>
                <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">内容</th>
                <th className="px-4 py-2.5 font-medium text-xs text-ink-soft text-right">行数</th>
              </tr>
            </thead>
            <tbody>
              {TABLES.map((t) => (
                <tr key={t.name} className="border-t border-hairline">
                  <td className="px-4 py-2.5 font-mono text-[13px] text-teal">{t.name}</td>
                  <td className="px-4 py-2.5 text-[13px]">{t.desc}</td>
                  <td className="px-4 py-2.5 num text-[13px] text-right">
                    {meta && t.metaKey ? meta.dataset[t.metaKey].toLocaleString() : t.fallback}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4 border-t border-hairline pt-8">
        <h2 className="font-display text-lg md:text-xl font-semibold">语义层指标字典（节选）</h2>
        <p className="text-[15px] leading-7 text-ink">
          每个指标：中文术语 → 唯一 SQL 口径。用户用哪个词提问都行，答案只有一种。
          完整定义见仓库 <code className="text-teal">data/semantic/semantic_layer.yaml</code>。
        </p>
        <div className="overflow-x-auto border border-hairline rounded-xl">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="bg-teal-soft/40 text-left">
                <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">指标</th>
                <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">可识别的中文问法</th>
                <th className="px-4 py-2.5 font-medium text-xs text-ink-soft">口径定义</th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map((m) => (
                <tr key={m.name} className="border-t border-hairline">
                  <td className="px-4 py-2.5 font-medium whitespace-nowrap">{m.name}</td>
                  <td className="px-4 py-2.5 text-[13px] text-ink-soft">{m.terms}</td>
                  <td className="px-4 py-2.5 text-[13px]">{m.def}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3 border-t border-hairline pt-8">
        <h2 className="font-display text-lg md:text-xl font-semibold">全局口径约定</h2>
        <ul className="text-[15px] leading-8 text-ink list-disc pl-5">
          <li>经营指标默认只统计有效订单（排除已取消 / 缺货），用户明确要求除外</li>
          <li>金额单位 BRL（巴西雷亚尔），保留两位小数</li>
          <li>品类展示输出英文名；客户一律按 customer_unique_id 去重</li>
          <li>系统只生成只读 SELECT，物理上无法改动数据</li>
        </ul>
      </section>
    </div>
  )
}
