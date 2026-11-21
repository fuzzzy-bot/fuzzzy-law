"""
Connector rate limiter — sliding-window request counts kept in memory.

The public law connector runs as one process with no database and no Redis,
so its limits are counted here. Nothing is written to disk and a key is
forgotten once its window has passed.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

DEFAULT_MAX_KEYS = 50_000


class SlidingWindowLimiter:
    """Allow at most ``limit`` requests per key in any ``window`` seconds."""

    def __init__(
        self,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_keys = max_keys
        self._clock = clock
        self._hits: dict[str, tuple[float, deque[float]]] = {}  # key → (window, request times)

    def __len__(self) -> int:
        return len(self._hits)

    def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Count one request for ``key``; returns (allowed, retry_after_seconds).

        A refused request is not counted, so a caller that keeps knocking is
        let in again as soon as its oldest counted request leaves the window.
        """
        now = self._clock()
        entry = self._hits.get(key)
        if entry is None:
            self._make_room(now)
            times: deque[float] = deque()
            self._hits[key] = (window, times)
        else:
            times = entry[1]
        while times and times[0] <= now - window:
            times.popleft()
        if len(times) >= limit:
            retry_after = int(window - (now - times[0])) + 1 if times else int(window)
            return False, max(1, retry_after)
        times.append(now)
        return True, 0

    def _make_room(self, now: float) -> None:
        """Forget finished windows; if still full, forget the oldest keys."""
        if len(self._hits) < self._max_keys:
            return
        finished = [k for k, (window, times) in self._hits.items()
                    if not times or times[-1] <= now - window]
        for key in finished:
            del self._hits[key]
        while len(self._hits) >= self._max_keys:
            del self._hits[next(iter(self._hits))]


_limiter = SlidingWindowLimiter()


async def check_memory_rate_limit(key: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
    """Same call shape as the app's Redis limiter, counted in this process."""
    return _limiter.check(key, limit, window)
