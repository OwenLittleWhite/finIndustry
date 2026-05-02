"""股票 → 申万二级行业映射。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.classification.fetch_industry_classification import fetch_industry_classification


@pytest.fixture
def fixture_data():
    path = Path(__file__).parent.parent / "fixtures" / "600519_classification.json"
    return json.loads(path.read_text())


@pytest.fixture
def mock_tushare(fixture_data):
    client = MagicMock()
    client.call.return_value = pd.DataFrame(fixture_data["tushare_index_member_all"])
    return client


def test_returns_l2_classification(mock_tushare):
    result = fetch_industry_classification(mock_tushare, ticker="600519")
    assert result["primary_industry"]["system"] == "申万二级"
    assert result["primary_industry"]["code"] == "801125.SI"
    assert result["primary_industry"]["name"] == "白酒"


def test_includes_l1_for_context(mock_tushare):
    result = fetch_industry_classification(mock_tushare, ticker="600519")
    assert result["l1_industry"]["code"] == "801120.SI"
    assert result["l1_industry"]["name"] == "食品饮料"


def test_unknown_ticker_returns_none():
    client = MagicMock()
    client.call.return_value = pd.DataFrame()  # 空结果
    result = fetch_industry_classification(client, ticker="999999")
    assert result is None
