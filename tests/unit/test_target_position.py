"""目标股 vs 行业龙头的位置判定测试。"""
import pytest

from scripts.leaders.compute_target_position import compute_target_position


# 一组通用的 fake leaders,5 只白酒,total_mv 降序
LEADERS = [
    {"ticker": "600519.SH", "name": "贵州茅台", "total_mv": 17341e4, "return_1m": -0.05, "return_3m": 0.03},
    {"ticker": "000858.SZ", "name": "五粮液",   "total_mv":  3768e4, "return_1m": -0.07, "return_3m": -0.04},
    {"ticker": "600809.SH", "name": "山西汾酒", "total_mv":  1749e4, "return_1m": -0.01, "return_3m": -0.11},
    {"ticker": "000568.SZ", "name": "泸州老窖", "total_mv":  1473e4, "return_1m": -0.06, "return_3m": -0.10},
    {"ticker": "002304.SZ", "name": "洋河股份", "total_mv":   742e4, "return_1m": -0.04, "return_3m": -0.09},
]


def test_target_is_top_1():
    """600519 是 Top 1 → 绝对龙头。"""
    result = compute_target_position(
        target_ticker="600519.SH",
        target_return_1m=-0.05,
        target_return_3m=0.03,
        leaders=LEADERS,
    )
    assert result["rank_in_industry"] == 1
    assert result["target_position"] == "绝对龙头"
    assert "茅台" in result["rationale"]


@pytest.mark.parametrize("ticker,expected_rank", [
    ("000858.SZ", 2),
    ("600809.SH", 3),
    ("000568.SZ", 4),
    ("002304.SZ", 5),
])
def test_target_in_top_2_to_5(ticker, expected_rank):
    """二线龙头(rank 2-5)。"""
    leader = next(L for L in LEADERS if L["ticker"] == ticker)
    result = compute_target_position(
        target_ticker=ticker,
        target_return_1m=leader["return_1m"],
        target_return_3m=leader["return_3m"],
        leaders=LEADERS,
    )
    assert result["rank_in_industry"] == expected_rank
    assert result["target_position"] == "二线龙头"


def test_target_outside_top5_but_strong():
    """非 Top 5 + 1M 强于龙头平均 → 跟随。"""
    # leaders 1M 平均 = (-0.05 + -0.07 + -0.01 + -0.06 + -0.04)/5 = -0.046
    # target_1m = +0.02,RS = (1+0.02)/(1+(-0.046)) = 1.02/0.954 ≈ 1.069 > 1
    result = compute_target_position(
        target_ticker="600702.SH",  # 沱牌舍得,不在 Top 5
        target_return_1m=0.02,
        target_return_3m=-0.05,
        leaders=LEADERS,
    )
    assert result["rank_in_industry"] is None
    assert result["target_position"] == "跟随"
    assert result["rs_vs_leaders_avg_1m"] > 1.0


def test_target_outside_top5_and_weak():
    """非 Top 5 + 1M 弱于龙头平均 → 落后。"""
    # leaders 1M avg ≈ -0.046,target_1m = -0.15 远低于,RS < 1
    result = compute_target_position(
        target_ticker="600702.SH",
        target_return_1m=-0.15,
        target_return_3m=-0.20,
        leaders=LEADERS,
    )
    assert result["rank_in_industry"] is None
    assert result["target_position"] == "落后"
    assert result["rs_vs_leaders_avg_1m"] < 1.0


def test_data_insufficient_returns_unknown():
    """leaders 为空 → 无法判断。"""
    result = compute_target_position(
        target_ticker="600702.SH",
        target_return_1m=-0.05,
        target_return_3m=-0.10,
        leaders=[],
    )
    assert result["rank_in_industry"] is None
    assert result["target_position"] == "无法判断"
    assert result["leaders_avg_1m"] is None


def test_data_insufficient_when_target_returns_none():
    """target return 为 None,无法算 RS,且不在 Top 5 → 无法判断。"""
    result = compute_target_position(
        target_ticker="600702.SH",
        target_return_1m=None,
        target_return_3m=None,
        leaders=LEADERS,
    )
    assert result["target_position"] == "无法判断"
    assert result["rs_vs_leaders_avg_1m"] is None


def test_rs_calculation_correct():
    """手算验证 RS。leaders 1M avg = -0.046,target_1m = 0.0,RS = 1/0.954 ≈ 1.0482。"""
    result = compute_target_position(
        target_ticker="600702.SH",
        target_return_1m=0.0,
        target_return_3m=0.0,
        leaders=LEADERS,
    )
    assert result["leaders_avg_1m"] == pytest.approx(-0.046, abs=1e-4)
    assert result["rs_vs_leaders_avg_1m"] == pytest.approx(1.0 / 0.954, abs=1e-3)


def test_avg_skips_none_returns():
    """leaders 中部分 return 为 None,平均时跳过。"""
    leaders_with_gaps = [
        {"ticker": "A.SH", "return_1m": -0.05, "return_3m": None},
        {"ticker": "B.SH", "return_1m": -0.07, "return_3m": -0.04},
        {"ticker": "C.SH", "return_1m": None, "return_3m": -0.10},
    ]
    result = compute_target_position(
        target_ticker="X.SH",
        target_return_1m=-0.06,
        target_return_3m=-0.05,
        leaders=leaders_with_gaps,
    )
    # 1M 平均:(-0.05 + -0.07) / 2 = -0.06
    # 3M 平均:(-0.04 + -0.10) / 2 = -0.07
    assert result["leaders_avg_1m"] == pytest.approx(-0.06, abs=1e-6)
    assert result["leaders_avg_3m"] == pytest.approx(-0.07, abs=1e-6)
