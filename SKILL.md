---
name: industry-analysis
description: 当总控需要分析 A 股股票所在行业的走势、龙头表现、行业景气度时调用。输入股票代码 + 上下文,输出符合 module_output_v1 的行业分析 JSON,包含 -100~100 的行业评分、对该股的行业层面影响判断、关键催化与风险。仅适用 A 股。MVP 阶段只激活"行业走势" agent,其他 agent 输出占位。
version: 1.0.0
schema_version: module_output_v1
inputs:
  required: [request_id, schema_version, ticker, analysis_date]
  optional: [stock_name, market, forecast_horizon, current_price]
outputs: module_output_v1
---

# Industry Analysis Skill (MVP)

> 设计文档:[docs/industry-analysis-design-v1.md](docs/industry-analysis-design-v1.md)
> 契约:[docs/sub-skill-spec-v1.md](docs/sub-skill-spec-v1.md)

## 1. When to Use

总控在以下场景调用本 skill:

- 用户请求中含有股票代码,且 `forecast_horizon >= 20d`
- 用户问"这只股票所在行业...",必调
- 总控做综合预测时,作为行业维度输入

## 2. Inputs

JSON 形式传入 prompt。字段定义见 [input_contract.md](input_contract.md)。

示例:

```json
{
  "request_id": "req_20260501_abc123",
  "schema_version": "module_output_v1",
  "ticker": "600519",
  "analysis_date": "2026-05-01",
  "forecast_horizon": "60d"
}
```

## 3. Execution Steps

按顺序执行。**严禁使用 `analysis_date` 之后的数据**。

### Step 1: 分类映射

调用以下脚本拿到行业分类与关联概念:

```bash
python scripts/classification/fetch_industry_classification.py \
  --ticker {ticker} --analysis-date {analysis_date} --cache-dir ./data --output -

python scripts/classification/fetch_concept_mapping.py \
  --ticker {ticker} --analysis-date {analysis_date} --cache-dir ./data --output - --top-n 3
```

记录主行业 `l2_code`、`l2_name`,以及最多 3 个热门关联概念。

### Step 2: 拉取行业走势数据

```bash
python scripts/trend/fetch_industry_index.py \
  --index-code {l2_code} --analysis-date {analysis_date} --cache-dir ./data --output -

python scripts/trend/fetch_market_index.py \
  --market-code 000300.SH --analysis-date {analysis_date} --cache-dir ./data --output -

python scripts/trend/compute_breadth.py \
  --industry-l2-code {l2_code} --analysis-date {analysis_date} --cache-dir ./data --output -
```

### Step 3: 行业走势 agent 推理

基于 Step 2 的数据,推理:

- 行业指数 1M/3M/6M/12M 涨跌(由 `forecast_horizon` 决定主窗口)
- 行业 vs 沪深 300 相对强度(RS)
- 行业内涨跌家数比、涨停数(分化)
- 趋势阶段(上升趋势 / 震荡 / 下行 / 底部反转)

输出:

```json
{
  "score": -100,
  "confidence": 0.0,
  "stage": "上升趋势|震荡|下行|底部反转",
  "key_signals": []
}
```

**Score 描述统一**:
- `> +60`:强 / `+30 ~ +60`:中等强 / `-30 ~ +30`:中性 / `-60 ~ -30`:中等弱 / `< -60`:弱

**Confidence 计算**(Hybrid):
- `ceiling`:看数据完整度(数据缺失越多越低)
- `base`:LLM 自评(信号一致性 / 强度)
- `final = min(ceiling, base)`

### Step 4: 其他 4 个 agent(MVP 占位)

MVP 阶段不调用,直接生成占位 stub:

```json
{
  "fundamentals":  {"score": 0, "confidence": 0.3, "note": "v2 will add"},
  "capital_flow":  {"score": 0, "confidence": 0.3, "note": "v2 will add"},
  "leaders":       {"score": 0, "confidence": 0.3, "note": "v2 will add"},
  "macro_policy":  {"score": 0, "confidence": 0.3, "note": "v2 will add"}
}
```

### Step 5: 综合(裁判逻辑简化版)

MVP 阶段裁判简化为:**直接采用走势 agent 的 score 和 confidence**,降低 confidence 上限到 0.5(因为只有 1 个维度)。

输出:

```json
{
  "score": "<来自走势 agent>",
  "confidence": "min(走势 agent confidence × 0.7, 0.5)",
  "industry_outlook": {"stage": "<来自走势>"},
  "stock_in_industry": {
    "relative_position": "无法判断(MVP 阶段无龙头数据)",
    "industry_boost": "round(走势 score / 50)"
  }
}
```

### Step 6: 派生 signal + 组装最终 JSON

按规则在 prompt 里直接派生:
- `score >= 30 → "看多"`
- `-30 < score < 30 → "中性"`
- `score <= -30 → "看空"`

(也可以从 Python 调用:`from scripts.common.derive_signal import derive_signal`)

组装符合 `module_output_v1` 的完整 JSON。

### Step 7: 校验输出

```bash
echo '{...完整 JSON...}' > /tmp/output.json
python scripts/output_validator.py --input /tmp/output.json
```

如果失败:**修正 JSON 后重试 1 次**;仍失败设 `status=failed`、`code=REASONING_FAILED`。

## 4. Output JSON Schema

完整 schema:[shared_schemas/module_output_v1.schema.json](shared_schemas/module_output_v1.schema.json)

字段约束:
- `score`:integer,-100 ~ 100
- `confidence`:number,0.0 ~ 1.0
- `signal`:`看多 | 中性 | 看空`(由 score 派生)
- `reasons`:3–5 条,每条 ≤ 80 字
- `risks`:1–5 条,每条 ≤ 80 字
- `summary`:≤ 50 字

完整字段示例见 [output_contract.md](output_contract.md)。

## 5. Error Handling

| 情况 | 处理 |
|---|---|
| 无法识别股票申万分类(ST/退市/新股) | `status=failed`,`code=DATA_NOT_FOUND`,`missing=["classification"]` |
| 行业指数数据缺失 | `status=failed`,`code=DATA_NOT_FOUND` |
| 走势数据不完整(< 60 个交易日) | `status=partial`,`confidence ≤ 0.4`,`reasons` 标注数据缺失 |
| 输出 JSON 校验失败 | 修正后重试 1 次,仍失败设 `status=failed`,`code=REASONING_FAILED` |

## 6. Examples

输入:

```json
{
  "request_id": "req_20260501_abc123",
  "schema_version": "module_output_v1",
  "ticker": "600519",
  "stock_name": "贵州茅台",
  "analysis_date": "2026-05-01",
  "forecast_horizon": "60d"
}
```

输出(MVP 简化版):

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260501_abc123",
  "analysis_date": "2026-05-01",
  "status": "partial",
  "signal": "看多",
  "score": 35,
  "confidence": 0.4,
  "reasons": [
    "白酒行业指数近 3 个月上涨 8%,跑赢沪深 300",
    "行业内涨跌家数比 7:3,板块整体偏强",
    "MVP 阶段,仅基于走势维度判断,其他维度待 v2 补全"
  ],
  "risks": [
    "MVP 仅看走势,缺基本面/资金/龙头/宏观信号,可能高估行业景气"
  ],
  "summary": "白酒行业走势强于大盘,茅台短期偏多。",
  "metrics": {
    "latency_ms": 8000,
    "data_sources_used": ["tushare", "akshare"]
  },
  "module_specific": {
    "classification": {
      "primary_industry": {"system": "申万二级", "code": "801123.SI", "name": "白酒"},
      "related_concepts": []
    },
    "agent_breakdown": {
      "trend": {"score": 50, "confidence": 0.6, "stage": "上升趋势", "key_signals": []},
      "fundamentals": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "capital_flow": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "leaders": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "macro_policy": {"score": 0, "confidence": 0.3, "note": "v2 will add"}
    },
    "weights_used": {"trend": 1.0, "_note": "MVP 阶段只走 trend 维度"}
  }
}
```
