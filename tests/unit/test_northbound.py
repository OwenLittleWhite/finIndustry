"""北向资金净流入(大盘级别代理) - 单元测试。"""
import warnings
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.capital.fetch_northbound import fetch_northbound

_ANALYSIS_DATE = "2026-04-30"
_L2_CODE = "801125.SI"


def _make_moneyflow_hsgt(rows: int = 11) -> pd.DataFrame:
    """生成 rows 行 moneyflow_hsgt 数据,trade_date 升序。

    north_money 字段单位:万元(我们除 10000 → 亿元)。
    """
    out = []
    for i in range(rows):
        day = 20 + i
        out.append({
            "trade_date": f"202604{day:02d}",
            "ggt_ss": 0.0,
            "ggt_sz": 0.0,
            "hgt": 10000.0 + i * 1000,    # 沪股通(万元)
            "sgt": 5000.0 + i * 500,      # 深股通(万元)
            "north_money": (10000.0 + i * 1000) + (5000.0 + i * 500),  # 万元
            "south_money": 0.0,
        })
    return pd.DataFrame(out)


def _make_client(hsgt_df: pd.DataFrame | None = None) -> MagicMock:
    if hsgt_df is None:
        hsgt_df = pd.DataFrame()
    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "moneyflow_hsgt":
            return hsgt_df.copy()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


def test_fetch_returns_required_fields():
    """返回字典必须包含所有规定字段。"""
    hsgt_df = _make_moneyflow_hsgt(11)
    client = _make_client(hsgt_df)
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    required = {
        "industry_l2_code", "scope",
        "north_money_today_yi", "north_money_5d_yi", "north_money_10d_yi",
        "current_holding_value", "change_5d_pct", "change_10d_pct",
    }
    assert required.issubset(result.keys())
    assert result["industry_l2_code"] == _L2_CODE
    assert result["scope"] == "market_level"


def test_today_north_money_in_yi():
    """今日(最后一行)north_money 转换成亿元(单位:万元 → 亿元 / 10000)。

    rows=11,最后一行 i=10:north_money=(10000+10000)+(5000+5000)=30000 万元 → 3.0 亿元
    """
    hsgt_df = _make_moneyflow_hsgt(11)
    client = _make_client(hsgt_df)
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    expected_today = 30000.0 / 10000.0  # 万 → 亿
    assert result["north_money_today_yi"] == pytest.approx(expected_today, abs=1e-6)


def test_5d_and_10d_aggregation():
    """近 5/10 日累计计算正确。

    11 行,每行 north_money = (10000+i*1000) + (5000+i*500)
    i=0:15000, i=1:16500, ..., i=10:30000(单位万元)
    最后 5 行(i=6..10):24000,25500,27000,28500,30000 → sum=135000 万 → 13.5 亿
    最后 10 行(i=1..10):sum=232500 万 → 23.25 亿
    """
    hsgt_df = _make_moneyflow_hsgt(11)
    client = _make_client(hsgt_df)
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    last_5_sum = (24000 + 25500 + 27000 + 28500 + 30000)
    expected_5d = last_5_sum / 10000.0
    last_10_sum = sum(((10000 + i * 1000) + (5000 + i * 500)) for i in range(1, 11))
    expected_10d = last_10_sum / 10000.0
    assert result["north_money_5d_yi"] == pytest.approx(expected_5d, abs=1e-6)
    assert result["north_money_10d_yi"] == pytest.approx(expected_10d, abs=1e-6)


def test_empty_data_returns_none_fields():
    """moneyflow_hsgt 返回空 → 全 None。"""
    client = _make_client(pd.DataFrame())
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["north_money_today_yi"] is None
    assert result["north_money_5d_yi"] is None
    assert result["north_money_10d_yi"] is None


def test_network_error_returns_none_fields():
    """ConnectionError 等网络错误 → 全 None,不抛异常。"""
    client = MagicMock()
    client.call.side_effect = ConnectionError("simulated proxy failure")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["north_money_today_yi"] is None
    assert result["north_money_5d_yi"] is None
    assert result["north_money_10d_yi"] is None
