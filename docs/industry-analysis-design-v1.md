# 行业分析子 Skill 设计 v1

> **状态**:draft · **作者**:行业分析模块 · **日期**:2026-05-01
> **模块 id**:`industry_analysis` · **目录**:`modules/industry-analysis/`
> **契约**:遵循 [sub-skill-spec-v1.md](sub-skill-spec-v1.md)

## 1. 概要

`industry-analysis` 是 stock-forecast-system 的子 skill,职责:**输入一只 A 股股票,分析其所属行业层面的走势、龙头表现、景气度,输出对该股的行业层面影响判断**(给总控合成最终预测)。

**不直接预测股价**,只对"行业维度对该股的加成/拖累"作结构化判断。

### 与其他子 skill 的边界

| 其他子 skill | 处理 | 我们不碰 |
|---|---|---|
| 技术 | 个股 K 线、技术指标 | 个股技术面 |
| 新闻 | 个股新闻 | 个股层面新闻 |
| 宏观 | 整体宏观环境 | 宏观本身 |
| 财务 | 个股财务 | 个股财务报表 |

我们的领地 = **"行业聚合 + 龙头横向 + 宏观→行业的传导"**。

---

## 2. 架构总览

```
                    输入: { ticker, analysis_date, forecast_horizon, ... }
                                       │
                                       ▼
                           ┌─────────────────────┐
                           │ 数据层(Python 脚本)│
                           │ - 分类映射          │
                           │ - 行业指数 / 财务   │
                           │ - 资金流 / 龙头     │
                           │ - 宏观 / 政策       │
                           └─────────┬───────────┘
                                     │ 结构化数据 dict
                                     ▼
        ┌─────────────────────────────────────────────────────┐
        │     5 个分析 agent(并行)                           │
        │                                                     │
        │  [行业走势] [行业基本面] [行业资金]                  │
        │  [龙头分析] [行业宏观&政策]                          │
        │                                                     │
        │  每个输出:score / confidence / 信号清单            │
        └─────────────────────────┬───────────────────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  ▼                                ▼
          [看多 agent: 5 论据]            [看空 agent: 5 论据]
                  │                                │
                  └──────────────┬─────────────────┘
                                 ▼
                        [裁判 agent]
                                 │
                                 ▼
                  module_output_v1 JSON
```

**8 步 LLM 推理**(5 并行 + 看多/看空并行 + 裁判),由 `SKILL.md` 编排,**宿主 LLM 执行**(不直接调 LLM API)。

---

## 3. 5 个分析 agent

### 3.1 行业走势 Agent

**职责**:判断行业指数自身走势阶段、行业内分化程度。

**输入数据**:
- 申万二级行业指数日线(`sw_daily`)
- 沪深 300 / 上证综指日线(`index_daily`)
- 行业内成分股日线(用于涨跌家数比)
- 概念板块指数日线(辅助)

**核心信号**:
- 多窗口涨跌(随 `forecast_horizon` 调整)
- 行业 vs 大盘相对强度(RS)
- 行业内涨跌家数比、涨停数(分化指标)
- 量价关系(量比、放量缩量)
- 趋势阶段(上升 / 震荡 / 下行 / 底部反转)

**输出**:
```json
{
  "score": -100,
  "confidence": 0.0,
  "stage": "上升趋势|震荡|下行|底部反转",
  "key_signals": [
    {"name": "1m_return", "value": 0.082, "interpretation": "+1"},
    {"name": "rs_vs_csi300", "value": 1.18, "interpretation": "+1"}
  ]
}
```

### 3.2 行业基本面 Agent

**职责**:判断行业景气度阶段 + 估值水位。

**输入数据**:
- 行业成分股财务(`fina_indicator`、`income`,近 8 季度)
- 行业 PE/PB 当前与历史(`daily_basic`,过去 5 年)

**核心信号**:
- 行业聚合营收 / 利润 YoY 趋势
- 行业 ROE / 毛利率近 8 季度走向
- 行业 PE / PB 当前历史分位(过去 5 年)
- 景气度阶段(底部 / 复苏 / 扩张 / 见顶)

**输出**:
```json
{
  "score": 0,
  "confidence": 0.0,
  "stage": "底部|复苏|扩张|见顶",
  "valuation_percentile": {"pe": 0.35, "pb": 0.42},
  "key_signals": [...]
}
```

### 3.3 行业资金 Agent ⭐️

**职责**:看聪明钱在加仓还是减仓(本 skill 最差异化的角度)。

**输入数据**:
- 行业主力资金净流入(akshare `stock_sector_fund_flow_rank`)
- 北向资金行业偏好(Tushare `hk_hold` + 行业聚合)
- 行业 ETF 资金流(akshare `fund_etf_fund_flow_em`)
- 融资融券余额行业聚合(Tushare `margin_detail` + 聚合)
- 概念板块资金(akshare,仅当概念热度 high)

**核心信号**:
- 主力资金近 5 / 10 / 20 / 60 日累计净流入(随 horizon)
- 北向资金近 5 / 10 日增减仓
- ETF 申赎方向
- 融资余额变化
- 主力 / 北向是否同向(共识强度)

**输出**:
```json
{
  "score": 0,
  "confidence": 0.0,
  "key_signals": [
    {"name": "main_capital_5d", "value": 1.2e9, "interpretation": "+1"},
    {"name": "northbound_alignment", "value": "同向加仓", "interpretation": "+2"}
  ]
}
```

### 3.4 龙头 Agent

**职责**:识别龙头并判断目标股票相对位置。

**输入数据**:
- 行业 Top 5 市值龙头(`index_member_all` + `daily_basic`)
- 龙头股近 1M / 3M 日线(`daily`)
- 龙头股近 30 天新闻(akshare `stock_news_em`)
- 概念龙头(akshare 概念成分股)

**核心信号**:
- 龙头是否带头领涨
- 目标股 vs 龙头动量对比(RS、相关性)
- 目标股梯队位置(绝对龙头 / 二线龙头 / 跟随 / 落后)
- 龙头近期催化清单
- 概念龙头映射(目标股属于哪个热门概念的龙头)

**输出**:
```json
{
  "score": 0,
  "confidence": 0.0,
  "leaders": [
    {"ticker": "000858", "name": "五粮液", "1m_return": 0.05, "3m_return": 0.18, "pe_pct": 0.32}
  ],
  "target_position": "绝对龙头|二线龙头|跟随|落后",
  "concept_leader_mapping": {}
}
```

### 3.5 行业宏观&政策 Agent

**职责**:宏观环境对行业是顺风/逆风,政策催化与风险。

**输入数据**:
- CPI / PPI / PMI / 社融 / M2 / SHIBOR(Tushare)
- 行业相关新闻(akshare `stock_news_em` + 关键词过滤)
- 政策搜索(WebSearch 工具,近 30 天)

**核心信号**:
- 关键宏观因子对该行业的方向(白酒看 CPI、银行看利率、地产看社融)
- 近期政策催化清单
- 近期政策风险清单

**输出**:
```json
{
  "score": 0,
  "confidence": 0.0,
  "macro_alignment": "顺风|中性|逆风",
  "policy_catalysts": [],
  "policy_risks": []
}
```

---

## 4. 看多 / 看空 / 裁判 Agent

### 4.1 看多 Agent

**输入**:5 个分析 agent 报告 + 目标股票上下文

**职责**:
- 提炼最强 5 条看多论据
- 每条标注来源 agent
- 预判看空可能反驳点,做预防性反驳

**输出**:
```json
{
  "bull_points": [
    {
      "point": "...",
      "from_agent": "fundamentals|trend|capital|leaders|macro_policy",
      "rebuttal_to_likely_bear": "..."
    }
  ]
}
```

### 4.2 看空 Agent

镜像看多 agent。输出 `bear_points`。

### 4.3 裁判 Agent

**输入**:5 agent 报告 + bull_points + bear_points + `forecast_horizon`

**职责**:
1. 综合 5 个 agent 评分,按 horizon 权重表加权
2. 评估 bull vs bear 论据强度
3. 输出最终 `score`、`confidence`、`industry_outlook`
4. 给出 `stock_in_industry.industry_boost`(行业对目标股加成,-2~+2)
5. 派生 `signal`(由 score 按 ±30 阈值)

**输出**:符合 `module_output_v1` 的所有顶层字段 + `module_specific` 扩展。

---

## 5. 时间窗口(horizon-aware)

各 agent 看的窗口随 `forecast_horizon` 动态调整:

| `forecast_horizon` | 走势主窗口 | 资金主窗口 | 基本面财报窗口 | 宏观窗口 |
|---|---|---|---|---|
| 5d | 1M | 5d / 10d | 4Q | 3M |
| 20d | 1M / 3M | 10d / 20d | 4Q | 3M / 6M |
| 60d | 3M / 6M | 20d / 60d | 4Q / 8Q | 6M / 12M |
| 120d | 3M / 6M / 12M | 60d | 8Q | 12M |
| 250d | 6M / 12M | 60d | 8Q | 12M+ |

估值历史分位**统一用 5 年**(基准不变)。

---

## 6. 评分与置信度

### 6.1 5 个 agent 各自

- `score`:-100 ~ 100 整数
- `confidence`:0–1 浮点(**Hybrid 方案**)
  - `ceiling = 数据完整度`(脚本计算,缺失关键数据 → 低)
  - `base = LLM 自评`(基于信号一致性)
  - `final = min(ceiling, base)`

### 6.2 Score 描述统一约定

| 区间 | 描述 |
|---|---|
| > +60 | 强 |
| +30 ~ +60 | 中等强 |
| -30 ~ +30 | 中性 |
| -60 ~ -30 | 中等弱 |
| < -60 | 弱 |

prompt 模板里强制各 agent 使用同一套描述,Judge 才能一致地合成。

### 6.3 裁判合成参考权重(prompt 提示)

| horizon | 走势 | 基本面 | 资金 | 龙头 | 宏观政策 |
|---|---|---|---|---|---|
| 5d | 30% | 5% | 35% | 25% | 5% |
| 20d | 25% | 10% | 25% | 25% | 15% |
| 60d | 20% | 20% | 20% | 20% | 20% |
| 120d | 15% | 30% | 15% | 20% | 20% |
| 250d | 10% | 35% | 10% | 15% | 30% |

参考权重,Judge 可基于辩论调整。**实际使用的权重写入 `module_specific.weights_used`**。

### 6.4 Judge 的 final_confidence 计算(prompt 提示)

```
final_confidence ≈
    0.5 × avg(5 agent confidences)         # 基础信心
  + 0.3 × score_agreement_factor           # 5 个 score 标准差小 → 一致
  + 0.2 × bull_bear_clarity_factor         # 一边压倒性 → 高
  - horizon_uncertainty_penalty            # 5d:0, 20d:0.05, 60d:0.10, 120d:0.15, 250d:0.20
```

Judge 给出的最终 confidence 不允许超过 1.0,也不允许低于 0.0。

---

## 7. 数据源映射(汇总)

| Agent | Tushare | akshare(东方财富) | 其他 |
|---|---|---|---|
| 走势 | `sw_daily`、`index_daily`、`daily`、`index_member_all` | `stock_board_concept_index_em` | - |
| 基本面 | `fina_indicator`、`income`、`daily_basic` | - | - |
| 资金 | `hk_hold`、`margin_detail` | `stock_sector_fund_flow_rank`、`fund_etf_fund_flow_em` | - |
| 龙头 | `index_member_all`、`daily_basic`、`daily` | `stock_news_em`、`stock_board_concept_cons_em` | - |
| 宏观&政策 | `cn_cpi`、`cn_ppi`、`cn_pmi`、`cn_m`、`shibor` | `stock_news_em`、`macro_china_*` | WebSearch 工具 |

数据脚本统一用 **SQLite 缓存**,key = `(api_name, params, analysis_date)`,防止重复请求。

### 行业 ETF 映射表(自维护)

文件:`scripts/classification/industry_etf_mapping.yaml`

```yaml
# 申万二级行业 → ETF 列表
"801080":  # 半导体
  - ticker: "159995"
    name: "半导体ETF"
  - ticker: "512760"
    name: "芯片ETF"
"801120":  # 食品饮料
  - ticker: "512690"
    name: "酒ETF"
# ... 覆盖申万二级 30 个主要行业
```

后续 v1.1 扩展。

---

## 8. 输出 Schema(`module_output_v1` + 扩展)

### 8.1 通用必备字段(规范要求)

```json
{
  "module_id": "industry_analysis",
  "module_name": "行业分析模块",
  "module_version": "1.0.0",
  "schema_version": "module_output_v1",
  "request_id": "req_20260501_abc123",
  "analysis_date": "2026-05-01",
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
    "data_sources_used": ["tushare", "akshare"]
  }
}
```

### 8.2 `module_specific` 扩展字段

```json
{
  "module_specific": {
    "classification": {
      "primary_industry": {
        "system": "申万二级",
        "code": "801080",
        "name": "半导体"
      },
      "related_concepts": [
        {"name": "芯片国产替代", "heat_rank": 3, "heat_score": 0.85}
      ]
    },
    "agent_breakdown": {
      "trend":         { "score": 60, "confidence": 0.7, "stage": "...", "key_signals": [] },
      "fundamentals":  { "score":  0, "confidence": 0.8, "stage": "...", "valuation_percentile": {} },
      "capital_flow":  { "score": 70, "confidence": 0.6, "key_signals": [] },
      "leaders":       { "score": 80, "confidence": 0.8, "leaders": [], "target_position": "..." },
      "macro_policy":  { "score": 30, "confidence": 0.5, "macro_alignment": "...", "policy_catalysts": [], "policy_risks": [] }
    },
    "industry_outlook": {
      "verdict": "顺风|中性|逆风",
      "stage": "底部|复苏|扩张|见顶",
      "horizon": "60d",
      "rationale": "..."
    },
    "stock_in_industry": {
      "relative_position": "绝对龙头|二线龙头|跟随|落后",
      "industry_boost": 1,
      "rationale": "..."
    },
    "debate": {
      "bull_points": [{"point": "...", "from_agent": "fundamentals"}],
      "bear_points": [{"point": "...", "from_agent": "macro_policy"}],
      "judge_summary": "..."
    },
    "weights_used": {
      "trend": 0.20, "fundamentals": 0.20, "capital_flow": 0.20,
      "leaders": 0.20, "macro_policy": 0.20
    }
  }
}
```

---

## 9. 错误处理

按 [sub-skill-spec-v1.md 第 6 节](sub-skill-spec-v1.md) 7 类 error code。

特殊情况处理:

| 情况 | 处理 |
|---|---|
| 股票无法找到申万分类(ST/退市/新股) | `status=failed`, `code=DATA_NOT_FOUND`, `missing=["classification"]` |
| 行业基本面数据缺失(财报未披露) | `status=partial`, `missing=["agent_breakdown.fundamentals"]` |
| 行业 ETF 不存在 | 不影响 status,资金 agent 跳过 ETF 信号,confidence ↓ |
| LLM agent 输出非 JSON | 重试 1 次,仍失败则该 agent 视为 failed |
| 5 agent 中 ≤ 2 个 success | `status=failed` |
| 3-4 个 success | `status=partial`,`confidence` ≤ 0.5 |
| 5 个 success | `status=success` |

`signal`、`score`、`confidence` 在 `failed` 时一律 null;在 `partial` 时给低 confidence 的弱信号。

---

## 10. 文件结构

```
finIndustry/  (= modules/industry-analysis/)
├── SKILL.md                           # ⭐️ 主入口
├── module_manifest.yaml
├── README.md
├── input_contract.md
├── output_contract.md
├── scripts/                           # 数据脚本(纯 Python)
│   ├── classification/
│   │   ├── fetch_industry_classification.py
│   │   ├── fetch_concept_mapping.py
│   │   └── industry_etf_mapping.yaml
│   ├── trend/
│   │   ├── fetch_industry_index.py
│   │   ├── fetch_market_index.py
│   │   └── compute_breadth.py
│   ├── fundamentals/
│   │   ├── fetch_industry_financials.py
│   │   ├── fetch_industry_valuation.py
│   │   └── compute_percentile.py
│   ├── capital/
│   │   ├── fetch_main_flow.py
│   │   ├── fetch_northbound.py
│   │   ├── fetch_etf_flow.py
│   │   └── fetch_margin.py
│   ├── leaders/
│   │   ├── fetch_industry_leaders.py
│   │   ├── fetch_leader_news.py
│   │   └── compute_relative_strength.py
│   ├── macro_policy/
│   │   ├── fetch_macro_indicators.py
│   │   └── fetch_industry_news.py
│   ├── common/
│   │   ├── cache.py                   # SQLite 缓存
│   │   ├── tushare_client.py
│   │   ├── akshare_client.py
│   │   └── derive_signal.py           # signal from score
│   ├── output_validator.py            # JSON Schema 校验
│   └── tests/                         # 脚本单元测试
├── tests/                             # skill 集成测试
│   ├── fixtures/
│   └── golden_outputs/
├── data/                              # SQLite 缓存(gitignore)
└── references/
    ├── papers.md                      # 论文清单(我们之前研究的)
    └── industry-rules/                # 行业特殊规则(后续扩展)
```

---

## 11. SKILL.md 内容大纲

### Frontmatter

```yaml
---
name: industry-analysis
description: 当总控需要分析 A 股股票所在行业的走势、龙头表现、行业景气度时调用。输入股票代码 + 上下文,输出符合 module_output_v1 的行业分析 JSON,包含 -100~100 的行业评分、对该股的行业层面影响判断、关键催化与风险。仅适用 A 股。
version: 1.0.0
schema_version: module_output_v1
inputs:
  required: [ticker, analysis_date]              # 业务必填(v1.1)
  system_filled: [request_id, schema_version]    # 总控自动填
  optional: [stock_name, market, forecast_horizon, current_price]
outputs: module_output_v1
---
```

### Body 章节

1. **When to Use**:何时被总控调用
   - `forecast_horizon ≥ 20d` 强烈建议
   - 用户问"这只股票所在行业..."必调
2. **Inputs**:字段表 + 示例
3. **Execution Steps**(给宿主 LLM 的 step-by-step):
   - **Step 1**:运行 `scripts/classification/*.py`,获得申万二级 + 关联概念
   - **Step 2**:并行运行 5 组数据脚本(走势/基本面/资金/龙头/宏观),拿到结构化数据
   - **Step 3**:用 5 个分析 prompt 模板分别推理(并行,5 次 LLM 调用)
   - **Step 4**:用 bull / bear prompt 推理(并行,2 次 LLM 调用)
   - **Step 5**:用 judge prompt 推理,综合所有输入,产生最终 `module_output_v1` JSON(1 次 LLM 调用)
   - **Step 6**:运行 `scripts/output_validator.py` 校验 JSON,失败则修正后重试 1 次
4. **Output JSON Schema**:完整 schema + 示例
5. **Error Handling**:见第 9 节
6. **Examples**:1 个完整 input → output 示例(贵州茅台)

---

## 12. 测试策略

### 12.1 单元测试(`scripts/tests/`)

每个 fetcher / computer 都有测试,用 fixture 数据,**不打外部 API**。

### 12.2 集成测试(`tests/`)

≥ 4 个 ticker 的 golden output:

| Ticker | 名称 | 用例代表性 |
|---|---|---|
| 600519 | 贵州茅台 | 白酒龙头,行业逻辑稳定 |
| 002475 | 立讯精密 | 消费电子,中盘,行业波动大 |
| 300750 | 宁德时代 | 新能源龙头,行业逻辑变化 |
| 688981 | 中芯国际 | 半导体,概念多重,科创板 |

加边界用例:
- 1 个 `partial` 状态(数据不全,如新股)
- 1 个 `failed` 状态(数据源 API 不可用,mock)
- 1 个 ST 股(行业逻辑被特殊规则覆盖)

`make test` 应**独立可跑**,不依赖外部 API。

---

## 13. 开放问题(v1 后再考虑)

- **行业类型分诊**(周期 / 成长 / 价值 / 防御):v2 引入,提升 prompt 针对性(参考 P1GPT)
- **多轮辩论**:第一版只 1 轮,后续看效果决定是否升级
- **跨市场支持**:港股、美股 GICS 行业分类 v2 考虑
- **产业链事件捕捉**:碳酸锂价格、WSTS 半导体周期等行业特有指标 v2 引入
- **概念热度算法**:目前依赖 akshare 现成数据,v2 自定义计算
- **回测模式**:批量 ticker × 日期回测的并发 / 限流策略

---

## 14. 参考论文

- [Top-Down Sector Allocation](https://arxiv.org/html/2503.09647v5)(arxiv 2503.09647):自上而下板块配置,影响 agent 5 设计
- [Sector-Aware Reasoning](https://link.springer.com/article/10.1007/s10614-026-11329-4)(Springer 2026):GICS prompt 注入思路
- [TradingAgents](https://arxiv.org/abs/2412.20138)(arxiv 2412.20138):多 agent 辩论范式
- [P1GPT](https://arxiv.org/html/2510.23032v1)(arxiv 2510.23032):行业专家路由(v2 参考)
- [CN-Buzz2Portfolio](https://arxiv.org/html/2603.22305v1)(arxiv 2603.22305):中文市场板块配置参考
- [FINSABER](https://arxiv.org/html/2505.07078v5)(arxiv 2505.07078):严格回测框架,警示 LLM 策略局限
- [FinRpt](https://arxiv.org/abs/2511.07322)(arxiv 2511.07322):多 agent 研报生成范式

---

## 15. 验收 checklist(对齐 sub-skill-spec-v1.md 第 13 节)

- [ ] `SKILL.md` frontmatter 完整,description 明确触发场景
- [ ] `module_manifest.yaml` 字段齐全
- [ ] `README.md` 含原理、数据源、依赖
- [ ] 输出 JSON 通过 `shared/schemas/module_output_v1.schema.json` 校验
- [ ] 通过 ≥ 4 个 golden output 测试
- [ ] 通过 partial 和 failed 状态测试
- [ ] 数据脚本 100% 通过单元测试
- [ ] 无 LLM API 直接调用
- [ ] 无跨 modules 引用
- [ ] 通过 `analysis_date` 防 lookahead bias 验证

---

**版本**:v1 · **状态**:draft · **下一步**:用户审阅 → writing-plans skill 转入实现计划
