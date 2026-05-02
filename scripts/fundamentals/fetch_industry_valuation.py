"""行业 PE/PB 当前值 + 历史分位获取。

数据流:
1. index_member_all(l2_code=, is_new='Y') → 行业成分股 ts_code 列表
2. 对每个成分股调 daily_basic(ts_code=, start_date=, end_date=) 拿过去 N 年日度 pe_ttm / pb
3. 每个交易日对所有成分股取 PE_TTM/PB 中位数 → 行业 PE/PB 时间序列
4. 当前 PE/PB 中位数 = 序列最后一日(最新日)值
5. PE/PB 分位 = 当前值在过去 N 年序列中的排名 / 总长度
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

# 历史分位计算需要的最少数据点(避免用极少数据计算无意义的分位)
MIN_HISTORY_POINTS = 20


# ---------------------------------------------------------------------------
# 分位计算
# ---------------------------------------------------------------------------


def _percentile_of(series: list[float], value: float) -> float:
    """
    计算 value 在 series 中的分位(0~1)。

    定义: 序列中 <= value 的比例。
    例: series=[10,12,14,16,18,20], value=14 → 3/6 = 0.5
    """
    if not series:
        return 0.0
    count_le = sum(1 for x in series if x <= value)
    return count_le / len(series)


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def fetch_industry_valuation(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,
    history_years: int = 5,
) -> dict:
    """
    返回行业 PE/PB 当前值及历史分位。

    返回结构:
      {
        "industry_l2_code": str,
        "current_pe_median": float | None,
        "current_pb_median": float | None,
        "pe_percentile_5y": float | None,
        "pb_percentile_5y": float | None,
        "constituent_count": int,
      }

    数据不足(< MIN_HISTORY_POINTS)时分位返回 None,current 值仍尝试填充。
    """
    empty_result: dict[str, Any] = {
        "industry_l2_code": industry_l2_code,
        "current_pe_median": None,
        "current_pb_median": None,
        "pe_percentile_5y": None,
        "pb_percentile_5y": None,
        "constituent_count": 0,
    }

    # ── Step 1: 行业成分股 ──────────────────────────────────────────────────
    members_df = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
    if members_df is None or members_df.empty or "ts_code" not in members_df.columns:
        return empty_result

    ts_codes: list[str] = members_df["ts_code"].dropna().unique().tolist()
    if not ts_codes:
        return empty_result

    empty_result["constituent_count"] = len(ts_codes)

    # ── Step 2: 计算历史时间范围 ────────────────────────────────────────────
    end_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=history_years * 365 + 30)  # 多加 30 天 buffer
    end_date_str = end_dt.strftime("%Y%m%d")
    start_date_str = start_dt.strftime("%Y%m%d")

    # ── Step 3: 拉每个成分股的 daily_basic 历史数据 ──────────────────────
    # trade_date → list of pe_ttm / pb (per stock)
    date_pe: dict[str, list[float]] = {}
    date_pb: dict[str, list[float]] = {}

    for ts_code in ts_codes:
        try:
            df = client.call(
                "daily_basic",
                ts_code=ts_code,
                start_date=start_date_str,
                end_date=end_date_str,
            )
        except Exception:
            continue
        if df is None or df.empty or "trade_date" not in df.columns:
            continue

        for _, row in df.iterrows():
            td = str(row["trade_date"])
            if "pe_ttm" in row and pd.notna(row["pe_ttm"]):
                val = float(row["pe_ttm"])
                if val > 0:  # 剔除负 PE(亏损股)
                    date_pe.setdefault(td, []).append(val)
            if "pb" in row and pd.notna(row["pb"]):
                val = float(row["pb"])
                if val > 0:
                    date_pb.setdefault(td, []).append(val)

    if not date_pe and not date_pb:
        return {**empty_result, "constituent_count": len(ts_codes)}

    # ── Step 4: 每日行业 PE/PB 中位数时间序列 ───────────────────────────────
    # 只保留 pe 和 pb 都有数据的日期,并按日期排序
    all_dates = sorted(set(date_pe.keys()) | set(date_pb.keys()))

    pe_series: list[float] = []
    pb_series: list[float] = []
    pe_dates: list[str] = []

    for td in all_dates:
        pe_vals = date_pe.get(td, [])
        pb_vals = date_pb.get(td, [])
        if pe_vals:
            pe_series.append(float(pd.Series(pe_vals).median()))
            pe_dates.append(td)
        if pb_vals:
            pb_series.append(float(pd.Series(pb_vals).median()))

    # ── Step 5: 当前值(序列最新日)+ 历史分位 ──────────────────────────────
    current_pe: float | None = pe_series[-1] if pe_series else None
    current_pb: float | None = pb_series[-1] if pb_series else None

    pe_pct: float | None = None
    pb_pct: float | None = None

    if len(pe_series) >= MIN_HISTORY_POINTS and current_pe is not None:
        pe_pct = _percentile_of(pe_series, current_pe)

    if len(pb_series) >= MIN_HISTORY_POINTS and current_pb is not None:
        pb_pct = _percentile_of(pb_series, current_pb)

    return {
        "industry_l2_code": industry_l2_code,
        "current_pe_median": current_pe,
        "current_pb_median": current_pb,
        "pe_percentile_5y": pe_pct,
        "pb_percentile_5y": pb_pct,
        "constituent_count": len(ts_codes),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="获取行业 PE/PB 当前值及历史分位")
    parser.add_argument("--industry-l2-code", required=True, help="申万二级行业代码,如 801125.SI")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
    parser.add_argument("--history-years", type=int, default=5)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)

    result = fetch_industry_valuation(
        client,
        industry_l2_code=args.industry_l2_code,
        analysis_date=args.analysis_date,
        history_years=args.history_years,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
