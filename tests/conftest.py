"""Shared fixtures for integration tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_tushare_for_600519(fixtures_dir):
    """聚合 600519 端到端的 mock Tushare 客户端。"""
    classification = json.loads((fixtures_dir / "600519_classification.json").read_text())
    industry_index = json.loads((fixtures_dir / "801123_index.json").read_text())
    csi300 = json.loads((fixtures_dir / "csi300_index.json").read_text())

    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            ts_code = params.get("ts_code", "")
            if ts_code == "600519.SH":
                return pd.DataFrame(classification["tushare_index_member_all"])
            # 行业成分股查询(给个简化的:10 只)
            return pd.DataFrame([{"con_code": f"00000{i}.SZ"} for i in range(10)])
        if api_name == "sw_daily":
            return pd.DataFrame(industry_index["industry_index"])
        if api_name == "index_daily":
            return pd.DataFrame(csi300["market_index"])
        if api_name == "daily":
            return pd.DataFrame([{"ts_code": params.get("ts_code"), "pct_chg": 1.5, "trade_date": "20260430"}])
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client


@pytest.fixture
def mock_akshare_for_600519(fixtures_dir):
    classification = json.loads((fixtures_dir / "600519_classification.json").read_text())
    client = MagicMock()

    def call_side_effect(function_name, **params):
        if function_name == "stock_board_concept_name_em":
            return pd.DataFrame(classification["akshare_concept_heat"])
        if function_name == "stock_board_concept_cons_em":
            symbol = params.get("symbol", "")
            for c in classification["akshare_concept_em"]:
                if c["概念名称"] == symbol:
                    return pd.DataFrame([
                        {"代码": code} for code in c["成分股"].split(",")
                    ])
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client
