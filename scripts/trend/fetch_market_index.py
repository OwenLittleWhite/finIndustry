"""大盘指数(沪深 300)日线 + 行业相对强度。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402


DEFAULT_LOOKBACK = 260  # 与 fetch_industry_index 保持一致(支持 12m 窗口)


def fetch_market_index(
    client,
    market_code: str,
    analysis_date: str,
    lookback_days: int = DEFAULT_LOOKBACK,
) -> pd.DataFrame:
    end_date = analysis_date.replace("-", "")
    df = client.call("index_daily", ts_code=market_code, end_date=end_date)
    if df.empty:
        return df
    df = df.sort_values("trade_date", ascending=False).head(lookback_days).reset_index(drop=True)
    return df


def compute_relative_strength(
    industry_returns: dict, market_returns: dict
) -> dict[str, float | None]:
    """
    RS = (1 + industry_return) / (1 + market_return)

    > 1 → 行业强于大盘
    < 1 → 行业弱于大盘
    """
    out: dict[str, float | None] = {}
    for window in industry_returns.keys() | market_returns.keys():
        ir = industry_returns.get(window)
        mr = market_returns.get(window)
        if ir is None or mr is None:
            out[window] = None
        else:
            out[window] = (1 + ir) / (1 + mr) if mr != -1 else None
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-code", default="000300.SH")
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    df = fetch_market_index(
        client,
        market_code=args.market_code,
        analysis_date=args.analysis_date,
        lookback_days=args.lookback_days,
    )
    payload = json.dumps(
        {"market_code": args.market_code, "rows": int(len(df)), "daily": df.to_dict(orient="records")},
        ensure_ascii=False, indent=2, default=str,
    )
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
