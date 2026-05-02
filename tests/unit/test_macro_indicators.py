"""单测:fetch_macro_indicators — 行业宏观传导层数据原料。"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from scripts.macro_policy.fetch_macro_indicators import fetch_macro_indicators


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_cpi_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"month": "202604", "nt_val": 0.2, "nt_mom": 0.1, "town_val": 0.3,
         "town_mom": 0.05, "cnt_val": 0.15, "cnt_mom": 0.02},
        {"month": "202603", "nt_val": 0.3, "nt_mom": 0.05, "town_val": 0.35,
         "town_mom": 0.03, "cnt_val": 0.2, "cnt_mom": 0.01},
        {"month": "202602", "nt_val": 0.1, "nt_mom": -0.1, "town_val": 0.12,
         "town_mom": -0.08, "cnt_val": 0.08, "cnt_mom": -0.05},
    ])


def _make_ppi_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"month": "202604", "ppi_yoy": -1.5, "ppi_mp": 0.2},
        {"month": "202603", "ppi_yoy": -1.8, "ppi_mp": -0.1},
    ])


def _make_pmi_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"month": "202604", "pmi010000": 50.4},
        {"month": "202603", "pmi010000": 50.1},
    ])


def _make_m_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"month": "202604", "m0": 10.5, "m0_yoy": 12.0, "m1": 65.0,
         "m1_yoy": 4.5, "m2": 320.0, "m2_yoy": 7.2},
        {"month": "202603", "m0": 10.3, "m0_yoy": 11.5, "m1": 64.0,
         "m1_yoy": 4.0, "m2": 318.0, "m2_yoy": 7.0},
    ])


def _make_shibor_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "20260430", "on": 1.8, "1w": 1.9, "2w": 2.0,
         "1m": 2.1, "3m": 2.3, "6m": 2.5, "9m": 2.6, "1y": 2.8},
    ])


@pytest.fixture
def mock_pro_full():
    """mock pro 对象,所有接口都正常返回数据。"""
    pro = MagicMock()
    pro.cn_cpi.return_value = _make_cpi_df()
    pro.cn_ppi.return_value = _make_ppi_df()
    pro.cn_pmi.return_value = _make_pmi_df()
    pro.cn_m.return_value = _make_m_df()
    pro.shibor.return_value = _make_shibor_df()
    return pro


@pytest.fixture
def mock_client_full(mock_pro_full):
    """带 mock pro 的 TushareClient-like 对象。"""
    client = MagicMock()
    client.pro = mock_pro_full
    return client


# ---------------------------------------------------------------------------
# Test 1: 返回 dict 含所有必需顶层 key
# ---------------------------------------------------------------------------

def test_returns_all_required_top_keys(mock_client_full):
    result = fetch_macro_indicators(
        mock_client_full,
        analysis_date="2026-04-30",
        months=12,
    )
    assert isinstance(result, dict)
    for key in ("analysis_date", "cpi", "ppi", "pmi", "m_supply", "shibor"):
        assert key in result, f"缺少顶层 key: {key}"

    assert result["analysis_date"] == "2026-04-30"
    # 有数据的字段不应为 None
    assert result["cpi"] is not None
    assert result["ppi"] is not None
    assert result["m_supply"] is not None
    assert result["shibor"] is not None


# ---------------------------------------------------------------------------
# Test 2: CPI 列表降序(最新月在前,最早月在后)
# ---------------------------------------------------------------------------

def test_descending_order(mock_client_full):
    result = fetch_macro_indicators(
        mock_client_full,
        analysis_date="2026-04-30",
        months=3,
    )
    cpi = result["cpi"]
    assert isinstance(cpi, list)
    assert len(cpi) >= 2

    months_list = [r["month"] for r in cpi]
    # 验证降序:前一项 >= 后一项
    for i in range(len(months_list) - 1):
        assert months_list[i] >= months_list[i + 1], (
            f"CPI 不是降序: [{i}]={months_list[i]} < [{i+1}]={months_list[i+1]}"
        )
    # 最新月应在 index 0
    assert months_list[0] == max(months_list), "cpi[0] 应是最新月"
    # 最早月应在最后
    assert months_list[-1] == min(months_list), "cpi[-1] 应是最早月"


# ---------------------------------------------------------------------------
# Test 3: cn_pmi 抛权限异常时 pmi 返回 None,不影响其他字段
# ---------------------------------------------------------------------------

def test_pmi_permission_error_returns_none(mock_pro_full, mock_client_full):
    # 模拟 PMI 权限不足异常
    mock_pro_full.cn_pmi.side_effect = Exception(
        "您没有访问该接口的权限,请联系 tushare.pro 的客服申请接口权限"
    )

    result = fetch_macro_indicators(
        mock_client_full,
        analysis_date="2026-04-30",
        months=6,
    )

    # PMI 应为 None
    assert result["pmi"] is None, "cn_pmi 权限异常时 pmi 应为 None"
    # 其他字段不受影响
    assert result["cpi"] is not None, "cpi 不应受 PMI 异常影响"
    assert result["ppi"] is not None, "ppi 不应受 PMI 异常影响"
    assert result["m_supply"] is not None, "m_supply 不应受 PMI 异常影响"
    assert result["shibor"] is not None, "shibor 不应受 PMI 异常影响"


# ---------------------------------------------------------------------------
# Test 4: CPI 接口异常,其他字段仍正常返回
# ---------------------------------------------------------------------------

def test_partial_failure_other_fields_intact(mock_pro_full, mock_client_full):
    # 模拟 CPI 接口超时/网络异常
    mock_pro_full.cn_cpi.side_effect = Exception("ConnectionTimeout: tushare API unreachable")

    result = fetch_macro_indicators(
        mock_client_full,
        analysis_date="2026-04-30",
        months=6,
    )

    # CPI 失败应返回 None,不抛异常
    assert result["cpi"] is None, "CPI 接口异常时 cpi 应为 None"

    # 其他接口正常,字段应有数据
    assert isinstance(result["ppi"], list) and len(result["ppi"]) > 0, (
        "ppi 应有数据"
    )
    assert isinstance(result["m_supply"], list) and len(result["m_supply"]) > 0, (
        "m_supply 应有数据"
    )
    assert isinstance(result["shibor"], dict), "shibor 应为 dict"
    assert result["analysis_date"] == "2026-04-30"
