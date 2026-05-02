"""行业聚合财务数据 - 单元测试。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.fundamentals.fetch_industry_financials import (
    fetch_industry_financials,
    _derive_quarter_list,
)

_ANALYSIS_DATE = "2026-04-30"
_L2_CODE = "801125.SI"


def _make_members(ts_codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"ts_code": ts_codes})


def _make_fina(ts_code: str, rows: list[dict]) -> pd.DataFrame:
    """rows 每项含 end_date / or_yoy / netprofit_yoy / roe / grossprofit_margin。

    Tushare fina_indicator 直接返回 or_yoy 和 netprofit_yoy 字段(单位:百分点)。
    """
    base = {
        "or_yoy": None,
        "netprofit_yoy": None,
        "roe": None,
        "grossprofit_margin": None,
    }
    records = [{"ts_code": ts_code, **base, **r} for r in rows]
    return pd.DataFrame(records)


def _make_client_from_fina_map(
    members: list[str],
    fina_map: dict[str, pd.DataFrame],
) -> MagicMock:
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


def test_fetch_returns_required_fields():
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = fetch_industry_financials(client, _L2_CODE, _ANALYSIS_DATE)
    required = {
        "industry_l2_code", "quarters", "agg_revenue_yoy", "agg_profit_yoy",
        "median_roe", "median_gross_margin", "constituent_count",
    }
    assert required.issubset(result.keys())


def test_quarters_in_descending_order():
    quarter_list = _derive_quarter_list("2026-04-30", 4)
    labels = [label for label, _ in quarter_list]
    assert labels[0] == "2026Q1"
    assert labels[1] == "2025Q4"
    assert labels[2] == "2025Q3"
    assert labels[3] == "2025Q2"


def test_quarters_descending_mid_quarter():
    quarter_list = _derive_quarter_list("2026-02-15", 2)
    labels = [label for label, _ in quarter_list]
    assert labels[0] == "2025Q4"
    assert labels[1] == "2025Q3"


def test_aggregation_correctness():
    """
    2 只成分股 × 1 季度,验证 YoY 中位数 + 百分点 → decimal。

    A 2026Q1: or_yoy=20.0(%), netprofit_yoy=15.0, roe=12.0, gm=42.0
    B 2026Q1: or_yoy=10.0,    netprofit_yoy=5.0,  roe=22.0, gm=48.0

    median(or_yoy)=15.0% → 0.15;median(netprofit_yoy)=10.0% → 0.10
    median(roe)=17.0;median(grossprofit_margin)=45.0
    """
    fina_a = _make_fina("000001.SH", [
        {"end_date": "20260331", "or_yoy": 20.0, "netprofit_yoy": 15.0,
         "roe": 12.0, "grossprofit_margin": 42.0},
    ])
    fina_b = _make_fina("000002.SZ", [
        {"end_date": "20260331", "or_yoy": 10.0, "netprofit_yoy": 5.0,
         "roe": 22.0, "grossprofit_margin": 48.0},
    ])

    client = _make_client_from_fina_map(
        ["000001.SH", "000002.SZ"],
        {"000001.SH": fina_a, "000002.SZ": fina_b},
    )

    result = fetch_industry_financials(client, _L2_CODE, "2026-04-30", quarters=1)

    assert result["quarters"] == ["2026Q1"]
    assert result["constituent_count"] == 2
    assert result["agg_revenue_yoy"][0] == pytest.approx(0.15, abs=1e-9)
    assert result["agg_profit_yoy"][0] == pytest.approx(0.10, abs=1e-9)
    assert result["median_roe"][0] == pytest.approx(17.0, abs=1e-9)
    assert result["median_gross_margin"][0] == pytest.approx(45.0, abs=1e-9)


def test_empty_industry_returns_empty_dict():
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = fetch_industry_financials(client, _L2_CODE, _ANALYSIS_DATE)
    assert isinstance(result, dict)
    assert result["quarters"] == []
    assert result["agg_revenue_yoy"] == []
    assert result["constituent_count"] == 0


def test_missing_yoy_field_returns_none():
    """成分股该季度 or_yoy / netprofit_yoy 全 None → 该季度 YoY=None。"""
    fina_a = _make_fina("000001.SH", [
        {"end_date": "20260331", "or_yoy": None, "netprofit_yoy": None,
         "roe": 15.0, "grossprofit_margin": 30.0},
    ])
    client = _make_client_from_fina_map(["000001.SH"], {"000001.SH": fina_a})
    result = fetch_industry_financials(client, _L2_CODE, "2026-04-30", quarters=1)

    assert result["agg_revenue_yoy"][0] is None
    assert result["agg_profit_yoy"][0] is None
    assert result["median_roe"][0] == pytest.approx(15.0)


def test_pct_to_decimal_conversion():
    """Tushare 真实数据 or_yoy=6.538 → 输出 0.06538。"""
    fina_a = _make_fina("000001.SH", [
        {"end_date": "20260331", "or_yoy": 6.538, "netprofit_yoy": -2.5,
         "roe": 10.5, "grossprofit_margin": 89.7},
    ])
    client = _make_client_from_fina_map(["000001.SH"], {"000001.SH": fina_a})
    result = fetch_industry_financials(client, _L2_CODE, "2026-04-30", quarters=1)

    assert result["agg_revenue_yoy"][0] == pytest.approx(0.06538, abs=1e-9)
    assert result["agg_profit_yoy"][0] == pytest.approx(-0.025, abs=1e-9)
