---
name: industry-analysis
description: 当总控需要分析 A 股股票所在行业的走势、基本面、资金流、龙头表现、宏观传导时调用。输入股票代码 + 上下文,输出符合 module_output_v1 的行业分析 JSON,包含 -100~100 的行业评分、对该股的行业层面影响判断(含目标股 vs 行业龙头的相对位置)、5 维度 agent 拆解、关键催化与风险。仅适用 A 股。所有 5 个分析 agent(走势/基本面/资金/龙头/宏观政策)全部激活。
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

### Step 2.6: 拉取基本面数据

```bash
python scripts/fundamentals/fetch_industry_financials.py \
  --industry-l2-code {l2_code} --analysis-date {analysis_date} \
  --cache-dir ./data --output -

python scripts/fundamentals/fetch_industry_valuation.py \
  --industry-l2-code {l2_code} --analysis-date {analysis_date} \
  --cache-dir ./data --output -
```

得到:
- 行业聚合营收/利润 YoY 趋势(过去 8 季度)
- 行业 ROE / 毛利率中位数趋势
- 行业 PE/PB 当前值 + **过去 5 年历史分位**(关键!判断估值水位)

### Step 2.7: 拉取资金流数据

```bash
python scripts/capital/fetch_main_flow.py \
  --industry-name "{l2_name}" --analysis-date {analysis_date} \
  --cache-dir ./data --output -

python scripts/capital/fetch_northbound.py \
  --industry-l2-code {l2_code} --analysis-date {analysis_date} \
  --cache-dir ./data --output -

python scripts/capital/fetch_margin.py \
  --industry-l2-code {l2_code} --analysis-date {analysis_date} \
  --cache-dir ./data --output -
```

得到:
- 板块主力资金净流入(akshare,东方财富数据,今日/5d/10d)
- 北向资金行业持仓变化(5d/10d)
- 融资余额变化(5d/20d)

> 注:akshare 受网络/代理影响时,返回字段全 None(graceful 降级),不阻塞主流程。

### Step 2.8: 拉取宏观指标数据

```bash
python scripts/macro_policy/fetch_macro_indicators.py \
  --analysis-date {analysis_date} --cache-dir ./data --output -
```

得到:CPI / PPI / PMI / M0/M1/M2 / SHIBOR(过去 12 个月月度数据 + 当日 SHIBOR 快照)。

### Step 3.6: 行业基本面 agent 推理

基于 Step 2.6 数据推理:

- **景气度阶段**(底部 / 复苏 / 扩张 / 见顶):看营收/利润 YoY 趋势走向
- **估值水位**:看 PE/PB 历史分位
  - 分位 < 20%:极便宜 → 估值修复空间大,加分
  - 分位 20-50%:合理偏低
  - 分位 50-80%:合理偏贵
  - 分位 > 80%:极贵 → 风险高,减分
- **盈利质量**:ROE / 毛利率中位数趋势

输出:
```json
{
  "score": -100,
  "confidence": 0.0,
  "stage": "底部|复苏|扩张|见顶",
  "valuation_percentile": {"pe": 0.35, "pb": 0.42},
  "key_signals": []
}
```

判分原则:
- 景气向上 + 估值低 → 高分(+50 ~ +80)
- 景气见顶 + 估值高 → 低分(-50 ~ -80)
- 矛盾信号 → 中性

### Step 3.7: 行业资金流 agent 推理

基于 Step 2.7 数据推理:

- **共识强度**:主力 + 北向 + 融资三者是否同向(都流入/都流出)
- **趋势节奏**:5d vs 10d/20d,加速还是减速
- **板块排名**:今日板块在所有板块中的资金流排名

输出:
```json
{
  "score": -100,
  "confidence": 0.0,
  "main_inflow_5d_yi": -25.4,
  "northbound_change_5d_pct": -0.08,
  "margin_change_5d_pct": -0.03,
  "consensus": "all_outflow|mixed|all_inflow",
  "key_signals": []
}
```

判分原则:
- 三向同流入 + 排名靠前 → 高分(+60 ~ +80)
- 三向同流出 → 低分(-60 ~ -80)
- 主力出 + 北向进(分歧) → 中性偏弱

### Step 3.8: 行业宏观&政策 agent 推理

基于 Step 2.8 宏观数据 + **目标行业的特性**做"宏观→行业传导"判断:

| 行业 | 关键宏观因子 | 顺风条件 |
|---|---|---|
| 白酒 / 食品饮料 | CPI、可选消费、消费税政策 | CPI 温和上行 + 消费复苏 |
| 银行 | 利率(SHIBOR)、社融、息差 | 利率上行 + 社融扩张 |
| 地产 | 利率、社融、政策(限购) | 利率下行 + 政策放松 |
| 出口 / 消费电子 | 汇率、美国 PMI | 人民币贬值 + 海外需求强 |
| 周期(煤炭/有色) | PPI、PMI、原材料价格 | PPI 上行 + PMI > 50 |
| TMT(半导体/计算机) | M2、风险偏好 | M2 增速高 + 政策利好 |

输出:
```json
{
  "score": -100,
  "confidence": 0.0,
  "macro_alignment": "顺风|中性|逆风",
  "key_signals": [
    {"name": "cpi_yoy", "value": 0.022, "interpretation": "..."},
    {"name": "shibor_1y", "value": 0.025, "interpretation": "..."}
  ]
}
```

### Step 4: 其他 0 个 agent(全部激活)

✅ 5 个 analyst agent 全部激活(trend / fundamentals / capital_flow / leaders / macro_policy)。无 stub。

### Step 5: 综合裁判(5 维度,horizon-aware 权重)

按 forecast_horizon 加权:

| forecast_horizon | trend | fundamentals | capital_flow | leaders | macro_policy |
|---|---|---|---|---|---|
| 5d | 30% | 5% | 35% | 25% | 5% |
| 20d | 25% | 10% | 25% | 25% | 15% |
| 60d | 20% | 20% | 20% | 20% | 20% |
| 120d | 15% | 30% | 15% | 20% | 20% |
| 250d | 10% | 35% | 10% | 15% | 30% |

**短期重技术/资金/龙头(动量主导),长期重基本面/宏观(基本面回归)**。

裁判输出:

- **final_score** = `Σ (weight_i × agent_i.score)`,四舍五入到整数
- **final_confidence**(参考公式):
  ```
  ≈ 0.5 × avg(5 agent confidences)
  + 0.3 × score_agreement_factor       # 5 个 score 标准差小 → 一致
  + 0.2 × bull_bear_clarity_factor     # 信号一致性
  - horizon_uncertainty_penalty        # 5d:0, 20d:0.05, 60d:0.10, 120d:0.15, 250d:0.20
  ```
  - 上限 0.85(5 维度全激活,但仍受 horizon 长度的天然不确定性影响)
- **industry_boost** = `round(final_score / 50)`,clip 到 [-2, +2]
- **stock_in_industry.relative_position**:来自 leaders agent 的 target_position
- **industry_outlook.verdict**:综合 trend + fundamentals → 顺风 / 中性 / 逆风
- **industry_outlook.stage**:综合 trend.stage 和 fundamentals.stage

如果 ≤ 2 个 agent success → status = failed;3-4 个 success → status = partial,confidence ≤ 0.5。

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
| 走势数据不完整(< 60 个交易日) | `status=partial`,`confidence ≤ 0.4` |
| 龙头数据获取失败(daily_basic 当日返回空) | `status=partial`,leaders agent 输出 stub |
| 目标股不在行业成分股(刚转板/重命名) | rank=None,position="无法判断",continue with leaders |
| 基本面数据 fina_indicator 报告期未发布 | fundamentals agent 用最近完成季度,confidence ↓ |
| 资金流 akshare 网络失败(代理问题) | capital_flow agent 字段全 None,score=0,confidence=0,不算入加权 |
| 北向 / 融资余额数据缺失 | capital_flow agent 用可用部分,confidence ↓ |
| 宏观 PMI 接口无权限 | macro_policy agent 用其他指标(CPI/PPI/M2/SHIBOR),pmi 字段=null |
| 输出 JSON 校验失败 | 修正后重试 1 次,仍失败设 `status=failed`,`code=REASONING_FAILED` |
| ≤ 2 个 agent success | `status=failed` |
| 3-4 个 agent success | `status=partial`,`confidence ≤ 0.5` |
| 5 个 agent success | `status=success` |

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

输出(5 agent 全激活,horizon-aware 加权):

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260501_abc123",
  "analysis_date": "2026-05-01",
  "status": "success",
  "signal": "中性",
  "score": -15,
  "confidence": 0.7,
  "reasons": [
    "白酒 12M -19% 显著跑输沪深 300,但 3M 跌速放缓",
    "行业 PE 历史分位 35%,估值已具吸引力",
    "茅台是绝对龙头(市值 1.7 万亿,领先五粮液 4.6 倍)",
    "板块主力 5d 净流出 28 亿,北向减仓 8%,资金面共识偏空",
    "CPI 温和上行 + M2 增速回暖,宏观对消费品长期有利"
  ],
  "risks": [
    "行业系统性下行未止,资金面共识偏空可能延续",
    "短期消费税政策不确定性",
    "估值见底信号未明,可能继续杀估值"
  ],
  "summary": "白酒估值已便宜 + 茅台绝对龙头 + 宏观长期友好,但短期资金共识偏空,综合中性。",
  "metrics": {
    "latency_ms": 30000,
    "data_sources_used": ["tushare", "akshare"]
  },
  "module_specific": {
    "classification": {
      "primary_industry": {"system": "申万二级", "code": "801125.SI", "name": "白酒Ⅱ"},
      "related_concepts": []
    },
    "agent_breakdown": {
      "trend": {"score": -55, "confidence": 0.75, "stage": "下行", "key_signals": []},
      "fundamentals": {
        "score": 25, "confidence": 0.7,
        "stage": "底部",
        "valuation_percentile": {"pe": 0.35, "pb": 0.42},
        "key_signals": []
      },
      "capital_flow": {
        "score": -40, "confidence": 0.65,
        "main_inflow_5d_yi": -28.4, "consensus": "all_outflow",
        "key_signals": []
      },
      "leaders": {
        "score": 10, "confidence": 0.65,
        "target_position": "绝对龙头", "rank_in_industry": 1,
        "rs_vs_leaders_avg_1m": 0.99, "key_signals": []
      },
      "macro_policy": {
        "score": 30, "confidence": 0.6,
        "macro_alignment": "顺风",
        "key_signals": []
      }
    },
    "industry_outlook": {
      "verdict": "中性偏弱",
      "stage": "下行",
      "horizon": "60d",
      "rationale": "走势资金面偏弱,但估值底部 + 宏观顺风给予支撑"
    },
    "stock_in_industry": {
      "relative_position": "绝对龙头",
      "industry_boost": 0,
      "rationale": "行业综合 -15 中性偏弱,龙头地位不足以扭转方向"
    },
    "weights_used": {
      "trend": 0.20, "fundamentals": 0.20, "capital_flow": 0.20,
      "leaders": 0.20, "macro_policy": 0.20,
      "_note": "horizon=60d 按 5 维度等权"
    }
  }
}
```
