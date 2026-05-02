# 子 Skill 规范 v1.1

> **状态**:proposed · **作者**:行业分析模块 · **日期**:2026-05-02
> **适用范围**:stock-forecast-system 的所有子 skill(技术、行业、新闻、宏观、财务、事件公告、情绪、资金流向 ...)
> **目标**:让总控 skill 以一致方式调用所有子 skill,并合成最终预测
>
> **v1.1 改动**:简化业务必填字段为 `ticker + analysis_date`;`request_id` 和 `schema_version` 改为系统层自动填充(总控负责生成默认值,业务方不关心)。

## 设计原则

1. **AI-AI 协作模型**:总控和子 skill 都是运行在 Claude Code / Codex 中的 skill,通过 **Agent 工具(隔离上下文)** 互相调用,而非 subprocess + JSON 文件中转
2. **每个子 skill 自包含**:数据脚本、推理逻辑、测试都在自己 module 目录下,不依赖跨模块代码
3. **统一对外契约,自由内部实现**:输入/输出/错误/版本强约束,内部如何编排 prompt、是否用多 agent 辩论完全自由
4. **永远返回合法 JSON**:子 skill 不抛异常,失败也返回结构化 error
5. **防 lookahead bias**:严禁使用 `analysis_date` 之后的数据(回测可重放)

---

## 1. 文件结构

每个子 skill 是一个完整目录,放在 `modules/<skill-name>/` 下:

```
modules/<skill-name>/
├── SKILL.md                  # ⭐️ 主入口,宿主 LLM 读取执行
├── module_manifest.yaml      # 机器可读元数据
├── README.md                 # 人类文档(原理、数据源、依赖)
├── input_contract.md         # 输入字段详解(可选但推荐)
├── output_contract.md        # 输出字段详解(可选但推荐)
├── scripts/                  # 数据获取/计算脚本,纯确定性,无 LLM
│   ├── *.py
│   └── tests/                # 脚本单元测试
├── tests/                    # 子 skill 集成测试(含 golden outputs)
│   ├── fixtures/
│   └── golden_outputs/
├── data/                     # 运行时缓存(gitignore)
└── references/               # 论文、设计、调研(可选)
```

**自包含原则**:
- 子 skill 不 import 其他 `modules/` 内容
- 数据脚本独立维护,**允许跨模块重复**(优先简化所有权,而非去重)
- 仅 `shared/schemas/` 和 `shared/contracts/` 可共用

---

## 2. SKILL.md 格式

### Frontmatter(强制)

```yaml
---
name: industry-analysis
description: 当总控需要分析股票所在行业的走势、龙头表现、行业景气度时调用。输入股票代码 + 上下文,输出符合 module_output_v1 的 JSON。仅适用 A 股。
version: 1.0.0
schema_version: module_output_v1
inputs:
  required: [ticker, analysis_date]              # 业务必填
  system_filled: [request_id, schema_version]    # 总控自动填(uuid + 默认 schema)
  optional: [stock_name, market, forecast_horizon, current_price]
outputs: module_output_v1
---
```

`description` 是总控判断"何时调用我"的关键依据,要写明:
- **When**:什么场景调用
- **What**:输入是什么
- **Format**:输出格式
- **Scope**:适用范围(如"仅 A 股")

### Body 必须章节

```markdown
# <skill-name>

## 1. When to Use(给总控的判断依据)
具体场景列表,触发条件

## 2. Inputs
字段表 + 示例

## 3. Execution Steps(给宿主 LLM 的指令)
- Step 1: 调用 scripts/foo.py 获取数据
- Step 2: 按 prompt 模板做分析(可多个子步骤、可多 agent 辩论)
- Step 3: 合成结论
- Step 4: 输出 JSON

## 4. Output JSON Schema
完整 schema + 示例

## 5. Error Handling
数据不全 / 超时 / 异常的处理指引

## 6. Examples
≥ 1 个完整 input → output 示例
```

---

## 3. module_manifest.yaml

```yaml
module_id: industry_analysis           # snake_case 英文 id,等于 module_output_v1.module_id
module_name: 行业分析模块               # 中文展示名
module_version: 1.0.0                  # semver
schema_version: module_output_v1
entrypoint: SKILL.md                   # 不再是 run_module.py

owner: 行业分析负责人
description: 分析目标股票所在行业的走势、龙头、景气度,给出行业层面对该股的影响判断

inputs:
  required: [ticker, analysis_date]              # 业务必填
  system_filled: [request_id, schema_version]    # 总控自动填(uuid + 默认 schema)
  optional: [stock_name, market, forecast_horizon, current_price]

outputs:
  schema: module_output_v1

dependencies:
  data_sources: [tushare, eastmoney]
  python_packages: [pandas, requests, akshare, tushare]

invocation_hints:                      # 给总控的调用提示(可选)
  - 当 forecast_horizon >= 20d 时强烈建议调用
  - 当用户问"这只股票所在行业..."时必调

tags: [industry, sector, leaders, fundamentals, capital_flow]
```

---

## 4. 输入契约(`forecast_request_v1`)

总控以 prompt 形式传给子 skill(不走文件系统)。**业务方只需关心 `ticker` 和 `analysis_date`**;其余系统字段总控自动填,可选字段有合理默认。

### 最小调用(总控真实最简形态)

```json
{
  "ticker": "600519",
  "analysis_date": "2026-04-30"
}
```

### 完整形态(全字段)

```json
{
  "request_id": "req_20260430_abc123",
  "schema_version": "module_output_v1",
  "ticker": "600519",
  "stock_name": "贵州茅台",
  "market": "A股",
  "analysis_date": "2026-04-30",
  "forecast_horizon": "60d",
  "current_price": 1680.5
}
```

### 字段分类

**业务必填**(总控调用方真正关心的两个字段):

| 字段 | 类型 | 说明 |
|---|---|---|
| `ticker` | string | 股票代码,A 股 6 位数字 |
| `analysis_date` | string | **数据截止日**,YYYY-MM-DD,严禁使用之后数据 |

**系统字段**(总控自动填,业务方不关心;子 skill 收到时直接使用,缺失时按下表默认):

| 字段 | 默认值 | 说明 |
|---|---|---|
| `request_id` | `uuid4()` 自动生成 | 一次完整 forecast 的追踪 id |
| `schema_version` | `"module_output_v1"` | 输出 schema 版本 |

**业务可选**(总控可不填,子 skill 用合理默认):

| 字段 | 默认 | 说明 |
|---|---|---|
| `stock_name` | 子 skill 从 ticker 反查 | 股票名称 |
| `market` | `A股` | 枚举:`A股 / 港股 / 美股` |
| `forecast_horizon` | `20d` | 预测窗口,枚举见下 |
| `current_price` | 子 skill 从 daily 取 | 该日收盘价 |

### 子 Skill 实现约定

- 子 skill 收到 request 后必须验证 `ticker` 和 `analysis_date` 不为空,缺失则返回 `status=failed, error.code=INVALID_INPUT`
- 其他字段缺失时,按上表默认值填充,**不视为错误**
- 输出 JSON 中的 `request_id` 和 `schema_version` 字段必须存在(若 request 没传,子 skill 用默认值)

### `forecast_horizon` 枚举(交易日)

| 值 | 含义 |
|---|---|
| `5d` | 短期(约 1 周) |
| `20d` | 中短期(约 1 个月) |
| `60d` | 中期(约 3 个月) |
| `120d` | 中长期(约 6 个月) |
| `250d` | 长期(约 1 年) |

子 skill 应根据 horizon 调整内部信号权重(短期重资金/技术,长期重基本面/宏观)。

---

## 5. 输出契约(`module_output_v1`)

### 通用必备字段(所有子 skill 一致)

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260430_abc123",
  "analysis_date": "2026-04-30",

  "status": "success",
  "signal": "看多",
  "score": 65,
  "confidence": 0.78,
  "reasons": [
    "白酒行业 PE 处于历史 35% 分位,估值合理",
    "近 30 日北向资金净流入行业 28 亿,持续加仓",
    "龙头茅台、五粮液同步走强,板块联动效应明显"
  ],
  "risks": [
    "消费税改革预期对高端白酒利润率有边际压力",
    "Q1 渠道库存仍处偏高水位"
  ],
  "summary": "白酒景气度回升,龙头领涨,贵州茅台位居核心受益位置。",

  "metrics": {
    "latency_ms": 12500,
    "data_sources_used": ["tushare", "eastmoney"]
  }
}
```

### 字段约束(强制)

| 字段 | 类型 | 约束 |
|---|---|---|
| `module_id` | string | 与 manifest 一致 |
| `score` | integer | -100 到 100 |
| `confidence` | number | 0.0 到 1.0 |
| `signal` | enum | `看多 / 中性 / 看空`,**由 score 派生**(见第 7 节) |
| `reasons` | string[] | 3–5 条,每条 ≤ 80 字 |
| `risks` | string[] | 1–5 条,每条 ≤ 80 字 |
| `summary` | string | ≤ 50 字 |
| `status` | enum | `success / partial / failed` |

### 模块特定扩展

子 skill 自由扩展,放在 `module_specific` 字段下:

```json
{
  ...通用字段,
  "module_specific": {
    "classification": { ... },
    "agent_breakdown": { ... },
    "debate": { ... }
  }
}
```

总控合成时优先看通用字段,需要细节时再钻 `module_specific`。

---

## 6. 错误契约

子 skill **永远返回合法 JSON**,不抛异常给总控。

### 失败示例

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260430_abc123",
  "analysis_date": "2026-04-30",

  "status": "failed",
  "signal": null,
  "score": null,
  "confidence": null,
  "reasons": [],
  "risks": [],
  "summary": "未能获取行业分类数据,分析失败。",

  "error": {
    "code": "DATA_NOT_FOUND",
    "message": "未能获取 600519 在 2026-04-30 的申万行业分类",
    "retriable": false,
    "missing_fields": ["classification"]
  },

  "metrics": {
    "latency_ms": 1200,
    "data_sources_used": ["tushare"]
  }
}
```

### 部分成功示例(`partial`)

部分数据缺失但仍可给出弱信号:

```json
{
  ...通用字段,
  "status": "partial",
  "signal": "中性",
  "score": 12,
  "confidence": 0.35,
  "reasons": ["..."],
  "risks": ["..."],
  "summary": "数据不完整,行业基本面信号缺失,仅基于走势/资金面判断。",

  "error": {
    "code": "DATA_PARTIAL",
    "message": "行业聚合财务数据缺失",
    "retriable": false,
    "missing_fields": ["module_specific.agent_breakdown.fundamentals"]
  }
}
```

### Error code 枚举

| code | 含义 | retriable |
|---|---|---|
| `DATA_NOT_FOUND` | 数据源无该数据 | false |
| `DATA_PARTIAL` | 数据不完整(配 partial status) | false |
| `DATA_SOURCE_TIMEOUT` | API 超时 | true |
| `DATA_SOURCE_RATE_LIMIT` | API 限流 | true |
| `REASONING_FAILED` | LLM 推理产物不合法 | true |
| `INVALID_INPUT` | 输入参数非法 | false |
| `INTERNAL_ERROR` | 其他 | false |

---

## 7. Signal ↔ Score 映射(全局统一)

```
score >= 30           → signal = "看多"
-30 < score < 30      → signal = "中性"
score <= -30          → signal = "看空"
```

子 skill 只输出 score(连续值,信息更细),`signal` 字段由 SKILL.md 的逻辑根据上述规则派生,**不允许各模块自定阈值**。

---

## 8. 数据脚本规范(`scripts/` 目录)

### 强制要求

- ✅ 纯函数,**无 LLM 调用**,无副作用(除缓存 IO)
- ✅ 必须支持 `--analysis-date YYYY-MM-DD`(数据截止)
- ✅ 必须支持 `--cache-dir <path>`、`--output <path|->`(`-` = stdout)
- ✅ 必须 idempotent:同输入 → 同输出
- ✅ 必须有 unit test(放 `scripts/tests/`)
- ✅ 缓存格式建议 SQLite 或 JSON 文件
- ❌ 严禁在脚本里调 LLM API
- ❌ 严禁使用 `analysis_date` 之后的数据

### 调用示例

```bash
python scripts/fetch_industry_index.py \
  --ticker 600519 \
  --analysis-date 2026-04-30 \
  --windows 1m,3m,6m,12m \
  --cache-dir ./data \
  --output -
```

### 数据脚本的所有权

每个子 skill **独立维护**自己的 scripts。**允许跨模块重复**(例如多个模块都需要"获取股票申万分类"),优先简化所有权和依赖管理,而非去重。

---

## 9. 版本规范

- `module_version`:模块代码版本(semver)
- `schema_version`:输出 JSON 格式版本(`module_output_v1`)
- 两者**独立演进**
- `schema_version` 升级 major 时,子 skill 必须**双写**新旧版至少一个 release cycle
- 总控通过 request 里的 `schema_version` 路由到对应版本的 SKILL.md 逻辑

---

## 10. 测试规范

`tests/` 目录必备:

- ≥ 3 个典型 ticker 的 golden output(覆盖大盘股 / 小盘股 / ST 股等边界)
- ≥ 1 个 `partial` 状态用例(数据不全)
- ≥ 1 个 `failed` 状态用例(数据源不可用)
- mock 数据放 `tests/fixtures/`
- `make test` 应**独立可跑**,不依赖外部 API

---

## 11. 总控的调用方式

### 单调用(隔离上下文)

总控通过 **Agent 工具** 调用子 skill:

```
Agent({
  description: "Industry analysis for 600519",
  subagent_type: "general-purpose",
  prompt: """
  请按 modules/industry-analysis/SKILL.md 执行行业分析。

  输入:
  {
    "request_id": "req_20260430_abc123",
    "schema_version": "module_output_v1",
    "ticker": "600519",
    "analysis_date": "2026-04-30",
    "forecast_horizon": "60d",
    ...
  }

  约束:
  - 严禁使用 analysis_date 之后的数据
  - 输出必须符合 module_output_v1
  - 失败时设 status=failed,不抛异常
  - 只返回 JSON,无其他文字
  """
})
```

### 并行 dispatch(关键性能优势)

总控在**一条 message**里发多个 Agent tool calls,5 个子模块并行执行:

```
[Agent: technical-analysis]    \
[Agent: industry-analysis]      \
[Agent: news-analysis]           > 并行
[Agent: macro-analysis]         /
[Agent: financial-analysis]    /
```

整体延迟 ≈ max(各模块耗时),不是 sum。

### 合成

总控收集 N 份 JSON,通过自己的 synthesizer prompt 综合:

```
你收到 5 个子模块的 JSON 输出。请按 forecast_horizon=60d 合成最终判断:
- 短期 horizon 重技术/资金/情绪
- 长期 horizon 重基本面/宏观
- 矛盾信号优先看 confidence 较高的

输出:符合 forecast_v1 的最终预测 JSON。
```

---

## 12. shared/ 目录(全项目共用)

```
shared/
├── schemas/
│   ├── module_output_v1.schema.json       # JSON Schema 校验
│   └── forecast_request_v1.schema.json
└── contracts/
    └── sub-skill-spec-v1.md               # 本文档
```

**仅** `shared/schemas/` 和 `shared/contracts/` 是真正共享。无 `shared/utils/`,各模块自包含。

---

## 13. 验收 checklist

子 skill 交付时,需满足以下 checklist 才能集成到总控:

- [ ] `SKILL.md` frontmatter 完整,description 明确触发场景
- [ ] `module_manifest.yaml` 字段齐全
- [ ] `README.md` 含原理、数据源、依赖
- [ ] 输出 JSON 通过 `shared/schemas/module_output_v1.schema.json` 校验
- [ ] 通过 ≥ 3 个 golden output 测试
- [ ] 通过 partial 和 failed 状态测试
- [ ] 数据脚本 100% 通过单元测试
- [ ] 无 LLM API 直接调用
- [ ] 无跨 modules 引用
- [ ] 通过 `analysis_date` 防 lookahead bias 验证

---

## 附:开放问题(待全局对齐)

以下问题需要总控负责人 + 各模块负责人共同决议:

1. **总控降级方案**:是否需要在 skill 之外提供 `run_module.py` 兼容壳(给 CI/批量回测用)?
2. **缓存共享**:跨模块的同一数据(如行情、行业分类)是否要共享缓存目录?(当前规范:不共享,各模块自缓存)
3. **成本上限**:每次 forecast 的 token 预算上限?子 skill 何时应该"贵但准"vs"便宜但快"?
4. **重试策略**:`retriable: true` 的错误,谁负责重试 —— 总控还是子 skill?
5. **回测模式**:批量回测时,数据脚本的并发 / 限流策略?

---

**版本**:v1 · **状态**:draft · **下一步**:总控负责人 + 各模块负责人审阅,定 v1 标准
