"""Sliding-window rate limiter.

In-memory implementation suits a single API instance. For multiple instances, implement the same
`RateLimiter.hit()` contract on Redis (INCR + EXPIRE or a sorted set) - callers don't change.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from .errors import RateLimited


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_s - (now - q[0])) + 1
                raise RateLimited(f"Too many requests. Try again in {retry}s.", details={"retry_after_s": retry})
            q.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
