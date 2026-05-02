"""股票 → 关联热门概念(akshare 东方财富数据)。

策略:
1. 取所有概念列表(含热度排名),按 rank 升序(rank 越小越热)
2. 对前 N 个概念,逐个看成分股是否含 ticker
3. 返回前 top_n 个含 ticker 的概念
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.common.akshare_client import AkshareClient
from scripts.common.cache import Cache


def fetch_concept_mapping(client, ticker: str, top_n: int = 3) -> list[dict]:
    """
    返回最多 top_n 个热度最高、且包含目标 ticker 的概念板块。

    格式:
      [
        {"name": "茅指数", "heat_rank": 3, "heat_score": 0.10},
        ...
      ]
    """
    concepts_df = client.call("stock_board_concept_name_em")
    if concepts_df.empty:
        return []

    # 按热度排名升序(假设字段名"热度排名")
    if "热度排名" in concepts_df.columns:
        concepts_df = concepts_df.sort_values("热度排名")

    result = []
    ticker_str = str(ticker).strip()
    for _, row in concepts_df.iterrows():
        if len(result) >= top_n:
            break
        concept_name = row["概念名称"]
        cons_df = client.call("stock_board_concept_cons_em", symbol=concept_name)
        if cons_df.empty or "代码" not in cons_df.columns:
            continue
        codes = {str(c).strip() for c in cons_df["代码"].tolist()}
        if ticker_str in codes:
            result.append({
                "name": concept_name,
                "heat_rank": int(row.get("热度排名", 0)),
                "heat_score": float(row.get("近5日涨幅", 0.0)),
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = AkshareClient(cache=cache, analysis_date=args.analysis_date)
    result = fetch_concept_mapping(client, args.ticker, top_n=args.top_n)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
