"""Minimal in-memory TTL cache shared by the Nexova FastAPI services.

The services run single-process in development (one Uvicorn worker each), so a
process-local dictionary is a correct cache layer. Entries expire on a
``time.monotonic`` TTL and can be dropped eagerly by key prefix when a write
changes the underlying data (cache invalidation).

No Redis is wired into this stack; if the deployment moves to multiple workers,
this module is the single seam to replace with a shared store.
"""

import threading
import time
from typing import Any


class TtlCache:
    """A thread-safe cache mapping string keys to ``(expires_at, value)`` pairs.

    ``get`` treats a missing or expired key as a miss (and removes expired
    entries lazily). ``invalidate(prefix)`` removes every key that starts with
    ``prefix``, which is how write routes clear the reads they just invalidated.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if now >= expires_at:
                del self._entries[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic() + ttl, value)

    def invalidate(self, prefix: str) -> None:
        with self._lock:
            stale = [key for key in self._entries if key.startswith(prefix)]
            for key in stale:
                del self._entries[key]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
