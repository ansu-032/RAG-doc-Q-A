import logging
import re
import time

from fastapi import Request

from src.deps import get_session_id
from src.logging_config import logger
from src.services.sessions import short_id

# The frontend polls this while a file processes: only logged at --log-level debug when it succeeds.
STATUS_POLL = re.compile(r"^/api/v1/file/[^/]+$")


async def log_requests(request: Request, call_next):
    """Log each request's method, path, status code, time taken, IP and session."""
    start = time.perf_counter()
    context = f"ip={request.client.host if request.client else 'unknown'} session={short_id(get_session_id(request))}"
    try:
        response = await call_next(request)
    except Exception:
        # uvicorn prints the traceback; this says which request it belongs to.
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error("%s %s -> unhandled error (%d ms) %s", request.method, request.url.path, duration_ms, context)
        raise
    duration_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Process-Time-Ms"] = str(duration_ms)

    status = response.status_code
    if status >= 500:
        level = logging.ERROR
    elif status >= 400:
        level = logging.WARNING
    elif request.method == "GET" and STATUS_POLL.match(request.url.path):
        level = logging.DEBUG
    else:
        level = logging.INFO
    logger.log(level, "%s %s -> %s (%d ms) %s", request.method, request.url.path, status, duration_ms, context)
    return response
