"""申万行业指数日线获取 + 多窗口涨跌计算。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.trend.fetch_industry_index import (
    compute_window_returns,
    fetch_industry_index,
)


@pytest.fixture
def index_data():
    path = Path(__file__).parent.parent / "fixtures" / "801123_index.json"
    return json.loads(path.read_text())["industry_index"]


@pytest.fixture
def mock_client(index_data):
    client = MagicMock()
    client.call.return_value = pd.DataFrame(index_data)
    return client


def test_fetch_returns_dataframe(mock_client):
    df = fetch_industry_index(
        mock_client,
        index_code="801123.SI",
        analysis_date="2026-01-31",
        lookback_days=250,
    )
    assert not df.empty
    assert "close" in df.columns


def test_compute_window_returns_includes_1m_3m_6m_12m(mock_client):
    df = fetch_industry_index(
        mock_client,
        index_code="801123.SI",
        analysis_date="2026-01-31",
        lookback_days=250,
    )
    returns = compute_window_returns(df)
    assert "1m" in returns
    assert "3m" in returns
    assert "6m" in returns
    assert "12m" in returns


def test_short_history_handles_missing_window(index_data):
    # 只给 30 天,12m 应该返回 None
    short = pd.DataFrame(index_data[:30])
    returns = compute_window_returns(short)
    assert returns["1m"] is not None
    assert returns["12m"] is None
