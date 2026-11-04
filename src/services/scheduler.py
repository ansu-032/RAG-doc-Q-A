"""Deletes all files (and their chunks) after a period with no user activity.

The scheduler only runs while there is data to clean: refresh() turns it on after an
upload, and off once nothing is left. Activity and running jobs are kept in memory, so a
server restart restarts the idle timer, and this assumes a single server process.
"""

import asyncio
import logging
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import select

from src.config import settings
from src.db.models import UploadedFile
from src.db.session import SessionLocal
from src.services import file_service

logger = logging.getLogger("uvicorn.error")

_last_activity = time.monotonic()
_running_jobs = 0
# The on/off switch: the scheduler is on while this task is alive.
_task: asyncio.Task | None = None
_lock = asyncio.Lock()


def touch() -> None:
    """Record user activity. Status polling does not call this, so an open tab alone stays idle."""
    global _last_activity
    _last_activity = time.monotonic()


def job_started() -> None:
    global _running_jobs
    _running_jobs += 1


def job_finished() -> None:
    global _running_jobs
    _running_jobs -= 1
    touch()


async def _file_ids() -> list[uuid.UUID]:
    async with SessionLocal() as db:
        return list(await db.scalars(select(UploadedFile.id)))


async def _has_data() -> bool:
    # Files rather than chunks: a file that failed processing has no chunks but is still stored.
    async with SessionLocal() as db:
        return await db.scalar(select(UploadedFile.id).limit(1)) is not None


async def _delete_file(file_id: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await file_service.delete_file(db, file_id)


async def clean_if_idle() -> int:
    """Delete every file if the idle time has passed; returns how many were deleted."""
    idle_seconds = time.monotonic() - _last_activity
    if _running_jobs or idle_seconds < settings.cleanup_idle_minutes * 60:
        return 0

    started_from = _last_activity
    deleted = 0
    for file_id in await _file_ids():
        # The user came back mid-cleanup: keep whatever is left.
        if _last_activity != started_from or _running_jobs:
            logger.info("Cleanup stopped early: new activity")
            break
        try:
            await _delete_file(file_id)
            deleted += 1
        except HTTPException:
            pass  # The user already deleted this one.
        except Exception:
            logger.exception("Cleanup could not delete %s", file_id)
    logger.info("Cleanup deleted %d file(s) after %d idle minutes", deleted, idle_seconds // 60)
    return deleted


async def _run() -> None:
    global _task
    while True:
        await asyncio.sleep(settings.cleanup_interval_minutes * 60)
        # A failure (e.g. database down) must not kill the scheduler: try again next time.
        try:
            await clean_if_idle()
            async with _lock:
                if not await _has_data():
                    _task = None
                    logger.info("Cleanup scheduler off: no data left")
                    return
        except Exception:
            logger.exception("Cleanup run failed")


async def refresh() -> None:
    """Turn the scheduler on or off to match the data. Call at startup, after uploads and deletes."""
    global _task
    try:
        async with _lock:
            has_data = await _has_data()
            running = _task is not None and not _task.done()
            if has_data and not running:
                _task = asyncio.create_task(_run())
                logger.info("Cleanup scheduler on")
            elif not has_data and running:
                _task.cancel()
                _task = None
                logger.info("Cleanup scheduler off: no data left")
    except Exception:
        # The upload or delete itself succeeded, so don't fail the request over this.
        logger.exception("Could not update the cleanup scheduler")


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
