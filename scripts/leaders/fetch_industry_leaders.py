"""申万行业 Top-N 市值龙头股获取。

数据流:
1. index_member_all(l2_code) → 行业全部成分股 ts_code
2. daily_basic(trade_date)   → 全市场当日基本面(总市值/PE/收盘)
3. 过滤出本行业,按 total_mv 降序取 Top N
4. 对每个龙头调 daily(start_date, end_date) 拿 65 行日线,算 1M/3M 涨跌
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402

# 1M = 20 个交易日, 3M = 60 个交易日
WINDOW_1M = 20
WINDOW_3M = 60
# 拉 65 行够同时算 1M(idx 20) 和 3M(idx 60)
DAILY_LOOKBACK = 65


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------


def _compute_return(df: pd.DataFrame, window: int) -> float | None:
    """
    给一个降序排列的 daily DataFrame,算 window 个交易日前的涨跌幅。

    - latest close = df.iloc[0]["close"]
    - past close   = df.iloc[window]["close"]  (window 行前)
    - 需要至少 window + 1 行数据
    """
    if len(df) <= window:
        return None
    latest = float(df.iloc[0]["close"])
    past = float(df.iloc[window]["close"])
    if past == 0:
        return None
    return (latest - past) / past


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def fetch_industry_leaders(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,  # YYYY-MM-DD
    top_n: int = 5,
) -> list[dict]:
    """
    返回 Top N 龙头股,按 total_mv 降序。

    每个 dict 字段:
      ticker:       str   "600519.SH"
      name:         str   "贵州茅台"(暂以 ts_code 填充,v2 可补全股票名称)
      total_mv:     float 万元
      close:        float 当日收盘价
      pe_ttm:       float | None
      return_1m:    float | None  20 交易日涨跌(decimal,如 -0.05)
      return_3m:    float | None  60 交易日涨跌
    """
    # ── Step 1: 行业成分股 ──────────────────────────────────────────────────
    members_df = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
    if members_df is None or members_df.empty or "ts_code" not in members_df.columns:
        return []

    member_codes: set[str] = set(members_df["ts_code"].tolist())
    # 从 index_member_all 直接拿股票中文名(如 600519.SH → "贵州茅台")
    if "name" in members_df.columns:
        code_to_name = dict(zip(members_df["ts_code"], members_df["name"]))
    else:
        code_to_name = {}

    # ── Step 2: 当日 daily_basic(全市场拉一次) ───────────────────────────
    trade_date = analysis_date.replace("-", "")  # YYYYMMDD
    basic_df = client.call("daily_basic", trade_date=trade_date)
    if basic_df is None or basic_df.empty or "ts_code" not in basic_df.columns:
        return []

    # ── Step 3: 过滤行业成分股 → 按 total_mv 降序取 Top N ───────────────
    industry_basic = basic_df[basic_df["ts_code"].isin(member_codes)].copy()
    if industry_basic.empty or "total_mv" not in industry_basic.columns:
        return []

    industry_basic = industry_basic.sort_values("total_mv", ascending=False).head(top_n)

    # ── Step 4: 逐个龙头拉日线,算涨跌 ──────────────────────────────────
    # 起始日期: analysis_date 往前约 90 天(实际交易日不足时 API 会返回有多少给多少)
    # 多给一些 buffer 以应对节假日:DAILY_LOOKBACK 行 ≈ 65 交易日 ≈ ~90 自然日
    end_date = trade_date
    start_dt = datetime.strptime(analysis_date, "%Y-%m-%d") - timedelta(days=100)
    start_date = start_dt.strftime("%Y%m%d")

    results: list[dict] = []
    for _, row in industry_basic.iterrows():
        ticker: str = str(row["ts_code"])
        total_mv: float = float(row.get("total_mv", 0.0))
        close: float = float(row.get("close", 0.0))
        pe_ttm: float | None = (
            float(row["pe_ttm"]) if "pe_ttm" in row and pd.notna(row["pe_ttm"]) else None
        )

        # 拉单股日线
        daily_df = client.call(
            "daily",
            ts_code=ticker,
            start_date=start_date,
            end_date=end_date,
        )

        # 确保降序(latest first)
        if daily_df is not None and not daily_df.empty and "trade_date" in daily_df.columns:
            daily_df = daily_df.sort_values("trade_date", ascending=False).reset_index(drop=True)
        else:
            daily_df = pd.DataFrame()

        return_1m = _compute_return(daily_df, WINDOW_1M) if not daily_df.empty else None
        return_3m = _compute_return(daily_df, WINDOW_3M) if not daily_df.empty else None

        results.append(
            {
                "ticker": ticker,
                "name": str(code_to_name.get(ticker, ticker)),
                "total_mv": total_mv,
                "close": close,
                "pe_ttm": pe_ttm,
                "return_1m": return_1m,
                "return_3m": return_3m,
            }
        )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="获取行业 Top-N 市值龙头股关键数据")
    parser.add_argument("--industry-l2-code", required=True, help="申万二级行业代码,如 801125.SI")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)

    leaders = fetch_industry_leaders(
        client,
        industry_l2_code=args.industry_l2_code,
        analysis_date=args.analysis_date,
        top_n=args.top_n,
    )

    payload = json.dumps(leaders, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
