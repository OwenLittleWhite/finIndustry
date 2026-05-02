"""行业主力资金净流入获取。

数据流:
1. akshare stock_sector_fund_flow_rank(indicator="今日") → 所有板块今日主力资金流
2. akshare stock_sector_fund_flow_rank(indicator="5日")  → 近 5 日累计
3. akshare stock_sector_fund_flow_rank(indicator="10日") → 近 10 日累计
4. 通过"名称"列模糊匹配目标 industry_name
5. 提取"今日主力净流入-净额"列并转为亿元

注意:akshare 数据为截至当日的实时/当日数据,不支持历史回查。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from scripts.common.akshare_client import AkshareClient  # noqa: E402
from scripts.common.cache import Cache  # noqa: E402

logger = logging.getLogger(__name__)

# 板块资金流列名映射(akshare 版本可能有细微差异,按优先级尝试)
_TODAY_NET_FLOW_COLS = [
    "今日主力净流入-净额",
    "今日主力净额",
]
_5D_NET_FLOW_COLS = [
    "5日主力净流入-净额",
    "5日主力净额",
]
_10D_NET_FLOW_COLS = [
    "10日主力净流入-净额",
    "10日主力净额",
]

# 万元 → 亿元
_WAN_TO_YI = 1e-4


def _extract_net_flow_yi(df: pd.DataFrame, col_candidates: list[str]) -> float | None:
    """从 DataFrame 中提取第一行的主力净流入值,转换为亿元。"""
    if df is None or df.empty:
        return None
    for col in col_candidates:
        if col in df.columns:
            val = df.iloc[0][col]
            if pd.isna(val):
                return None
            # akshare 返回单位是元,需要转为亿元(除以 1e8)
            try:
                return float(val) / 1e8
            except (ValueError, TypeError):
                return None
    return None


def _fuzzy_match_industry(df: pd.DataFrame, industry_name: str) -> pd.DataFrame:
    """
    在 '名称' 列中模糊匹配 industry_name。

    规则:
    1. 精确匹配优先
    2. 精确匹配失败时,对 industry_name 去掉尾缀"Ⅱ""I""II"等再匹配
    3. 退而求其次:包含关系匹配(industry_name 包含在板块名中,或板块名包含在 industry_name 中)
    """
    if df is None or df.empty or "名称" not in df.columns:
        return pd.DataFrame()

    # 精确匹配
    exact = df[df["名称"] == industry_name]
    if not exact.empty:
        return exact.head(1)

    # 去尾缀后匹配(如"白酒Ⅱ" → "白酒")
    stripped = industry_name.rstrip("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXiivx").strip()
    if stripped and stripped != industry_name:
        stripped_match = df[df["名称"] == stripped]
        if not stripped_match.empty:
            return stripped_match.head(1)

    # 包含匹配(板块名包含 stripped 或 stripped 包含在板块名中)
    if stripped:
        contains = df[df["名称"].str.contains(stripped, na=False, regex=False)]
        if not contains.empty:
            return contains.head(1)

    # 包含匹配(用原名)
    contains_orig = df[df["名称"].str.contains(industry_name, na=False, regex=False)]
    if not contains_orig.empty:
        return contains_orig.head(1)

    return pd.DataFrame()


def fetch_main_flow(
    client: Any,
    industry_name: str,
    analysis_date: str,
) -> dict:
    """
    获取行业主力资金净流入。

    参数:
        client:        AkshareClient 实例
        industry_name: 中文板块名,如"白酒Ⅱ" / "白酒"
        analysis_date: 分析日期 YYYY-MM-DD(akshare 不支持历史回查,此参数主要用于记录)

    返回:
        {
          "industry_name": str,
          "main_inflow_today_yi": float | None,    # 今日主力净流入(亿元)
          "main_inflow_5d_yi":    float | None,    # 近 5 日累计
          "main_inflow_10d_yi":   float | None,
          "rank_in_all_sectors_today": int | None, # 今日在所有板块中的排名(越前越多流入)
        }
    """
    _empty: dict = {
        "industry_name": industry_name,
        "main_inflow_today_yi": None,
        "main_inflow_5d_yi": None,
        "main_inflow_10d_yi": None,
        "rank_in_all_sectors_today": None,
    }

    try:
        # ── 今日资金流(含排名) ───────────────────────────────────────────
        today_df = client.call("stock_sector_fund_flow_rank", indicator="今日")
        matched_today = _fuzzy_match_industry(today_df, industry_name)

        main_inflow_today_yi: float | None = None
        rank_today: int | None = None

        if not matched_today.empty:
            main_inflow_today_yi = _extract_net_flow_yi(matched_today, _TODAY_NET_FLOW_COLS)
            # 排名:在全量 today_df 里找该行的位置(按主力净额降序排列时的位次)
            if not today_df.empty and "名称" in today_df.columns:
                matched_name = matched_today.iloc[0]["名称"]
                # 按今日主力净额降序排名
                for col in _TODAY_NET_FLOW_COLS:
                    if col in today_df.columns:
                        ranked = today_df.sort_values(col, ascending=False).reset_index(drop=True)
                        found = ranked[ranked["名称"] == matched_name]
                        if not found.empty:
                            rank_today = int(found.index[0]) + 1
                        break

        # ── 近 5 日资金流 ────────────────────────────────────────────────
        df_5d = client.call("stock_sector_fund_flow_rank", indicator="5日")
        matched_5d = _fuzzy_match_industry(df_5d, industry_name)
        main_inflow_5d_yi = _extract_net_flow_yi(matched_5d, _5D_NET_FLOW_COLS)

        # ── 近 10 日资金流 ───────────────────────────────────────────────
        df_10d = client.call("stock_sector_fund_flow_rank", indicator="10日")
        matched_10d = _fuzzy_match_industry(df_10d, industry_name)
        main_inflow_10d_yi = _extract_net_flow_yi(matched_10d, _10D_NET_FLOW_COLS)

        return {
            "industry_name": industry_name,
            "main_inflow_today_yi": main_inflow_today_yi,
            "main_inflow_5d_yi": main_inflow_5d_yi,
            "main_inflow_10d_yi": main_inflow_10d_yi,
            "rank_in_all_sectors_today": rank_today,
        }

    except (ConnectionError, TimeoutError, OSError) as exc:
        warnings.warn(
            f"fetch_main_flow: 网络错误,返回全 None 字段。原因: {exc}",
            stacklevel=2,
        )
        return _empty


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="获取行业主力资金净流入(板块级别)")
    parser.add_argument("--industry-name", required=True, help="板块中文名,如 '白酒'")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = AkshareClient(cache=cache, analysis_date=args.analysis_date)

    result = fetch_main_flow(
        client,
        industry_name=args.industry_name,
        analysis_date=args.analysis_date,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
