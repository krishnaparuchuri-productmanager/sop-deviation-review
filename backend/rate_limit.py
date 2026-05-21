"""
rate_limit.py — Simple in-memory per-IP rate limiter.

Uses a sliding-window counter (last 60 seconds) stored in a module-level dict.
Thread-safe via a standard Lock.  Resets on process restart — suitable for
a single-instance portfolio deployment on Railway.

Usage:
    from rate_limit import is_rate_limited

    if is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests.")
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

_lock: Lock = Lock()
_requests: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(ip: str, max_per_minute: int = 10) -> bool:
    """
    Return True if the given IP has exceeded max_per_minute requests
    in the past 60 seconds (sliding window).

    Side effect: records the current request timestamp if NOT limited.
    """
    now = time.monotonic()
    cutoff = now - 60.0

    with _lock:
        # Discard timestamps outside the sliding window
        _requests[ip] = [t for t in _requests[ip] if t > cutoff]

        if len(_requests[ip]) >= max_per_minute:
            return True  # Limit exceeded — do NOT record this request

        _requests[ip].append(now)
        return False
