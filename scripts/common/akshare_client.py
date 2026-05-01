"""Thin wrapper over akshare functions with caching."""
from __future__ import annotations

from typing import Any

import pandas as pd

from scripts.common.cache import Cache


class AkshareClient:
    """
    akshare 调用封装。

    akshare 多数函数返回 DataFrame,且不像 Tushare 那样支持 end_date 参数。
    防 lookahead 由调用方在拿到 DataFrame 后自行过滤(akshare 通常返回截至当前的数据)。
    """

    def __init__(self, ak_module: Any = None, cache: Cache | None = None, analysis_date: str = ""):
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
