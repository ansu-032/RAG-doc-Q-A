import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings
from src.logging_config import configure_logging, logger
from src.middleware import log_requests
from src.routes import files, query
from src.services import scheduler, storage


@asynccontextmanager
async def lifespan(app: FastAPI):

    configure_logging()
    logging.getLogger("uvicorn.access").disabled = True
    logger.info(
        "Starting Citely: cleanup_interval=%dm cleanup_idle=%dm limits=%d questions/h, %d uploads/h per IP",
        settings.cleanup_interval_minutes,
        settings.cleanup_idle_minutes,
        settings.rate_limit_queries_per_hour,
        settings.rate_limit_uploads_per_hour,
    )
    await asyncio.to_thread(storage.ensure_bucket)
    await scheduler.refresh()
    yield
    scheduler.stop()
    logger.info("Citely stopped")


app = FastAPI(title="Citely", lifespan=lifespan)
app.middleware("http")(log_requests)
app.include_router(files.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")
