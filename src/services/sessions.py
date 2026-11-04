"""Anonymous browser sessions: no login, but each browser only reaches its own files."""

import uuid

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import UserSession

COOKIE_NAME = "citely_session"
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


async def ensure_session(db: AsyncSession, session_id: uuid.UUID | None) -> uuid.UUID:
    """Return the browser's session, or a new one.

    An id with no matching row gets a new random id, so a client can never choose its own.
    """
    if session_id is not None and await db.get(UserSession, session_id) is not None:
        return session_id
    session = UserSession()
    db.add(session)
    await db.commit()
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
