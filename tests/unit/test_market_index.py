"""大盘指数日线 + 行业 vs 大盘相对强度计算。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.trend.fetch_market_index import compute_relative_strength, fetch_market_index


@pytest.fixture
def csi300_data():
    path = Path(__file__).parent.parent / "fixtures" / "csi300_index.json"
    return json.loads(path.read_text())["market_index"]


@pytest.fixture
def mock_client(csi300_data):
    client = MagicMock()
    client.call.return_value = pd.DataFrame(csi300_data)
    return client


def test_fetch_csi300(mock_client):
    df = fetch_market_index(mock_client, market_code="000300.SH", analysis_date="2026-01-31")
    assert not df.empty


def test_relative_strength_industry_vs_market():
    industry_returns = {"1m": 0.05, "3m": 0.10, "6m": 0.15, "12m": 0.20}
    market_returns = {"1m": 0.02, "3m": 0.05, "6m": 0.08, "12m": 0.10}
    rs = compute_relative_strength(industry_returns, market_returns)
    # 行业涨得比大盘多 → RS > 1
    assert rs["1m"] > 1
    assert rs["12m"] > 1


def test_relative_strength_underperformance():
    industry_returns = {"1m": -0.02, "3m": 0.01}
    market_returns = {"1m": 0.05, "3m": 0.05}
    rs = compute_relative_strength(industry_returns, market_returns)
    assert rs["1m"] < 1


def test_relative_strength_handles_none():
    industry_returns = {"1m": None, "3m": 0.05}
    market_returns = {"1m": 0.02, "3m": None}
    rs = compute_relative_strength(industry_returns, market_returns)
    assert rs["1m"] is None
    assert rs["3m"] is None
