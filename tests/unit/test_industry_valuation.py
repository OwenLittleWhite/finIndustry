"""行业 PE/PB 当前值及历史分位 - 单元测试。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.fundamentals.fetch_industry_valuation import (
    fetch_industry_valuation,
    _percentile_of,
    MIN_HISTORY_POINTS,
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


def _make_daily_basic(ts_code: str, rows: list[dict]) -> pd.DataFrame:
    """rows 每项含 trade_date / pe_ttm / pb。"""
    base = {"pe_ttm": None, "pb": None}
    records = [{"ts_code": ts_code, **base, **r} for r in rows]
    return pd.DataFrame(records)


def _make_client(
    members: list[str],
    daily_basic_map: dict[str, pd.DataFrame],
) -> MagicMock:
    """
    构建 mock client:
    - index_member_all → members DataFrame
    - daily_basic(ts_code=X, ...) → daily_basic_map[X]
    """
    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return _make_members(members)
        if api_name == "daily_basic":
            ts_code = params.get("ts_code", "")
            return daily_basic_map.get(ts_code, pd.DataFrame())
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


# ---------------------------------------------------------------------------
# 测试 1: 返回必要字段
# ---------------------------------------------------------------------------


def test_returns_required_fields():
    """返回 dict 必须包含所有规定的 key。"""
    client = MagicMock()
    client.call.return_value = pd.DataFrame()  # 空成分股 → graceful

    result = fetch_industry_valuation(client, _L2_CODE, _ANALYSIS_DATE)

    required = {
        "industry_l2_code",
        "current_pe_median",
        "current_pb_median",
        "pe_percentile_5y",
        "pb_percentile_5y",
        "constituent_count",
    }
    assert required.issubset(result.keys()), f"缺少字段: {required - result.keys()}"


# ---------------------------------------------------------------------------
# 测试 2: 分位计算正确性 (_percentile_of 单测)
# ---------------------------------------------------------------------------


def test_percentile_calculation_basic():
    """
    给定序列 [10, 12, 14, 16, 18, 20],当前值 14:
    <= 14 的有 10, 12, 14,共 3 个 → 3/6 = 0.5
    """
    series = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
    pct = _percentile_of(series, 14.0)
    assert abs(pct - 0.5) < 1e-9, f"期望 0.5,得到 {pct}"


def test_percentile_min_value():
    """当前值是最小值 → 分位 = 1/n。"""
    series = [10.0, 20.0, 30.0, 40.0, 50.0]
    pct = _percentile_of(series, 10.0)
    assert abs(pct - 0.2) < 1e-9, f"期望 0.2,得到 {pct}"


def test_percentile_max_value():
    """当前值是最大值 → 分位 = 1.0。"""
    series = [10.0, 20.0, 30.0]
    pct = _percentile_of(series, 30.0)
    assert abs(pct - 1.0) < 1e-9, f"期望 1.0,得到 {pct}"


def test_percentile_empty_series():
    """空序列返回 0.0 而非抛异常。"""
    pct = _percentile_of([], 15.0)
    assert pct == 0.0


# ---------------------------------------------------------------------------
# 测试 3: 历史数据不足时分位返回 None,但 current 值仍可返回
# ---------------------------------------------------------------------------


def test_no_history_returns_none_percentile():
    """
    历史数据点数 < MIN_HISTORY_POINTS → pe/pb percentile 返回 None。
    但 current_pe_median / current_pb_median 有值(只要当天有数据)。
    """
    # 只给 5 个交易日数据(远少于 MIN_HISTORY_POINTS=20)
    daily_a = _make_daily_basic("000001.SH", [
        {"trade_date": f"2026043{i}", "pe_ttm": 20.0 + i, "pb": 2.0 + i * 0.1}
        for i in range(5)
    ])

    client = _make_client(["000001.SH"], {"000001.SH": daily_a})

    result = fetch_industry_valuation(client, _L2_CODE, _ANALYSIS_DATE, history_years=1)

    # current 值有数据
    assert result["current_pe_median"] is not None
    assert result["current_pb_median"] is not None
    # 分位因数据不足返回 None
    assert result["pe_percentile_5y"] is None
    assert result["pb_percentile_5y"] is None


# ---------------------------------------------------------------------------
# 测试 4: 成分股为空时 graceful
# ---------------------------------------------------------------------------


def test_empty_industry_returns_none_values():
    """成分股查询为空 → 所有 current/percentile 字段为 None,不抛异常。"""
    client = MagicMock()
    client.call.return_value = pd.DataFrame()

    result = fetch_industry_valuation(client, _L2_CODE, _ANALYSIS_DATE)

    assert isinstance(result, dict)
    assert result["current_pe_median"] is None
    assert result["current_pb_median"] is None
    assert result["pe_percentile_5y"] is None
    assert result["pb_percentile_5y"] is None
    assert result["constituent_count"] == 0


# ---------------------------------------------------------------------------
# 测试 5: 足够历史数据时正确计算分位和当前值
# ---------------------------------------------------------------------------


def test_percentile_with_sufficient_history():
    """
    两只成分股,给足 25 天数据(>= MIN_HISTORY_POINTS=20):
    - 股票 A: pe 从 10 缓慢升至 10+24*0.1=12.4,最新=12.4
    - 股票 B: pe 从 20 缓慢升至 20+24*0.1=22.4,最新=22.4

    每日行业 PE 中位数 = (A + B) / 2
    第0天(最旧): median(10.0, 20.0) = 15.0
    第24天(最新): median(12.4, 22.4) = 17.4

    当前 PE 中位数 = 17.4
    历史 PE 序列长度 25(全部日期都有数据)
    17.4 是序列最大值 → 分位 = 25/25 = 1.0
    """
    n = 25
    rows_a = [
        {"trade_date": f"202603{i + 1:02d}", "pe_ttm": 10.0 + i * 0.1, "pb": 2.0}
        for i in range(n)
    ]
    rows_b = [
        {"trade_date": f"202603{i + 1:02d}", "pe_ttm": 20.0 + i * 0.1, "pb": 3.0}
        for i in range(n)
    ]

    client = _make_client(
        ["000001.SH", "000002.SZ"],
        {
            "000001.SH": _make_daily_basic("000001.SH", rows_a),
            "000002.SZ": _make_daily_basic("000002.SZ", rows_b),
        },
    )

    result = fetch_industry_valuation(client, _L2_CODE, _ANALYSIS_DATE, history_years=1)

    assert result["current_pe_median"] is not None
    # 最新日 pe: median(12.4, 22.4) = 17.4
    assert abs(result["current_pe_median"] - 17.4) < 0.01

    # 当前值是序列最大值 → 分位 = 1.0
    assert result["pe_percentile_5y"] is not None
    assert abs(result["pe_percentile_5y"] - 1.0) < 1e-9
