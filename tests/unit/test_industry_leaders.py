"""申万行业 Top-N 市值龙头股获取 - 单元测试。"""
from unittest.mock import MagicMock, call

import pandas as pd
import pytest

from scripts.leaders.fetch_industry_leaders import fetch_industry_leaders

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_ANALYSIS_DATE = "2026-04-30"
_TRADE_DATE = "20260430"
_L2_CODE = "801125.SI"


def _make_member_df(n: int) -> pd.DataFrame:
    """生成 n 只成分股的 index_member_all 返回结果。"""
    return pd.DataFrame({"ts_code": [f"{i:06d}.SH" for i in range(1, n + 1)]})


def _make_daily_basic_df(ts_codes: list[str]) -> pd.DataFrame:
    """给每只股一个不同 total_mv,方便测试排序(市值与列表顺序相同但值不同)。"""
    rows = []
    for i, code in enumerate(ts_codes):
        rows.append(
            {
                "ts_code": code,
                "total_mv": float((len(ts_codes) - i) * 10_000),  # 降序: 第1只最大
                "close": 100.0 + i,
                "pe_ttm": 25.0 + i,
            }
        )
    return pd.DataFrame(rows)


def _make_daily_df(n_rows: int, ts_code: str = "000001.SH") -> pd.DataFrame:
    """生成 n_rows 行的 daily 日线数据(降序 trade_date)。"""
    rows = []
    for i in range(n_rows):
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": f"2026{(4 - i // 30 + 1):02d}{(30 - i % 30):02d}",
                "close": 100.0 - i * 0.1,  # 轻微下跌,方便验算
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# mock client factory
# ---------------------------------------------------------------------------


def _make_client(
    n_members: int = 10,
    daily_rows: int = 65,
) -> MagicMock:
    """
    构建一个 MagicMock client,按 api_name 返回对应数据。
    成分股固定 n_members 只,每只股 daily 给 daily_rows 行。
    """
    members = _make_member_df(n_members)
    ts_codes = members["ts_code"].tolist()
    daily_basic = _make_daily_basic_df(ts_codes)

    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            return members.copy()
        if api_name == "daily_basic":
            return daily_basic.copy()
        if api_name == "daily":
            return _make_daily_df(daily_rows, ts_code=params.get("ts_code", ""))
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_returns_top_n_by_market_cap():
    """成分股 10 只,按 total_mv 降序取 Top 5。"""
    client = _make_client(n_members=10, daily_rows=65)
    result = fetch_industry_leaders(client, _L2_CODE, _ANALYSIS_DATE, top_n=5)

    assert len(result) == 5
    # 确认按 total_mv 降序
    mvs = [r["total_mv"] for r in result]
    assert mvs == sorted(mvs, reverse=True)


def test_includes_required_fields():
    """每个龙头 dict 必须包含全部 7 个字段。"""
    client = _make_client(n_members=10, daily_rows=65)
    result = fetch_industry_leaders(client, _L2_CODE, _ANALYSIS_DATE, top_n=5)

    required = {"ticker", "name", "total_mv", "close", "pe_ttm", "return_1m", "return_3m"}
    for item in result:
        assert required.issubset(item.keys()), f"缺少字段: {required - item.keys()}"


def test_returns_1m_3m_when_data_sufficient():
    """给 65 行 daily 数据时,return_1m 和 return_3m 都不为 None。"""
    client = _make_client(n_members=5, daily_rows=65)
    result = fetch_industry_leaders(client, _L2_CODE, _ANALYSIS_DATE, top_n=5)

    for item in result:
        assert item["return_1m"] is not None, f"{item['ticker']} return_1m 应该不为 None"
        assert item["return_3m"] is not None, f"{item['ticker']} return_3m 应该不为 None"


def test_returns_none_when_history_insufficient():
    """只给 10 行 daily,1m(需要 21 行)不满足 → return_1m 为 None;3m 同理。"""
    client = _make_client(n_members=5, daily_rows=10)
    result = fetch_industry_leaders(client, _L2_CODE, _ANALYSIS_DATE, top_n=5)

    for item in result:
        # 10 行 < 21(latest + idx 20),1m 也应该是 None
        assert item["return_1m"] is None, f"{item['ticker']} return_1m 应该为 None(数据不足)"
        assert item["return_3m"] is None, f"{item['ticker']} return_3m 应该为 None(数据不足)"


def test_empty_industry_returns_empty_list():
    """成分股查询返回空 DataFrame → 函数返回空列表。"""
    client = MagicMock()
    client.call.return_value = pd.DataFrame()

    result = fetch_industry_leaders(client, _L2_CODE, _ANALYSIS_DATE, top_n=5)
    assert result == []
