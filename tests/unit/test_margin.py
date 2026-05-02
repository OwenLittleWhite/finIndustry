"""行业融资融券余额聚合 - 单元测试。"""
import warnings
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.capital.fetch_margin import fetch_margin

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_ANALYSIS_DATE = "2026-04-30"
_L2_CODE = "801125.SI"

# 行业成分股(白酒 3 只)
_MEMBERS = [
    {"ts_code": "600519.SH", "name": "贵州茅台", "l2_code": _L2_CODE},
    {"ts_code": "000858.SZ", "name": "五粮液",   "l2_code": _L2_CODE},
    {"ts_code": "600809.SH", "name": "山西汾酒", "l2_code": _L2_CODE},
]

# 全市场融资余额数据(包含行业内外的股票)
# 金额单位:元;结果转换后单位:亿元(÷ 1e8)
_MARKET_MARGIN_CURRENT = pd.DataFrame([
    {"ts_code": "600519.SH", "rzye": 5_000_000_000.0},   # 50亿元  (行业内)
    {"ts_code": "000858.SZ", "rzye": 3_000_000_000.0},   # 30亿元  (行业内)
    {"ts_code": "600809.SH", "rzye": 2_000_000_000.0},   # 20亿元  (行业内)
    {"ts_code": "000001.SZ", "rzye": 1_000_000_000.0},   # 10亿元  (行业外)
    {"ts_code": "600036.SH", "rzye":   800_000_000.0},   #  8亿元  (行业外)
])

# 5 日前的行业内融资余额
_MARKET_MARGIN_5D = pd.DataFrame([
    {"ts_code": "600519.SH", "rzye": 4_800_000_000.0},
    {"ts_code": "000858.SZ", "rzye": 2_900_000_000.0},
    {"ts_code": "600809.SH", "rzye": 1_900_000_000.0},
    {"ts_code": "000001.SZ", "rzye":   950_000_000.0},
])

# 20 日前的行业内融资余额
_MARKET_MARGIN_20D = pd.DataFrame([
    {"ts_code": "600519.SH", "rzye": 4_500_000_000.0},
    {"ts_code": "000858.SZ", "rzye": 2_700_000_000.0},
    {"ts_code": "600809.SH", "rzye": 1_800_000_000.0},
    {"ts_code": "000001.SZ", "rzye":   900_000_000.0},
])

# 行业内融资余额合计(亿元)  = 元合计 ÷ 1e8
_CURRENT_YI = (50 + 30 + 20)   # 100亿
_5D_YI = (48 + 29 + 19)        # 96亿
_20D_YI = (45 + 27 + 18)       # 90亿


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_client(
    member_rows=None,
    current_df=None,
    df_5d=None,
    df_20d=None,
) -> MagicMock:
    """
    构建 mock TushareClient。
    按 trade_date 返回不同的 margin_detail 数据。
    """
    if member_rows is None:
        member_rows = _MEMBERS
    if current_df is None:
        current_df = _MARKET_MARGIN_CURRENT
    if df_5d is None:
        df_5d = _MARKET_MARGIN_5D
    if df_20d is None:
        df_20d = _MARKET_MARGIN_20D

    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return pd.DataFrame(member_rows)
        if api_name == "margin_detail":
            trade_date = params.get("trade_date", "")
            # 当日
            if trade_date == "20260430":
                return current_df.copy()
            # 约 5 日前(20260422)
            if trade_date == "20260422":
                return df_5d.copy()
            # 约 20 日前(20260331)
            if trade_date == "20260331":
                return df_20d.copy()
            return pd.DataFrame()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


# ---------------------------------------------------------------------------
# 测试 1: 返回所有必需字段
# ---------------------------------------------------------------------------


def test_fetch_returns_required_fields():
    """返回字典必须包含全部 4 个字段,且 industry_l2_code 正确。"""
    client = _make_client()
    result = fetch_margin(client, _L2_CODE, _ANALYSIS_DATE)

    required = {
        "industry_l2_code",
        "current_margin_balance_yi",
        "change_5d_pct",
        "change_20d_pct",
    }
    assert required.issubset(result.keys()), f"缺少字段: {required - result.keys()}"
    assert result["industry_l2_code"] == _L2_CODE


# ---------------------------------------------------------------------------
# 测试 2: 只聚合行业成分股,过滤行业外股票
# ---------------------------------------------------------------------------


def test_aggregation_filters_industry_constituents():
    """
    全市场融资余额包含行业外股票(000001.SZ, 600036.SH),
    只有行业内的 3 只股票应被纳入加总。

    当日行业总融资余额 = 50 + 30 + 20 = 100 亿元
    (_MARKET_MARGIN_CURRENT 中行业外的 000001/600036 不计入)
    """
    client = _make_client()
    result = fetch_margin(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["current_margin_balance_yi"] is not None
    # 50+30+20 = 100 亿元(单位:亿元 = 元 ÷ 1e8)
    assert abs(result["current_margin_balance_yi"] - _CURRENT_YI) < 1e-6, (
        f"期望 {_CURRENT_YI} 亿,实际 {result['current_margin_balance_yi']}"
    )


# ---------------------------------------------------------------------------
# 测试 3: 变化率计算正确性
# ---------------------------------------------------------------------------


def test_change_calculation_correctness():
    """
    精确验算 change_5d_pct 和 change_20d_pct:
    current = 100亿, 5d_ago = 96亿, 20d_ago = 90亿
    change_5d  = (100 - 96) / 96
    change_20d = (100 - 90) / 90
    """
    client = _make_client()
    result = fetch_margin(client, _L2_CODE, _ANALYSIS_DATE)

    expected_5d = (_CURRENT_YI - _5D_YI) / _5D_YI
    expected_20d = (_CURRENT_YI - _20D_YI) / _20D_YI

    assert result["change_5d_pct"] is not None
    assert abs(result["change_5d_pct"] - expected_5d) < 1e-6, (
        f"期望 change_5d_pct={expected_5d:.6f}, 实际={result['change_5d_pct']:.6f}"
    )

    assert result["change_20d_pct"] is not None
    assert abs(result["change_20d_pct"] - expected_20d) < 1e-6, (
        f"期望 change_20d_pct={expected_20d:.6f}, 实际={result['change_20d_pct']:.6f}"
    )
