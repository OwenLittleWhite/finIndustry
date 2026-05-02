"""行业主力资金净流入 - 单元测试。"""
import warnings
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.capital.fetch_main_flow import fetch_main_flow

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_ANALYSIS_DATE = "2026-04-30"
_INDUSTRY_NAME = "白酒Ⅱ"

# akshare stock_sector_fund_flow_rank 典型返回(今日)
# 金额单位:元;结果转换后单位:亿元(÷ 1e8)
_SECTOR_TODAY_ROWS = [
    {"名称": "食品饮料", "今日主力净流入-净额":  500_000_000.0},  # 5亿 → rank 1
    {"名称": "白酒",     "今日主力净流入-净额":  320_000_000.0},  # 3.2亿 → rank 2
    {"名称": "银行",     "今日主力净流入-净额":  180_000_000.0},
    {"名称": "医药",     "今日主力净流入-净额":  -50_000_000.0},
]

_SECTOR_5D_ROWS = [
    {"名称": "食品饮料", "5日主力净流入-净额": 2_000_000_000.0},
    {"名称": "白酒",     "5日主力净流入-净额": 1_200_000_000.0},  # 12亿
    {"名称": "银行",     "5日主力净流入-净额":   800_000_000.0},
]

_SECTOR_10D_ROWS = [
    {"名称": "食品饮料", "10日主力净流入-净额": 4_000_000_000.0},
    {"名称": "白酒",     "10日主力净流入-净额": 2_500_000_000.0},  # 25亿
    {"名称": "银行",     "10日主力净流入-净额": 1_500_000_000.0},
]


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_client(
    today_rows=_SECTOR_TODAY_ROWS,
    five_d_rows=_SECTOR_5D_ROWS,
    ten_d_rows=_SECTOR_10D_ROWS,
) -> MagicMock:
    client = MagicMock()

    def call_side_effect(func_name, **params):
        if func_name == "stock_sector_fund_flow_rank":
            indicator = params.get("indicator", "今日")
            if indicator == "今日":
                return pd.DataFrame(today_rows)
            if indicator == "5日":
                return pd.DataFrame(five_d_rows)
            if indicator == "10日":
                return pd.DataFrame(ten_d_rows)
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


# ---------------------------------------------------------------------------
# 测试 1: 返回所有必需字段
# ---------------------------------------------------------------------------


def test_fetch_returns_required_fields():
    """返回字典必须包含全部 5 个字段。"""
    client = _make_client()
    result = fetch_main_flow(client, _INDUSTRY_NAME, _ANALYSIS_DATE)

    required = {
        "industry_name",
        "main_inflow_today_yi",
        "main_inflow_5d_yi",
        "main_inflow_10d_yi",
        "rank_in_all_sectors_today",
    }
    assert required.issubset(result.keys()), f"缺少字段: {required - result.keys()}"
    assert result["industry_name"] == _INDUSTRY_NAME


# ---------------------------------------------------------------------------
# 测试 2: 模糊匹配(查"白酒Ⅱ"能命中"白酒")
# ---------------------------------------------------------------------------


def test_industry_name_matched_correctly():
    """
    查询"白酒Ⅱ"时,板块名称列中只有"白酒"(不带 Ⅱ),应能模糊匹配成功。
    今日主力净流入 = 3_200_000_000 元 ÷ 1e8 = 3.2 亿元。
    """
    client = _make_client()
    result = fetch_main_flow(client, "白酒Ⅱ", _ANALYSIS_DATE)

    assert result["main_inflow_today_yi"] is not None
    assert abs(result["main_inflow_today_yi"] - 3.2) < 1e-6, (
        f"期望 3.2 亿,实际 {result['main_inflow_today_yi']}"
    )
    assert result["main_inflow_5d_yi"] is not None
    assert abs(result["main_inflow_5d_yi"] - 12.0) < 1e-6
    assert result["main_inflow_10d_yi"] is not None
    assert abs(result["main_inflow_10d_yi"] - 25.0) < 1e-6


# ---------------------------------------------------------------------------
# 测试 3: 网络错误 → 所有字段为 None
# ---------------------------------------------------------------------------


def test_network_error_returns_none_fields():
    """
    AkshareClient.call 抛出 ConnectionError 时,
    fetch_main_flow 应捕获并返回所有数值字段为 None,不向上抛异常。
    """
    client = MagicMock()
    client.call.side_effect = ConnectionError("网络不通")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fetch_main_flow(client, _INDUSTRY_NAME, _ANALYSIS_DATE)

    # 不应抛异常
    assert result["industry_name"] == _INDUSTRY_NAME
    assert result["main_inflow_today_yi"] is None
    assert result["main_inflow_5d_yi"] is None
    assert result["main_inflow_10d_yi"] is None
    assert result["rank_in_all_sectors_today"] is None
    # 应有 warning
    assert any("网络错误" in str(w.message) for w in caught)
