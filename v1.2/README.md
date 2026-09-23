# InsightCopilot v1.2 企业只读架构 Demo

v1.2 在 v1.1 的 SAP 风格财务数据之上提供一个可运行的企业只读架构 Demo，并同时保留面向真实企业试点的实施契约。Demo 的表规模保持较小，但完整走过 Router、业务语义、权威血缘、Schema Linking、Join Planner、Query Planner、确定性 SQL、只读校验、结果质量、Insight 和 Grounding。

企业试点中，系统只能读取企业批准的数据源、元数据和业务目录，生成查询计划，执行只读查询，返回可核验结果和证据。系统不提供写库、改凭证、过账、清账、支付、审批、删除、配置变更或自动回写接口。

## 每一层都需要企业输入

| 层 | 平台职责 | 企业必须提供或确认 |
|---|---|---|
| Router | 识别问题类型和业务域候选 | 业务域边界、组织语言、支持/不支持问题 |
| Business Semantic | 检索定义和候选口径 | 指标定义、同义词、例外、时间口径、币种规则、负责人 |
| Metadata Retrieval | 按权限检索表、字段、视图和关系 | 血缘关系表/目录、字段说明、版本、可信度和更新时间 |
| Schema Linking | 将业务概念绑定到物理对象 | 字段映射、粒度、代码值、复合键和人工确认 |
| Join Planner | 规划合法关联路径 | 主外键、基数、桥表、有效期、允许/禁止路径 |
| Query Planner | 形成只读逻辑计划 | 查询模板、维度、指标可加性和边界案例 |
| SQL Validator | 编译、检查、限流并只读执行 | 数据库方言、只读账号、授权视图、预算和安全策略 |
| Result Validation | 检查精度、质量、对账和新鲜度 | 对账报表、质量阈值、异常规则、刷新水位 |
| Insight/Grounding | 只引用可核验事实 | 业务表达、禁止推断、敏感信息策略 |
| Evaluation | 运行题集和记录误差 | 脱敏问题、标准答案、业务验收人和发布门槛 |

企业提供的“数据血缘关系查询表”是元数据检索的一个权威输入示例，但不是唯一输入。平台提供模板和默认规则，不能把默认模板当成企业事实。没有企业确认的口径、血缘或权限，系统必须澄清、拒答或标记尚未配置。

## 运行 Demo

要求 Python 3.10+。先在 `v1.2/.env` 配置 DeepSeek；也可以复用上级 `v1.1/.env`。不要提交密钥。

```powershell
cd v1.2
.\setup.bat
.\start.bat
```

服务地址为 <http://127.0.0.1:8112>，接口文档为 <http://127.0.0.1:8112/api/docs>。当前自然语言查询要求 DeepSeek，模型只负责意图理解、澄清措辞和已验证证据选择；Join Planner 的关联路径、Query Planner 的类型化计划、SQL 编译、校验、执行和数字核对由程序与企业配置完成。

权威输入示例：

- `data/semantic.json`：指标、SAP 风格字段和业务口径。
- `data/lineage_relations.csv`：已批准的数据血缘关系快照，Join Planner 的唯一关系事实来源。
- `data/enterprise_config.json`：只读策略、模型参与边界、企业配置版本和允许公司。

## 评测实验

评测题集位于 `eval/benchmark.json`。运行器会用同一批问题比较：

1. **v1.2 trusted pipeline**：企业语义、权威血缘、类型化计划、只读校验、结果检查和证据绑定。
2. **raw-model baseline**：DeepSeek 直接根据问题和物理表名输出计划，没有语义层、血缘 Join Planner 或 Grounding。

```powershell
cd v1.2
$env:PYTHONPATH='.'
python eval/run_eval.py --repeat 2
```

报告写入 `eval/results/`，包括状态准确率、可答题数值准确率、澄清/拒答正确率和平均延迟。评测结果不能外推为所有企业或所有模型的结论；正式试点应替换为企业脱敏黄金题、标准答案和业务验收人。

完整的 36 题、两轮、三组 `deepseek-flash` 实验结果见 [评测报告](eval/EXPERIMENT_REPORT.md)。

## 只读边界

```text
用户问题 -> 身份与数据范围 -> 企业语义目录 -> 企业血缘/元数据目录
-> 只读逻辑计划 -> 只读SQL与成本检查 -> 企业批准的只读源
-> 结果质量检查 -> 证据绑定解释
```

部署时使用企业提供的只读账号或只读服务接口。数据库、网络和应用层都拒绝写操作；导出也是只读复制，需再次经过权限和敏感字段策略。

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [企业输入契约](docs/ENTERPRISE_INPUT_CONTRACT.md)
- [元数据与血缘规范](docs/METADATA_LINEAGE_SPEC.md)
- [只读安全与治理](docs/READ_ONLY_GOVERNANCE.md)
- [试点实施计划](docs/PILOT_IMPLEMENTATION_PLAN.md)
- [验收框架](docs/ACCEPTANCE_FRAMEWORK.md)
- [架构决策记录](docs/DECISIONS.md)
- [企业模板](templates/)

v1.2 的目标是让企业或实施方看到需要什么输入、输入如何进入系统、每一步如何约束下一步，以及无法确认时如何停止。它不承诺连接任意 SAP 系统后自动得到正确答案，也不把企业治理工作隐藏在模型提示词里。

v1.1 是较短的 SAP 风格应收 Demo；v1.2 是在同一数据域上补齐企业输入、权威血缘、分阶段状态、只读边界和对照评测的版本。两者可以并行保留，方便观察从固定 Demo 到企业实施架构的变化。
