# industry-analysis

> stock-forecast-system 的**行业分析子 skill**。输入 A 股股票代码 → 输出该股**所属行业层面**的走势、龙头、景气度分析,作为总控合成最终预测的"行业维度"输入。

**状态**:🟢 v1.1 / Plan 2a 已交付 / 64 测试全过 / 真实 Tushare 数据已跑通

---

## ⚡ 谁在看?5 秒导航

| 你是 | 直接去 |
|---|---|
| 🤝 **总控 skill 对接人** | [**docs/integration.md**](docs/integration.md) — 5 分钟看懂怎么调用、输出长啥样、错误怎么处理 |
| 👷 **本仓库开发者** | 下面 [Quick start](#quick-start) → [SKILL.md](SKILL.md) → [开发文档](#开发文档) |
| 📐 **设计 / 产品 / 审阅** | [docs/industry-analysis-design-v1.md](docs/industry-analysis-design-v1.md)(架构) + [docs/sub-skill-spec-v1.md](docs/sub-skill-spec-v1.md)(全局子 skill 规范) |
| 🧐 **总控负责人,看子 skill 全景规范** | [docs/sub-skill-spec-v1.md](docs/sub-skill-spec-v1.md)(v1.1) |

---

## 真实输出示范(2026-04-30 跑 600519 贵州茅台)

```
trend agent:    score = -55  (白酒 12M 跑输沪深 300 RS=0.635,行业内 3 涨 16 跌)
leaders agent:  score = +10  (茅台是绝对龙头,市值 1.7 万亿领先五粮液 4.6 倍)
裁判综合:        score = -23  (行业弱与龙头地位部分对冲)→ signal "中性"

Top 5 白酒龙头:
  600519.SH  贵州茅台  17341 亿  1M -5.11%  3M +3.11%  PE 21.0  ← 目标股,绝对龙头
  000858.SZ  五粮液    3768 亿  1M -7.00%  3M -3.90%  PE 13.3
  600809.SH  山西汾酒  1749 亿  1M -0.71%  3M -11.11% PE 15.9
  ...
```

完整 JSON:[outputs/run_live.json](outputs/run_live.json)

---

## 当前能力 / 路线图

| Agent | 状态 | 信号源 |
|---|---|---|
| 行业走势 | ✅ Plan 1 | 申万二级指数 + 沪深 300 + 行业内涨跌家数 |
| 龙头分析 | ✅ Plan 2a | Top 5 市值龙头 + 1M/3M 涨跌 + 估值 + 目标股位置 |
| 行业基本面(行业 PE 分位、行业 ROE 聚合)| ⏳ Plan 2b stub | 待跟 financial-analysis 对齐边界 |
| 行业资金流(板块主力 / 北向 / ETF) | ⏳ Plan 2b stub | 待跟 capital-flow-analysis 对齐边界 |
| 行业宏观&政策(宏观→行业传导) | ⏳ Plan 2b stub | 待跟 macro-analysis / event 对齐边界 |
| 看多/看空辩论 + 裁判 | 📋 Plan 3 | 5 agent 都激活后再做 |

**重要**:Plan 2b 的 3 个 agent 跟其他子 skill 名字看起来撞,但**我们做的是行业聚合层面**,不是个股层面。具体边界见 [docs/integration.md 第 2 / 9 节](docs/integration.md)。

---

## Quick Start

### 安装

```bash
git clone git@github.com-personal:OwenLittleWhite/finIndustry.git  # 或 https
cd finIndustry
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 配置 Tushare token

```bash
cp .env.example .env
# 编辑 .env,把 your_tushare_pro_token_here 替换为你的真实 token
# 申请地址: https://tushare.pro/user/token (需要 ≥5000 积分跑全部接口)
```

### 跑测试

```bash
pytest tests/                           # 全套 64 个测试(用 mock,不打 API)
pytest tests/unit/ -v                   # 只单测
pytest tests/integration/ -v            # 集成(端到端 + JSON Schema 校验)
```

### 真实数据冒烟(跑 600519)

```bash
python scripts/classification/fetch_industry_classification.py \
  --ticker 600519 --analysis-date 2026-04-30 --cache-dir ./data

python scripts/leaders/fetch_industry_leaders.py \
  --industry-l2-code 801125.SI --analysis-date 2026-04-30 --cache-dir ./data
```

完整流程见 [SKILL.md](SKILL.md)。

---

## 开发文档

| 文档 | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | Skill 主入口(给宿主 LLM 看的执行步骤) |
| [docs/integration.md](docs/integration.md) | **总控对接指南**(怎么调用 / 输出 / 错误处理) |
| [docs/industry-analysis-design-v1.md](docs/industry-analysis-design-v1.md) | 详细架构设计(5 个 agent + 辩论 + 裁判) |
| [docs/sub-skill-spec-v1.md](docs/sub-skill-spec-v1.md) | 全局子 skill 规范 v1.1(适用所有 sub-skill) |
| [docs/plans/](docs/plans/) | 历史实施计划 |
| [input_contract.md](input_contract.md) | 输入字段详解 |
| [output_contract.md](output_contract.md) | 输出字段详解 |
| [shared_schemas/module_output_v1.schema.json](shared_schemas/module_output_v1.schema.json) | JSON Schema 校验文件 |
| [module_manifest.yaml](module_manifest.yaml) | 模块元数据(机器可读) |

---

## 项目结构

```
finIndustry/
├── SKILL.md                              # 主入口(被宿主 LLM 读取执行)
├── module_manifest.yaml / *_contract.md  # 元数据 + 输入/输出契约
├── scripts/
│   ├── common/         (cache + tushare/akshare client + signal 派生)
│   ├── classification/ (申万二级 + 概念映射)
│   ├── trend/          (行业指数 + 大盘 + breadth) — Plan 1
│   ├── leaders/        (Top 5 龙头 + 目标股位置) — Plan 2a
│   └── output_validator.py
├── shared_schemas/                       # JSON Schema
├── tests/                                # 64 测试
│   ├── unit/, integration/, fixtures/
│   └── conftest.py
├── docs/                                 # 文档
└── outputs/                              # 真实数据跑出来的 JSON 样本
```

---

## 数据源 / 依赖

| 数据 | 来源 | 备注 |
|---|---|---|
| 申万二级行业分类、行业指数日线、个股日线、宏观、概念 | **Tushare PRO** | 需 ≥5000 积分 |
| 板块资金流、个股新闻 | akshare(东方财富/同花顺) | 免费,但**走代理时部分接口可能受限**(代码已加 NO_PROXY 白名单 + graceful 降级) |

**Python**:3.10+
**主要依赖**:`tushare / akshare / pandas / pyyaml / jsonschema / python-dotenv`

---

## 给总控负责人的 3 个开放问题

(开发 Plan 2b 之前必须对齐,**详见 [docs/integration.md 第 9 节](docs/integration.md)**:)

1. 行业层面"资金流"归我做,还是 capital-flow-analysis 子 skill 做?
2. 行业层面"基本面聚合"归我做,还是 financial-analysis 做?
3. 行业层面"政策催化"归我做,还是 event-announcement-analysis 做?

回答完这 3 个问题,Plan 2b 才能开工。

---

## License / Author

Internal — stock-forecast-system 的子模块。

负责人:行业分析模块。Issue / 对齐 / 修改意见请在仓库 issue 里提。
