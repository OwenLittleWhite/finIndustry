# industry-analysis

> stock-forecast-system 的**行业分析子 skill**。输入 A 股股票代码 → 输出该股**所属行业层面**的走势、龙头、景气度分析,作为总控合成最终预测的"行业维度"输入。

**状态**:🟢 v1.1 / Plan 2b 已交付 / **91 测试全过** / **5 个 analyst agent 全激活** / 真实 Tushare 数据已跑通

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
| 行业基本面 | ✅ Plan 2b | 行业聚合营收/利润 YoY、ROE 中位数、**PE/PB 历史 5 年分位** |
| 行业资金流 | ✅ Plan 2b | 板块主力(akshare)+ 北向(hk_hold 聚合)+ 融资余额(margin_detail 聚合)|
| 行业宏观&政策 | ✅ Plan 2b | CPI / PPI / PMI / M0/M1/M2 / SHIBOR(LLM 做"宏观→行业传导"判断)|
| 看多/看空辩论 + 综合裁判 | 📋 Plan 3 | 5 agent 已激活,可加辩论层提升判断质量 |

**5 agent 都是"行业聚合层面"**,跟个股层面 sub-skill(financial-analysis / capital-flow-analysis / event-announcement-analysis / macro-analysis)互补。具体边界见 [docs/integration.md 第 2 节](docs/integration.md)。

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
│   ├── fundamentals/   (行业聚合财务 + PE/PB 历史分位) — Plan 2b
│   ├── capital/        (行业主力 / 北向 / 融资融券) — Plan 2b
│   ├── macro_policy/   (CPI/PPI/PMI/M2/SHIBOR) — Plan 2b
│   └── output_validator.py
├── shared_schemas/                       # JSON Schema
├── tests/                                # 91 测试
│   ├── unit/(每个 agent 都有专门测试),integration/, fixtures/
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

## 给总控负责人的对齐建议

> Plan 2b 已交付,5 个 agent 都做的是**行业聚合层面**(跟个股层面互补)。但仍建议跟其他 sub-skill 负责人对齐,确保信号合成时不重复加权。

| 我们做(行业聚合) | 其他 sub-skill(个股层面) |
|---|---|
| 行业聚合 PE 历史分位、行业 ROE 趋势 | financial-analysis 做个股 PE / 个股 ROE |
| 板块主力净流入、北向行业偏好、融资余额行业聚合 | capital-flow-analysis 做个股资金流 / 个股龙虎榜 |
| 宏观→行业传导(CPI/PPI/PMI/M2/SHIBOR + 行业敏感度) | macro-analysis 做整体宏观 / event 做个股公告 |

**总控合成时**,行业 skill 和个股层面 sub-skill 给的是**互补的两种信号**(行业 β + 个股 alpha),应分别加权,不重复。

详见 [docs/integration.md 第 2 / 6 节](docs/integration.md)。

---

## License / Author

Internal — stock-forecast-system 的子模块。

负责人:行业分析模块。Issue / 对齐 / 修改意见请在仓库 issue 里提。
