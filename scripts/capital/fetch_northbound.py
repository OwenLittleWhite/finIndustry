"""北向资金净流入(大盘级别,作为外资流向代理)。

历史背景:Tushare 的 hk_hold 接口实际是"港股通持股"(大陆买港股),不能反查
"陆股通持股"(北向资金持有 A 股)。Tushare 也没有"行业级别北向持股"的现成接口。

折中方案:用 `moneyflow_hsgt` 拿**大盘级别**北向资金每日净流入,作为外资整体流向
的代理信号。这不是行业级别,但能告诉 LLM 整体外资是流入还是流出 A 股,
LLM 可以结合其他信号(主力 / 融资)判断对该行业的影响。

数据流:
1. 调 moneyflow_hsgt(start_date=, end_date=) 拿过去 ~30 自然日的每日数据
2. 字段 north_money 单位是 **万元**(实测:350682.49 万元 = 35.07 亿,
   与媒体报道的真实单日数字一致;Tushare 文档写"百万元"是错的)
3. 输出今日 / 5d 累计 / 10d 累计的北向净流入(亿元)
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402

_LOOKBACK_DAYS = 30


def _to_yi(wan: float | None) -> float | None:
    """万元 → 亿元(1 亿元 = 10000 万元)。"""
    if wan is None:
        return None
    return float(wan) / 10000.0


def fetch_northbound(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,
) -> dict:
    """
    获取大盘级别北向资金净流入(行业级数据 Tushare 不直接提供)。

    industry_l2_code 参数保留是为了 API 兼容,实际不参与查询(返回的是大盘级数据)。

    返回:
      {
        "industry_l2_code": str,
        "scope": "market_level",                       # 提示这是大盘级别,非行业
        "north_money_today_yi": float | None,          # 今日北向净流入(亿元)
        "north_money_5d_yi": float | None,             # 近 5 交易日累计
        "north_money_10d_yi": float | None,            # 近 10 交易日累计
        "current_holding_value": None,                 # 兼容旧 schema 字段(永远 None)
        "change_5d_pct": None,                         # 兼容旧 schema 字段
        "change_10d_pct": None,                        # 兼容旧 schema 字段
      }

    > 行业聚合:无 — Tushare 没有行业级别接口
    > LLM 推理:用市场级别北向 + 其他信号(主力/融资)对行业层面做归纳
    """
    empty: dict = {
        "industry_l2_code": industry_l2_code,
        "scope": "market_level",
        "north_money_today_yi": None,
        "north_money_5d_yi": None,
        "north_money_10d_yi": None,
        "current_holding_value": None,
        "change_5d_pct": None,
        "change_10d_pct": None,
    }

    try:
        end_date = analysis_date.replace("-", "")
        start_dt = datetime.strptime(analysis_date, "%Y-%m-%d") - timedelta(days=_LOOKBACK_DAYS)
        start_date = start_dt.strftime("%Y%m%d")

        df = client.call("moneyflow_hsgt", start_date=start_date, end_date=end_date)
        if df is None or df.empty or "north_money" not in df.columns:
            return empty

        # 按 trade_date 升序
        df = df.sort_values("trade_date").reset_index(drop=True)
        df["north_money"] = pd.to_numeric(df["north_money"], errors="coerce")

        if df.empty:
            return empty

        today_million = float(df.iloc[-1]["north_money"]) if pd.notna(df.iloc[-1]["north_money"]) else None
        last_5 = df["north_money"].dropna().tail(5).sum() if len(df) >= 5 else None
        last_10 = df["north_money"].dropna().tail(10).sum() if len(df) >= 10 else None

        return {
            "industry_l2_code": industry_l2_code,
            "scope": "market_level",
            "north_money_today_yi": _to_yi(today_million),
            "north_money_5d_yi": _to_yi(float(last_5)) if last_5 is not None else None,
            "north_money_10d_yi": _to_yi(float(last_10)) if last_10 is not None else None,
            "current_holding_value": None,
            "change_5d_pct": None,
            "change_10d_pct": None,
        }

    except (ConnectionError, TimeoutError, OSError) as exc:
        warnings.warn(
            f"fetch_northbound: 网络错误,返回全 None 字段。原因: {exc}",
            stacklevel=2,
        )
        return empty


def main() -> int:
    parser = argparse.ArgumentParser(description="北向资金净流入(大盘级别代理)")
    parser.add_argument("--industry-l2-code", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)

    result = fetch_northbound(
        client,
        industry_l2_code=args.industry_l2_code,
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
