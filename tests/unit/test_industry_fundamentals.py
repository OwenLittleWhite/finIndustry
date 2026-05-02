"""行业聚合财务数据 - 单元测试。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.fundamentals.fetch_industry_financials import (
    fetch_industry_financials,
    _derive_quarter_list,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_ANALYSIS_DATE = "2026-04-30"
_L2_CODE = "801125.SI"

# ---------------------------------------------------------------------------
# 合成数据工厂
# ---------------------------------------------------------------------------


def _make_members(ts_codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"ts_code": ts_codes})


def _make_fina(ts_code: str, rows: list[dict]) -> pd.DataFrame:
    """rows 每项含 end_date / revenue / n_income_attr_p / roe / grossprofit_margin。"""
    base = {
        "revenue": None,
        "n_income_attr_p": None,
        "roe": None,
        "grossprofit_margin": None,
    }
    records = []
    for r in rows:
        rec = {"ts_code": ts_code, **base, **r}
        records.append(rec)
    return pd.DataFrame(records)


def _make_client_from_fina_map(
    members: list[str],
    fina_map: dict[str, pd.DataFrame],
) -> MagicMock:
    """
    构建 mock client:
    - index_member_all → members DataFrame
    - fina_indicator(ts_code=X) → fina_map[X]
    """
    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return _make_members(members)
        if api_name == "fina_indicator":
            ts_code = params.get("ts_code", "")
            return fina_map.get(ts_code, pd.DataFrame())
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


# ---------------------------------------------------------------------------
# 测试 1: 返回必要字段
# ---------------------------------------------------------------------------


def test_fetch_returns_required_fields():
    """返回 dict 必须包含所有规定的 key。"""
    client = MagicMock()
    client.call.return_value = pd.DataFrame()  # 空成分股 → graceful

    result = fetch_industry_financials(client, _L2_CODE, _ANALYSIS_DATE)

    required = {
        "industry_l2_code",
        "quarters",
        "agg_revenue_yoy",
        "agg_profit_yoy",
        "median_roe",
        "median_gross_margin",
        "constituent_count",
    }
    assert required.issubset(result.keys()), f"缺少字段: {required - result.keys()}"


# ---------------------------------------------------------------------------
# 测试 2: 季度倒序 (最新在前)
# ---------------------------------------------------------------------------


def test_quarters_in_descending_order():
    """quarters[0] 必须是最新(最近)季度。"""
    # 2026-04-30 → 最新完结季度是 2026Q1(3月31日 <= 4月30日)
    quarter_list = _derive_quarter_list("2026-04-30", 4)
    labels = [label for label, _ in quarter_list]

    assert labels[0] == "2026Q1", f"期望 2026Q1,得到 {labels[0]}"
    assert labels[1] == "2025Q4"
    assert labels[2] == "2025Q3"
    assert labels[3] == "2025Q2"


def test_quarters_descending_mid_quarter():
    """分析日期在季度中间时,当前未完结季度不应出现。"""
    # 2026-02-15 → 2026Q1 尚未完结(3月31日还未到) → 最新应为 2025Q4
    quarter_list = _derive_quarter_list("2026-02-15", 2)
    labels = [label for label, _ in quarter_list]
    assert labels[0] == "2025Q4"
    assert labels[1] == "2025Q3"


# ---------------------------------------------------------------------------
# 测试 3: 聚合正确性 (手算验证)
# ---------------------------------------------------------------------------


def test_aggregation_correctness():
    """
    2 只成分股 × 4 季度数据,手算验证 YoY 增速和中位数。

    股票 A:
      2025Q1 (20250331): revenue=100, n_income=10, roe=10.0, gm=40.0
      2026Q1 (20260331): revenue=120, n_income=12, roe=12.0, gm=42.0

    股票 B:
      2025Q1 (20250331): revenue=200, n_income=20, roe=20.0, gm=50.0
      2026Q1 (20260331): revenue=240, n_income=22, roe=22.0, gm=48.0

    2026Q1 行业总营收 YoY = (120+240)/(100+200) - 1 = 360/300 - 1 = 0.2
    2026Q1 行业总净利 YoY = (12+22)/(10+20) - 1 = 34/30 - 1 ≈ 0.1333
    2026Q1 ROE 中位数 = median([12.0, 22.0]) = 17.0
    2026Q1 GM 中位数  = median([42.0, 48.0]) = 45.0
    """
    fina_a = _make_fina("000001.SH", [
        {"end_date": "20250331", "revenue": 100.0, "n_income_attr_p": 10.0,
         "roe": 10.0, "grossprofit_margin": 40.0},
        {"end_date": "20260331", "revenue": 120.0, "n_income_attr_p": 12.0,
         "roe": 12.0, "grossprofit_margin": 42.0},
    ])
    fina_b = _make_fina("000002.SZ", [
        {"end_date": "20250331", "revenue": 200.0, "n_income_attr_p": 20.0,
         "roe": 20.0, "grossprofit_margin": 50.0},
        {"end_date": "20260331", "revenue": 240.0, "n_income_attr_p": 22.0,
         "roe": 22.0, "grossprofit_margin": 48.0},
    ])

    client = _make_client_from_fina_map(
        ["000001.SH", "000002.SZ"],
        {"000001.SH": fina_a, "000002.SZ": fina_b},
    )

    result = fetch_industry_financials(client, _L2_CODE, "2026-04-30", quarters=1)

    assert result["quarters"] == ["2026Q1"]
    assert result["constituent_count"] == 2

    yoy_rev = result["agg_revenue_yoy"][0]
    assert yoy_rev is not None
    assert abs(yoy_rev - 0.2) < 1e-9, f"YoY 营收期望 0.2,得到 {yoy_rev}"

    yoy_profit = result["agg_profit_yoy"][0]
    assert yoy_profit is not None
    assert abs(yoy_profit - (34 / 30 - 1)) < 1e-9, f"YoY 净利期望 ~0.1333,得到 {yoy_profit}"

    roe = result["median_roe"][0]
    assert roe is not None
    assert abs(roe - 17.0) < 1e-9, f"ROE 中位数期望 17.0,得到 {roe}"

    gm = result["median_gross_margin"][0]
    assert gm is not None
    assert abs(gm - 45.0) < 1e-9, f"毛利率中位数期望 45.0,得到 {gm}"


# ---------------------------------------------------------------------------
# 测试 4: 空成分股 graceful
# ---------------------------------------------------------------------------


def test_empty_industry_returns_empty_dict():
    """成分股查询返回空 DataFrame → 返回空 quarters/lists,不抛异常。"""
    client = MagicMock()
    client.call.return_value = pd.DataFrame()

    result = fetch_industry_financials(client, _L2_CODE, _ANALYSIS_DATE)

    assert isinstance(result, dict)
    assert result["quarters"] == []
    assert result["agg_revenue_yoy"] == []
    assert result["agg_profit_yoy"] == []
    assert result["median_roe"] == []
    assert result["median_gross_margin"] == []
    assert result["constituent_count"] == 0


# ---------------------------------------------------------------------------
# 测试 5: 财务数据缺失时 YoY 为 None
# ---------------------------------------------------------------------------


def test_missing_prior_year_yoy_is_none():
    """只有当前季度数据,无去年同期 → YoY 返回 None。"""
    fina_a = _make_fina("000001.SH", [
        {"end_date": "20260331", "revenue": 100.0, "n_income_attr_p": 10.0,
         "roe": 15.0, "grossprofit_margin": 30.0},
        # 故意没有 20250331 数据
    ])

    client = _make_client_from_fina_map(
        ["000001.SH"],
        {"000001.SH": fina_a},
    )

    result = fetch_industry_financials(client, _L2_CODE, "2026-04-30", quarters=1)

    assert result["agg_revenue_yoy"][0] is None
    assert result["agg_profit_yoy"][0] is None
    # 但 ROE / 毛利率仍有值
    assert result["median_roe"][0] is not None
