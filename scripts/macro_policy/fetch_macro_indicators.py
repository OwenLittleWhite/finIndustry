"""关键宏观月度指标获取 — 行业宏观传导层数据原料。

拉 CPI / PPI / PMI / M0-M2 / SHIBOR,供后续 LLM agent 推断宏观对具体行业的顺逆风。
脚本只负责数据拉取,行业传导推理交给 LLM。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.cache import Cache  # noqa: E402
from scripts.common.tushare_client import TushareClient  # noqa: E402


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _to_yyyymm(d: date) -> str:
    """date → '202604'(6位,Tushare 宏观接口格式)。"""
    return d.strftime("%Y%m")


def _month_to_ym(month_str: str) -> str:
    """把 Tushare 返回的 month 字段统一成 'YYYY-MM' 格式。

    Tushare 返回格式可能是 '202604' 或 '2026-04'。
    """
    s = str(month_str).strip()
    if len(s) == 6 and "-" not in s:
        return f"{s[:4]}-{s[4:]}"
    return s


def _start_month(analysis_date: str, months: int) -> date:
    """计算往前 months 个月的 1 号。"""
    d = date.fromisoformat(analysis_date)
    # 往前 months 个月
    year = d.year
    month = d.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


# ---------------------------------------------------------------------------
# 各指标拉取函数
# ---------------------------------------------------------------------------

def _fetch_cpi(pro: Any, start_m: str, end_m: str) -> list[dict] | None:
    """CPI:pro.cn_cpi(start_m, end_m) → 标准化列表,按月份降序。"""
    try:
        df = pro.cn_cpi(start_m=start_m, end_m=end_m)
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            records.append({
                "month": _month_to_ym(row.get("month", "")),
                "national_yoy": _safe_float(row.get("nt_val")),
                "national_mom": _safe_float(row.get("nt_mom")),
                "urban_yoy": _safe_float(row.get("town_val")),
                "urban_mom": _safe_float(row.get("town_mom")),
                "rural_yoy": _safe_float(row.get("cnt_val")),
                "rural_mom": _safe_float(row.get("cnt_mom")),
            })
        # 降序:最新月在前
        records.sort(key=lambda r: r["month"], reverse=True)
        return records
    except Exception:
        return None


def _fetch_ppi(pro: Any, start_m: str, end_m: str) -> list[dict] | None:
    """PPI:pro.cn_ppi(start_m, end_m) → 标准化列表,按月份降序。"""
    try:
        df = pro.cn_ppi(start_m=start_m, end_m=end_m)
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            records.append({
                "month": _month_to_ym(row.get("month", "")),
                "ppi_yoy": _safe_float(row.get("ppi_yoy")),
                "ppi_mom": _safe_float(row.get("ppi_mp")),
            })
        records.sort(key=lambda r: r["month"], reverse=True)
        return records
    except Exception:
        return None


def _fetch_pmi(pro: Any, start_m: str, end_m: str) -> list[dict] | None:
    """PMI:必须传 fields 参数,否则 Tushare 返回大写字段名(65 列),无法读出值。

    pmi010000 = 制造业 PMI 综合指数(>50 扩张,<50 收缩)
    pmi020100 = 非制造业 PMI 综合指数
    """
    try:
        df = pro.cn_pmi(start_m=start_m, end_m=end_m,
                        fields="month,pmi010000,pmi020100")
        if df is None or df.empty:
            return None
        records = []
        for _, row in df.iterrows():
            records.append({
                "month": _month_to_ym(row.get("month", "")),
                "manufacturing_pmi": _safe_float(row.get("pmi010000")),
                "non_manufacturing_pmi": _safe_float(row.get("pmi020100")),
            })
        records.sort(key=lambda r: r["month"], reverse=True)
        return records
    except Exception:
        return None


def _fetch_m_supply(pro: Any, start_m: str, end_m: str) -> list[dict] | None:
    """M0/M1/M2:pro.cn_m(start_m, end_m) → 标准化列表,按月份降序。"""
    try:
        df = pro.cn_m(start_m=start_m, end_m=end_m)
        if df is None or df.empty:
            return []
        records = []
        for _, row in df.iterrows():
            records.append({
                "month": _month_to_ym(row.get("month", "")),
                "m0_yoy": _safe_float(row.get("m0_yoy")),
                "m1_yoy": _safe_float(row.get("m1_yoy")),
                "m2_yoy": _safe_float(row.get("m2_yoy")),
                "m0": _safe_float(row.get("m0")),
                "m1": _safe_float(row.get("m1")),
                "m2": _safe_float(row.get("m2")),
            })
        records.sort(key=lambda r: r["month"], reverse=True)
        return records
    except Exception:
        return None


def _fetch_shibor(pro: Any, analysis_date: str) -> dict | None:
    """SHIBOR 当日快照。如当日非交易日,往前最多 retry 5 天。"""
    d = date.fromisoformat(analysis_date)
    for _ in range(5):
        date_str = d.strftime("%Y%m%d")
        try:
            df = pro.shibor(start_date=date_str, end_date=date_str)
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "on": _safe_float(row.get("on")),
                    "1w": _safe_float(row.get("1w")),
                    "1m": _safe_float(row.get("1m")),
                    "3m": _safe_float(row.get("3m")),
                    "1y": _safe_float(row.get("1y")),
                }
        except Exception:
            return None
        d -= timedelta(days=1)
    return None


def _safe_float(val: Any) -> float | None:
    """安全转 float,None/NaN/空字符串均返回 None。"""
    if val is None:
        return None
    try:
        import math
        f = float(val)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 主接口
# ---------------------------------------------------------------------------

def fetch_macro_indicators(
    client,  # TushareClient
    analysis_date: str,  # YYYY-MM-DD,作为截止日
    months: int = 12,  # 取过去几个月
) -> dict:
    """
    返回关键宏观月度指标字典,用于行业宏观传导分析。

    Returns::

        {
          "analysis_date": str,
          "cpi": [
            {"month": "2026-04", "national_yoy": 0.02, "national_mom": 0.001, ...},
            ... (最新在前,共约 months 条)
          ],
          "ppi": [...同结构],
          "pmi": [...] | None,            # 5000积分接口,无权限时为 None
          "m_supply": [
            {"month": "2026-04", "m0_yoy": ..., "m1_yoy": ..., "m2_yoy": ...}
          ],
          "shibor": {                     # 当日利率快照
            "on": float | None,           # 隔夜
            "1w": float | None,
            "1m": float | None,
            "3m": float | None,
            "1y": float | None,
          },
        }

    任何接口失败均 graceful:该字段返回 None 或空 list,不抛异常。
    """
    pro = client.pro

    # 月份范围
    start_date = _start_month(analysis_date, months)
    end_date_obj = date.fromisoformat(analysis_date)

    start_m = _to_yyyymm(start_date)
    end_m = _to_yyyymm(end_date_obj)

    cpi = _fetch_cpi(pro, start_m, end_m)
    ppi = _fetch_ppi(pro, start_m, end_m)
    pmi = _fetch_pmi(pro, start_m, end_m)
    m_supply = _fetch_m_supply(pro, start_m, end_m)
    shibor = _fetch_shibor(pro, analysis_date)

    return {
        "analysis_date": analysis_date,
        "cpi": cpi,
        "ppi": ppi,
        "pmi": pmi,
        "m_supply": m_supply,
        "shibor": shibor,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="拉关键宏观月度指标(CPI/PPI/PMI/M/SHIBOR),行业宏观传导数据原料"
    )
    parser.add_argument("--analysis-date", required=True, help="截止日期 YYYY-MM-DD")
    parser.add_argument("--months", type=int, default=12, help="取过去几个月(默认12)")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,- 为 stdout")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)
    result = fetch_macro_indicators(
        client,
        analysis_date=args.analysis_date,
        months=args.months,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output == "-":
        sys.stdout.write(payload)
        sys.stdout.write("\n")
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
