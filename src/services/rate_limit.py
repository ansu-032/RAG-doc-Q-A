"""Per-IP limits on the routes that cost money or heavy work. Sessions can't do this: clearing
cookies gives anyone a new session.

Counts are kept in memory, so they reset on restart and apply per server process.
"""

import math
import time
from collections import deque

from fastapi import HTTPException, Request

from src.config import settings
from src.logging_config import logger

WINDOW_SECONDS = 60 * 60
# Above this many tracked clients, forget the ones with nothing left in their window.
MAX_TRACKED_BEFORE_SWEEP = 10_000

_hits: dict[tuple[str, str], deque[float]] = {}


def _sweep(now: float) -> None:
    for key in [k for k, q in _hits.items() if not q or now - q[-1] >= WINDOW_SECONDS]:
        del _hits[key]


def check(action: str, client_ip: str, limit: int) -> None:
    """Count one request, or raise 429 if this IP has used up its limit for the past hour."""
    now = time.monotonic()
    if len(_hits) > MAX_TRACKED_BEFORE_SWEEP:
        _sweep(now)

    hits = _hits.setdefault((action, client_ip), deque())
    while hits and now - hits[0] >= WINDOW_SECONDS:
        hits.popleft()

    if len(hits) >= limit:
        retry_after = math.ceil(WINDOW_SECONDS - (now - hits[0]))
        logger.warning(
            "Rate limit hit: action=%s ip=%s limit=%d/h retry_after=%ds", action, client_ip, limit, retry_after
        )
        raise HTTPException(
            429,
            f"Too many requests. Please try again in {math.ceil(retry_after / 60)} minute(s).",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit_queries(request: Request) -> None:
    check("query", _client_ip(request), settings.rate_limit_queries_per_hour)


def limit_uploads(request: Request) -> None:
    check("upload", _client_ip(request), settings.rate_limit_uploads_per_hour)
