import uuid

from fastapi import Request

from src.db.session import SessionLocal
from src.services.sessions import COOKIE_NAME


async def get_db():
    async with SessionLocal() as session:
        yield session


def get_session_id(request: Request) -> uuid.UUID | None:
    """The browser's session id from its cookie, or None if missing or malformed."""
    try:
        return uuid.UUID(request.cookies.get(COOKIE_NAME))
    except (TypeError, ValueError):
        return None
