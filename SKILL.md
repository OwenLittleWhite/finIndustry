---
name: industry-analysis
description: 当总控需要分析 A 股股票所在行业的走势、龙头表现、行业景气度时调用。输入股票代码 + 上下文,输出符合 module_output_v1 的行业分析 JSON,包含 -100~100 的行业评分、对该股的行业层面影响判断(含目标股 vs 行业龙头的相对位置)、关键催化与风险。仅适用 A 股。当前激活:行业走势 agent + 龙头 agent;基本面/资金/宏观政策 agent 暂为 stub(待 Plan 2 补全)。
version: 1.0.0
schema_version: module_output_v1
inputs:
  required: [ticker, analysis_date]              # 业务必填
  system_filled: [request_id, schema_version]    # 总控自动填,缺失时子 skill 用默认值(uuid / module_output_v1)
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

### Step 2.5: 拉取龙头数据

```bash
python scripts/leaders/fetch_industry_leaders.py \
  --industry-l2-code {l2_code} --analysis-date {analysis_date} \
  --cache-dir ./data --output /tmp/leaders.json --top-n 5

# 把目标股自身的 1M/3M return(从 Step 2 行业指数数据中,或单独调 daily 算)传给 compute_target_position
python scripts/leaders/compute_target_position.py \
  --target-ticker {ticker_with_suffix} \
  --target-return-1m {target_1m_return} \
  --target-return-3m {target_3m_return} \
  --leaders-json /tmp/leaders.json \
  --output -
```

得到:Top 5 龙头列表(各自 ticker / name / 总市值 / 1M/3M 涨跌 / PE) + 目标股位置标签(绝对龙头 / 二线龙头 / 跟随 / 落后 / 无法判断) + RS_vs_leaders。

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

### Step 3.5: 龙头 agent 推理

基于 Step 2.5 的龙头数据 + 目标股位置,推理:

- **目标股位置**:绝对龙头 / 二线龙头 / 跟随 / 落后 / 无法判断
- **龙头集体走势**:Top 5 平均 1M/3M 涨跌,龙头是带头领涨还是带头杀跌
- **目标股 vs 龙头强弱**:RS_1m / RS_3m,> 1 强、< 1 弱
- **龙头分化**:Top 5 内部涨跌分歧大不大(都跌 vs 一两只独强)

输出:
```json
{
  "score": -100,
  "confidence": 0.0,
  "key_signals": [
    {"name": "rank_in_industry", "value": 1, "interpretation": "+2"},
    {"name": "leaders_avg_1m", "value": -0.046, "interpretation": "-1"},
    {"name": "rs_vs_leaders_1m", "value": 1.02, "interpretation": "+1"}
  ]
}
```

判分原则:
- 目标股是绝对龙头 + 龙头集体走势好 → 高分(+50 ~ +80)
- 目标股是绝对龙头但龙头集体杀跌 → 中性偏弱(-20 ~ +20),龙头地位部分对冲行业弱势
- 目标股二线龙头 + 跑赢龙头平均 → +30
- 目标股落后 + 龙头都跌 → 显著负分(-40 ~ -60)
- 目标股不在 Top 5 + RS 弱 → 负分

### Step 4: 其他 3 个 agent(MVP 占位)

**注意:这 3 个都是"行业层面"agent,不是个股层面** —— 个股财务/资金/公告归 financial-analysis / capital-flow-analysis / event-announcement-analysis 子 skill 处理,我们不碰。

| Stub agent | 我们做的(行业层面) | 不做(个股层面,归其他子 skill) |
|---|---|---|
| `fundamentals`(行业基本面) | 行业 PE 历史分位、行业聚合 ROE / 营收 / 毛利率趋势 | 个股财报、个股估值 |
| `capital_flow`(行业资金) | 板块主力净流入、北向行业偏好、行业 ETF 申赎、融资融券行业聚合 | 个股资金流、个股龙虎榜 |
| `macro_policy`(行业宏观&政策) | 宏观→行业传导(白酒看 CPI、银行看利率)、行业政策催化 | 整体宏观、个股公告 |

3 个 agent 暂未实现(Plan 2b 待跟其他子 skill 对齐边界后开工),先生成占位 stub:

```json
{
  "fundamentals":  {"score": 0, "confidence": 0.3, "note": "v2 will add (行业聚合层面)"},
  "capital_flow":  {"score": 0, "confidence": 0.3, "note": "v2 will add (行业聚合层面)"},
  "macro_policy":  {"score": 0, "confidence": 0.3, "note": "v2 will add (行业聚合层面)"}
}
```

### Step 5: 综合(裁判逻辑简化版)

当前激活 trend + leaders 2 个 agent。简化裁判:

- **score** = `0.5 × trend_score + 0.5 × leader_score`(权重均分)
- **confidence** = `min(0.7 × max(trend_conf, leader_conf), 0.6)`
  - 上限 0.6(2 个维度,比单维度可信,但还差 3 个 agent)
- **industry_boost**:取 final_score / 50,四舍五入到 [-2, +2]
- **stock_in_industry.relative_position**:直接来自 compute_target_position 的标签

如果 trend / leaders 数据都缺失 → status = failed;只有一个缺失 → status = partial,confidence ≤ 0.4。

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
| 龙头数据获取失败(daily_basic 当日返回空) | `status=partial`,leaders agent 输出 stub,只用 trend |
| 目标股不在行业成分股(刚转板/重命名) | rank=None,position="无法判断",continue with leaders |
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

输出(trend + leaders 双激活):

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260501_abc123",
  "analysis_date": "2026-05-01",
  "status": "partial",
  "signal": "中性",
  "score": -10,
  "confidence": 0.5,
  "reasons": [
    "白酒行业 12M -19%,显著跑输沪深 300,趋势下行",
    "茅台是绝对龙头(市值 1.7 万亿,2 倍领先五粮液),龙头地位部分对冲行业弱势",
    "Top 5 龙头 1M 平均跌 4.6%,茅台跌幅相近,无独立 alpha",
    "行业基本面 / 资金 / 宏观维度待 v2 补全"
  ],
  "risks": [
    "行业跌幅可能继续扩大,龙头地位无法挽救趋势",
    "MVP 缺资金面 / 政策催化信号"
  ],
  "summary": "白酒走势弱但茅台是绝对龙头,综合中性。",
  "metrics": {
    "latency_ms": 12000,
    "data_sources_used": ["tushare"]
  },
  "module_specific": {
    "classification": {
      "primary_industry": {"system": "申万二级", "code": "801125.SI", "name": "白酒Ⅱ"},
      "related_concepts": []
    },
    "agent_breakdown": {
      "trend": {"score": -45, "confidence": 0.75, "stage": "下行", "key_signals": []},
      "leaders": {
        "score": 25, "confidence": 0.7,
        "target_position": "绝对龙头",
        "rank_in_industry": 1,
        "rs_vs_leaders_avg_1m": 1.0,
        "key_signals": []
      },
      "fundamentals": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "capital_flow": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "macro_policy": {"score": 0, "confidence": 0.3, "note": "v2 will add"}
    },
    "stock_in_industry": {
      "relative_position": "绝对龙头",
      "industry_boost": 0,
      "rationale": "行业弱(-45)与龙头地位强(+25)抵消,综合中性"
    },
    "weights_used": {"trend": 0.5, "leaders": 0.5, "_note": "trend + leaders 均权"}
  }
}
```
