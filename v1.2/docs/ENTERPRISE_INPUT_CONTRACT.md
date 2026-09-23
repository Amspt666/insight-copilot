# 企业输入契约

企业需要贡献什么由本契约定义。平台提供模板、导入器、校验器和检索机制，但不能用通用行业知识替代企业事实。

## A. 基本信息

企业提交 `enterprise_id`、系统类型和版本、时区、会计日历、启用业务域、数据覆盖范围、刷新SLA、财务/数据治理/安全负责人。

## B. 业务语义与澄清规则

企业为每个业务域填写业务对象和别名、指标定义、公式、粒度、可加性、时间角色、币种、排除项、歧义词候选、澄清问题、支持/拒绝问题、负责人、审批状态和生效版本。

```yaml
metric_id: ar_balance
enterprise_id: enterprise-demo
domain: finance.ar
business_name: 企业确认的应收余额名称
synonyms: []
definition: 企业确认的业务定义
grain: customer-company-currency-as_of
formula: 企业批准的计算规则引用
time_role: 企业确认的时间字段
currency_policy: 企业确认的币种与汇率规则
exclusions: []
source_bindings: []
clarification_rules: []
owner: finance-owner
approval_state: draft
version: 2026.1
```

没有 `approved` 版本的指标不能进入企业查询。

## C. 数据源与 Schema

企业提供可查询对象（优先安全视图或发布的 CDS/OData 接口）、表/视图/字段说明、类型、单位、敏感级别、更新时间、SAP字段与业务名映射、代码值字典、复合主键、历史保留规则和更正/删除表达。

平台不因识别到 `BKPF`、`BSEG` 或 `ACDOCA` 就假定企业配置相同；每个字段都需要来源版本和确认状态。

## D. 血缘关系查询表

企业可以贡献一张权威血缘关系查询表，也可以通过治理平台 API 提供同样契约。最低字段如下：

| 字段 | 含义 |
|---|---|
| `lineage_id` | 稳定边标识 |
| `source_system_id` | 来源系统 |
| `upstream_object/column` | 上游对象/字段 |
| `downstream_object/column` | 下游对象/字段 |
| `transformation_expression` | 批准的转换说明或引用 |
| `join_key` | 关联字段和复合键顺序 |
| `cardinality` | 1:1、N:1、1:N、N:N |
| `grain_before/after` | 关联前后粒度 |
| `valid_from/valid_to` | 关系有效期 |
| `source_version` | 元数据快照版本 |
| `confidence/approval_state` | 可信度和审批状态 |
| `owner/updated_at` | 维护人和更新时间 |

平台将企业批准的血缘表作为元数据检索的权威关系输入时：

1. 只索引有效且已批准的边。
2. 用版本固定一次查询看到的血缘快照。
3. 将复合键、粒度和基数传给 Join Planner。
4. 发现权威边冲突时停止自动规划，返回冲突来源和负责人。
5. DB catalog、模型推断和字段相似度只能补充候选，不能覆盖权威边。
6. 每次召回记录 `lineage_id`，使结果可追溯。

## E. 权限、质量与验收

企业提供身份提供商、租户/公司/组织/客户范围、行列权限、敏感字段分类、只读账号或服务凭证托管、导出策略、审计保留期、数据出境策略、标准报表、对账口径、容差、数据刷新水位和脱敏样例。

企业题集中的每题应包含问题、期望澄清或拒答、批准计划、参考结果、允许误差、证据要求和验收人。

## F. 维护责任

企业数据源、字段、指标、血缘或权限变化时必须发布新版本。平台发现版本不匹配、血缘过期或质量不达标时必须停止受影响查询，不能静默使用旧配置计算新数据。
