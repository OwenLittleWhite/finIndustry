"""行业内涨跌家数比、涨停数(分化指标)。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.common.cache import Cache
from scripts.common.tushare_client import TushareClient

LIMIT_UP_THRESHOLD = 9.9  # A 股主板 10% 涨停,留 0.1% 余地


def compute_breadth_for_industry(
    client,
    industry_l2_code: str,
    analysis_date: str,
) -> dict:
    """
    返回:
      {
        "advance": int,            # 上涨家数
        "decline": int,            # 下跌家数
        "flat": int,               # 平盘家数
        "limit_up": int,           # 涨停家数
        "advance_decline_ratio": float | None,
      }
    """
    # Tushare index_member_all: 用 l2_code 查申万二级行业的成分股
    members = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
    if members.empty or "con_code" not in members.columns:
        return {"advance": 0, "decline": 0, "flat": 0, "limit_up": 0, "advance_decline_ratio": None}

    end_date = analysis_date.replace("-", "")
    advance = decline = flat = limit_up = 0

    for code in members["con_code"].tolist():
        df = client.call("daily", ts_code=code, end_date=end_date)
        if df.empty or "pct_chg" not in df.columns:
            continue
        latest = df.sort_values("trade_date", ascending=False).iloc[0]
        pct = float(latest["pct_chg"])
        if pct > 0:
            advance += 1
        elif pct < 0:
            decline += 1
        else:
            flat += 1
        if pct >= LIMIT_UP_THRESHOLD:
            limit_up += 1

    ratio = (advance / decline) if decline > 0 else None
    return {
        "advance": advance,
        "decline": decline,
        "flat": flat,
        "limit_up": limit_up,
        "advance_decline_ratio": ratio,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry-l2-code", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    result = compute_breadth_for_industry(
        client, industry_l2_code=args.industry_l2_code, analysis_date=args.analysis_date
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
