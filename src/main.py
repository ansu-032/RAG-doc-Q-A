import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from src import __version__
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


app = FastAPI(title="Citely", version=__version__, lifespan=lifespan)

# CORS middleware for browser clients and proxies
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(https?://.*|null)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.middleware("http")(log_requests)


@app.get("/health", tags=["system"])
@app.get("/api/v1/health", tags=["system"])
async def health_check():
    return {"status": "ok", "version": __version__}


app.include_router(files.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")

# Mount frontend directory for direct single-port access
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

