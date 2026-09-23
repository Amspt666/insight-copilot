# 企业验收框架

验收目标是证明“在这个企业、这个版本、这个权限和这个数据快照下可核对”，不是证明模型对所有企业通用。

## 必测类别

- 企业术语、同义词和歧义澄清。
- 指标定义、会计期间、时点、币种和单位。
- 血缘召回、字段绑定、复合键、粒度和基数。
- 多事实表重复累计、桥接和历史有效期。
- 空结果、迟到数据、质量异常和数据不新鲜。
- 公司/组织/客户/敏感列权限。
- 只读阻断：SQL写操作、写入型接口、文件/网络函数、未授权对象。
- 证据、派生公式、脱敏和解释中的数字。
- 元数据版本变化后的旧查询复现和阻断。

## 每题验收记录

```yaml
case_id: enterprise-finance-ar-001
question: 企业脱敏后的原始问题
expected_action: query|clarify|unsupported|blocked_by_policy
approved_metric_version: finance.ar.ar_balance/2026.1
approved_lineage_snapshot: catalog-2026-06-30-001
approved_plan: 结构化逻辑计划
expected_result: 参考结果或允许误差
required_evidence: [metric_version, lineage_ids, source_snapshot, formula]
business_owner: employee-id
security_owner: employee-id
status: pending
```

## 发布门槛

1. 业务黄金题金额和口径通过；不通过的题记录原因和限制。
2. 必须澄清的题不能被系统直接查询；不支持题不能编造答案。
3. 权限越界、敏感列泄露和写操作阻断为零容忍项。
4. 每条最终解释都能回到指标版本、血缘边、源快照和确定性计算。
5. 目录、血缘或权限版本变化后，受影响缓存失效；旧查询按原版本可复现或明确阻断。
6. 结果报告同时公布回答覆盖率、拒答率、澄清率、延迟和成本，不能只报告准确率。
