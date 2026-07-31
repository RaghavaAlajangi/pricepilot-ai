"""In-memory TTL cache backed by cachetools.TTLCache.

Replaces the previous Redis-based cache. Single process only — sufficient
for this deployment model. TTL and max size are taken from settings.
"""

from typing import Optional

from cachetools import TTLCache

from .config import get_settings
from .logging_conf import get_logger

log = get_logger(__name__)

_cache: Optional[TTLCache] = None


def _get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        s = get_settings()
        _cache = TTLCache(maxsize=s.cache_max_size, ttl=s.cache_ttl_seconds)
    return _cache


def cache_get(key: str) -> Optional[dict]:
    try:
        return _get_cache()[key]
    except KeyError:
        return None


def cache_set(key: str, value: dict) -> None:
    try:
        _get_cache()[key] = value
    except Exception as exc:
        log.warning("cache_set_failed", key=key, error=str(exc))
