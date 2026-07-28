"""Optional Redis JSON cache. If Redis is unconfigured or down, caching
silently degrades to a no-op so the app keeps working."""

import json
from functools import lru_cache
from typing import Optional

import redis

from app.config import get_settings
from app.logging_conf import get_logger

log = get_logger(__name__)


@lru_cache
def _client() -> Optional[redis.Redis]:
    url = get_settings().redis_url
    if not url:
        return None
    return redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)


def cache_get(key: str) -> Optional[dict]:
    """Fetch a cached JSON object, or None on miss/unavailable cache."""
    client = _client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except redis.RedisError as exc:
        log.warning("cache_get_failed", key=key, error=str(exc))
        return None


def cache_set(key: str, value: dict) -> None:
    """Store a JSON object with the configured TTL; failures are non-fatal."""
    client = _client()
    if client is None:
        return
    try:
        client.setex(key, get_settings().cache_ttl_seconds, json.dumps(value))
    except redis.RedisError as exc:
        log.warning("cache_set_failed", key=key, error=str(exc))
