"""北向资金行业偏好 - 单元测试。"""
import warnings
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.capital.fetch_northbound import fetch_northbound

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_ANALYSIS_DATE = "2026-04-30"
_L2_CODE = "801125.SI"

# 3 只成分股
_MEMBERS = [
    {"ts_code": "600519.SH", "name": "贵州茅台", "l2_code": _L2_CODE},
    {"ts_code": "000858.SZ", "name": "五粮液",   "l2_code": _L2_CODE},
    {"ts_code": "600809.SH", "name": "山西汾酒", "l2_code": _L2_CODE},
]

# 每只股的 hk_hold 数据(market_value 单位:万元)
# 11 天数据:trade_date 升序,日期 20260420 ~ 20260430
def _make_hk_hold(ts_code: str, base_mv: float) -> pd.DataFrame:
    """生成 11 行港股通持仓数据,trade_date 升序。"""
    rows = []
    for i in range(11):
        # 20260420 → 20260430
        day = 20 + i
        rows.append({
            "ts_code": ts_code,
            "trade_date": f"202604{day:02d}",
            "market_value": base_mv * (1 + i * 0.01),  # 每天小幅增加
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _make_client(
    member_rows=None,
    hk_hold_data: dict | None = None,
) -> MagicMock:
    """
    构建 mock TushareClient。
    hk_hold_data: {ts_code: DataFrame} 或 None(返回空 DataFrame)
    """
    if member_rows is None:
        member_rows = _MEMBERS
    if hk_hold_data is None:
        hk_hold_data = {}

    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return pd.DataFrame(member_rows)
        if api_name == "hk_hold":
            ts_code = params.get("ts_code", "")
            if ts_code in hk_hold_data:
                return hk_hold_data[ts_code].copy()
            return pd.DataFrame()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


# ---------------------------------------------------------------------------
# 测试 1: 返回所有必需字段
# ---------------------------------------------------------------------------


def test_fetch_returns_required_fields():
    """返回字典必须包含全部 4 个字段,且 industry_l2_code 正确。"""
    hk_hold_data = {
        ts: _make_hk_hold(ts, base_mv=10000.0)
        for ts in ["600519.SH", "000858.SZ", "600809.SH"]
    }
    client = _make_client(hk_hold_data=hk_hold_data)
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    required = {
        "industry_l2_code",
        "current_holding_value",
        "change_5d_pct",
        "change_10d_pct",
    }
    assert required.issubset(result.keys()), f"缺少字段: {required - result.keys()}"
    assert result["industry_l2_code"] == _L2_CODE


# ---------------------------------------------------------------------------
# 测试 2: 持仓市值为各成分股之和
# ---------------------------------------------------------------------------


def test_aggregation_sums_constituents():
    """
    3 只成分股各有持仓数据,当日总持仓 = 3 只之和。
    base_mv: 茅台 50000, 五粮液 30000, 山西汾酒 20000 (万元)
    最后一天 (i=10): mv * (1 + 10 * 0.01)
    茅台: 50000 * 1.10 = 55000
    五粮液: 30000 * 1.10 = 33000
    山西汾酒: 20000 * 1.10 = 22000
    总计: 110000 万元
    """
    hk_hold_data = {
        "600519.SH": _make_hk_hold("600519.SH", base_mv=50000.0),
        "000858.SZ": _make_hk_hold("000858.SZ", base_mv=30000.0),
        "600809.SH": _make_hk_hold("600809.SH", base_mv=20000.0),
    }
    client = _make_client(hk_hold_data=hk_hold_data)
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["current_holding_value"] is not None
    expected = (50000 + 30000 + 20000) * 1.10
    assert abs(result["current_holding_value"] - expected) < 1.0, (
        f"期望约 {expected:.0f} 万元,实际 {result['current_holding_value']:.0f}"
    )


# ---------------------------------------------------------------------------
# 测试 3: 变化率计算正确性
# ---------------------------------------------------------------------------


def test_change_calculation_correctness():
    """
    用单只股票精确验算 change_5d_pct 和 change_10d_pct。

    构造: 11 天数据,每天固定值(不增长)→ 变化率应为 0.0
    用等差增长验算精确数值。
    """
    # 单只成分股,持仓市值从 100 → 110(每天 +1)
    # i=0: 100, i=1: 101, ..., i=10: 110
    # change_5d_pct = (110 - 105) / 105 = 5/105
    # change_10d_pct = (110 - 100) / 100 = 10/100 = 0.1
    rows = []
    for i in range(11):
        rows.append({
            "ts_code": "600519.SH",
            "trade_date": f"202604{20 + i:02d}",
            "market_value": float(100 + i),
        })
    hk_hold_data = {"600519.SH": pd.DataFrame(rows)}

    # 单只成分股
    members = [{"ts_code": "600519.SH", "name": "贵州茅台", "l2_code": _L2_CODE}]
    client = _make_client(member_rows=members, hk_hold_data=hk_hold_data)
    result = fetch_northbound(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["current_holding_value"] is not None
    assert abs(result["current_holding_value"] - 110.0) < 1e-6

    # change_5d: (110 - 105) / 105
    expected_5d = (110 - 105) / 105
    assert result["change_5d_pct"] is not None
    assert abs(result["change_5d_pct"] - expected_5d) < 1e-6, (
        f"期望 change_5d_pct={expected_5d:.6f}, 实际={result['change_5d_pct']:.6f}"
    )

    # change_10d: (110 - 100) / 100 = 0.1
    assert result["change_10d_pct"] is not None
    assert abs(result["change_10d_pct"] - 0.1) < 1e-6
