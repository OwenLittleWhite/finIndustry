"""行业融资融券余额聚合获取。

数据流:
1. index_member_all(l2_code=...) → 行业成分股列表
2. 对 3 个关键交易日(当日、约 5 个交易日前、约 20 个交易日前)各调一次
   margin_detail(trade_date=YYYYMMDD) → 全市场融资余额
3. 过滤出行业成分股 → 加总融资余额
4. 计算 5 日 / 20 日变化率

注意:
- margin_detail 按 trade_date 拉全市场,返回 rzye(融资余额,元)
- 只拉 3 个关键日期,避免过多 API 调用
- 最终结果转换为亿元
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402

logger = logging.getLogger(__name__)

# 近似交易日换算:1 交易日 ≈ 1.4 自然日(考虑周末/节假日)
_TRADING_DAYS_5 = 5
_TRADING_DAYS_20 = 20
# 自然日缓冲:拉取区间稍大于目标,确保覆盖节假日
_NATURAL_DAYS_5 = 8
_NATURAL_DAYS_20 = 30

# 融资余额列名(tushare margin_detail 字段)
_MARGIN_VALUE_COL = "rzye"  # 融资余额(元)

# 元 → 亿元
_YUAN_TO_YI = 1e-8


def _date_to_tushare(date_str: str) -> str:
    """YYYY-MM-DD → YYYYMMDD"""
    return date_str.replace("-", "")


def _offset_date(date_str: str, days: int) -> str:
    """返回 date_str 往前 days 自然日的日期,格式 YYYYMMDD。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=days)
    return dt.strftime("%Y%m%d")


def _aggregate_margin(
    client: Any,
    trade_date: str,
    member_codes: set[str],
) -> float | None:
    """
    拉指定交易日全市场融资余额,过滤行业成分股后加总,返回亿元。

    trade_date: YYYYMMDD
    """
    try:
        df = client.call("margin_detail", trade_date=trade_date)
    except (ConnectionError, TimeoutError, OSError):
        return None

    if df is None or df.empty or "ts_code" not in df.columns:
        return None

    if _MARGIN_VALUE_COL not in df.columns:
        # 尝试备用列名
        alt_cols = ["rzye", "margin_balance", "rzye_balance"]
        for col in alt_cols:
            if col in df.columns:
                df = df.rename(columns={col: _MARGIN_VALUE_COL})
                break
        else:
            return None

    industry_df = df[df["ts_code"].isin(member_codes)].copy()
    if industry_df.empty:
        return None

    industry_df[_MARGIN_VALUE_COL] = pd.to_numeric(
        industry_df[_MARGIN_VALUE_COL], errors="coerce"
    ).fillna(0.0)

    total_yuan = float(industry_df[_MARGIN_VALUE_COL].sum())
    return total_yuan * _YUAN_TO_YI


def fetch_margin(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,
) -> dict:
    """
    获取行业融资融券余额聚合。

    参数:
        client:           TushareClient 实例
        industry_l2_code: 申万二级行业代码,如 "801125.SI"
        analysis_date:    分析日期 YYYY-MM-DD

    返回:
        {
          "industry_l2_code": str,
          "current_margin_balance_yi": float | None,  # 当日行业融资余额(亿元)
          "change_5d_pct":  float | None,             # 近 5 交易日变化(%)
          "change_20d_pct": float | None,
        }
    """
    _empty: dict = {
        "industry_l2_code": industry_l2_code,
        "current_margin_balance_yi": None,
        "change_5d_pct": None,
        "change_20d_pct": None,
    }

    try:
        # ── Step 1: 行业成分股 ──────────────────────────────────────────────
        members_df = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
        if members_df is None or members_df.empty or "ts_code" not in members_df.columns:
            return _empty

        member_codes: set[str] = set(members_df["ts_code"].tolist())

        # ── Step 2: 3 个关键交易日 ──────────────────────────────────────────
        current_date = _date_to_tushare(analysis_date)
        date_5d_ago = _offset_date(analysis_date, _NATURAL_DAYS_5)
        date_20d_ago = _offset_date(analysis_date, _NATURAL_DAYS_20)

        # ── Step 3: 各日聚合融资余额 ─────────────────────────────────────────
        current_yi = _aggregate_margin(client, current_date, member_codes)
        value_5d_yi = _aggregate_margin(client, date_5d_ago, member_codes)
        value_20d_yi = _aggregate_margin(client, date_20d_ago, member_codes)

        # ── Step 4: 变化率 ───────────────────────────────────────────────────
        def _safe_pct(current: float | None, past: float | None) -> float | None:
            if current is None or past is None or past == 0:
                return None
            return (current - past) / past

        return {
            "industry_l2_code": industry_l2_code,
            "current_margin_balance_yi": current_yi,
            "change_5d_pct": _safe_pct(current_yi, value_5d_yi),
            "change_20d_pct": _safe_pct(current_yi, value_20d_yi),
        }

    except (ConnectionError, TimeoutError, OSError) as exc:
        warnings.warn(
            f"fetch_margin: 网络错误,返回全 None 字段。原因: {exc}",
            stacklevel=2,
        )
        return _empty


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="获取行业融资融券余额聚合")
    parser.add_argument("--industry-l2-code", required=True, help="申万二级行业代码,如 801125.SI")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)

    result = fetch_margin(
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
