import logging
import time

from fastapi import Request

logger = logging.getLogger("uvicorn.error")


async def log_requests(request: Request, call_next):
    """Log each request's method, path, status code and time taken."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    logger.info("%s %s -> %s (%d ms)", request.method, request.url.path, response.status_code, duration_ms)
    return response
