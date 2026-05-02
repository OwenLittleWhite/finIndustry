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
                {"ts_code": f"00000{i}.SZ"} for i in range(10)
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
        industry_l2_code="801125.SI",
        analysis_date="2026-04-30",
    )
    assert result["advance"] == 7
    assert result["decline"] == 3
    assert result["limit_up"] == 2
    assert result["advance_decline_ratio"] == pytest.approx(7 / 3, rel=1e-3)


def test_no_constituents_returns_zeros():
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = compute_breadth_for_industry(
        client, industry_l2_code="801999.SI", analysis_date="2026-04-30"
    )
    assert result["advance"] == 0
    assert result["decline"] == 0
    assert result["advance_decline_ratio"] is None
