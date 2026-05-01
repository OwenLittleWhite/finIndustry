"""TushareClient - thin wrapper that adds caching + analysis_date guard."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient


@pytest.fixture
def mock_pro():
    """Mock tushare pro_api object."""
    pro = MagicMock()
    pro.sw_daily.return_value = pd.DataFrame(
        [{"trade_date": "20260429", "ts_code": "801080.SI", "close": 5000.0}]
    )
    return pro


@pytest.fixture
def client(tmp_path, mock_pro):
    return TushareClient(pro=mock_pro, cache=Cache(tmp_path), analysis_date="2026-04-30")


def test_call_invokes_underlying_api(client, mock_pro):
    df = client.call("sw_daily", ts_code="801080.SI", end_date="20260429")
    mock_pro.sw_daily.assert_called_once()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["ts_code"] == "801080.SI"


def test_second_call_hits_cache(client, mock_pro):
    client.call("sw_daily", ts_code="801080.SI", end_date="20260429")
    client.call("sw_daily", ts_code="801080.SI", end_date="20260429")
    assert mock_pro.sw_daily.call_count == 1  # 第二次走缓存


def test_returns_empty_df_when_api_returns_none(tmp_path):
    pro = MagicMock()
    pro.sw_daily.return_value = None
    client = TushareClient(pro=pro, cache=Cache(tmp_path), analysis_date="2026-04-30")
    df = client.call("sw_daily", ts_code="X")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_lookahead_guard_rejects_future_end_date(client):
    with pytest.raises(ValueError, match="lookahead"):
        client.call("sw_daily", ts_code="801080.SI", end_date="20260501")
