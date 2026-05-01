"""SQLite-based cache for data fetchers.

Cache key = (api_name, sorted(params), analysis_date) — analysis_date 强制分离
确保同一 ticker 在不同 analysis_date 下缓存独立,防 lookahead bias。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.cache_dir / "cache.db"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    api_name TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @staticmethod
    def _make_key(api_name: str, params: dict, analysis_date: str) -> str:
        params_canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
        raw = f"{api_name}|{params_canonical}|{analysis_date}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, api_name: str, params: dict, analysis_date: str) -> Any | None:
        key = self._make_key(api_name, params, analysis_date)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value_json FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, api_name: str, params: dict, analysis_date: str, value: Any) -> None:
        key = self._make_key(api_name, params, analysis_date)
        params_json = json.dumps(params, sort_keys=True, ensure_ascii=False)
        value_json = json.dumps(value, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, api_name, params_json, analysis_date, value_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, api_name, params_json, analysis_date, value_json),
            )
