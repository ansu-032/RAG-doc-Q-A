import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.middleware import log_requests
from src.routes import files, query
from src.services import scheduler, storage


@asynccontextmanager
async def lifespan(app: FastAPI):

    logging.getLogger("uvicorn.access").disabled = True
    await asyncio.to_thread(storage.ensure_bucket)
    await scheduler.refresh()
    yield
    scheduler.stop()


app = FastAPI(title="Citely", lifespan=lifespan)
app.middleware("http")(log_requests)
app.include_router(files.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")
