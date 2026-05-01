"""Thin wrapper over tushare's pro_api with caching and lookahead guard."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd

from scripts.common.cache import Cache


class TushareClient:
    """
    Tushare 调用封装。

    - 自动缓存(以 analysis_date 隔离)
    - 拒绝任何 end_date / start_date / trade_date 超过 analysis_date 的调用(防 lookahead)
    """

    def __init__(self, pro: Any = None, cache: Cache | None = None, analysis_date: str = ""):
        self.pro = pro or self._init_pro()
        self.cache = cache
        self.analysis_date = analysis_date  # YYYY-MM-DD

    @staticmethod
    def _init_pro() -> Any:
        import tushare as ts

        token = os.environ.get("TUSHARE_TOKEN")
        if not token:
            raise RuntimeError("TUSHARE_TOKEN env var not set")
        ts.set_token(token)
        return ts.pro_api()

    def _check_lookahead(self, params: dict) -> None:
        """Tushare 通常 end_date 是 YYYYMMDD 格式,我们的 analysis_date 是 YYYY-MM-DD。"""
        if not self.analysis_date:
            return
        cutoff = datetime.strptime(self.analysis_date, "%Y-%m-%d").date()
        for key in ("end_date", "start_date", "trade_date"):
            value = params.get(key)
            if not value:
                continue
            try:
                d = datetime.strptime(str(value), "%Y%m%d").date()
            except ValueError:
                continue
            if d > cutoff:
                raise ValueError(
                    f"lookahead detected: param {key}={value} > analysis_date={self.analysis_date}"
                )

    def call(self, api_name: str, **params: Any) -> pd.DataFrame:
        self._check_lookahead(params)

        if self.cache is not None:
            cached = self.cache.get(f"tushare.{api_name}", params, self.analysis_date)
            if cached is not None:
                return pd.DataFrame(cached)

        method = getattr(self.pro, api_name)
        df = method(**params)
        if df is None:
            df = pd.DataFrame()

        if self.cache is not None:
            self.cache.set(
                f"tushare.{api_name}", params, self.analysis_date,
                df.to_dict(orient="records"),
            )

        return df
