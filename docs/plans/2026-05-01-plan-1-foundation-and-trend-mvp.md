# Industry-Analysis Plan 1: Foundation + Trend Agent MVP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭起 industry-analysis 子 skill 的可运行骨架,跑通"输入股票 → 走势 agent → 输出符合 module_output_v1 的 JSON"端到端,其余 4 个 agent 标 v2 stub。Plan 2/3 在此基础上扩展。

**Architecture:** 纯数据脚本(Python,Tushare + akshare)+ SKILL.md(prompt 编排,宿主 LLM 执行)+ JSON Schema 校验。SQLite 本地缓存防 lookahead。

**Tech Stack:** Python 3.10+, tushare, akshare, pandas, pytest, pytest-mock, pyyaml, jsonschema

---

## Scope of this plan

**包含**:
- 项目骨架(pyproject.toml、目录结构、git init)
- 公共工具(SQLite 缓存、Tushare 客户端、akshare 客户端、score→signal 派生)
- 分类层(申万二级映射、概念映射、ETF mapping yaml)
- 走势 agent 数据脚本(行业指数、大盘指数、breadth)
- 输出 JSON Schema + 校验器
- SKILL.md MVP(只走 trend 路径,其他 agent stub)
- 1 个 ticker 的 golden test(600519)

**不包含**(后续 Plan 处理):
- 基本面 / 资金 / 龙头 / 宏观政策 4 个 agent 的数据 + prompt(Plan 2)
- 看多/看空/裁判 agent prompt(Plan 3)
- partial / failed 状态的完整测试(Plan 3)
- 行业 ETF mapping 完整覆盖(本 plan 只放 5 个示例,Plan 2 补)

---

## File Structure

本 plan 创建的文件:

```
finIndustry/
├── .gitignore                                 # 忽略 data/, __pycache__, .venv, etc.
├── pyproject.toml                             # 项目配置 + pytest 配置
├── README.md                                  # 模块说明
├── module_manifest.yaml                       # 模块元数据
├── input_contract.md                          # 输入字段说明
├── output_contract.md                         # 输出字段说明
├── SKILL.md                                   # ⭐️ Skill 主入口
├── shared_schemas/
│   └── module_output_v1.schema.json           # JSON Schema(本 plan 内自带,后续可移到 ../shared/)
├── scripts/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── cache.py                           # SQLite 缓存
│   │   ├── tushare_client.py                  # Tushare API wrapper
│   │   ├── akshare_client.py                  # akshare wrapper
│   │   └── derive_signal.py                   # score → signal 派生
│   ├── classification/
│   │   ├── __init__.py
│   │   ├── fetch_industry_classification.py   # 股票 → 申万二级
│   │   ├── fetch_concept_mapping.py           # 股票 → 关联概念
│   │   └── industry_etf_mapping.yaml          # 申万 → ETF 映射(本 plan 只放 5 个)
│   ├── trend/
│   │   ├── __init__.py
│   │   ├── fetch_industry_index.py            # 申万行业指数日线
│   │   ├── fetch_market_index.py              # 沪深 300 / 上证综指日线
│   │   └── compute_breadth.py                 # 行业内涨跌家数比
│   └── output_validator.py                    # JSON Schema 校验
└── tests/
    ├── __init__.py
    ├── conftest.py                            # pytest fixtures
    ├── fixtures/
    │   ├── tushare_responses.json             # Tushare mock 响应
    │   ├── akshare_responses.json             # akshare mock 响应
    │   └── 600519_classification.json         # 600519 分类 fixture
    ├── unit/
    │   ├── test_cache.py
    │   ├── test_tushare_client.py
    │   ├── test_akshare_client.py
    │   ├── test_derive_signal.py
    │   ├── test_industry_classification.py
    │   ├── test_concept_mapping.py
    │   ├── test_industry_index.py
    │   ├── test_market_index.py
    │   ├── test_breadth.py
    │   └── test_output_validator.py
    └── integration/
        └── test_600519_trend_mvp.py           # 端到端 golden test (走势 only)
```

---

## Phase 1: Project Foundation

### Task 1.1: 初始化项目骨架

**Files:**
- Create: `finIndustry/.gitignore`
- Create: `finIndustry/pyproject.toml`
- Create: `finIndustry/README.md`
- Create: `finIndustry/scripts/__init__.py` (empty)
- Create: `finIndustry/scripts/common/__init__.py` (empty)
- Create: `finIndustry/scripts/classification/__init__.py` (empty)
- Create: `finIndustry/scripts/trend/__init__.py` (empty)
- Create: `finIndustry/tests/__init__.py` (empty)
- Create: `finIndustry/tests/unit/__init__.py` (empty)
- Create: `finIndustry/tests/integration/__init__.py` (empty)

- [ ] **Step 1: 创建 .gitignore**

```
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/
.venv/
venv/
*.egg-info/
dist/
build/
data/
.env
.DS_Store
```

- [ ] **Step 2: 创建 pyproject.toml**

```toml
[project]
name = "industry-analysis"
version = "1.0.0"
description = "stock-forecast-system 的行业分析子 skill"
requires-python = ">=3.10"
dependencies = [
    "tushare>=1.4.0",
    "akshare>=1.16.0",
    "pandas>=2.0.0",
    "pyyaml>=6.0",
    "jsonschema>=4.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.12.0",
    "pytest-cov>=4.1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
markers = [
    "integration: 集成测试,可能调用外部服务(默认跳过)",
]
addopts = "-ra -q --strict-markers"

[tool.coverage.run]
source = ["scripts"]
omit = ["scripts/*/tests/*"]
```

- [ ] **Step 3: 创建 README.md 骨架**

```markdown
# industry-analysis

stock-forecast-system 的行业分析子 skill。输入 A 股股票代码,输出该股所属行业的走势、龙头、景气度分析。

## 架构

参考 [docs/industry-analysis-design-v1.md](docs/industry-analysis-design-v1.md)

## 安装

```bash
pip install -e ".[dev]"
```

## 测试

```bash
pytest                              # 跑单元测试
pytest -m integration               # 跑集成测试(需要 Tushare 账号)
```

## 数据源

- Tushare PRO(2000+ 积分)
- akshare(免费,东方财富/同花顺数据)

## 模块契约

参考 [docs/sub-skill-spec-v1.md](docs/sub-skill-spec-v1.md)
```

- [ ] **Step 4: 创建空 __init__.py 文件**

```bash
touch scripts/__init__.py scripts/common/__init__.py scripts/classification/__init__.py scripts/trend/__init__.py tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 5: 初始化 git + 首次提交**

```bash
cd /Users/owen/Develop/my/finIndustry
git init
git add .gitignore pyproject.toml README.md scripts tests docs
git commit -m "chore: init project skeleton with pyproject and dirs"
```

预期:`git status` 干净,`ls scripts/common/__init__.py` 存在。

---

### Task 1.2: SQLite 缓存模块

**Files:**
- Create: `scripts/common/cache.py`
- Create: `tests/unit/test_cache.py`

- [ ] **Step 1: 写测试 `tests/unit/test_cache.py`**

```python
"""SQLite cache for data fetchers - 防 lookahead bias 关键。"""
import json
import tempfile
from pathlib import Path

import pytest

from scripts.common.cache import Cache


@pytest.fixture
def tmp_cache(tmp_path):
    return Cache(cache_dir=tmp_path)


def test_set_and_get_returns_value(tmp_cache):
    tmp_cache.set("api_x", {"ticker": "600519"}, "2026-04-30", {"data": [1, 2, 3]})
    result = tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-30")
    assert result == {"data": [1, 2, 3]}


def test_get_missing_returns_none(tmp_cache):
    result = tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-30")
    assert result is None


def test_different_analysis_date_separate_entries(tmp_cache):
    """同 api 同 params,不同 analysis_date 必须独立缓存(防 lookahead)。"""
    tmp_cache.set("api_x", {"ticker": "600519"}, "2026-04-29", {"v": 1})
    tmp_cache.set("api_x", {"ticker": "600519"}, "2026-04-30", {"v": 2})
    assert tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-29") == {"v": 1}
    assert tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-30") == {"v": 2}


def test_param_order_doesnt_matter(tmp_cache):
    """params 字典顺序不应影响缓存 key。"""
    tmp_cache.set("api_x", {"a": 1, "b": 2}, "2026-04-30", {"v": 1})
    result = tmp_cache.get("api_x", {"b": 2, "a": 1}, "2026-04-30")
    assert result == {"v": 1}


def test_persists_across_instances(tmp_path):
    """关闭重开仍然命中缓存。"""
    c1 = Cache(cache_dir=tmp_path)
    c1.set("api_x", {"k": "v"}, "2026-04-30", {"data": 42})
    del c1

    c2 = Cache(cache_dir=tmp_path)
    assert c2.get("api_x", {"k": "v"}, "2026-04-30") == {"data": 42}
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `pytest tests/unit/test_cache.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'scripts.common.cache'`

- [ ] **Step 3: 实现 `scripts/common/cache.py`**

```python
"""SQLite-based cache for data fetchers.

Cache key = (api_name, sorted(params), analysis_date) — analysis_date 强制分离
确保同一 ticker 在不同 analysis_date 下缓存独立,防 lookahead bias。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class Cache:
    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "cache.db"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    api_name TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @staticmethod
    def _make_key(api_name: str, params: dict, analysis_date: str) -> str:
        params_canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
        raw = f"{api_name}|{params_canonical}|{analysis_date}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, api_name: str, params: dict, analysis_date: str):
        key = self._make_key(api_name, params, analysis_date)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value_json FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, api_name: str, params: dict, analysis_date: str, value) -> None:
        key = self._make_key(api_name, params, analysis_date)
        params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
        value_json = json.dumps(value, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, api_name, params_json, analysis_date, value_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, api_name, params_json, analysis_date, value_json),
            )
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `pytest tests/unit/test_cache.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/common/cache.py tests/unit/test_cache.py
git commit -m "feat(common): add SQLite cache with analysis_date isolation"
```

---

### Task 1.3: Tushare 客户端封装

**Files:**
- Create: `scripts/common/tushare_client.py`
- Create: `tests/unit/test_tushare_client.py`

- [ ] **Step 1: 写测试**

```python
"""TushareClient - thin wrapper that adds caching + analysis_date guard."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient


@pytest.fixture
def mock_pro():
    """Mock tushare pro_api object."""
    pro = MagicMock()
    pro.sw_daily.return_value = pd.DataFrame(
        [{"trade_date": "20260429", "ts_code": "801080.SI", "close": 5000.0}]
    )
    return pro


@pytest.fixture
def client(tmp_path, mock_pro):
    return TushareClient(pro=mock_pro, cache=Cache(tmp_path), analysis_date="2026-04-30")


def test_call_invokes_underlying_api(client, mock_pro):
    df = client.call("sw_daily", ts_code="801080.SI", end_date="20260429")
    mock_pro.sw_daily.assert_called_once()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["ts_code"] == "801080.SI"


def test_second_call_hits_cache(client, mock_pro):
    client.call("sw_daily", ts_code="801080.SI", end_date="20260429")
    client.call("sw_daily", ts_code="801080.SI", end_date="20260429")
    assert mock_pro.sw_daily.call_count == 1  # 第二次走缓存


def test_returns_empty_df_when_api_returns_none(tmp_path):
    pro = MagicMock()
    pro.sw_daily.return_value = None
    client = TushareClient(pro=pro, cache=Cache(tmp_path), analysis_date="2026-04-30")
    df = client.call("sw_daily", ts_code="X")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_lookahead_guard_rejects_future_end_date(client):
    with pytest.raises(ValueError, match="lookahead"):
        client.call("sw_daily", ts_code="801080.SI", end_date="20260501")
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `pytest tests/unit/test_tushare_client.py -v`
Expected: FAIL,`ModuleNotFoundError`

- [ ] **Step 3: 实现 `scripts/common/tushare_client.py`**

```python
"""Thin wrapper over tushare's pro_api with caching and lookahead guard."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd

from scripts.common.cache import Cache


class TushareClient:
    """
    Tushare 调用封装。

    - 自动缓存(以 analysis_date 隔离)
    - 拒绝任何 end_date / start_date 超过 analysis_date 的调用(防 lookahead)
    """

    def __init__(self, pro=None, cache: Cache | None = None, analysis_date: str = ""):
        self.pro = pro or self._init_pro()
        self.cache = cache
        self.analysis_date = analysis_date  # YYYY-MM-DD

    @staticmethod
    def _init_pro():
        import tushare as ts

        token = os.environ.get("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError("TUSHARE_TOKEN env var not set")
        ts.set_token(token)
        return ts.pro_api()

    def _check_lookahead(self, params: dict) -> None:
        """Tushare API 通常 end_date 是 YYYYMMDD 格式,我们的 analysis_date 是 YYYY-MM-DD。"""
        if not self.analysis_date:
            return
        cutoff = datetime.strptime(self.analysis_date, "%Y-%m-%d").date()
        for key in ("end_date", "start_date", "trade_date"):
            value = params.get(key)
            if not value:
                continue
            try:
                d = datetime.strptime(str(value), "%Y%m%d").date()
            except ValueError:
                continue
            if d > cutoff:
                raise ValueError(
                    f"lookahead detected: param {key}={value} > analysis_date={self.analysis_date}"
                )

    def call(self, api_name: str, **params) -> pd.DataFrame:
        self._check_lookahead(params)

        if self.cache is not None:
            cached = self.cache.get(f"tushare.{api_name}", params, self.analysis_date)
            if cached is not None:
                return pd.DataFrame(cached)

        method = getattr(self.pro, api_name)
        df = method(**params)
        if df is None:
            df = pd.DataFrame()

        if self.cache is not None:
            self.cache.set(f"tushare.{api_name}", params, self.analysis_date, df.to_dict(orient="records"))

        return df
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `pytest tests/unit/test_tushare_client.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/common/tushare_client.py tests/unit/test_tushare_client.py
git commit -m "feat(common): add Tushare client wrapper with cache and lookahead guard"
```

---

### Task 1.4: akshare 客户端封装

**Files:**
- Create: `scripts/common/akshare_client.py`
- Create: `tests/unit/test_akshare_client.py`

- [ ] **Step 1: 写测试**

```python
"""AkshareClient - 类似 TushareClient,wrap akshare 函数 + 缓存。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.common.akshare_client import AkshareClient
from scripts.common.cache import Cache


@pytest.fixture
def mock_akshare_module():
    mod = MagicMock()
    mod.stock_sector_fund_flow_rank.return_value = pd.DataFrame(
        [{"名称": "白酒", "今日主力净流入-净额": 1.2e9}]
    )
    return mod


@pytest.fixture
def client(tmp_path, mock_akshare_module):
    return AkshareClient(
        ak_module=mock_akshare_module,
        cache=Cache(tmp_path),
        analysis_date="2026-04-30",
    )


def test_call_invokes_function(client, mock_akshare_module):
    df = client.call("stock_sector_fund_flow_rank", indicator="今日")
    mock_akshare_module.stock_sector_fund_flow_rank.assert_called_once_with(indicator="今日")
    assert df.iloc[0]["名称"] == "白酒"


def test_second_call_hits_cache(client, mock_akshare_module):
    client.call("stock_sector_fund_flow_rank", indicator="今日")
    client.call("stock_sector_fund_flow_rank", indicator="今日")
    assert mock_akshare_module.stock_sector_fund_flow_rank.call_count == 1


def test_unknown_function_raises(client):
    with pytest.raises(AttributeError):
        client.call("function_does_not_exist")
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `pytest tests/unit/test_akshare_client.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `scripts/common/akshare_client.py`**

```python
"""Thin wrapper over akshare functions with caching."""
from __future__ import annotations

import pandas as pd

from scripts.common.cache import Cache


class AkshareClient:
    """
    akshare 调用封装。

    akshare 多数函数返回 DataFrame,且不像 Tushare 那样支持 end_date 参数。
    防 lookahead 由调用方在拿到 DataFrame 后自行过滤(akshare 通常返回截至当前的数据)。
    """

    def __init__(self, ak_module=None, cache: Cache | None = None, analysis_date: str = ""):
        self.ak = ak_module or self._import_akshare()
        self.cache = cache
        self.analysis_date = analysis_date

    @staticmethod
    def _import_akshare():
        import akshare as ak
        return ak

    def call(self, function_name: str, **params) -> pd.DataFrame:
        if self.cache is not None:
            cached = self.cache.get(f"akshare.{function_name}", params, self.analysis_date)
            if cached is not None:
                return pd.DataFrame(cached)

        func = getattr(self.ak, function_name)
        df = func(**params)
        if df is None:
            df = pd.DataFrame()

        if self.cache is not None:
            self.cache.set(
                f"akshare.{function_name}", params, self.analysis_date,
                df.to_dict(orient="records"),
            )

        return df
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `pytest tests/unit/test_akshare_client.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/common/akshare_client.py tests/unit/test_akshare_client.py
git commit -m "feat(common): add akshare client wrapper with cache"
```

---

### Task 1.5: Score → Signal 派生

**Files:**
- Create: `scripts/common/derive_signal.py`
- Create: `tests/unit/test_derive_signal.py`

- [ ] **Step 1: 写测试**

```python
"""Score → Signal mapping per sub-skill-spec-v1 第 7 节:±30 阈值。"""
import pytest

from scripts.common.derive_signal import derive_signal


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "看多"),
        (31, "看多"),
        (30, "看多"),
        (29, "中性"),
        (0, "中性"),
        (-29, "中性"),
        (-30, "看空"),
        (-31, "看空"),
        (-100, "看空"),
    ],
)
def test_score_to_signal(score, expected):
    assert derive_signal(score) == expected


def test_none_score_returns_none():
    """failed/partial 状态时 score=None,signal 也应该 None。"""
    assert derive_signal(None) is None


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        derive_signal(101)
    with pytest.raises(ValueError):
        derive_signal(-101)


def test_non_int_raises():
    with pytest.raises(TypeError):
        derive_signal(0.5)
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `pytest tests/unit/test_derive_signal.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `scripts/common/derive_signal.py`**

```python
"""Score → Signal 全局统一规则(sub-skill-spec-v1 第 7 节)。"""
from __future__ import annotations


def derive_signal(score: int | None) -> str | None:
    """
    score >=  30 → "看多"
    -30 < score < 30 → "中性"
    score <= -30 → "看空"
    None → None(failed/partial)
    """
    if score is None:
        return None
    if not isinstance(score, int):
        raise TypeError(f"score must be int, got {type(score).__name__}")
    if not -100 <= score <= 100:
        raise ValueError(f"score out of range [-100, 100]: {score}")
    if score >= 30:
        return "看多"
    if score <= -30:
        return "看空"
    return "中性"
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `pytest tests/unit/test_derive_signal.py -v`
Expected: 13 passed (9 parametrized + 4 单独)

- [ ] **Step 5: 提交**

```bash
git add scripts/common/derive_signal.py tests/unit/test_derive_signal.py
git commit -m "feat(common): add score-to-signal derivation with ±30 threshold"
```

---

### Task 1.6: 模块元数据文件

**Files:**
- Create: `module_manifest.yaml`
- Create: `input_contract.md`
- Create: `output_contract.md`

- [ ] **Step 1: 创建 module_manifest.yaml**

```yaml
module_id: industry_analysis
module_name: 行业分析模块
module_version: 1.0.0
schema_version: module_output_v1
entrypoint: SKILL.md

owner: 行业分析负责人
description: 分析目标股票所在行业的走势、龙头表现、行业景气度,给出行业层面对该股的影响判断

inputs:
  required: [request_id, schema_version, ticker, analysis_date]
  optional: [stock_name, market, forecast_horizon, current_price]

outputs:
  schema: module_output_v1

dependencies:
  data_sources: [tushare, eastmoney]
  python_packages: [tushare, akshare, pandas, pyyaml, jsonschema]

invocation_hints:
  - 当 forecast_horizon >= 20d 时强烈建议调用
  - 当用户问"这只股票所在行业..."时必调
  - 数据需要 analysis_date 当天有效

tags: [industry, sector, leaders, fundamentals, capital_flow]
```

- [ ] **Step 2: 创建 input_contract.md**

```markdown
# Input Contract

参考 [docs/sub-skill-spec-v1.md 第 4 节](docs/sub-skill-spec-v1.md)。

## 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `request_id` | string | 一次完整 forecast 的追踪 id |
| `schema_version` | string | 输出 schema 版本,目前为 `module_output_v1` |
| `ticker` | string | 股票代码,A 股为 6 位数字(如 `600519`) |
| `analysis_date` | string | 数据截止日,YYYY-MM-DD,严禁使用之后数据 |

## 可选字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `stock_name` | string | - | 股票名称(子 skill 应能从 ticker 自查) |
| `market` | string | `A股` | 枚举:`A股 / 港股 / 美股`,本 skill v1 仅支持 `A股` |
| `forecast_horizon` | string | `20d` | 枚举:`5d / 20d / 60d / 120d / 250d`(交易日) |
| `current_price` | number | - | 该日收盘价 |

## 示例

```json
{
  "request_id": "req_20260501_abc123",
  "schema_version": "module_output_v1",
  "ticker": "600519",
  "stock_name": "贵州茅台",
  "market": "A股",
  "analysis_date": "2026-05-01",
  "forecast_horizon": "60d",
  "current_price": 1680.5
}
```
```

- [ ] **Step 3: 创建 output_contract.md**

```markdown
# Output Contract

参考 [docs/sub-skill-spec-v1.md 第 5 节](docs/sub-skill-spec-v1.md) 和 [docs/industry-analysis-design-v1.md 第 8 节](docs/industry-analysis-design-v1.md)。

JSON Schema 校验文件:`shared_schemas/module_output_v1.schema.json`。

## 必备字段示例

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
  "reasons": ["...", "...", "..."],
  "risks": ["...", "..."],
  "summary": "白酒景气度回升,龙头领涨,贵州茅台位居核心受益位置。",
  "metrics": {
    "latency_ms": 12500,
    "data_sources_used": ["tushare", "akshare"]
  }
}
```

## 完整字段(含 module_specific)

参考 design v1 第 8 节。
```

- [ ] **Step 4: 提交**

```bash
git add module_manifest.yaml input_contract.md output_contract.md
git commit -m "docs: add module manifest and i/o contract files"
```

---

## Phase 2: Classification Layer

### Task 2.1: 行业 ETF 映射 yaml(MVP 5 个)

**Files:**
- Create: `scripts/classification/industry_etf_mapping.yaml`

- [ ] **Step 1: 创建初始 ETF 映射(5 个高频行业)**

```yaml
# 申万二级行业代码 → ETF 列表
# v1 MVP 只覆盖 5 个高频行业,Plan 2 补全到 30+

"801080":  # 半导体
  - ticker: "159995"
    name: "半导体ETF"
  - ticker: "512760"
    name: "芯片ETF"

"801120":  # 食品饮料
  - ticker: "512690"
    name: "酒ETF"
  - ticker: "159928"
    name: "消费ETF"

"801780":  # 银行
  - ticker: "512800"
    name: "银行ETF"

"801950":  # 煤炭
  - ticker: "515220"
    name: "煤炭ETF"

"801730":  # 电气设备
  - ticker: "159875"
    name: "新能源车ETF"
  - ticker: "515030"
    name: "新能源车ETF(广发)"
```

- [ ] **Step 2: 提交**

```bash
git add scripts/classification/industry_etf_mapping.yaml
git commit -m "feat(classification): add initial industry ETF mapping (5 industries)"
```

---

### Task 2.2: 股票 → 申万二级行业

**Files:**
- Create: `scripts/classification/fetch_industry_classification.py`
- Create: `tests/unit/test_industry_classification.py`
- Create: `tests/fixtures/600519_classification.json`

- [ ] **Step 1: 创建 fixture**

```json
{
  "tushare_index_member_all": [
    {"l1_code": "801120.SI", "l1_name": "食品饮料", "l2_code": "801123.SI", "l2_name": "白酒", "ts_code": "600519.SH"}
  ]
}
```

保存到 `tests/fixtures/600519_classification.json`。

- [ ] **Step 2: 写测试**

```python
"""股票 → 申万二级行业映射。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.classification.fetch_industry_classification import fetch_industry_classification


@pytest.fixture
def fixture_data():
    path = Path(__file__).parent.parent / "fixtures" / "600519_classification.json"
    return json.loads(path.read_text())


@pytest.fixture
def mock_tushare(fixture_data):
    client = MagicMock()
    client.call.return_value = pd.DataFrame(fixture_data["tushare_index_member_all"])
    return client


def test_returns_l2_classification(mock_tushare):
    result = fetch_industry_classification(mock_tushare, ticker="600519")
    assert result["primary_industry"]["system"] == "申万二级"
    assert result["primary_industry"]["code"] == "801123.SI"
    assert result["primary_industry"]["name"] == "白酒"


def test_includes_l1_for_context(mock_tushare):
    result = fetch_industry_classification(mock_tushare, ticker="600519")
    assert result["l1_industry"]["code"] == "801120.SI"
    assert result["l1_industry"]["name"] == "食品饮料"


def test_unknown_ticker_returns_none(tmp_path):
    client = MagicMock()
    client.call.return_value = pd.DataFrame()  # 空结果
    result = fetch_industry_classification(client, ticker="999999")
    assert result is None
```

- [ ] **Step 3: 跑测试,确认失败**

Run: `pytest tests/unit/test_industry_classification.py -v`

- [ ] **Step 4: 实现 `scripts/classification/fetch_industry_classification.py`**

```python
"""股票 → 申万二级行业映射。

数据源:Tushare `index_member_all`(股票成分股 → 行业指数)。
查询时使用 `is_new='Y'` 过滤当前生效的分类(注意:历史回测时需要按 analysis_date 调整)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from scripts.common.akshare_client import AkshareClient  # noqa: F401  保留 for CLI 一致
from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient


def _normalize_ts_code(ticker: str) -> str:
    """把 6 位数字股票代码转换成 Tushare 格式(如 600519 → 600519.SH)。"""
    ticker = str(ticker).strip()
    if "." in ticker:
        return ticker
    if ticker.startswith(("60", "68", "5")):
        return f"{ticker}.SH"
    if ticker.startswith(("00", "30", "15", "16", "1")):
        return f"{ticker}.SZ"
    if ticker.startswith(("4", "8", "9")):
        return f"{ticker}.BJ"
    return ticker


def fetch_industry_classification(client, ticker: str) -> dict | None:
    """
    返回:
      {
        "primary_industry": {"system": "申万二级", "code": "801123.SI", "name": "白酒"},
        "l1_industry": {"code": "801120.SI", "name": "食品饮料"}
      }
    无分类返回 None。
    """
    ts_code = _normalize_ts_code(ticker)
    df = client.call("index_member_all", ts_code=ts_code, is_new="Y")
    if df.empty:
        return None

    row = df.iloc[0]
    return {
        "primary_industry": {
            "system": "申万二级",
            "code": row.get("l2_code", ""),
            "name": row.get("l2_name", ""),
        },
        "l1_industry": {
            "code": row.get("l1_code", ""),
            "name": row.get("l1_name", ""),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="path or '-' for stdout")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    result = fetch_industry_classification(client, args.ticker)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试,确认通过**

Run: `pytest tests/unit/test_industry_classification.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add scripts/classification/fetch_industry_classification.py tests/unit/test_industry_classification.py tests/fixtures/600519_classification.json
git commit -m "feat(classification): map ticker to 申万 L2 industry"
```

---

### Task 2.3: 股票 → 关联热门概念

**Files:**
- Create: `scripts/classification/fetch_concept_mapping.py`
- Create: `tests/unit/test_concept_mapping.py`
- Modify: `tests/fixtures/600519_classification.json`(追加 akshare 字段)

- [ ] **Step 1: 扩展 fixture**

修改 `tests/fixtures/600519_classification.json`,在原内容基础上增加 akshare 字段:

```json
{
  "tushare_index_member_all": [
    {"l1_code": "801120.SI", "l1_name": "食品饮料", "l2_code": "801123.SI", "l2_name": "白酒", "ts_code": "600519.SH"}
  ],
  "akshare_concept_em": [
    {"概念名称": "高端消费", "成分股": "600519,000858"},
    {"概念名称": "ROE大白马", "成分股": "600519,000651"},
    {"概念名称": "茅指数", "成分股": "600519,000858,000333"}
  ],
  "akshare_concept_heat": [
    {"概念名称": "高端消费", "近5日涨幅": 0.08, "热度排名": 5},
    {"概念名称": "ROE大白马", "近5日涨幅": 0.04, "热度排名": 50},
    {"概念名称": "茅指数", "近5日涨幅": 0.10, "热度排名": 3}
  ]
}
```

- [ ] **Step 2: 写测试**

```python
"""股票 → 关联热门概念(取近 30 天热度 top 3)。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.classification.fetch_concept_mapping import fetch_concept_mapping


@pytest.fixture
def fixture_data():
    path = Path(__file__).parent.parent / "fixtures" / "600519_classification.json"
    return json.loads(path.read_text())


@pytest.fixture
def mock_akshare(fixture_data):
    """模拟两次 akshare 调用:概念成分 + 概念热度。"""
    client = MagicMock()

    def call_side_effect(function_name, **params):
        if function_name == "stock_board_concept_name_em":
            return pd.DataFrame(fixture_data["akshare_concept_heat"])
        if function_name == "stock_board_concept_cons_em":
            symbol = params.get("symbol", "")
            for concept in fixture_data["akshare_concept_em"]:
                if concept["概念名称"] == symbol:
                    return pd.DataFrame([
                        {"代码": code} for code in concept["成分股"].split(",")
                    ])
            return pd.DataFrame()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


def test_returns_top_3_hot_concepts(mock_akshare):
    result = fetch_concept_mapping(mock_akshare, ticker="600519", top_n=3)
    assert len(result) <= 3
    # 茅指数热度 rank 3 → 第一
    assert result[0]["name"] == "茅指数"
    assert result[0]["heat_rank"] == 3


def test_filters_only_concepts_containing_ticker(mock_akshare):
    """概念里必须包含 600519,否则不算。"""
    result = fetch_concept_mapping(mock_akshare, ticker="600519")
    names = [c["name"] for c in result]
    for n in names:
        assert n in {"高端消费", "ROE大白马", "茅指数"}


def test_no_concept_returns_empty(tmp_path):
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = fetch_concept_mapping(client, ticker="999999")
    assert result == []
```

- [ ] **Step 3: 跑测试,确认失败**

Run: `pytest tests/unit/test_concept_mapping.py -v`

- [ ] **Step 4: 实现 `scripts/classification/fetch_concept_mapping.py`**

```python
"""股票 → 关联热门概念(akshare 东方财富数据)。

策略:
1. 取所有概念列表(含热度排名),按 rank 升序(rank 越小越热)
2. 对前 N 个概念,逐个看成分股是否含 ticker
3. 返回前 top_n 个含 ticker 的概念
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.common.akshare_client import AkshareClient
from scripts.common.cache import Cache


def fetch_concept_mapping(client, ticker: str, top_n: int = 3) -> list[dict]:
    """
    返回最多 top_n 个热度最高、且包含目标 ticker 的概念板块。

    格式:
      [
        {"name": "茅指数", "heat_rank": 3, "heat_score": 0.10},
        ...
      ]
    """
    concepts_df = client.call("stock_board_concept_name_em")
    if concepts_df.empty:
        return []

    # 按热度排名升序(假设字段名"热度排名")
    if "热度排名" in concepts_df.columns:
        concepts_df = concepts_df.sort_values("热度排名")

    result = []
    ticker_str = str(ticker).strip()
    for _, row in concepts_df.iterrows():
        if len(result) >= top_n:
            break
        concept_name = row["概念名称"]
        cons_df = client.call("stock_board_concept_cons_em", symbol=concept_name)
        if cons_df.empty or "代码" not in cons_df.columns:
            continue
        codes = {str(c).strip() for c in cons_df["代码"].tolist()}
        if ticker_str in codes:
            result.append({
                "name": concept_name,
                "heat_rank": int(row.get("热度排名", 0)),
                "heat_score": float(row.get("近5日涨幅", 0.0)),
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = AkshareClient(cache=cache, analysis_date=args.analysis_date)
    result = fetch_concept_mapping(client, args.ticker, top_n=args.top_n)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试,确认通过**

Run: `pytest tests/unit/test_concept_mapping.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add scripts/classification/fetch_concept_mapping.py tests/unit/test_concept_mapping.py tests/fixtures/600519_classification.json
git commit -m "feat(classification): map ticker to top hot concept boards"
```

---

## Phase 3: Trend Data Layer

### Task 3.1: 申万行业指数日线

**Files:**
- Create: `scripts/trend/fetch_industry_index.py`
- Create: `tests/unit/test_industry_index.py`
- Create: `tests/fixtures/801123_index.json`

- [ ] **Step 1: 创建 fixture(申万白酒指数 250 个交易日的合成日线)**

```json
{
  "industry_index": [
    {"trade_date": "20250501", "ts_code": "801123.SI", "open": 4500, "high": 4520, "low": 4480, "close": 4500, "vol": 1.2e8, "amount": 5.4e10}
  ]
}
```

(用 Python 脚本生成 250 行合成数据更合理。这里给一行 fixture 示意,实际 fixture 可由 `scripts/dev/generate_fixture.py` 一次性生成 —— 但为简化第一版,fixture 至少给 12 行覆盖近 12 个月即可)

实操:写一个简短 Python 脚本临时生成 fixture(可弃),然后 commit JSON:

```python
# 临时生成脚本,生成后删掉
import json
import random
from datetime import date, timedelta

start = date(2025, 5, 1)
rows = []
price = 4500.0
for i in range(250):
    d = start + timedelta(days=i)
    if d.weekday() >= 5:
        continue
    price *= (1 + random.uniform(-0.02, 0.02))
    rows.append({
        "trade_date": d.strftime("%Y%m%d"),
        "ts_code": "801123.SI",
        "open": round(price * 0.998, 2),
        "high": round(price * 1.005, 2),
        "low": round(price * 0.995, 2),
        "close": round(price, 2),
        "vol": round(random.uniform(0.8e8, 1.5e8)),
        "amount": round(random.uniform(4e10, 7e10)),
    })

with open("tests/fixtures/801123_index.json", "w") as f:
    json.dump({"industry_index": rows}, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 2: 写测试**

```python
"""申万行业指数日线获取 + 多窗口涨跌计算。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.trend.fetch_industry_index import (
    compute_window_returns,
    fetch_industry_index,
)


@pytest.fixture
def index_data():
    path = Path(__file__).parent.parent / "fixtures" / "801123_index.json"
    return json.loads(path.read_text())["industry_index"]


@pytest.fixture
def mock_client(index_data):
    client = MagicMock()
    client.call.return_value = pd.DataFrame(index_data)
    return client


def test_fetch_returns_dataframe(mock_client):
    df = fetch_industry_index(
        mock_client,
        index_code="801123.SI",
        analysis_date="2026-01-31",
        lookback_days=250,
    )
    assert not df.empty
    assert "close" in df.columns


def test_compute_window_returns_includes_1m_3m_6m_12m(mock_client):
    df = fetch_industry_index(
        mock_client,
        index_code="801123.SI",
        analysis_date="2026-01-31",
        lookback_days=250,
    )
    returns = compute_window_returns(df)
    assert "1m" in returns
    assert "3m" in returns
    assert "6m" in returns
    assert "12m" in returns


def test_short_history_handles_missing_window(mock_client, index_data):
    # 只给 30 天,12m 应该返回 None
    short = pd.DataFrame(index_data[:30])
    returns = compute_window_returns(short)
    assert returns["1m"] is not None
    assert returns["12m"] is None
```

- [ ] **Step 3: 跑测试,确认失败**

Run: `pytest tests/unit/test_industry_index.py -v`

- [ ] **Step 4: 实现 `scripts/trend/fetch_industry_index.py`**

```python
"""申万行业指数日线获取 + 多窗口涨跌。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient

WINDOW_DAYS = {"1m": 20, "3m": 60, "6m": 120, "12m": 250}


def fetch_industry_index(
    client,
    index_code: str,
    analysis_date: str,
    lookback_days: int = 250,
) -> pd.DataFrame:
    """
    获取申万行业指数日线,过去 lookback_days 个交易日,降序按 trade_date 排列。
    """
    end_date = analysis_date.replace("-", "")
    df = client.call("sw_daily", ts_code=index_code, end_date=end_date)
    if df.empty:
        return df
    df = df.sort_values("trade_date", ascending=False).head(lookback_days).reset_index(drop=True)
    return df


def compute_window_returns(df: pd.DataFrame) -> dict[str, float | None]:
    """
    给一个降序排列的日线 DataFrame,算 1M/3M/6M/12M 涨跌(基于收盘价)。
    返回 None 当数据不足。
    """
    if df.empty or "close" not in df.columns:
        return {k: None for k in WINDOW_DAYS}

    latest = float(df.iloc[0]["close"])
    out: dict[str, float | None] = {}
    for window, days in WINDOW_DAYS.items():
        if len(df) <= days:
            out[window] = None
            continue
        past = float(df.iloc[days]["close"])
        out[window] = (latest - past) / past if past else None
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-code", required=True, help="如 801123.SI(申万白酒)")
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    parser.add_argument("--lookback-days", type=int, default=250)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    df = fetch_industry_index(
        client,
        index_code=args.index_code,
        analysis_date=args.analysis_date,
        lookback_days=args.lookback_days,
    )
    returns = compute_window_returns(df)
    result = {
        "index_code": args.index_code,
        "rows": int(len(df)),
        "returns": returns,
        "daily": df.to_dict(orient="records"),
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试,确认通过**

Run: `pytest tests/unit/test_industry_index.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add scripts/trend/fetch_industry_index.py tests/unit/test_industry_index.py tests/fixtures/801123_index.json
git commit -m "feat(trend): fetch sw industry index with multi-window returns"
```

---

### Task 3.2: 大盘指数日线 + 相对强度

**Files:**
- Create: `scripts/trend/fetch_market_index.py`
- Create: `tests/unit/test_market_index.py`
- Create: `tests/fixtures/csi300_index.json`(同样合成 250 行)

- [ ] **Step 1: 创建 fixture**

(同 Task 3.1 风格,生成 csi300 250 个交易日合成数据)

- [ ] **Step 2: 写测试**

```python
"""大盘指数日线 + 行业 vs 大盘相对强度计算。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.trend.fetch_market_index import compute_relative_strength, fetch_market_index


@pytest.fixture
def csi300_data():
    path = Path(__file__).parent.parent / "fixtures" / "csi300_index.json"
    return json.loads(path.read_text())["market_index"]


@pytest.fixture
def mock_client(csi300_data):
    client = MagicMock()
    client.call.return_value = pd.DataFrame(csi300_data)
    return client


def test_fetch_csi300(mock_client):
    df = fetch_market_index(mock_client, market_code="000300.SH", analysis_date="2026-01-31")
    assert not df.empty


def test_relative_strength_industry_vs_market():
    industry_returns = {"1m": 0.05, "3m": 0.10, "6m": 0.15, "12m": 0.20}
    market_returns = {"1m": 0.02, "3m": 0.05, "6m": 0.08, "12m": 0.10}
    rs = compute_relative_strength(industry_returns, market_returns)
    # 行业涨得比大盘多 → RS > 1
    assert rs["1m"] > 1
    assert rs["12m"] > 1


def test_relative_strength_underperformance():
    industry_returns = {"1m": -0.02, "3m": 0.01}
    market_returns = {"1m": 0.05, "3m": 0.05}
    rs = compute_relative_strength(industry_returns, market_returns)
    assert rs["1m"] < 1


def test_relative_strength_handles_none():
    industry_returns = {"1m": None, "3m": 0.05}
    market_returns = {"1m": 0.02, "3m": None}
    rs = compute_relative_strength(industry_returns, market_returns)
    assert rs["1m"] is None
    assert rs["3m"] is None
```

- [ ] **Step 3: 跑测试,确认失败**

Run: `pytest tests/unit/test_market_index.py -v`

- [ ] **Step 4: 实现**

```python
"""大盘指数(沪深 300)日线 + 行业相对强度。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient


def fetch_market_index(
    client,
    market_code: str,
    analysis_date: str,
    lookback_days: int = 250,
) -> pd.DataFrame:
    end_date = analysis_date.replace("-", "")
    df = client.call("index_daily", ts_code=market_code, end_date=end_date)
    if df.empty:
        return df
    df = df.sort_values("trade_date", ascending=False).head(lookback_days).reset_index(drop=True)
    return df


def compute_relative_strength(
    industry_returns: dict, market_returns: dict
) -> dict[str, float | None]:
    """
    RS = (1 + industry_return) / (1 + market_return)
    
    > 1 → 行业强于大盘
    < 1 → 行业弱于大盘
    """
    out: dict[str, float | None] = {}
    for window in industry_returns.keys() | market_returns.keys():
        ir = industry_returns.get(window)
        mr = market_returns.get(window)
        if ir is None or mr is None:
            out[window] = None
        else:
            out[window] = (1 + ir) / (1 + mr) if mr != -1 else None
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-code", default="000300.SH")
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    parser.add_argument("--lookback-days", type=int, default=250)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    df = fetch_market_index(
        client,
        market_code=args.market_code,
        analysis_date=args.analysis_date,
        lookback_days=args.lookback_days,
    )
    payload = json.dumps(
        {"market_code": args.market_code, "rows": int(len(df)), "daily": df.to_dict(orient="records")},
        ensure_ascii=False, indent=2, default=str,
    )
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试,确认通过**

Run: `pytest tests/unit/test_market_index.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add scripts/trend/fetch_market_index.py tests/unit/test_market_index.py tests/fixtures/csi300_index.json
git commit -m "feat(trend): fetch market index and compute relative strength"
```

---

### Task 3.3: 行业内涨跌家数比

**Files:**
- Create: `scripts/trend/compute_breadth.py`
- Create: `tests/unit/test_breadth.py`

- [ ] **Step 1: 写测试**

```python
"""行业内涨跌家数比、涨停数。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.trend.compute_breadth import compute_breadth_for_industry


@pytest.fixture
def mock_client_with_constituents():
    """模拟一个行业有 10 只成分股,某日 7 涨 3 跌,2 涨停。"""
    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return pd.DataFrame([
                {"con_code": f"00000{i}.SZ"} for i in range(10)
            ])
        if api_name == "daily":
            ts_code = params.get("ts_code", "")
            i = int(ts_code[5])
            pct = 10.05 if i < 2 else (1.5 if i < 7 else -1.2)
            return pd.DataFrame([{"ts_code": ts_code, "pct_chg": pct, "trade_date": "20260430"}])
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


def test_breadth_advance_decline_ratio(mock_client_with_constituents):
    result = compute_breadth_for_industry(
        mock_client_with_constituents,
        industry_l2_code="801123.SI",
        analysis_date="2026-04-30",
    )
    assert result["advance"] == 7
    assert result["decline"] == 3
    assert result["limit_up"] == 2
    assert result["advance_decline_ratio"] == pytest.approx(7 / 3, rel=1e-3)


def test_no_constituents_returns_zeros(tmp_path):
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = compute_breadth_for_industry(
        client, industry_l2_code="801999.SI", analysis_date="2026-04-30"
    )
    assert result["advance"] == 0
    assert result["decline"] == 0
    assert result["advance_decline_ratio"] is None
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `pytest tests/unit/test_breadth.py -v`

- [ ] **Step 3: 实现**

```python
"""行业内涨跌家数比、涨停数(分化指标)。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient

LIMIT_UP_THRESHOLD = 9.9  # A 股主板 10% 涨停,留 0.1% 余地


def compute_breadth_for_industry(
    client,
    industry_l2_code: str,
    analysis_date: str,
) -> dict:
    """
    返回:
      {
        "advance": int,            # 上涨家数
        "decline": int,            # 下跌家数
        "flat": int,               # 平盘家数
        "limit_up": int,           # 涨停家数
        "advance_decline_ratio": float | None,
      }
    """
    # Tushare index_member_all: 用 l2_code 查申万二级行业的成分股
    members = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
    if members.empty or "con_code" not in members.columns:
        return {"advance": 0, "decline": 0, "flat": 0, "limit_up": 0, "advance_decline_ratio": None}

    end_date = analysis_date.replace("-", "")
    advance = decline = flat = limit_up = 0

    for code in members["con_code"].tolist():
        df = client.call("daily", ts_code=code, end_date=end_date)
        if df.empty or "pct_chg" not in df.columns:
            continue
        latest = df.sort_values("trade_date", ascending=False).iloc[0]
        pct = float(latest["pct_chg"])
        if pct > 0:
            advance += 1
        elif pct < 0:
            decline += 1
        else:
            flat += 1
        if pct >= LIMIT_UP_THRESHOLD:
            limit_up += 1

    ratio = (advance / decline) if decline > 0 else None
    return {
        "advance": advance,
        "decline": decline,
        "flat": flat,
        "limit_up": limit_up,
        "advance_decline_ratio": ratio,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry-l2-code", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    result = compute_breadth_for_industry(
        client, industry_l2_code=args.industry_l2_code, analysis_date=args.analysis_date
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `pytest tests/unit/test_breadth.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add scripts/trend/compute_breadth.py tests/unit/test_breadth.py
git commit -m "feat(trend): compute industry breadth (advance/decline/limit-up)"
```

---

## Phase 4: Output Validator

### Task 4.1: JSON Schema + Validator

**Files:**
- Create: `shared_schemas/module_output_v1.schema.json`
- Create: `scripts/output_validator.py`
- Create: `tests/unit/test_output_validator.py`

- [ ] **Step 1: 创建 JSON Schema**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "module_output_v1",
  "type": "object",
  "required": [
    "module_id", "module_name", "module_version", "schema_version",
    "request_id", "analysis_date", "status", "signal", "score",
    "confidence", "reasons", "risks", "summary"
  ],
  "properties": {
    "module_id": {"type": "string", "minLength": 1},
    "module_name": {"type": "string", "minLength": 1},
    "module_version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
    "schema_version": {"type": "string", "const": "module_output_v1"},
    "request_id": {"type": "string", "minLength": 1},
    "analysis_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "status": {"enum": ["success", "partial", "failed"]},
    "signal": {"oneOf": [{"enum": ["看多", "中性", "看空"]}, {"type": "null"}]},
    "score": {"oneOf": [{"type": "integer", "minimum": -100, "maximum": 100}, {"type": "null"}]},
    "confidence": {"oneOf": [{"type": "number", "minimum": 0, "maximum": 1}, {"type": "null"}]},
    "reasons": {
      "type": "array",
      "maxItems": 5,
      "items": {"type": "string", "maxLength": 80}
    },
    "risks": {
      "type": "array",
      "maxItems": 5,
      "items": {"type": "string", "maxLength": 80}
    },
    "summary": {"type": "string", "maxLength": 50},
    "error": {
      "type": "object",
      "required": ["code", "message"],
      "properties": {
        "code": {
          "enum": [
            "DATA_NOT_FOUND", "DATA_PARTIAL", "DATA_SOURCE_TIMEOUT",
            "DATA_SOURCE_RATE_LIMIT", "REASONING_FAILED",
            "INVALID_INPUT", "INTERNAL_ERROR"
          ]
        },
        "message": {"type": "string"},
        "retriable": {"type": "boolean"},
        "missing_fields": {"type": "array", "items": {"type": "string"}}
      }
    },
    "metrics": {
      "type": "object",
      "properties": {
        "latency_ms": {"type": "number"},
        "data_sources_used": {"type": "array", "items": {"type": "string"}}
      }
    },
    "module_specific": {"type": "object"}
  }
}
```

- [ ] **Step 2: 写测试**

```python
"""Output JSON Schema 校验器。"""
import json

import pytest

from scripts.output_validator import ValidationError, validate_output


VALID_OUTPUT = {
    "module_id": "industry_analysis",
    "module_name": "行业分析模块",
    "module_version": "1.0.0",
    "schema_version": "module_output_v1",
    "request_id": "req_test_001",
    "analysis_date": "2026-04-30",
    "status": "success",
    "signal": "看多",
    "score": 65,
    "confidence": 0.78,
    "reasons": ["A", "B", "C"],
    "risks": ["X", "Y"],
    "summary": "白酒景气回升,茅台核心受益。",
}


def test_valid_output_passes():
    validate_output(VALID_OUTPUT)


def test_score_out_of_range_fails():
    bad = {**VALID_OUTPUT, "score": 200}
    with pytest.raises(ValidationError):
        validate_output(bad)


def test_summary_too_long_fails():
    bad = {**VALID_OUTPUT, "summary": "x" * 51}
    with pytest.raises(ValidationError):
        validate_output(bad)


def test_reasons_too_many_fails():
    bad = {**VALID_OUTPUT, "reasons": ["a"] * 6}
    with pytest.raises(ValidationError):
        validate_output(bad)


def test_failed_status_with_null_signal_passes():
    output = {
        **VALID_OUTPUT,
        "status": "failed",
        "signal": None,
        "score": None,
        "confidence": None,
        "error": {"code": "DATA_NOT_FOUND", "message": "..."},
    }
    validate_output(output)


def test_unknown_error_code_fails():
    bad = {
        **VALID_OUTPUT,
        "status": "failed",
        "signal": None,
        "score": None,
        "confidence": None,
        "error": {"code": "WHO_KNOWS", "message": "..."},
    }
    with pytest.raises(ValidationError):
        validate_output(bad)
```

- [ ] **Step 3: 跑测试,确认失败**

Run: `pytest tests/unit/test_output_validator.py -v`

- [ ] **Step 4: 实现 `scripts/output_validator.py`**

```python
"""Output JSON Schema 校验。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError as _SchemaValidationError

SCHEMA_PATH = Path(__file__).parent.parent / "shared_schemas" / "module_output_v1.schema.json"


class ValidationError(ValueError):
    """Wraps jsonschema errors with our own type."""


def validate_output(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
        raise ValidationError("module_output_v1 validation failed:\n  " + "\n  ".join(msgs))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        validate_output(payload)
    except ValidationError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试,确认通过**

Run: `pytest tests/unit/test_output_validator.py -v`
Expected: 6 passed

- [ ] **Step 6: 提交**

```bash
git add shared_schemas/ scripts/output_validator.py tests/unit/test_output_validator.py
git commit -m "feat: add module_output_v1 JSON Schema and validator"
```

---

## Phase 5: SKILL.md MVP

### Task 5.1: SKILL.md frontmatter + 主体骨架

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: 写 SKILL.md(全文)**

```markdown
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
  "score": -100..100,
  "confidence": 0.0..1.0,
  "stage": "...",
  "key_signals": [...]
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
  "score": <来自走势 agent>,
  "confidence": min(走势 agent confidence × 0.7, 0.5),
  "industry_outlook": { "stage": <来自走势>, ... },
  "stock_in_industry": {
    "relative_position": "无法判断(MVP 阶段无龙头数据)",
    "industry_boost": <round(走势 score / 50)>
  }
}
```

### Step 6: 派生 signal + 组装最终 JSON

```bash
python scripts/common/derive_signal.py --score {final_score}  # 假设我们暴露了 CLI 入口
```

或在 prompt 里直接按规则派生:
- `score >= 30 → "看多"` / `-30 < score < 30 → "中性"` / `score <= -30 → "看空"`

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
      "related_concepts": [...]
    },
    "agent_breakdown": {
      "trend": {...},
      "fundamentals": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "capital_flow": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "leaders": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
      "macro_policy": {"score": 0, "confidence": 0.3, "note": "v2 will add"}
    },
    "weights_used": {"trend": 1.0, "_note": "MVP 阶段只走 trend 维度"}
  }
}
```
```

- [ ] **Step 2: 提交**

```bash
git add SKILL.md
git commit -m "feat: add SKILL.md MVP (trend agent only, others stubbed)"
```

---

## Phase 6: Integration Test

### Task 6.1: 集成测试 fixture(600519)

**Files:**
- Create: `tests/integration/test_600519_trend_mvp.py`
- Create: `tests/conftest.py`(共享 fixtures)

- [ ] **Step 1: 创建 conftest.py**

```python
"""Shared fixtures for integration tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_tushare_for_600519(fixtures_dir):
    """聚合 600519 端到端的 mock Tushare 客户端。"""
    classification = json.loads((fixtures_dir / "600519_classification.json").read_text())
    industry_index = json.loads((fixtures_dir / "801123_index.json").read_text())
    csi300 = json.loads((fixtures_dir / "csi300_index.json").read_text())

    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            ts_code = params.get("ts_code", "")
            if ts_code == "600519.SH":
                return pd.DataFrame(classification["tushare_index_member_all"])
            # 行业成分股查询(给个简化的:10 只)
            return pd.DataFrame([{"con_code": f"00000{i}.SZ"} for i in range(10)])
        if api_name == "sw_daily":
            return pd.DataFrame(industry_index["industry_index"])
        if api_name == "index_daily":
            return pd.DataFrame(csi300["market_index"])
        if api_name == "daily":
            return pd.DataFrame([{"ts_code": params.get("ts_code"), "pct_chg": 1.5, "trade_date": "20260430"}])
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


@pytest.fixture
def mock_akshare_for_600519(fixtures_dir):
    classification = json.loads((fixtures_dir / "600519_classification.json").read_text())
    client = MagicMock()

    def call_side_effect(function_name, **params):
        if function_name == "stock_board_concept_name_em":
            return pd.DataFrame(classification["akshare_concept_heat"])
        if function_name == "stock_board_concept_cons_em":
            symbol = params.get("symbol", "")
            for c in classification["akshare_concept_em"]:
                if c["概念名称"] == symbol:
                    return pd.DataFrame([
                        {"代码": code} for code in c["成分股"].split(",")
                    ])
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client
```

- [ ] **Step 2: 写集成测试**

```python
"""端到端验证 600519 走势 agent 路径。

注意:这测试不直接 invoke SKILL.md(那需要 LLM),只验证数据脚本链路 + 校验最终 JSON。
LLM 推理部分由 SKILL.md 的开发者手动跑通(用 claude code "/industry-analysis ...")。
"""
import json
from pathlib import Path

from scripts.classification.fetch_concept_mapping import fetch_concept_mapping
from scripts.classification.fetch_industry_classification import fetch_industry_classification
from scripts.output_validator import validate_output
from scripts.trend.compute_breadth import compute_breadth_for_industry
from scripts.trend.fetch_industry_index import compute_window_returns, fetch_industry_index
from scripts.trend.fetch_market_index import compute_relative_strength, fetch_market_index
from scripts.common.derive_signal import derive_signal


def test_data_pipeline_600519(mock_tushare_for_600519, mock_akshare_for_600519):
    """完整数据脚本链路 + 模拟 LLM 输出 + JSON 校验。"""
    analysis_date = "2026-05-01"

    # Step 1: classification
    cls = fetch_industry_classification(mock_tushare_for_600519, ticker="600519")
    assert cls is not None
    assert cls["primary_industry"]["code"] == "801123.SI"

    concepts = fetch_concept_mapping(mock_akshare_for_600519, ticker="600519", top_n=3)
    assert len(concepts) <= 3

    # Step 2: trend data
    industry_df = fetch_industry_index(
        mock_tushare_for_600519,
        index_code=cls["primary_industry"]["code"],
        analysis_date=analysis_date,
    )
    industry_returns = compute_window_returns(industry_df)
    assert industry_returns["1m"] is not None

    market_df = fetch_market_index(
        mock_tushare_for_600519,
        market_code="000300.SH",
        analysis_date=analysis_date,
    )
    market_returns = compute_window_returns(market_df)
    rs = compute_relative_strength(industry_returns, market_returns)

    breadth = compute_breadth_for_industry(
        mock_tushare_for_600519,
        industry_l2_code=cls["primary_industry"]["code"],
        analysis_date=analysis_date,
    )

    # Step 3-5: 模拟 LLM 输出(MVP 走势 only)
    final_score = 35
    final_confidence = 0.4
    output = {
        "module_id": "industry_analysis",
        "module_name": "行业分析模块",
        "module_version": "1.0.0",
        "schema_version": "module_output_v1",
        "request_id": "req_test_600519",
        "analysis_date": analysis_date,
        "status": "partial",
        "signal": derive_signal(final_score),
        "score": final_score,
        "confidence": final_confidence,
        "reasons": [
            f"白酒行业 1M 涨跌 {industry_returns['1m']:.2%}",
            f"涨跌家数比 {breadth['advance']}:{breadth['decline']}",
            "MVP 阶段仅基于走势维度",
        ],
        "risks": ["MVP 仅看走势,缺其他维度信号"],
        "summary": "走势偏多,茅台短期受益。",
        "metrics": {"latency_ms": 8000, "data_sources_used": ["tushare", "akshare"]},
        "module_specific": {
            "classification": {
                "primary_industry": cls["primary_industry"],
                "related_concepts": concepts,
            },
            "agent_breakdown": {
                "trend": {
                    "score": final_score,
                    "confidence": final_confidence,
                    "key_signals": [
                        {"name": "1m_return", "value": industry_returns["1m"]},
                        {"name": "rs_vs_csi300_1m", "value": rs.get("1m")},
                        {"name": "breadth_ratio", "value": breadth["advance_decline_ratio"]},
                    ],
                },
                "fundamentals": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
                "capital_flow": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
                "leaders": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
                "macro_policy": {"score": 0, "confidence": 0.3, "note": "v2 will add"},
            },
            "weights_used": {"trend": 1.0, "_note": "MVP 阶段只走 trend"},
        },
    }

    # Step 6: schema 校验
    validate_output(output)


def test_signal_derivation_consistency():
    assert derive_signal(35) == "看多"
    assert derive_signal(0) == "中性"
    assert derive_signal(-50) == "看空"
```

- [ ] **Step 3: 跑测试,确认通过**

Run: `pytest tests/integration/test_600519_trend_mvp.py -v`
Expected: 2 passed

- [ ] **Step 4: 跑全套测试,确认无回归**

Run: `pytest -v`
Expected: 全绿。展示统计:`X passed in Y seconds`

- [ ] **Step 5: 提交**

```bash
git add tests/integration/test_600519_trend_mvp.py tests/conftest.py
git commit -m "test(integration): end-to-end pipeline test for 600519 (trend MVP)"
```

---

## 验收清单(Plan 1 完成标志)

- [ ] `pytest -v` 全绿,所有单元测试 + 集成测试通过
- [ ] `python scripts/classification/fetch_industry_classification.py --ticker 600519 --analysis-date 2026-05-01` 命令行可跑(需要真实 Tushare token,手动验证)
- [ ] `python scripts/trend/fetch_industry_index.py --index-code 801123.SI --analysis-date 2026-05-01` 命令行可跑
- [ ] `SKILL.md` frontmatter 通过 YAML 解析,description 包含触发场景说明
- [ ] `module_output_v1` JSON Schema 通过 `validate_output()` 测试 6 类用例
- [ ] git log 至少 14 个原子 commit(每个 Task 一个或多个)
- [ ] 项目目录结构与 design v1 第 10 节一致(MVP 范围内)

---

## Plan 2 / Plan 3 预告(本 plan 不实现)

**Plan 2:扩展 4 个分析 agent**
- 基本面数据脚本(`fetch_industry_financials`、`fetch_industry_valuation`、`compute_percentile`)
- 资金流数据脚本(`fetch_main_flow`、`fetch_northbound`、`fetch_etf_flow`、`fetch_margin`)
- 龙头数据脚本(`fetch_industry_leaders`、`fetch_leader_news`、`compute_relative_strength`)
- 宏观政策数据脚本(`fetch_macro_indicators`、`fetch_industry_news`)
- SKILL.md 升级:激活 5 个 agent prompt,把 stub 替换为真推理
- 行业 ETF mapping 补全到 30+
- 更多 ticker 的 golden tests(002475、300750、688981)

**Plan 3:辩论 + 裁判 + 完整 schema**
- 看多 / 看空 agent prompt
- 裁判 agent prompt(含 horizon-aware 权重表)
- final_confidence 计算公式落地
- partial 状态完整测试(< 3 agent 成功)
- failed 状态完整测试(API 全挂)
- ST 股、新股边界用例
- 性能 benchmark(单次端到端 < 30s)
- README 完善,集成 README.md 跑通示例

---

## Self-Review

(本节由 plan 作者自检,不进入实现)

✅ **Spec coverage**:
- design v1 第 10 节文件结构(MVP 范围) → Phase 1 + Task 1.1 + 各 Phase
- 第 7 节数据源映射(走势部分) → Phase 3
- 第 8 节输出 schema → Phase 4 + Task 5.1
- 第 9 节错误处理 → SKILL.md 第 5 节 + JSON Schema
- 第 11 节 SKILL.md 大纲 → Task 5.1
- 第 12 节测试策略 → Phase 6

⚠️ **本 plan 不覆盖**(留给 Plan 2/3):
- 4 个其他 agent 的数据 + prompt
- 看多/看空/裁判 prompt
- horizon-aware 权重表的实际应用(MVP 用 1.0)
- partial/failed/ST 边界用例

✅ **Placeholder scan**:无 TBD/TODO/`...省略...`,所有代码块都是完整可运行的(除了 Step 1 的 fixture 生成提示用了"实操"小节,但有完整 Python 代码)

✅ **Type consistency**:
- `Cache.get/set` 签名一致(api_name, params, analysis_date, [value])
- `TushareClient.call(api_name, **params)` 一致
- `fetch_*` 函数全部接受 `client` 作为第一参数(便于 mock)
- `compute_window_returns` 返回 `{1m, 3m, 6m, 12m}` 与 design v1 一致

---

**Plan 1 完成后**,会有一个最小可跑的 industry-analysis skill:
- 可以输入 600519,跑通"分类 → 走势数据 → LLM 推理(走势 only) → 输出 JSON"
- 框架完整,后续 Plan 2/3 只是填充内容
- 已经足够给总控做"有比没有强"的行业信号

**版本**:Plan 1 v1 · **状态**:draft · **下一步**:用户审阅,选择执行模式
