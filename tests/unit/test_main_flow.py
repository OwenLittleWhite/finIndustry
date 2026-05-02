"""行业主力资金净流入(Tushare moneyflow 聚合)- 单元测试。"""
import warnings
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.capital.fetch_main_flow import fetch_main_flow

_ANALYSIS_DATE = "2026-04-30"
_L2_CODE = "801125.SI"

_MEMBERS = [
    {"ts_code": "600519.SH", "name": "贵州茅台", "l2_code": _L2_CODE},
    {"ts_code": "000858.SZ", "name": "五粮液", "l2_code": _L2_CODE},
]


def _make_moneyflow(ts_code: str, daily_amounts_wan: list[float]) -> pd.DataFrame:
    """生成 moneyflow 单股多日数据,trade_date 升序。

    daily_amounts_wan: 单位万元的 net_mf_amount 列表
    """
    rows = []
    for i, amount in enumerate(daily_amounts_wan):
        day = 16 + i
        rows.append({
            "trade_date": f"202604{day:02d}",
            "ts_code": ts_code,
            "net_mf_amount": amount,
        })
    return pd.DataFrame(rows)


def _make_client(
    members: list[dict] | None = None,
    flow_map: dict[str, pd.DataFrame] | None = None,
) -> MagicMock:
    if members is None:
        members = _MEMBERS
    if flow_map is None:
        flow_map = {}
    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return pd.DataFrame(members)
        if api_name == "moneyflow":
            ts_code = params.get("ts_code", "")
            if ts_code in flow_map:
                return flow_map[ts_code].copy()
            return pd.DataFrame()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


def test_fetch_returns_required_fields():
    flow_map = {
        "600519.SH": _make_moneyflow("600519.SH", [1000.0] * 11),
        "000858.SZ": _make_moneyflow("000858.SZ", [500.0] * 11),
    }
    client = _make_client(flow_map=flow_map)
    result = fetch_main_flow(client, _L2_CODE, _ANALYSIS_DATE)

    required = {
        "industry_l2_code", "main_inflow_today_yi",
        "main_inflow_5d_yi", "main_inflow_10d_yi",
        "constituent_count", "data_source",
    }
    assert required.issubset(result.keys())
    assert result["industry_l2_code"] == _L2_CODE
    assert result["data_source"] == "tushare.moneyflow"


def test_aggregation_sums_constituents():
    """
    2 只成分股,每天 net_mf_amount:茅台 10000 / 五粮液 5000 万元。
    11 天,行业当日 = 15000 万 = 1.5 亿;
    近 5 日累计 = 75000 万 = 7.5 亿;近 10 日累计 = 150000 万 = 15 亿。
    """
    flow_map = {
        "600519.SH": _make_moneyflow("600519.SH", [10000.0] * 11),
        "000858.SZ": _make_moneyflow("000858.SZ", [5000.0] * 11),
    }
    client = _make_client(flow_map=flow_map)
    result = fetch_main_flow(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["main_inflow_today_yi"] == pytest.approx(1.5, abs=1e-6)
    assert result["main_inflow_5d_yi"] == pytest.approx(7.5, abs=1e-6)
    assert result["main_inflow_10d_yi"] == pytest.approx(15.0, abs=1e-6)
    assert result["constituent_count"] == 2


def test_outflow_negative_values():
    """流出场景 — net_mf_amount 为负数(茅台 4-30 真实值)。"""
    flow_map = {
        "600519.SH": _make_moneyflow("600519.SH", [-168618.84] * 11),
    }
    client = _make_client(
        members=[{"ts_code": "600519.SH", "name": "贵州茅台", "l2_code": _L2_CODE}],
        flow_map=flow_map,
    )
    result = fetch_main_flow(client, _L2_CODE, _ANALYSIS_DATE)

    # -168618.84 万 = -16.8619 亿
    assert result["main_inflow_today_yi"] == pytest.approx(-16.8619, abs=1e-3)


def test_empty_industry_returns_empty():
    """成分股空 → graceful。"""
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = fetch_main_flow(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["main_inflow_today_yi"] is None
    assert result["constituent_count"] == 0


def test_partial_constituent_data_missing():
    """有些成分股 moneyflow 返回空 → 只用有数据的聚合。"""
    flow_map = {
        "600519.SH": _make_moneyflow("600519.SH", [10000.0] * 11),
        # 000858.SZ 没数据
    }
    client = _make_client(flow_map=flow_map)
    result = fetch_main_flow(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["main_inflow_today_yi"] == pytest.approx(1.0, abs=1e-6)


def test_network_error_returns_none_fields():
    client = MagicMock()
    client.call.side_effect = ConnectionError("simulated")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = fetch_main_flow(client, _L2_CODE, _ANALYSIS_DATE)

    assert result["main_inflow_today_yi"] is None
    assert result["constituent_count"] == 0
