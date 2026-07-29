# 问数 InsightCopilot · 可信对话式商业智能

> 让 AI 给的每个数字，都能被核验。

面向业务人员的中英双语对话式 BI：自然语言提问 → 自动生成 SQL → 可视化与洞察。
与常见 ChatBI 不同的是，本项目针对其最大落地障碍——**“AI 的分析结论没人敢信”**——
设计了四层各自可检验的可信机制，并在 100 题自建评测集上用消融实验量化每一层的贡献。

## 四层可信机制

| 层 | 机制 | 解决什么 |
|---|---|---|
| 问得对 | YAML 语义层（指标口径/术语映射/歧义规则）+ 澄清/拒答门 + 意图回译校验 | 口径靠猜、答非所问 |
| 算得对 | sqlglot 静态校验（幻觉表/列、危险函数、写操作拦截）+ 只读沙箱执行 + 自我修正 | SQL 语法错、执行错、注入风险 |
| 说得对 | 洞察文字逐数字程序化溯源核验，未溯源数字显式标记 | 解读编数字 |
| 不硬撑 | 歧义反问、超纲拒答、低置信标注 | 一本正经地胡说八道 |

**机制是实测过的，不是宣称**：静态校验器 15/15 拦截恶意与幻觉 SQL、8/8 不误杀合法查询；
数字溯源对千分位/百分数/万·亿单位/四舍五入容差全部实测通过
（`cd backend && python3 -m pytest tests/ -q` 可复跑）。

## 快速开始（一键）

```bash
bash setup.sh     # 安装依赖 + 构建 DuckDB 数据库（Windows 用 setup.bat）
# 编辑 .env 填入你的模型 Key（不配也能跑：进入示例回放模式）
bash start.sh     # 启动 → http://localhost:8000
```

- 支持任何 OpenAI 兼容接口：DeepSeek / Kimi / 通义千问，见 `.env.example`
- 前端已预构建（`frontend/dist`），日常运行**不需要 Node 环境**
- 数据集（Olist 巴西电商公开数据集，gzip 压缩约 29MB）已随仓库携带，无需联网下载

## 架构

```
用户问题（中/英）
      │
      ▼
┌─────────────┐   歧义 → 反问澄清   超纲 → 拒答
│ 澄清/拒答门   │ ──────────────────────────────┐
└─────────────┘                                │
      │ 通过                                    │
      ▼
┌─────────────┐   语义层上下文（DDL+口径+约定+时间锚点）
│ SQL 生成     │ ◄── 自我修正（错误回灌，最多 3 轮）
└─────────────┘
      │
      ▼
┌─────────────┐   语法/幻觉表列/危险函数/写操作 拦截
│ 静态校验器   │ ── 不通过 → 回炉修正
└─────────────┘
      │
      ▼
┌─────────────┐   只读连接 · 超时中断 · 行数截断
│ 沙箱执行     │ ── 失败 → 回炉修正
└─────────────┘
      │
      ▼
┌─────────────┐   SQL → 业务语言回译 → 与原问题一致性判定
│ 意图回译     │ ── 不一致 → 显著标注
└─────────────┘
      │
      ▼
┌─────────────┐   洞察中每个数字 ↔ 结果集逐一比对
│ 数字溯源     │ ── 未溯源 → 标记剔除 + 忠实度计入
└─────────────┘
      │
      ▼
  回答 + SQL + 图表 + 证据面板（全程可展开核验）
```

技术栈：FastAPI · DuckDB · sqlglot · React + TypeScript · Tailwind · Recharts

## 评测（100 题自建基准）

五类题型：简单聚合 25 / 多表关联 25 / 时间对比 20 / 歧义澄清 15 / 超纲拒答 15，
可答题附人工标注 gold SQL（全部在真实数据库上验证过）。

```bash
make eval            # 完整管线
make eval-ablation   # 基线 + 消融
```

指标：执行准确率（EX，结果集与 gold 比对）、澄清率、拒答率、误拒率、洞察忠实度、平均修正轮数。
本仓库 `backend/eval/results/` 保留历次实测原始记录。

## 项目结构

```
├── setup.sh / setup.bat / start.sh / start.bat / Makefile
├── .env.example
├── data/
│   ├── raw/*.csv.gz            # Olist 数据集（gzip）
│   └── semantic/semantic_layer.yaml   # 语义层：指标口径 + 歧义规则 + 全局约定
├── scripts/
│   ├── build_db.py             # CSV → DuckDB
│   └── gen_demo_data.py        # 真实运行产物 → 前端内置演示数据
├── backend/
│   ├── app/                    # 管线核心：clarify/sqlgen/validator/executor/
│   │                           #   backtranslate/insight/grounding/pipeline
│   ├── api/main.py             # FastAPI（问答 + 证据面板 + 回放模式 + 静态托管）
│   ├── benchmark/              # 100 题评测集（含 gold SQL 与构建验证脚本）
│   ├── eval/run_eval.py        # 跑分器（含消融配置）
│   └── tests/test_mechanisms.py# 机制级单元测试
├── examples/replay/            # 10 个真实运行的完整问答轨迹
├── frontend/                   # React 源码 + 预构建 dist
└── docs/                       # 设计文档 · 简历文案
```

## 设计取舍（为什么这样做）

- **不套 LangChain 现成链**：核心管线自研，每个环节可独立测试、可消融、可解释
- **语义层是 YAML 不是代码**：业务人员可维护口径；中文术语到英文 schema 的映射天然需要它
- **校验永不关闭**：消融只作用于“喂给模型的上下文”，安全底线（静态校验+只读沙箱）任何配置下都在
- **回放模式**：未配 Key 时展示真实运行的完整轨迹，演示不依赖现场网络与额度

## 数据集与许可

- [Olist Brazilian E-Commerce Public Dataset](https://github.com/olist/work-at-olist-data)，由 Olist 公开发布
- 本项目代码以 MIT 许可开源
