"""行业主力资金净流入(Tushare moneyflow 聚合到行业)。

历史:
  v1 用 akshare stock_sector_fund_flow_rank,在用户 Clash TUN 模式代理下完全不可达
  (TCP 连接 OK 但 HTTP 不响应,代码层 NO_PROXY 也绕不过)。

  v2(本版本):改用 Tushare `moneyflow` 基础接口
  - 对每只行业成分股拉过去 ~15 自然日的逐日资金流(net_mf_amount = 大单+特大单 净流入)
  - 按 trade_date 聚合 → 行业级日度主力净流入
  - 输出 today / 5d / 10d 累计

数据流:
  1. index_member_all(l2_code=, is_new='Y') → 成分股 ts_code 列表
  2. 对每只成分股 moneyflow(ts_code=, start_date=, end_date=) 拉 ~15 天 daily
  3. 合并 + groupby trade_date + sum(net_mf_amount) → 行业日度主力流入
  4. 单位换算:net_mf_amount 字段单位是**万元**,/10000 → 亿元

注意:moneyflow 接口对每只股单独调用,~20 只成分股 = ~20 次 API 调用,
moneyflow 限流较宽松(实测连 5 次每次 < 1s)。
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

# 拉过去 ~15 自然日,确保覆盖 10 个交易日 + buffer
_LOOKBACK_DAYS = 20

# net_mf_amount 单位是万元,/10000 → 亿元
_WAN_TO_YI = 1e-4


def fetch_main_flow(
    client: Any,
    industry_l2_code: str,
    analysis_date: str,
) -> dict:
    """
    获取行业主力资金净流入(基于 Tushare moneyflow + 行业成分股聚合)。

    参数:
        client:           TushareClient 实例
        industry_l2_code: 申万二级行业代码,如 "801125.SI"
        analysis_date:    分析日期 YYYY-MM-DD

    返回:
      {
        "industry_l2_code": str,
        "main_inflow_today_yi": float | None,    # 当日行业主力净流入(亿元,= 大单+特大单 净流入)
        "main_inflow_5d_yi":    float | None,    # 近 5 个交易日累计
        "main_inflow_10d_yi":   float | None,    # 近 10 个交易日累计
        "constituent_count":    int,
        "data_source":          "tushare.moneyflow",
      }

    任何成分股调用失败不阻塞整体,继续聚合;全部成分股都失败 → 返回 None 字段。
    """
    empty: dict = {
        "industry_l2_code": industry_l2_code,
        "main_inflow_today_yi": None,
        "main_inflow_5d_yi": None,
        "main_inflow_10d_yi": None,
        "constituent_count": 0,
        "data_source": "tushare.moneyflow",
    }

    try:
        # ── Step 1: 行业成分股 ──────────────────────────────────────────────
        members_df = client.call("index_member_all", l2_code=industry_l2_code, is_new="Y")
        if members_df is None or members_df.empty or "ts_code" not in members_df.columns:
            return empty

        member_codes: list[str] = members_df["ts_code"].dropna().unique().tolist()
        if not member_codes:
            return empty

        # ── Step 2: 拉每只成分股的过去 ~15 自然日资金流 ──────────────────────
        end_date = analysis_date.replace("-", "")
        start_dt = datetime.strptime(analysis_date, "%Y-%m-%d") - timedelta(days=_LOOKBACK_DAYS)
        start_date = start_dt.strftime("%Y%m%d")

        all_flows: list[pd.DataFrame] = []
        for ts_code in member_codes:
            try:
                df = client.call(
                    "moneyflow",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                if df is not None and not df.empty and "net_mf_amount" in df.columns:
                    all_flows.append(df[["trade_date", "ts_code", "net_mf_amount"]])
            except (ConnectionError, TimeoutError, OSError):
                continue

        if not all_flows:
            return {**empty, "constituent_count": len(member_codes)}

        combined = pd.concat(all_flows, ignore_index=True)
        combined["net_mf_amount"] = pd.to_numeric(combined["net_mf_amount"], errors="coerce")

        # ── Step 3: 按交易日聚合 ────────────────────────────────────────────
        daily_industry = (
            combined.dropna(subset=["net_mf_amount"])
            .groupby("trade_date")["net_mf_amount"]
            .sum()
            .sort_index()  # 升序
        )

        if daily_industry.empty:
            return {**empty, "constituent_count": len(member_codes)}

        # ── Step 4: 转亿元 + 累计 ────────────────────────────────────────────
        today_wan = float(daily_industry.iloc[-1])
        last_5 = daily_industry.tail(5).sum() if len(daily_industry) >= 5 else None
        last_10 = daily_industry.tail(10).sum() if len(daily_industry) >= 10 else None

        return {
            "industry_l2_code": industry_l2_code,
            "main_inflow_today_yi": today_wan * _WAN_TO_YI,
            "main_inflow_5d_yi": float(last_5) * _WAN_TO_YI if last_5 is not None else None,
            "main_inflow_10d_yi": float(last_10) * _WAN_TO_YI if last_10 is not None else None,
            "constituent_count": len(member_codes),
            "data_source": "tushare.moneyflow",
        }

    except (ConnectionError, TimeoutError, OSError) as exc:
        warnings.warn(
            f"fetch_main_flow: 网络错误,返回全 None 字段。原因: {exc}",
            stacklevel=2,
        )
        return empty


def main() -> int:
    parser = argparse.ArgumentParser(description="行业主力资金净流入(Tushare moneyflow 聚合)")
    parser.add_argument("--industry-l2-code", required=True, help="申万二级行业代码,如 801125.SI")
    parser.add_argument("--analysis-date", required=True, help="分析日期 YYYY-MM-DD")
    parser.add_argument("--cache-dir", default="./data")
    parser.add_argument("--output", default="-", help="输出路径,'-' 表示 stdout")
    args = parser.parse_args()

    cache = Cache(args.cache_dir)
    client = TushareClient(cache=cache, analysis_date=args.analysis_date)

    result = fetch_main_flow(
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
