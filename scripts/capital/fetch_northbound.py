"""北向资金行业偏好获取(港股通持股 → 行业聚合)。

数据流:
1. index_member_all(l2_code=industry_l2_code, is_new='Y') → 行业成分股列表
2. 对每个成分股调 hk_hold(ts_code=, start_date=, end_date=) → 日度港股通持股市值
3. 按交易日加总所有成分股的持仓市值 → 行业北向持仓时间序列
4. 计算近 5 / 10 交易日持仓变化率

注意:
- hk_hold 接口需要 ≥2000 积分
- 持仓数据可能有缺失(并非所有 A 股都在港股通名单内)
- 返回单位:万元
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

# 往前拉多少自然日的数据(确保能覆盖 10 个交易日 + buffer)
_LOOKBACK_DAYS = 20


def _date_to_tushare(date_str: str) -> str:
    """YYYY-MM-DD → YYYYMMDD"""
    return date_str.replace("-", "")


def _compute_change_pct(series: pd.Series, window: int) -> float | None:
    """
    给定按日期升序排列的持仓市值序列,计算最近 window 个交易日的变化百分比。

    series: index 为交易日(升序), value 为持仓市值
    """
    if series is None or len(series) < window + 1:
        return None
    latest = float(series.iloc[-1])
    past = float(series.iloc[-(window + 1)])
    if past == 0:
        return None
    return (latest - past) / past


def fetch_northbound(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,
) -> dict:
    """
    获取北向资金行业偏好。

    参数:
        client:           TushareClient 实例
        industry_l2_code: 申万二级行业代码,如 "801125.SI"
        analysis_date:    分析日期 YYYY-MM-DD

    返回:
        {
          "industry_l2_code": str,
          "current_holding_value": float | None,  # 当日北向持有该行业的总市值(万元)
          "change_5d_pct":  float | None,         # 近 5 交易日持仓市值变化(%)
          "change_10d_pct": float | None,
        }
    """
    _empty: dict = {
        "industry_l2_code": industry_l2_code,
        "current_holding_value": None,
        "change_5d_pct": None,
        "change_10d_pct": None,
    }

    try:
        # ── Step 1: 行业成分股 ──────────────────────────────────────────────
        members_df = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
        if members_df is None or members_df.empty or "ts_code" not in members_df.columns:
            return _empty

        member_codes: list[str] = members_df["ts_code"].tolist()

        # ── Step 2: 拉各成分股港股通持股 ────────────────────────────────────
        end_date = _date_to_tushare(analysis_date)
        start_dt = datetime.strptime(analysis_date, "%Y-%m-%d") - timedelta(days=_LOOKBACK_DAYS)
        start_date = start_dt.strftime("%Y%m%d")

        all_holdings: list[pd.DataFrame] = []
        for ts_code in member_codes:
            try:
                df = client.call(
                    "hk_hold",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if df is not None and not df.empty:
                    all_holdings.append(df)
            except (ConnectionError, TimeoutError, OSError):
                # 单只股票失败不影响整体,继续
                continue

        if not all_holdings:
            return _empty

        # ── Step 3: 按交易日聚合 ────────────────────────────────────────────
        combined = pd.concat(all_holdings, ignore_index=True)

        # hk_hold 返回字段: trade_date, ts_code, exchg, vol, ratio, avg_price, close, market_value
        # market_value 单位是万元
        value_col = None
        for col in ("market_value", "vol"):
            if col in combined.columns:
                value_col = col
                break

        if value_col is None:
            return _empty

        # 转为数值
        combined[value_col] = pd.to_numeric(combined[value_col], errors="coerce").fillna(0.0)

        # 按交易日加总
        daily_agg = (
            combined.groupby("trade_date")[value_col]
            .sum()
            .sort_index()  # 升序
        )

        if daily_agg.empty:
            return _empty

        # ── Step 4: 计算变化率 ───────────────────────────────────────────────
        current_value = float(daily_agg.iloc[-1])
        change_5d = _compute_change_pct(daily_agg, window=5)
        change_10d = _compute_change_pct(daily_agg, window=10)

        return {
            "industry_l2_code": industry_l2_code,
            "current_holding_value": current_value,
            "change_5d_pct": change_5d,
            "change_10d_pct": change_10d,
        }

    except (ConnectionError, TimeoutError, OSError) as exc:
        warnings.warn(
            f"fetch_northbound: 网络错误,返回全 None 字段。原因: {exc}",
            stacklevel=2,
        )
        return _empty


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="获取北向资金行业偏好(港股通持股聚合)")
    parser.add_argument("--industry-l2-code", required=True, help="申万二级行业代码,如 801125.SI")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
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
