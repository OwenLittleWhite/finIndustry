"""Score → Signal 全局统一规则(sub-skill-spec-v1 第 7 节)。"""
from __future__ import annotations


def derive_signal(score: int | None) -> str | None:
    """
    score >=  30 → "看多"
    -30 < score < 30 → "中性"
    score <= -30 → "看空"
    None → None(failed/partial)
    """
    if score is None:
        return None
    if not isinstance(score, int):
        raise TypeError(f"score must be int, got {type(score).__name__}")
    if not -100 <= score <= 100:
        raise ValueError(f"score out of range [-100, 100]: {score}")
    if score >= 30:
        return "看多"
    if score <= -30:
        return "看空"
    return "中性"
