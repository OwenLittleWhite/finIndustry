"""股票 → 申万二级行业映射。

数据源:Tushare `index_member_all`(股票成分股 → 行业指数)。
查询时使用 `is_new='Y'` 过滤当前生效的分类(注意:历史回测时需要按 analysis_date 调整)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 注入项目根到 sys.path,使脚本可以直接运行(`python scripts/.../foo.py`)。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402


def _normalize_ts_code(ticker: str) -> str:
    """把 6 位数字股票代码转换成 Tushare 格式(如 600519 → 600519.SH)。"""
    ticker = str(ticker).strip()
    if "." in ticker:
        return ticker
    if ticker.startswith(("60", "68", "5")):
        return f"{ticker}.SH"
    if ticker.startswith(("00", "30", "15", "16", "1")):
        return f"{ticker}.SZ"
    if ticker.startswith(("4", "8", "9")):
        return f"{ticker}.BJ"
    return ticker


def fetch_industry_classification(client, ticker: str) -> dict | None:
    """
    返回:
      {
        "primary_industry": {"system": "申万二级", "code": "801125.SI", "name": "白酒"},
        "l1_industry": {"code": "801120.SI", "name": "食品饮料"}
      }
    无分类返回 None。
    """
    ts_code = _normalize_ts_code(ticker)
    df = client.call("index_member_all", ts_code=ts_code, is_new="Y")
    if df.empty:
        return None

    row = df.iloc[0]
    return {
        "primary_industry": {
            "system": "申万二级",
            "code": row.get("l2_code", ""),
            "name": row.get("l2_name", ""),
        },
        "l1_industry": {
            "code": row.get("l1_code", ""),
            "name": row.get("l1_name", ""),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="path or '-' for stdout")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    result = fetch_industry_classification(client, args.ticker)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
