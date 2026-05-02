"""申万行业指数日线获取 + 多窗口涨跌。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient

WINDOW_DAYS = {"1m": 20, "3m": 60, "6m": 120, "12m": 250}


def fetch_industry_index(
    client,
    index_code: str,
    analysis_date: str,
    lookback_days: int = 250,
) -> pd.DataFrame:
    """
    获取申万行业指数日线,过去 lookback_days 个交易日,降序按 trade_date 排列。
    """
    end_date = analysis_date.replace("-", "")
    df = client.call("sw_daily", ts_code=index_code, end_date=end_date)
    if df.empty:
        return df
    df = df.sort_values("trade_date", ascending=False).head(lookback_days).reset_index(drop=True)
    return df


def compute_window_returns(df: pd.DataFrame) -> dict[str, float | None]:
    """
    给一个降序排列的日线 DataFrame,算 1M/3M/6M/12M 涨跌(基于收盘价)。
    返回 None 当数据不足。
    """
    if df.empty or "close" not in df.columns:
        return {k: None for k in WINDOW_DAYS}

    latest = float(df.iloc[0]["close"])
    out: dict[str, float | None] = {}
    for window, days in WINDOW_DAYS.items():
        if len(df) <= days:
            out[window] = None
            continue
        past = float(df.iloc[days]["close"])
        out[window] = (latest - past) / past if past else None
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-code", required=True, help="如 801123.SI(申万白酒)")
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    parser.add_argument("--lookback-days", type=int, default=250)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    df = fetch_industry_index(
        client,
        index_code=args.index_code,
        analysis_date=args.analysis_date,
        lookback_days=args.lookback_days,
    )
    returns = compute_window_returns(df)
    result = {
        "index_code": args.index_code,
        "rows": int(len(df)),
        "returns": returns,
        "daily": df.to_dict(orient="records"),
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
