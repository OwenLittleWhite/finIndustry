"""股票 → 关联热门概念(取近 30 天热度 top 3)。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.classification.fetch_concept_mapping import fetch_concept_mapping


@pytest.fixture
def fixture_data():
    path = Path(__file__).parent.parent / "fixtures" / "600519_classification.json"
    return json.loads(path.read_text())


@pytest.fixture
def mock_akshare(fixture_data):
    """模拟两次 akshare 调用:概念列表(含热度) + 概念成分。"""
    client = MagicMock()

    def call_side_effect(function_name, **params):
        if function_name == "stock_board_concept_name_em":
            return pd.DataFrame(fixture_data["akshare_concept_heat"])
        if function_name == "stock_board_concept_cons_em":
            symbol = params.get("symbol", "")
            for concept in fixture_data["akshare_concept_em"]:
                if concept["概念名称"] == symbol:
                    return pd.DataFrame([
                        {"代码": code} for code in concept["成分股"].split(",")
                    ])
            return pd.DataFrame()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


def test_returns_top_3_hot_concepts(mock_akshare):
    result = fetch_concept_mapping(mock_akshare, ticker="600519", top_n=3)
    assert len(result) <= 3
    # 茅指数热度 rank 3 → 第一
    assert result[0]["name"] == "茅指数"
    assert result[0]["heat_rank"] == 3


def test_filters_only_concepts_containing_ticker(mock_akshare):
    """概念里必须包含 600519,否则不算。"""
    result = fetch_concept_mapping(mock_akshare, ticker="600519")
    names = [c["name"] for c in result]
    for n in names:
        assert n in {"高端消费", "ROE大白马", "茅指数"}


def test_no_concept_returns_empty():
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = fetch_concept_mapping(client, ticker="999999")
    assert result == []
