"""Deletes a session's files (and their chunks) after that session has been idle for a while.

The scheduler only runs while there is data to clean: refresh() turns it on after an
upload, and off once no files are left. Activity is stored in the database, so it
survives server restarts and each browser session has its own idle timer.
"""

import asyncio
import datetime
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, exists, func, select, update

from src.config import settings
from src.db.models import UploadedFile, UserSession
from src.db.session import SessionLocal
from src.logging_config import logger
from src.services import file_service
from src.services.sessions import short_id

# The on/off switch: the scheduler is on while this task is alive.
_task: asyncio.Task | None = None
_lock = asyncio.Lock()


async def touch(session_id: uuid.UUID | None) -> None:
    """Record user activity. Status polling does not call this, so an open tab alone stays idle."""
    if session_id is None:
        return
    try:
        async with SessionLocal() as db:
            await db.execute(
                update(UserSession).where(UserSession.id == session_id).values(last_activity_at=func.now())
            )
            await db.commit()
        logger.debug("Activity recorded: session=%s", short_id(session_id))
    except Exception:
        # Never fail the user's request over this.
        logger.exception("Could not record session activity")


def _idle_condition():
    """True for sessions past the idle time with no file being processed.

    A file stuck in processing since before the cutoff (its job died in a restart) does
    not count, or that session could never be cleaned.
    """
    cutoff = func.now() - datetime.timedelta(minutes=settings.cleanup_idle_minutes)
    being_processed = exists().where(
        UploadedFile.session_id == UserSession.id,
        UploadedFile.status.in_(("pending", "processing")),
        UploadedFile.updated_at >= cutoff,
    )
    return UserSession.last_activity_at < cutoff, ~being_processed


async def _is_idle(session_id: uuid.UUID) -> bool:
    async with SessionLocal() as db:
        query = select(UserSession.id).where(UserSession.id == session_id, *_idle_condition())
        return await db.scalar(query) is not None


async def _clean_session(session_id: uuid.UUID) -> int:
    async with SessionLocal() as db:
        file_ids = list(await db.scalars(select(UploadedFile.id).where(UploadedFile.session_id == session_id)))
    logger.info("Cleanup: session %s is idle, deleting %d file(s)", short_id(session_id), len(file_ids))

    deleted = 0
    for file_id in file_ids:
        # The user came back mid-cleanup: keep whatever is left.
        if not await _is_idle(session_id):
            logger.info(
                "Cleanup stopped for session %s: new activity, kept %d file(s)",
                short_id(session_id),
                len(file_ids) - deleted,
            )
            return deleted
        try:
            async with SessionLocal() as db:
                await file_service.delete_file(db, file_id, session_id)
            deleted += 1
        except HTTPException:
            logger.info("Cleanup: file %s was already deleted", file_id)
        except Exception:
            logger.exception("Cleanup could not delete file %s; will retry next run", file_id)

    # Only once it is empty and still idle: a failed delete keeps the session for the next run.
    async with SessionLocal() as db:
        has_files = exists().where(UploadedFile.session_id == UserSession.id)
        result = await db.execute(
            delete(UserSession).where(UserSession.id == session_id, *_idle_condition(), ~has_files)
        )
        await db.commit()
    if result.rowcount:
        logger.info("Cleanup: session %s removed", short_id(session_id))
    else:
        logger.warning("Cleanup: session %s kept: files remain or it became active", short_id(session_id))
    return deleted


async def clean_idle_sessions() -> int:
    """Clean every idle session; returns how many files were deleted."""
    async with SessionLocal() as db:
        session_ids = list(await db.scalars(select(UserSession.id).where(*_idle_condition())))
        total_sessions = await db.scalar(select(func.count()).select_from(UserSession))
    logger.info(
        "Cleanup check: %d of %d session(s) idle for %d+ minutes",
        len(session_ids),
        total_sessions,
        settings.cleanup_idle_minutes,
    )

    deleted = 0
    for session_id in session_ids:
        # One bad session must not stop the others from being cleaned.
        try:
            deleted += await _clean_session(session_id)
        except Exception:
            logger.exception("Cleanup failed for session %s; will retry next run", short_id(session_id))
    if session_ids:
        logger.info("Cleanup finished: deleted %d file(s) from %d idle session(s)", deleted, len(session_ids))
    return deleted


async def _has_data() -> bool:
    # Files rather than chunks: a file that failed processing has no chunks but is still stored.
    async with SessionLocal() as db:
        return await db.scalar(select(UploadedFile.id).limit(1)) is not None


async def _run() -> None:
    global _task
    while True:
        await asyncio.sleep(settings.cleanup_interval_minutes * 60)
        # A failure (e.g. database down) must not kill the scheduler: try again next time.
        try:
            await clean_idle_sessions()
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
                logger.info(
                    "Cleanup scheduler on: checks every %d minutes, deletes after %d idle minutes",
                    settings.cleanup_interval_minutes,
                    settings.cleanup_idle_minutes,
                )
            elif not has_data and running:
                _task.cancel()
                _task = None
                logger.info("Cleanup scheduler off: no data left")
            else:
                logger.debug("Cleanup scheduler unchanged: running=%s has_data=%s", running, has_data)
    except Exception:
        # The upload or delete itself succeeded, so don't fail the request over this.
        logger.exception("Could not update the cleanup scheduler")


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("Cleanup scheduler stopped: server shutting down")
