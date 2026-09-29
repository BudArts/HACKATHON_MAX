from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.errors import RateLimitedError


@dataclass(slots=True)
class Bucket:
    limit: int
    window_seconds: float


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def check(self, key: str, bucket: Bucket) -> None:
        now = time.monotonic()
        self._sweep(now)
        window = self._hits[key]
        cutoff = now - bucket.window_seconds
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= bucket.limit:
            retry_after = max(1, int(bucket.window_seconds - (now - window[0])) + 1)
            raise RateLimitedError(
                "Слишком много запросов, попробуйте позже",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        for key in list(self._hits):
            window = self._hits[key]
            while window and window[0] < now - 3600:
                window.popleft()
            if not window:
                del self._hits[key]


limiter = SlidingWindowLimiter()
