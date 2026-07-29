import type { MetaInfo } from '../lib/types'
import AskWorkspace from './AskWorkspace'

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="num text-xl md:text-2xl font-medium text-teal">{value}</div>
      <div className="text-xs text-ink-soft mt-0.5">{label}</div>
    </div>
  )
}

const PIPELINE = [
  { no: '01', title: '问得对', desc: '语义层锁定业务口径；歧义问题反问澄清，超纲问题直接拒答' },
  { no: '02', title: '算得对', desc: 'SQL 静态校验 + 只读沙箱执行 + 出错自我修正，SQL 全程透明可见' },
  { no: '03', title: '说得对', desc: '洞察文字中的每个数字自动溯源到查询结果，对不上就标记' },
  { no: '04', title: '不硬撑', desc: '意图回译校验“答非所问”；拿不准就明说，绝不一本正经地编' },
]

export default function HomeView({ meta, demo }: { meta: MetaInfo | null; demo: boolean }) {
  return (
    <div className="py-8 md:py-12 space-y-14">
      {/* 首屏：左主张右产品 —— 产品即首页，不用传统 hero */}
      <section className="grid lg:grid-cols-[1fr_1.25fr] gap-8 lg:gap-10 items-start">
        <div className="space-y-6 lg:sticky lg:top-20">
          <h1 className="font-display text-3xl md:text-[2.6rem] leading-[1.2] font-semibold tracking-tight">
            让 AI 给的每个数字，<br />都能被核验。
          </h1>
          <p className="text-[15px] leading-7 text-ink-soft">
            对话式 BI 最大的障碍不是技术，是信任：AI 生成 SQL 会错、写解读会编。
            「问数」用四层可信机制把每次回答变成可验证的结果——口径有语义层锁定、
            SQL 透明可执行、结论逐数溯源、拿不准主动拒答。
          </p>
          {meta && (
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4 gap-x-4 gap-y-5 pt-2 border-t border-hairline">
              <Stat value={meta.dataset.orders.toLocaleString()} label="真实订单" />
              <Stat value={`${meta.dataset.date_min.slice(0, 4)}–${meta.dataset.date_max.slice(0, 4)}`} label="数据年份" />
              <Stat value={String(meta.dataset.tables)} label="关联数据表" />
              <Stat value="4" label="层可信机制" />
            </div>
          )}
          <p className="text-xs text-ink-soft/80">
            基于 Olist 巴西电商公开数据集 · 支持中英文提问 · 本地一键部署可接自己的模型 Key
          </p>
        </div>
        <AskWorkspace demo={demo} meta={meta} />
      </section>

      {/* 四层机制速览：编号横向条，不是三栏特性卡 */}
      <section className="border-t border-hairline pt-10">
        <h2 className="font-display text-xl md:text-2xl font-semibold mb-6">四层可信机制</h2>
        <ol className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-hairline border border-hairline rounded-xl overflow-hidden">
          {PIPELINE.map((p) => (
            <li key={p.no} className="bg-card p-5 space-y-2">
              <div className="num text-xs text-teal">{p.no}</div>
              <div className="font-medium">{p.title}</div>
              <p className="text-[13px] leading-6 text-ink-soft">{p.desc}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
