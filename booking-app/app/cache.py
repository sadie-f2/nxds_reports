"""
Simple in-process TTL cache. Good enough for a single-process deployment.
Replace with Redis if multi-process or sticky sessions become necessary.
"""

import time
from typing import Any, Optional

_store: dict[str, tuple[float, Any]] = {}


def get(key: str, ttl: int = 300) -> Optional[Any]:
    """Return cached value if present and not expired, else None."""
    entry = _store.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts > ttl:
        del _store[key]
        return None
    return value


def set(key: str, value: Any) -> None:
    """Store value with current timestamp."""
    _store[key] = (time.time(), value)


def invalidate(key: str) -> None:
    """Remove a cache entry."""
    _store.pop(key, None)


def clear_all() -> None:
    """Clear the entire cache (useful in tests)."""
    _store.clear()
