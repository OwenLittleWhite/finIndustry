"""股票 → 关联概念(Tushare concept_detail 反查)。"""
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
def mock_tushare(fixture_data):
    """模拟 Tushare concept_detail 反查 600519。"""
    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "concept_detail":
            ts_code = params.get("ts_code", "")
            if ts_code == "600519.SH":
                return pd.DataFrame(fixture_data["tushare_concept_detail_600519"])
            return pd.DataFrame()
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


def test_returns_top_3_concepts_in_order(mock_tushare):
    """按 Tushare 返回顺序取前 N 个,heat_rank 是 1-based index。"""
    result = fetch_concept_mapping(mock_tushare, ticker="600519", top_n=3)
    assert len(result) == 3
    assert result[0]["name"] == "白酒概念"
    assert result[0]["code"] == "TS267"
    assert result[0]["heat_rank"] == 1
    assert result[1]["name"] == "沪股通"
    assert result[1]["heat_rank"] == 2
    assert result[2]["heat_rank"] == 3


def test_top_n_caps_result(mock_tushare):
    """top_n=2 限制返回 2 个。"""
    result = fetch_concept_mapping(mock_tushare, ticker="600519", top_n=2)
    assert len(result) == 2


def test_no_concept_returns_empty():
    client = MagicMock()
    client.call.return_value = pd.DataFrame()
    result = fetch_concept_mapping(client, ticker="999999")
    assert result == []


def test_includes_required_fields(mock_tushare):
    """每条记录都有 name / code / heat_rank / heat_score。"""
    result = fetch_concept_mapping(mock_tushare, ticker="600519", top_n=1)
    assert "name" in result[0]
    assert "code" in result[0]
    assert "heat_rank" in result[0]
    assert "heat_score" in result[0]
    assert result[0]["heat_score"] == 0.0  # Tushare 不提供热度
