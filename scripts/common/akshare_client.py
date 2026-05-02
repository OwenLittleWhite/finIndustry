"""Thin wrapper over akshare functions with caching."""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

from scripts.common.cache import Cache

# akshare 抓的国内站(东方财富/新浪/同花顺/雪球...),如果系统配了代理(如 Clash),
# 代理规则常常拒绝这些请求。把它们加到 NO_PROXY 让 requests 跳过代理直连。
_AKSHARE_BYPASS_DOMAINS = (
    ".eastmoney.com,"          # 东方财富(akshare 主要数据源)
    "push2.eastmoney.com,"     # 实时行情推送
    "push2his.eastmoney.com,"  # 历史行情推送
    "quote.eastmoney.com,"
    ".sina.com.cn,"            # 新浪财经
    ".sina.cn,"
    "hq.sinajs.cn,"
    ".xueqiu.com,"             # 雪球
    ".10jqka.com.cn,"          # 同花顺
    "stockpage.10jqka.com.cn"
)


def _ensure_proxy_bypass() -> None:
    """把上述域名加到 NO_PROXY/no_proxy。idempotent,重复加不会膨胀。"""
    for var in ("NO_PROXY", "no_proxy"):
        existing = os.environ.get(var, "")
        # 已经包含我们的标记则跳过
        if "eastmoney.com" in existing and "sina.com.cn" in existing:
            continue
        new_value = f"{existing},{_AKSHARE_BYPASS_DOMAINS}".strip(",") if existing else _AKSHARE_BYPASS_DOMAINS
        os.environ[var] = new_value


class AkshareClient:
    """
    akshare 调用封装。

    akshare 多数函数返回 DataFrame,且不像 Tushare 那样支持 end_date 参数。
    防 lookahead 由调用方在拿到 DataFrame 后自行过滤(akshare 通常返回截至当前的数据)。

    自动设置 NO_PROXY,让 akshare 抓国内站时跳过代理(配合 Clash 这类工具)。
    """

    def __init__(self, ak_module: Any = None, cache: Cache | None = None, analysis_date: str = ""):
        _ensure_proxy_bypass()
        self.ak = ak_module or self._import_akshare()
        self.cache = cache
        self.analysis_date = analysis_date

    @staticmethod
    def _import_akshare() -> Any:
        import akshare as ak
        return ak

    def call(self, function_name: str, **params: Any) -> pd.DataFrame:
        if self.cache is not None:
            cached = self.cache.get(f"akshare.{function_name}", params, self.analysis_date)
            if cached is not None:
                return pd.DataFrame(cached)

        func = getattr(self.ak, function_name)
        df = func(**params)
        if df is None:
            df = pd.DataFrame()

        if self.cache is not None:
            self.cache.set(
                f"akshare.{function_name}", params, self.analysis_date,
                df.to_dict(orient="records"),
            )

        return df
