import asyncio
import hashlib
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import UploadedFile
from src.deps import get_db
from src.schemas.file import FileOut
from src.services import storage

router = APIRouter(prefix="/files", tags=["files"])


async def get_file_or_404(file_id: uuid.UUID, db: AsyncSession) -> UploadedFile:
    record = await db.get(UploadedFile, file_id)
    if record is None:
        raise HTTPException(404, "File not found")
    return record


@router.post("", response_model=FileOut, status_code=201)
async def upload_file(file: UploadFile, db: AsyncSession = Depends(get_db)):
    if file.content_type not in settings.allowed_mime_types:
        raise HTTPException(415, f"File type '{file.content_type}' is not allowed")

    data = await file.read()
    file_id = uuid.uuid4()
    extension = Path(file.filename).suffix.lower().lstrip(".") or None
    key = f"files/{file_id}.{extension}" if extension else f"files/{file_id}"

    etag = await asyncio.to_thread(storage.put_file, key, data, file.content_type)

    record = UploadedFile(
        id=file_id,
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
        await asyncio.to_thread(storage.delete_file, key)
        raise
    await db.refresh(record)
    return record


@router.get("/{file_id}", response_model=FileOut)
async def get_file_info(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await get_file_or_404(file_id, db)


@router.get("/{file_id}/download")
async def download_file(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    record = await get_file_or_404(file_id, db)
    data = await asyncio.to_thread(storage.get_file, record.minio_object_key)
    return Response(
        content=data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.original_filename)}"
        },
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    record = await get_file_or_404(file_id, db)
    await asyncio.to_thread(storage.delete_file, record.minio_object_key)
    await db.delete(record)
    await db.commit()
