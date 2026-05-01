"""Score → Signal mapping per sub-skill-spec-v1 第 7 节:±30 阈值。"""
import pytest

from scripts.common.derive_signal import derive_signal


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, "看多"),
        (31, "看多"),
        (30, "看多"),
        (29, "中性"),
        (0, "中性"),
        (-29, "中性"),
        (-30, "看空"),
        (-31, "看空"),
        (-100, "看空"),
    ],
)
def test_score_to_signal(score, expected):
    assert derive_signal(score) == expected


def test_none_score_returns_none():
    """failed/partial 状态时 score=None,signal 也应该 None。"""
    assert derive_signal(None) is None


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        derive_signal(101)
    with pytest.raises(ValueError):
        derive_signal(-101)


def test_non_int_raises():
    with pytest.raises(TypeError):
        derive_signal(0.5)
