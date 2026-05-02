"""股票 → 关联概念(Tushare `concept_detail` 反查)。

数据源:Tushare `concept_detail(ts_code=...)`,返回该股所属的全部 Tushare 概念。

输出格式:
  [
    {"name": "白酒概念", "code": "TS267", "heat_rank": 1, "heat_score": 0.0},
    {"name": "沪股通",   "code": "TS392", "heat_rank": 2, "heat_score": 0.0},
    ...
  ]

说明:
- `heat_rank`:用 Tushare 返回的列表顺序模拟"热度",1 = 最相关。
- `heat_score`:Tushare 不提供热度数据,统一为 0.0。
- 该字段为占位,保持与 v0 输出 schema 兼容,LLM 可忽略 heat 字段。
- 实际"行业相关概念"由 LLM 在分析时基于概念名称语义挑选(见 SKILL.md)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402


def _normalize_ts_code(ticker: str) -> str:
    """6 位数字 → Tushare 格式(如 600519 → 600519.SH)。复用 fetch_industry_classification 同样逻辑。"""
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


def fetch_concept_mapping(client, ticker: str, top_n: int = 3) -> list[dict]:
    """
    返回该股票所属的 Tushare 概念,最多 top_n 个,按 Tushare 返回顺序。

    无概念 / 数据源不可用时返回空列表。
    """
    ts_code = _normalize_ts_code(ticker)
    df = client.call("concept_detail", ts_code=ts_code)
    if df.empty or "concept_name" not in df.columns:
        return []

    result = []
    for idx, row in df.iterrows():
        if len(result) >= top_n:
            break
        result.append({
            "name": str(row.get("concept_name", "")),
            "code": str(row.get("id", "")),
            "heat_rank": len(result) + 1,
            "heat_score": 0.0,
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
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    result = fetch_concept_mapping(client, args.ticker, top_n=args.top_n)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
