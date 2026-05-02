"""Shared fixtures for integration tests."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

# 白酒 Top 5 (申万二级 801125.SI) - 真实股票 + 虚拟市值,用于 leader integration test
WHITE_LIQUOR_TOP5 = [
    {"ts_code": "600519.SH", "name": "贵州茅台", "total_mv": 17341e4, "close": 1384.79, "pe_ttm": 21.0},
    {"ts_code": "000858.SZ", "name": "五粮液",   "total_mv":  3768e4, "close":  100.0, "pe_ttm": 13.3},
    {"ts_code": "600809.SH", "name": "山西汾酒", "total_mv":  1749e4, "close":  150.0, "pe_ttm": 15.9},
    {"ts_code": "000568.SZ", "name": "泸州老窖", "total_mv":  1473e4, "close":  120.0, "pe_ttm": 14.8},
    {"ts_code": "002304.SZ", "name": "洋河股份", "total_mv":   742e4, "close":   80.0, "pe_ttm": 73.0},
]


def _synth_daily_for_leader(ts_code: str, base_close: float, n_rows: int = 25) -> pd.DataFrame:
    """生成 n_rows 行降序日线,close 从 base_close 缓慢下跌(模拟白酒近期下跌走势)。"""
    rows = []
    close = base_close
    for i in range(n_rows):
        # 倒序递增 trade_date (latest first)
        date = f"2026{4 if i < 21 else 3:02d}{30 - i if i < 21 else 30 - i + 30:02d}"
        rows.append({
            "ts_code": ts_code,
            "trade_date": date,
            "open": close * 1.005,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": round(close, 2),
            "pct_chg": -0.3 if i % 3 != 0 else 0.5,
        })
        close *= 1.002  # 越往前越高(模拟下跌)
    return pd.DataFrame(rows)


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_tushare_for_600519(fixtures_dir):
    """聚合 600519 端到端的 mock Tushare 客户端。

    覆盖的接口:
    - index_member_all: 股票 → 申万二级 / 行业 → 成分股(含 name 字段)
    - sw_daily: 申万行业指数日线
    - index_daily: 大盘指数日线
    - daily: 个股日线(支持白酒 Top 5,返回 25 行用于 1M 计算)
    - daily_basic: 全市场基本面(返回白酒 Top 5 的 total_mv / close / pe_ttm)
    - concept_detail: 股票 → 所属 Tushare 概念
    """
    classification = json.loads((fixtures_dir / "600519_classification.json").read_text())
    industry_index = json.loads((fixtures_dir / "801125_index.json").read_text())
    csi300 = json.loads((fixtures_dir / "csi300_index.json").read_text())

    client = MagicMock()

    def call_side_effect(api_name, **params):
        if api_name == "index_member_all":
            ts_code = params.get("ts_code", "")
            l2_code = params.get("l2_code", "")
            if ts_code == "600519.SH":
                return pd.DataFrame(classification["tushare_index_member_all"])
            if l2_code == "801125.SI":
                # 白酒 5 只龙头(带 name 字段,leader fetcher 会用)
                return pd.DataFrame([
                    {"ts_code": L["ts_code"], "name": L["name"], "l2_code": "801125.SI",
                     "l1_code": "801120.SI", "is_new": "Y"}
                    for L in WHITE_LIQUOR_TOP5
                ])
            # 其他行业成分股查询的 fallback
            return pd.DataFrame([{"ts_code": f"00000{i}.SZ"} for i in range(10)])
        if api_name == "daily_basic":
            # 全市场基本面,leader fetcher 会过滤本行业成分股
            return pd.DataFrame([
                {"ts_code": L["ts_code"], "total_mv": L["total_mv"],
                 "close": L["close"], "pe_ttm": L["pe_ttm"]}
                for L in WHITE_LIQUOR_TOP5
            ])
        if api_name == "concept_detail":
            ts_code = params.get("ts_code", "")
            if ts_code == "600519.SH":
                return pd.DataFrame(classification["tushare_concept_detail_600519"])
            return pd.DataFrame()
        if api_name == "sw_daily":
            return pd.DataFrame(industry_index["industry_index"])
        if api_name == "index_daily":
            return pd.DataFrame(csi300["market_index"])
        if api_name == "daily":
            ts_code = params.get("ts_code", "")
            for L in WHITE_LIQUOR_TOP5:
                if L["ts_code"] == ts_code:
                    return _synth_daily_for_leader(ts_code, L["close"])
            # fallback: breadth 测试用单行
            return pd.DataFrame([{"ts_code": ts_code, "pct_chg": 1.5, "trade_date": "20260430"}])
        return pd.DataFrame()

    client.call.side_effect = call_side_effect
    return client
