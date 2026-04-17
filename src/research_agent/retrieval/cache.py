from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from diskcache import Cache

CacheMode = Literal["default", "refresh", "off"]

CACHE_SCHEMA_VERSION = 1
SCORING_SCHEMA_VERSION = 1
EVIDENCE_SERIALIZATION_SCHEMA_VERSION = 1

DEFAULT_CACHE_DIR = "~/.cache/research-agent"

TTL_TAVILY_SEC = 24 * 60 * 60
TTL_PAPER_QUERY_SEC = 7 * 24 * 60 * 60
TTL_DOI_LOOKUP_SEC = 30 * 24 * 60 * 60
TTL_PAGE_METADATA_SEC = 7 * 24 * 60 * 60
TTL_AGGREGATE_SEC = 24 * 60 * 60
TTL_EMPTY_SHORT_SEC = 10 * 60


@dataclass(frozen=True)
class CacheSettings:
    mode: CacheMode = "default"
    cache_dir: str | None = None


def get_cache(cache_dir: str | None = None) -> Cache:
    raw_dir = cache_dir or os.environ.get("RESEARCH_AGENT_CACHE_DIR") or DEFAULT_CACHE_DIR
    return Cache(os.path.expanduser(raw_dir))


def normalize_url_for_cache(url: str) -> str:
    stripped = url.strip()
    if not stripped:
        return stripped
    parts = urlsplit(stripped)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path
    if path == "/":
        path = ""
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def cache_key(kind: str, payload: dict[str, Any]) -> str:
    packed = json.dumps({"kind": kind, "payload": payload}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"ra:{kind}:{hashlib.sha256(packed.encode('utf-8')).hexdigest()}"


def should_read_cache(settings: CacheSettings) -> bool:
    return settings.mode == "default"


def should_write_cache(settings: CacheSettings) -> bool:
    return settings.mode in {"default", "refresh"}


def serialize_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))

