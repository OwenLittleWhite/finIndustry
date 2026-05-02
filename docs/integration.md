# Integration Guide — 给总控对接人

> 给 stock-forecast-system 总控 skill 的对接人用,**5 分钟看懂怎么调用 industry-analysis 子 skill**。
>
> 阅读顺序:本文 → [输入契约](../input_contract.md) → [输出契约](../output_contract.md) → 真跑 [outputs/run_live.json](../outputs/run_live.json) 看效果。

---

## 1. 我是谁,做什么

**industry-analysis** = 输入 A 股股票代码 → 输出该股**行业层面**的分析。

我**不**做的事(明确边界,避免和其他子 skill 撞车):

| 其他子 skill 的领地 | 我不碰 |
|---|---|
| technical-analysis | 个股 K 线、技术指标 |
| financial-analysis | 个股财务报表 |
| capital-flow-analysis | 个股资金流(我做行业聚合层面,见下) |
| macro-analysis | 整体宏观环境 |
| event-announcement-analysis | 个股新闻、公告 |

**我的领地** = 行业聚合 + 龙头横向 + 宏观→行业的传导。

---

## 2. 当前能力(v1.1)

已激活 2 个 analyst agent:

| Agent | 输入 | 信号 |
|---|---|---|
| 行业走势 | 申万二级行业指数日线 + 沪深 300 + 行业内涨跌家数 | 行业趋势阶段、行业 vs 大盘 RS、breadth |
| 龙头分析 | 行业 Top 5 市值龙头 + 各自 1M/3M 涨跌 + 估值 | 目标股位置标签(绝对龙头/二线/跟随/落后)、RS vs 龙头平均 |

stub 中(占位返回 0,等 Plan 2b)。**这 3 个都是"行业层面"**,不是个股层面:

| Stub agent | 我们做的(行业聚合) | 不做(个股层面,归其他子 skill) |
|---|---|---|
| `fundamentals` | 行业 PE 历史分位、行业聚合 ROE / 营收 / 毛利率趋势 | 个股财报 → financial-analysis |
| `capital_flow` | 板块主力净流入、北向行业偏好、行业 ETF 申赎、融资融券行业聚合 | 个股资金 → capital-flow-analysis |
| `macro_policy` | 宏观→行业传导(白酒看 CPI、银行看利率)、行业政策催化 | 个股公告 → event-announcement-analysis;整体宏观 → macro-analysis |

> **Plan 2b 边界仍需跟你对齐**:这 3 个 agent 名字跟你的子 skill 撞名,但我们做的是**行业聚合层面**(不重叠)还是**有部分重叠**,需要确认 — 见第 9 节 3 个问题。

---

## 3. 怎么调用

### 3.1 最简单形态(总控真实最简调用)

业务方**只关心 2 个字段**:

```json
{
  "ticker": "600519",
  "analysis_date": "2026-04-30"
}
```

字段说明:
- `ticker`:6 位 A 股代码
- `analysis_date`:数据截止日 YYYY-MM-DD,**严禁使用之后数据**(防 lookahead bias)

其余字段:
- `request_id` / `schema_version`:总控自动填,缺失时子 skill 用默认(uuid / `module_output_v1`)
- `forecast_horizon`:可选,默认 `20d`,枚举 `5d/20d/60d/120d/250d`(交易日)
- `stock_name` / `market` / `current_price`:可选,缺失时子 skill 自查

完整契约见 [input_contract.md](../input_contract.md)。

### 3.2 调用模式 A:Agent 工具(**推荐**,隔离上下文)

```python
Agent({
  description: "Industry analysis for 600519",
  subagent_type: "general-purpose",
  prompt: """
  请按 modules/industry-analysis/SKILL.md 执行行业分析。

  输入(JSON):
  {
    "ticker": "600519",
    "analysis_date": "2026-04-30",
    "forecast_horizon": "60d"
  }

  约束:
  - 严禁使用 analysis_date 之后数据
  - 输出符合 module_output_v1 schema
  - 失败时设 status=failed,不抛异常
  - 只返回 JSON,无其他文字
  """
})
```

**好处**:子 skill 在 isolated sub-context 跑,reasoning 细节不污染总控 context;5 个子模块可**并行 dispatch**。

### 3.3 调用模式 B:Skill 工具(同上下文,适合调试)

```python
Skill({
  skill: "industry-analysis",
  args: '{"ticker": "600519", "analysis_date": "2026-04-30"}'
})
```

**何时用 A vs B**:总控生产环境用 A(隔离 + 并行);开发 / 调试用 B(看完整 reasoning)。

### 3.4 并行 dispatch 5 个子模块(关键性能优势)

总控在**一条 message** 里发多个 Agent tool calls,所有子模块**并行跑**:

```
[Agent: technical-analysis]    \
[Agent: industry-analysis]      \
[Agent: news-analysis]           > 整体延迟 = max(各子模块),不是 sum
[Agent: macro-analysis]         /
[Agent: financial-analysis]    /
```

---

## 4. 输出长什么样

### 4.1 顶层字段(所有子 skill 一致)

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260430_xxx",
  "analysis_date": "2026-04-30",

  "status": "partial",
  "signal": "中性",
  "score": -23,
  "confidence": 0.53,

  "reasons": [...],
  "risks": [...],
  "summary": "...",

  "metrics": {...},
  "module_specific": {...}
}
```

字段约束:
- `score` 整数 -100 ~ 100,`signal` 由 score 按 ±30 阈值派生(`>=30` 看多 / `<=-30` 看空 / 其他中性)
- `confidence` 浮点 0~1
- `reasons` 3-5 条,每条 ≤ 80 字
- `risks` 1-5 条,每条 ≤ 80 字
- `summary` ≤ 50 字
- `status` 枚举 `success | partial | failed`

完整契约见 [output_contract.md](../output_contract.md) 和 [shared_schemas/module_output_v1.schema.json](../shared_schemas/module_output_v1.schema.json)。

### 4.2 模块特定扩展(`module_specific`)

行业子 skill 在 `module_specific` 下扩展 5 个子字段:

```json
{
  "module_specific": {
    "classification": {
      "primary_industry": {"system": "申万二级", "code": "801125.SI", "name": "白酒Ⅱ"},
      "l1_industry": {"code": "801120.SI", "name": "食品饮料"},
      "related_concepts": [{"name": "...", "code": "TS108"}]
    },
    "agent_breakdown": {
      "trend": { "score": -55, "confidence": 0.75, "stage": "下行", "key_signals": [...] },
      "leaders": {
        "score": 10, "confidence": 0.65,
        "target_position": "绝对龙头",
        "rank_in_industry": 1,
        "rs_vs_leaders_avg_1m": 0.99,
        "top5_leaders": [...]
      },
      "fundamentals": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "capital_flow": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "macro_policy": {"score": 0, "confidence": 0.3, "note": "v2 will add"}
    },
    "industry_outlook": {
      "verdict": "顺风|中性|逆风",
      "stage": "底部|复苏|扩张|见顶|下行",
      "horizon": "60d",
      "rationale": "..."
    },
    "stock_in_industry": {
      "relative_position": "绝对龙头|二线龙头|跟随|落后|无法判断",
      "industry_boost": 0,
      "rationale": "..."
    },
    "weights_used": {"trend": 0.5, "leaders": 0.5}
  }
}
```

### 4.3 真实输出样本

完整一份(2026-04-30 跑 600519):[outputs/run_live.json](../outputs/run_live.json)

关键洞察示范:

> 600519 贵州茅台 / 行业:白酒Ⅱ
> trend agent: -55(白酒 12M 跑输沪深 300 46%)
> leaders agent: +10(茅台是绝对龙头,但龙头集体跌)
> **综合 -23 中性偏弱**(行业弱与龙头地位部分对冲)
> industry_boost = 0,relative_position = "绝对龙头"

---

## 5. 错误处理

子 skill **永远返回合法 JSON**,不抛异常给总控。

| 情况 | status | error.code |
|---|---|---|
| `ticker` / `analysis_date` 缺失或非法 | `failed` | `INVALID_INPUT` |
| 找不到股票申万分类(ST / 退市 / 新股) | `failed` | `DATA_NOT_FOUND` |
| 行业指数数据缺失 | `failed` | `DATA_NOT_FOUND` |
| 行业基本面 / 龙头数据部分缺失 | `partial` | `DATA_PARTIAL` |
| Tushare API 超时 | `failed` | `DATA_SOURCE_TIMEOUT`(retriable=true) |
| Tushare API 限流 | `failed` | `DATA_SOURCE_RATE_LIMIT`(retriable=true) |
| 输出 JSON 校验失败 | `failed` | `REASONING_FAILED`(retriable=true) |

`status=failed` 时:`signal` / `score` / `confidence` 一律 `null`。

`status=partial` 时:给低 confidence 的弱信号,`reasons` 标注哪些维度缺失。

---

## 6. 怎么合成到最终预测

总控收到我的 JSON 后,建议这样用:

1. **顶层 `signal` / `score` / `confidence`** 直接进总控的合成 prompt
2. **`module_specific.industry_outlook.verdict`** 给 LLM 总控做"行业是顺风/逆风"的判断
3. **`module_specific.stock_in_industry.industry_boost`** 给最终预测价的 alpha 调整(行业对个股加成 -2 ~ +2)
4. **`module_specific.agent_breakdown`** 必要时钻取细节
5. **`module_specific.classification`** 在最终研报里标注"该股属于 X 行业"

总控合成时的权重建议(随 forecast_horizon 调整):

| forecast_horizon | 行业权重 | 备注 |
|---|---|---|
| 5d | 15-20% | 短期重技术/资金 |
| 20d | 20-25% | |
| 60d | 25-30% | 行业趋势开始显著 |
| 120d | 30% | 行业景气度成主导 |
| 250d | 30-35% | 长期看行业基本面 |

---

## 7. 性能 / 成本

实测数据(单次 600519 完整端到端,2026-04-30):

| 项 | 数值 |
|---|---|
| Tushare API 调用 | ~9 次(冷缓存),0 次(热缓存) |
| 总耗时(冷缓存) | ~30s 数据 + ~1min LLM 推理 = ~1.5 min |
| 总耗时(热缓存) | <30s |
| Token 消耗 | ~15K(stub agent 阶段),Plan 2b 后预计 ~25K |

**成本控制**:数据脚本结果走 SQLite 缓存,key=(api, params, analysis_date),同一天重复调用 0 API 成本。

---

## 8. 验收 checklist(对接前确认)

- [ ] 你能成功用 Agent 工具调到我的 SKILL.md 并拿回符合 `module_output_v1` 的 JSON
- [ ] 我返回的 JSON 通过 [shared_schemas/module_output_v1.schema.json](../shared_schemas/module_output_v1.schema.json) 校验
- [ ] 你能解析 `signal` / `score` / `confidence` 进合成 prompt
- [ ] 你能在我返回 `status=failed` 时正确处理(降级或重试)
- [ ] 你的 forecast_horizon 用了枚举值之一(`5d/20d/60d/120d/250d`)

---

## 9. 等你确认的 3 个问题

> 这是 Plan 2b(基本面/资金/政策 3 个 agent)动工**之前**必须对齐的:

1. **行业资金 vs capital-flow-analysis**:你做个股资金流,还是也做行业层面(板块净流入、北向行业偏好、ETF)?如果你做行业层面,我这个 agent 就**砍掉**直接消费你的输出。
2. **行业基本面 vs financial-analysis**:你做个股财报,还是也做行业聚合(行业 PE 中枢、行业 ROE 趋势)?
3. **行业政策 vs event-announcement-analysis**:你做个股公告,还是也做行业政策(政府文件、产业链事件)?

回答这 3 个问题后,我们就能继续 Plan 2b。

---

## 10. 链接索引

- [README.md](../README.md):项目主页
- [SKILL.md](../SKILL.md):skill 主入口(给宿主 LLM 看的)
- [input_contract.md](../input_contract.md):输入字段详解
- [output_contract.md](../output_contract.md):输出字段详解
- [docs/sub-skill-spec-v1.md](sub-skill-spec-v1.md):全局子 skill 规范 v1.1
- [docs/industry-analysis-design-v1.md](industry-analysis-design-v1.md):本子 skill 详细架构
- [shared_schemas/module_output_v1.schema.json](../shared_schemas/module_output_v1.schema.json):JSON Schema
- [outputs/run_live.json](../outputs/run_live.json):真实数据完整输出样本

---

**问题、对齐、修改意见**:在仓库 issue 里提,或者直接联系我。
