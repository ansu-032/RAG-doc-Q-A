import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import UploadedFile
from src.logging_config import logger
from src.services import storage
from src.services.sessions import short_id


async def get_file_or_404(db: AsyncSession, file_id: uuid.UUID, session_id: uuid.UUID | None) -> UploadedFile:
    record = await db.get(UploadedFile, file_id)
    # Another session's file looks exactly like one that does not exist.
    if record is None:
        logger.info("File %s not found (session=%s)", file_id, short_id(session_id))
        raise HTTPException(404, "File not found")
    if record.session_id != session_id:
        logger.warning(
            "File %s blocked: belongs to session %s, requested by session %s",
            file_id,
            short_id(record.session_id),
            short_id(session_id),
        )
        raise HTTPException(404, "File not found")
    return record


async def upload_file(db: AsyncSession, file: UploadFile, session_id: uuid.UUID) -> UploadedFile:
    if file.content_type not in settings.allowed_mime_types:
        logger.warning("Upload rejected: type %s not allowed (session=%s)", file.content_type, short_id(session_id))
        raise HTTPException(415, f"File type '{file.content_type}' is not allowed")

    data = await file.read()
    file_id = uuid.uuid4()
    extension = Path(file.filename).suffix.lower().lstrip(".") or None
    key = f"files/{file_id}.{extension}" if extension else f"files/{file_id}"

    etag = await asyncio.to_thread(storage.put_file, key, data, file.content_type)

    record = UploadedFile(
        id=file_id,
        session_id=session_id,
        original_filename=file.filename,
        mime_type=file.content_type,
        file_extension=extension,
        size_bytes=len(data),
        sha256_checksum=hashlib.sha256(data).hexdigest(),
        minio_bucket=settings.minio_bucket,
        minio_object_key=key,
        minio_etag=etag,
    )
    db.add(record)
    try:
        await db.commit()
    except Exception:
        # Don't leave an object in MinIO that no row points to.
        logger.exception("Upload failed saving file %s to the database; removing it from storage", file_id)
        await asyncio.to_thread(storage.delete_file, key)
        raise
    await db.refresh(record)
    logger.info(
        "Uploaded file %s: %d bytes, type=%s, session=%s", file_id, len(data), file.content_type, short_id(session_id)
    )
    return record


async def download_file(
    db: AsyncSession, file_id: uuid.UUID, session_id: uuid.UUID | None
) -> tuple[UploadedFile, bytes]:
    record = await get_file_or_404(db, file_id, session_id)
    data = await asyncio.to_thread(storage.get_file, record.minio_object_key)
    logger.info("Downloaded file %s: %d bytes, session=%s", file_id, len(data), short_id(session_id))
    return record, data


async def delete_file(db: AsyncSession, file_id: uuid.UUID, session_id: uuid.UUID | None) -> None:
    record = await get_file_or_404(db, file_id, session_id)
    await asyncio.to_thread(storage.delete_file, record.minio_object_key)
    await db.delete(record)
    await db.commit()
    logger.info("Deleted file %s with its chunks, session=%s", file_id, short_id(session_id))
