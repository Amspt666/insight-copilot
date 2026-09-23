# 元数据与血缘检索规范

## 1. 检索对象

元数据至少分为业务层（指标、实体、术语、澄清规则）、逻辑层（事实、维度、粒度、可加性、时间角色）、物理层（表/视图、字段、类型、代码值、敏感标签）、关系层（血缘边、转换、关联键、基数、有效期、版本）和运行层（新鲜度、质量、可用性、成本）。

只有企业确认的关系层输入能够证明“可以沿这条路径规划”；其他来源只能支持理解和排序。

## 2. 权威性

来源优先级由企业配置，不由平台固定。典型顺序是：企业批准的治理平台/血缘发布 > 企业批准的 CDS/安全视图契约 > 企业维护的字段映射和 Join 规则 > 数据库目录发现 > 模型或向量候选。某企业可以选择不同顺序，但必须记录优先级、冲突处理人和失效时间。

## 3. 检索流程

```text
问题 -> 已批准指标/实体 -> 按权限、业务域、版本过滤目录
-> 用指标绑定对象反查企业血缘边 -> 扩展必要维表/桥表
-> 按粒度、基数、日期条件剪枝 -> 生成候选子图和召回证据
-> Join Planner 审核 -> Query Planner
```

候选结果必须显示指标版本、对象来源、血缘边 ID、快照版本、粒度和基数。排序不能替代审批状态。

## 4. 缺失与冲突

- 权威边不存在：不能凭字段名补一条生产路径，返回缺少已批准血缘。
- 权威边冲突：暂停规划，列出版本、负责人和差异。
- 关系过期：不能生成业务金额。
- 只有 N:N 路径：要求企业提供桥接规则或先聚合方案。
- 字段存在但无业务含义：不能进入已确认绑定。
- 指标有定义但没有物理绑定：返回语义已配置、数据暂不可用。

## 5. 平台索引模型

```sql
CREATE TABLE lineage_edge (
  lineage_id TEXT PRIMARY KEY,
  enterprise_id TEXT NOT NULL,
  source_system_id TEXT NOT NULL,
  upstream_object TEXT NOT NULL,
  upstream_column TEXT,
  downstream_object TEXT NOT NULL,
  downstream_column TEXT,
  join_key_json TEXT,
  transformation_ref TEXT,
  cardinality TEXT NOT NULL,
  grain_before TEXT,
  grain_after TEXT,
  valid_from DATE,
  valid_to DATE,
  source_version TEXT NOT NULL,
  approval_state TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
```

这是平台索引模型，不要求企业改变原始表名。导入器保留来源和字段，不把多个企业的血缘强行合并成一个通用字典。

## 6. 召回结果契约

```json
{
  "catalog_snapshot": "catalog-2026-06-30-001",
  "metric_version": "finance.ar.ar_balance/2026.1",
  "candidates": [{
    "object": "enterprise-approved-view",
    "fields": ["customer_id", "amount", "posting_date"],
    "lineage_ids": ["L-001", "L-004"],
    "grain": "customer-company-currency-day",
    "cardinality": "N:1",
    "approved": true,
    "reason": "metric binding + approved lineage path"
  }],
  "missing": [],
  "conflicts": []
}
```
