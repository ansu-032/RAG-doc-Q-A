import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db
from src.schemas.file import FileOut
from src.services import file_service

router = APIRouter(tags=["files"])


@router.post("/file", response_model=FileOut, status_code=201)
async def upload_file(file: UploadFile, db: AsyncSession = Depends(get_db)):
    return await file_service.upload_file(db, file)


@router.get("/file/{file_id}", response_model=FileOut)
async def get_file_info(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await file_service.get_file_or_404(db, file_id)


@router.get("/file/{file_id}/download")
async def download_file(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    record, data = await file_service.download_file(db, file_id)
    return Response(
        content=data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.original_filename)}"
        },
    )


@router.delete("/file/{file_id}", status_code=204)
async def delete_file(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await file_service.delete_file(db, file_id)
