"""目标股 vs 行业 Top N 龙头的位置判定 + 相对强度计算。

输入:
  - target_ticker / target_return_1m / target_return_3m
  - leaders 列表(fetch_industry_leaders 的输出)

输出:
  - rank_in_industry:目标股在 Top N 中的 1-based 排名(不在 → None)
  - target_position:绝对龙头 / 二线龙头 / 跟随 / 落后 / 无法判断
  - rs_vs_leaders_avg_1m / 3m
  - leaders_avg_1m / 3m
  - rationale:一句话总结
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# 位置标签常量(对外稳定)
POS_ABSOLUTE_LEADER = "绝对龙头"
POS_SECOND_TIER = "二线龙头"
POS_FOLLOW = "跟随"
POS_LAGGING = "落后"
POS_UNKNOWN = "无法判断"


def _avg_return(leaders: list[dict], key: str) -> float | None:
    """对 leaders 中 key 字段非 None 的值取算术平均。全 None → None。"""
    values = [float(L[key]) for L in leaders if L.get(key) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _relative_strength(target: float | None, avg: float | None) -> float | None:
    """RS = (1+target) / (1+avg);任一为 None → None;avg = -1 时返回 None 防除零。"""
    if target is None or avg is None or avg == -1:
        return None
    return (1 + target) / (1 + avg)


def _find_rank(target_ticker: str, leaders: list[dict]) -> int | None:
    """1-based rank;不在 leaders → None。"""
    for idx, L in enumerate(leaders, start=1):
        if L.get("ticker") == target_ticker:
            return idx
    return None


def _build_rationale(
    target_ticker: str,
    rank: int | None,
    position: str,
    target_r1m: float | None,
    leaders_avg_1m: float | None,
    rs_1m: float | None,
    leaders: list[dict],
) -> str:
    """一句话总结(30-60 字),带具体数字。"""
    target_name = next(
        (L.get("name", target_ticker) for L in leaders if L.get("ticker") == target_ticker),
        target_ticker,
    )

    def pct(v: float | None) -> str:
        return f"{v:.2%}" if v is not None else "N/A"

    if position == POS_ABSOLUTE_LEADER and len(leaders) >= 2:
        top1_mv = float(leaders[0].get("total_mv") or 0)
        top2_mv = float(leaders[1].get("total_mv") or 0) or 1.0
        ratio = top1_mv / top2_mv
        return f"{target_name} 是行业市值绝对龙头,领先第二名 {ratio:.1f} 倍。"
    if position == POS_SECOND_TIER and rank is not None:
        return f"{target_name} 在行业市值 Top 5 中排名第 {rank},属二线龙头。"
    if position == POS_FOLLOW:
        rs_str = f"{rs_1m:.2f}" if rs_1m is not None else "N/A"
        return (
            f"{target_name} 不在 Top 5,但 1M 涨跌 {pct(target_r1m)} "
            f"跟得上龙头平均 {pct(leaders_avg_1m)}(RS={rs_str})。"
        )
    if position == POS_LAGGING:
        rs_str = f"{rs_1m:.2f}" if rs_1m is not None else "N/A"
        return (
            f"{target_name} 不在 Top 5,1M 涨跌 {pct(target_r1m)} 落后龙头平均 "
            f"{pct(leaders_avg_1m)}(RS={rs_str})。"
        )
    return f"数据不足,无法定位 {target_name} 在行业中的相对位置。"


def compute_target_position(
    target_ticker: str,
    target_return_1m: float | None,
    target_return_3m: float | None,
    leaders: list[dict],
) -> dict[str, Any]:
    """
    主函数,见模块 docstring。
    """
    rank = _find_rank(target_ticker, leaders)
    leaders_avg_1m = _avg_return(leaders, "return_1m")
    leaders_avg_3m = _avg_return(leaders, "return_3m")
    rs_1m = _relative_strength(target_return_1m, leaders_avg_1m)
    rs_3m = _relative_strength(target_return_3m, leaders_avg_3m)

    # 位置决策树
    if rank == 1:
        position = POS_ABSOLUTE_LEADER
    elif rank is not None and 2 <= rank <= 5:
        position = POS_SECOND_TIER
    elif rs_1m is None:
        # 不在 Top 5 且无法算 RS → 无法判断
        position = POS_UNKNOWN
    elif rs_1m >= 1.0:
        position = POS_FOLLOW
    else:
        position = POS_LAGGING

    rationale = _build_rationale(
        target_ticker=target_ticker,
        rank=rank,
        position=position,
        target_r1m=target_return_1m,
        leaders_avg_1m=leaders_avg_1m,
        rs_1m=rs_1m,
        leaders=leaders,
    )

    return {
        "target_ticker": target_ticker,
        "rank_in_industry": rank,
        "target_position": position,
        "rs_vs_leaders_avg_1m": rs_1m,
        "rs_vs_leaders_avg_3m": rs_3m,
        "leaders_avg_1m": leaders_avg_1m,
        "leaders_avg_3m": leaders_avg_3m,
        "rationale": rationale,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="目标股 vs 行业龙头的位置 + 相对强度")
    parser.add_argument("--target-ticker", required=True)
    parser.add_argument("--target-return-1m", type=float, required=True)
    parser.add_argument("--target-return-3m", type=float, required=True)
    parser.add_argument("--leaders-json", required=True, help="fetch_industry_leaders 的 JSON 输出文件路径")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    leaders = json.loads(Path(args.leaders_json).read_text(encoding="utf-8"))

    result = compute_target_position(
        target_ticker=args.target_ticker,
        target_return_1m=args.target_return_1m,
        target_return_3m=args.target_return_3m,
        leaders=leaders,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
