from __future__ import annotations

import time

from research_agent.retrieval.cache import (
    CacheSettings,
    cache_key,
    get_cache,
    normalize_url_for_cache,
    should_read_cache,
    should_write_cache,
)


def test_cache_key_deterministic() -> None:
    p = {"a": 1, "b": ["x", "y"]}
    assert cache_key("k", p) == cache_key("k", p)


def test_url_normalization_for_cache() -> None:
    url = " HTTPS://Example.COM/#frag "
    assert normalize_url_for_cache(url) == "https://example.com"


def test_cache_mode_read_write_semantics() -> None:
    assert should_read_cache(CacheSettings(mode="default"))
    assert should_write_cache(CacheSettings(mode="default"))
    assert not should_read_cache(CacheSettings(mode="refresh"))
    assert should_write_cache(CacheSettings(mode="refresh"))
    assert not should_read_cache(CacheSettings(mode="off"))
    assert not should_write_cache(CacheSettings(mode="off"))


def test_diskcache_ttl_expiry(tmp_path) -> None:
    cache = get_cache(str(tmp_path))
    cache.set("k", {"x": 1}, expire=1)
    assert cache.get("k") == {"x": 1}
    time.sleep(1.2)
    assert cache.get("k") is None

