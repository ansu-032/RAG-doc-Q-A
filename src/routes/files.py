import uuid
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db, get_session_id
from src.schemas.file import FileOut
from src.services import file_service, processing, rate_limit, scheduler, sessions

router = APIRouter(tags=["files"])


@router.post(
    "/file", response_model=FileOut, status_code=201, dependencies=[Depends(rate_limit.limit_uploads)]
)
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    response: Response,
    db: AsyncSession = Depends(get_db),
    session_id: uuid.UUID | None = Depends(get_session_id),
):
    session_id = await sessions.ensure_session(db, session_id)
    sessions.set_cookie(response, session_id)
    # Before the file is stored, so cleanup cannot remove this session in between.
    await scheduler.touch(session_id)
    record = await file_service.upload_file(db, file, session_id)
    await scheduler.refresh()
    background_tasks.add_task(processing.process_file, record.id, session_id)
    return record


@router.get("/file/{file_id}", response_model=FileOut)
async def get_file_info(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    session_id: uuid.UUID | None = Depends(get_session_id),
):
    return await file_service.get_file_or_404(db, file_id, session_id)


@router.get("/file/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    session_id: uuid.UUID | None = Depends(get_session_id),
):
    await scheduler.touch(session_id)
    record, data = await file_service.download_file(db, file_id, session_id)
    return Response(
        content=data,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.original_filename)}"
        },
    )


@router.delete("/file/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    session_id: uuid.UUID | None = Depends(get_session_id),
):
    await scheduler.touch(session_id)
    await file_service.delete_file(db, file_id, session_id)
    await scheduler.refresh()
