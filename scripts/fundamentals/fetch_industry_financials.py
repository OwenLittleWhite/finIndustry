"""行业聚合财务数据获取。

数据流:
1. index_member_all(l2_code=, is_new='Y') → 行业成分股 ts_code 列表
2. 对每个成分股调 fina_indicator(ts_code=) 拉全量已发布财务指标
3. 按 end_date 字段聚合到季度 bucket(取 analysis_date 之前完结的季度)
4. 输出行业聚合营收/利润 YoY 增速 + ROE/毛利率中位数
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402


# ---------------------------------------------------------------------------
# 季度工具
# ---------------------------------------------------------------------------


def _quarter_end_date(year: int, quarter: int) -> str:
    """返回季度末日期字符串 YYYYMMDD。"""
    ends = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
    return f"{year}{ends[quarter]}"


def _quarter_label(year: int, quarter: int) -> str:
    """返回季度标签,如 '2024Q1'。"""
    return f"{year}Q{quarter}"


def _derive_quarter_list(analysis_date: str, quarters: int) -> list[tuple[str, str]]:
    """
    从 analysis_date 倒推 quarters 个已完结季度。

    返回: [(quarter_label, end_date_yyyymmdd), ...] 最新在前
    分析日期前已完结的季度:季度末日期 <= analysis_date
    """
    cutoff = datetime.strptime(analysis_date, "%Y-%m-%d").date()
    result: list[tuple[str, str]] = []

    year = cutoff.year
    quarter = (cutoff.month - 1) // 3 + 1  # 当前所在季度

    # 从当前季度往前扫,找已完结的季度
    y, q = year, quarter
    while len(result) < quarters:
        end_str = _quarter_end_date(y, q)
        end_date = datetime.strptime(end_str, "%Y%m%d").date()
        if end_date <= cutoff:
            result.append((_quarter_label(y, q), end_str))
        # 上一季度
        q -= 1
        if q == 0:
            q = 4
            y -= 1
        if y < 2000:
            break

    return result


# ---------------------------------------------------------------------------
# 聚合逻辑
# ---------------------------------------------------------------------------


def _compute_yoy(current: float | None, prior: float | None) -> float | None:
    """YoY = current / prior - 1,prior 为 0 或 None 则返回 None。"""
    if current is None or prior is None:
        return None
    if prior == 0:
        return None
    return (current - prior) / abs(prior)


def _aggregate_quarter(
    all_fina: pd.DataFrame,
    end_date: str,
    field: str,
    agg: str = "sum",
) -> float | None:
    """
    从全量 fina_indicator 数据中,按 end_date 过滤当季数据,
    对 field 做聚合(sum 或 median)。
    """
    if all_fina.empty or field not in all_fina.columns:
        return None
    quarter_df = all_fina[all_fina["end_date"] == end_date][field].dropna()
    if quarter_df.empty:
        return None
    if agg == "sum":
        return float(quarter_df.sum())
    if agg == "median":
        return float(quarter_df.median())
    return None


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def fetch_industry_financials(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,
    quarters: int = 8,
) -> dict:
    """
    返回行业聚合财务数据。

    返回结构:
      {
        "industry_l2_code": str,
        "quarters": [str, ...],              # 季度标签,最新在前
        "agg_revenue_yoy": [float|None, ...],
        "agg_profit_yoy": [float|None, ...],
        "median_roe": [float|None, ...],
        "median_gross_margin": [float|None, ...],
        "constituent_count": int,
      }

    异常情况一律 graceful:成分股空 / 数据缺失 → 对应位置填 None。
    """
    empty_result = {
        "industry_l2_code": industry_l2_code,
        "quarters": [],
        "agg_revenue_yoy": [],
        "agg_profit_yoy": [],
        "median_roe": [],
        "median_gross_margin": [],
        "constituent_count": 0,
    }

    # ── Step 1: 行业成分股 ──────────────────────────────────────────────────
    members_df = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
    if members_df is None or members_df.empty or "ts_code" not in members_df.columns:
        return empty_result

    ts_codes: list[str] = members_df["ts_code"].dropna().unique().tolist()
    if not ts_codes:
        return empty_result

    # ── Step 2: 季度列表(取 quarters 个 + 额外 4 个用于 YoY 同比) ────────
    # 多拉 4 个季度是为了能算第一批季度的 YoY(需要去年同期)
    quarter_list = _derive_quarter_list(analysis_date, quarters + 4)
    if not quarter_list:
        return empty_result

    # 我们输出的季度是前 quarters 个
    output_quarters = quarter_list[:quarters]
    all_end_dates = {end for _, end in quarter_list}

    # ── Step 3: 拉成分股财务数据 ────────────────────────────────────────────
    fina_frames: list[pd.DataFrame] = []
    for ts_code in ts_codes:
        try:
            df = client.call("fina_indicator", ts_code=ts_code)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        # 只保留需要的列
        needed = {"ts_code", "end_date", "revenue", "n_income_attr_p", "roe", "grossprofit_margin"}
        available = needed & set(df.columns)
        fina_frames.append(df[list(available)].copy())

    if not fina_frames:
        return {**empty_result, "constituent_count": len(ts_codes)}

    all_fina = pd.concat(fina_frames, ignore_index=True)

    # end_date 转为统一字符串格式(有时 tushare 返回 int)
    all_fina["end_date"] = all_fina["end_date"].astype(str).str.replace(r"\.0$", "", regex=True)

    # ── Step 4: 按季度聚合 ───────────────────────────────────────────────────
    quarter_labels: list[str] = []
    agg_revenue_yoy: list[float | None] = []
    agg_profit_yoy: list[float | None] = []
    median_roe: list[float | None] = []
    median_gross_margin: list[float | None] = []

    for label, end_date in output_quarters:
        quarter_labels.append(label)

        # ROE / 毛利率直接取中位数
        median_roe.append(_aggregate_quarter(all_fina, end_date, "roe", "median"))
        median_gross_margin.append(
            _aggregate_quarter(all_fina, end_date, "grossprofit_margin", "median")
        )

        # YoY: 找去年同期 end_date(季度末 -1 年 = 同月同日)
        prior_year = str(int(end_date[:4]) - 1) + end_date[4:]
        current_rev = _aggregate_quarter(all_fina, end_date, "revenue", "sum")
        prior_rev = _aggregate_quarter(all_fina, prior_year, "revenue", "sum")
        agg_revenue_yoy.append(_compute_yoy(current_rev, prior_rev))

        current_profit = _aggregate_quarter(all_fina, end_date, "n_income_attr_p", "sum")
        prior_profit = _aggregate_quarter(all_fina, prior_year, "n_income_attr_p", "sum")
        agg_profit_yoy.append(_compute_yoy(current_profit, prior_profit))

    return {
        "industry_l2_code": industry_l2_code,
        "quarters": quarter_labels,
        "agg_revenue_yoy": agg_revenue_yoy,
        "agg_profit_yoy": agg_profit_yoy,
        "median_roe": median_roe,
        "median_gross_margin": median_gross_margin,
        "constituent_count": len(ts_codes),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="获取行业聚合财务数据")
    parser.add_argument("--industry-l2-code", required=True, help="申万二级行业代码,如 801125.SI")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
    parser.add_argument("--quarters", type=int, default=8)
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)

    result = fetch_industry_financials(
        client,
        industry_l2_code=args.industry_l2_code,
        analysis_date=args.analysis_date,
        quarters=args.quarters,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
