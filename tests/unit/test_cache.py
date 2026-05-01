"""SQLite cache for data fetchers - 防 lookahead bias 关键。"""
import json
import tempfile
from pathlib import Path

import pytest

from scripts.common.cache import Cache


@pytest.fixture
def tmp_cache(tmp_path):
    return Cache(cache_dir=tmp_path)


def test_set_and_get_returns_value(tmp_cache):
    tmp_cache.set("api_x", {"ticker": "600519"}, "2026-04-30", {"data": [1, 2, 3]})
    result = tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-30")
    assert result == {"data": [1, 2, 3]}


def test_get_missing_returns_none(tmp_cache):
    result = tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-30")
    assert result is None


def test_different_analysis_date_separate_entries(tmp_cache):
    """同 api 同 params,不同 analysis_date 必须独立缓存(防 lookahead)。"""
    tmp_cache.set("api_x", {"ticker": "600519"}, "2026-04-29", {"v": 1})
    tmp_cache.set("api_x", {"ticker": "600519"}, "2026-04-30", {"v": 2})
    assert tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-29") == {"v": 1}
    assert tmp_cache.get("api_x", {"ticker": "600519"}, "2026-04-30") == {"v": 2}


def test_param_order_doesnt_matter(tmp_cache):
    """params 字典顺序不应影响缓存 key。"""
    tmp_cache.set("api_x", {"a": 1, "b": 2}, "2026-04-30", {"v": 1})
    result = tmp_cache.get("api_x", {"b": 2, "a": 1}, "2026-04-30")
    assert result == {"v": 1}


def test_persists_across_instances(tmp_path):
    """关闭重开仍然命中缓存。"""
    c1 = Cache(cache_dir=tmp_path)
    c1.set("api_x", {"k": "v"}, "2026-04-30", {"data": 42})
    del c1

    c2 = Cache(cache_dir=tmp_path)
    assert c2.get("api_x", {"k": "v"}, "2026-04-30") == {"data": 42}
