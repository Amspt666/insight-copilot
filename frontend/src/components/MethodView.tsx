import { DEMO_TRACES } from '../lib/demoData'

const LAYERS = [
  {
    no: '01',
    title: '问得对：语义层 + 澄清/拒答门',
    body: [
      'AI 分析出错，一半错在 SQL，另一半错在“口径”：用户说“销量”，指的是件数、订单数还是销售额？说“复购率”，分子分母各是什么？没有统一答案，模型只能猜。',
      '问数用一份 YAML 语义层把业务语言钉死成确定口径：指标定义、表间连接、有效订单口径、相对时间锚点（数据是静态快照，“最近”一律以数据最大日期推算）全部显式声明，生成 SQL 前注入上下文。',
      '前置一道分流门：命中歧义规则的提问先反问（“您说的销量指哪种口径？”），与数据无关或数据不具备的提问直接拒答。宁可多问一句、少答一题，不可猜错。',
    ],
    code: `metrics:
  repeat_purchase_rate:
    name: 复购率
    zh_terms: [复购率, 回头客比例]
    description: 有效订单数 ≥ 2 的独立客户数 / 独立客户总数
    sql: >
      SELECT COUNT(*) FILTER (cnt >= 2) * 1.0 / COUNT(*) FROM (
        SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS cnt
        FROM customers c JOIN orders o ON o.customer_id = c.customer_id
        WHERE o.order_status NOT IN ('canceled','unavailable')
        GROUP BY c.customer_unique_id) t`,
    codeLabel: '语义层片段 · data/semantic/semantic_layer.yaml',
  },
  {
    no: '02',
    title: '算得对：静态校验 + 沙箱执行 + 自我修正',
    body: [
      '生成的 SQL 先过 sqlglot 静态校验：语法合法性、只允许单条只读 SELECT、表白名单（拦截幻觉表）、列白名单（拦截幻觉列）、危险函数黑名单（read_csv / read_parquet / ATTACH 等可触达文件系统的能力一律拒绝）。',
      '通过校验后进入只读沙箱执行：连接级只读、独立线程超时中断、结果行数截断。校验与执行任一失败，错误信息回灌给模型自动修正，最多三轮。',
      '这一层是安全底线：任何消融配置下校验都不关闭。',
    ],
    code: `-- 校验器实测（本仓库 tests/ 可复现）
DROP TABLE orders                     → 拦截（写操作）
SELECT * FROM read_csv_auto('/etc/passwd') → 拦截（危险函数）
SELECT order_total FROM orders        → 拦截（幻觉列）
SELECT 1; DROP TABLE orders           → 拦截（多语句）`,
    codeLabel: '静态校验实测案例',
  },
  {
    no: '03',
    title: '说得对：洞察数字逐条溯源',
    body: [
      '即使 SQL 正确，模型写“解读”时仍会编造：把 993,592.98 约成“98 万”、虚构不存在的同比。这是 ChatBI 最容易被忽视、也最伤信任的一环。',
      '问数在洞察生成后做程序化核验：抽取文中每个数字（支持千分位/百分数/万/亿写法），与查询结果集逐一比对（容忍四舍五入），对不上的数字标记为“未溯源”并从正式输出中剔除。',
      '证据面板会如实展示：N 个数字中几个可溯源、哪几个未通过。',
    ],
    code: `洞察原文：…其中 SP 州贡献 320万 BRL，同比增长 142%。
溯源核验：结果集中不存在 3200000 与 1.42
系统输出：…其中 SP 州贡献 [未溯源:320万]，同比增长 [未溯源:142%]`,
    codeLabel: '溯源校验工作方式（真实机制演示）',
  },
  {
    no: '04',
    title: '不硬撑：意图回译 + 置信表达',
    body: [
      'SQL 能跑 ≠ SQL 答的是用户的问题。系统把最终 SQL 反向翻译成业务语言，再与原问题做一致性判定；不一致就修正或显著标注“结果仅供参考”。',
      '四层机制的任何一层拿不准，系统的选择都是反问、拒答或标注——而不是输出一个看起来漂亮的错误答案。',
    ],
    code: null,
    codeLabel: '',
  },
]

export default function MethodView() {
  const example = DEMO_TRACES['monthly_revenue_2018']
  return (
    <div className="py-8 md:py-12 max-w-3xl space-y-12">
      <header className="space-y-3">
        <h1 className="font-display text-2xl md:text-3xl font-semibold tracking-tight">可信是怎么炼成的</h1>
        <p className="text-[15px] leading-7 text-ink-soft">
          不是一句“我们重视准确性”，而是四层各自可检验的机制。每一层都可以被绕过、被攻击、被单独测量——
          仓库里的测试与消融实验就是这么做的。
        </p>
      </header>

      {LAYERS.map((l) => (
        <section key={l.no} className="border-t border-hairline pt-8 space-y-4">
          <div className="flex items-baseline gap-3">
            <span className="num text-sm text-teal">{l.no}</span>
            <h2 className="font-display text-lg md:text-xl font-semibold">{l.title}</h2>
          </div>
          {l.body.map((p, i) => (
            <p key={i} className="text-[15px] leading-7 text-ink">{p}</p>
          ))}
          {l.code && (
            <figure className="border border-hairline rounded-lg overflow-hidden">
              <figcaption className="px-3 py-1.5 text-[11px] text-ink-soft bg-muted/60">{l.codeLabel}</figcaption>
              <pre className="bg-code text-code-ink text-[12.5px] leading-6 p-4 overflow-x-auto">
                <code>{l.code}</code>
              </pre>
            </figure>
          )}
        </section>
      ))}

      {example?.sql && (
        <section className="border-t border-hairline pt-8 space-y-3">
          <h2 className="font-display text-lg md:text-xl font-semibold">一次真实运行的完整轨迹</h2>
          <p className="text-[15px] leading-7 text-ink">
            问题：「{example.question}」。以下为系统真实生成的 SQL（未做任何人工修饰）：
          </p>
          <figure className="border border-hairline rounded-lg overflow-hidden">
            <figcaption className="px-3 py-1.5 text-[11px] text-ink-soft bg-muted/60">
              真实生成 · 模型 {example.model ?? 'deepseek'} · 自我修正 {example.repairs ?? 0} 轮
            </figcaption>
            <pre className="bg-code text-code-ink text-[12.5px] leading-6 p-4 overflow-x-auto">
              <code>{example.sql}</code>
            </pre>
          </figure>
          {example.grounding && (
            <p className="text-[13px] text-ink-soft">
              该次回答的洞察共引用 {example.grounding.total} 个数字，
              其中 {example.grounding.supported} 个通过溯源核验。
            </p>
          )}
        </section>
      )}
    </div>
  )
}
