"""AkshareClient - 类似 TushareClient,wrap akshare 函数 + 缓存。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.common.akshare_client import AkshareClient
from scripts.common.cache import Cache


@pytest.fixture
def mock_akshare_module():
    mod = MagicMock()
    mod.stock_sector_fund_flow_rank.return_value = pd.DataFrame(
        [{"名称": "白酒", "今日主力净流入-净额": 1.2e9}]
    )
    # Make accessing unknown attributes raise AttributeError (mimicking real module strictness)
    mod.function_does_not_exist = MagicMock(side_effect=AttributeError("function_does_not_exist"))
    return mod


@pytest.fixture
def client(tmp_path, mock_akshare_module):
    return AkshareClient(
        ak_module=mock_akshare_module,
        cache=Cache(tmp_path),
        analysis_date="2026-04-30",
    )


def test_call_invokes_function(client, mock_akshare_module):
    df = client.call("stock_sector_fund_flow_rank", indicator="今日")
    mock_akshare_module.stock_sector_fund_flow_rank.assert_called_once_with(indicator="今日")
    assert df.iloc[0]["名称"] == "白酒"


def test_second_call_hits_cache(client, mock_akshare_module):
    client.call("stock_sector_fund_flow_rank", indicator="今日")
    client.call("stock_sector_fund_flow_rank", indicator="今日")
    assert mock_akshare_module.stock_sector_fund_flow_rank.call_count == 1


def test_unknown_function_raises(client):
    with pytest.raises(AttributeError):
        client.call("function_does_not_exist")
