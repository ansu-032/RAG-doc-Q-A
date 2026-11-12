"""Anonymous browser sessions: no login, but each browser only reaches its own files."""

import uuid

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import UserSession
from src.logging_config import logger

COOKIE_NAME = "citely_session"
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def short_id(session_id: uuid.UUID | None) -> str:
    """A session id for logs. Never log the whole id: it works like a password."""
    return str(session_id)[:8] if session_id else "none"


async def ensure_session(db: AsyncSession, session_id: uuid.UUID | None) -> uuid.UUID:
    """Return the browser's session, or a new one.

    An id with no matching row gets a new random id, so a client can never choose its own.
    """
    if session_id is not None and await db.get(UserSession, session_id) is not None:
        return session_id
    session = UserSession()
    db.add(session)
    await db.commit()
    logger.info("New session %s (browser sent an unknown id: %s)", short_id(session.id), session_id is not None)
    return session.id


def set_cookie(response: Response, session_id: uuid.UUID) -> None:
    response.set_cookie(
        COOKIE_NAME,
        str(session_id),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,  # Page scripts cannot read it.
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
