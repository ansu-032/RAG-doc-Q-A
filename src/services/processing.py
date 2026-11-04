import asyncio
import datetime
import logging
import uuid

from sqlalchemy.orm.exc import StaleDataError

from src.db.models import DocumentChunk, UploadedFile
from src.db.session import SessionLocal
from src.services import scheduler, storage
from src.services.chunking import split_pages
from src.services.embeddings import embed_passages
from src.services.extraction import extract_text

logger = logging.getLogger("uvicorn.error")


async def process_file(file_id: uuid.UUID, session_id: uuid.UUID) -> None:
    try:
        await _process_file(file_id)
    finally:
        # The idle time starts counting when processing ends.
        await scheduler.touch(session_id)


async def _process_file(file_id: uuid.UUID) -> None:
    """Background task run after upload: file in MinIO -> text -> chunks -> embeddings.

    Uses its own DB session, because the request's session is closed by the time this runs.
    """
    async with SessionLocal() as db:
        record = await db.get(UploadedFile, file_id)
        if record is None:
            return
        try:
            record.status = "processing"
            await db.commit()

            data = await asyncio.to_thread(storage.get_file, record.minio_object_key)
            pages = await asyncio.to_thread(extract_text, data, record.mime_type)
            chunks = await asyncio.to_thread(split_pages, pages)
            vectors = await asyncio.to_thread(embed_passages, [c.content for c in chunks])

            db.add_all(
                DocumentChunk(
                    file_id=file_id, chunk_index=c.chunk_index, content=c.content, embedding=v
                )
                for c, v in zip(chunks, vectors)
            )
            record.page_count = max((p.page_number for p in pages if p.page_number), default=None)
            record.chunk_count = len(chunks)
            record.status = "ready"
            record.processed_at = datetime.datetime.now(datetime.timezone.utc)
            await db.commit()
            logger.info("Processed %s: %d pages, %d chunks", file_id, len(pages), len(chunks))
        except Exception as e:
            await db.rollback()
            # The file may have been deleted while it was processing: nothing left to mark as failed.
            if await db.get(UploadedFile, file_id, populate_existing=True) is None:
                logger.info("File %s was deleted during processing; results discarded", file_id)
                return
            logger.exception("Processing failed for %s", file_id)
            try:
                record.status = "failed"
                record.error_message = str(e)
                await db.commit()
            except StaleDataError:
                # Deleted in the moment between that check and this commit.
                await db.rollback()
                logger.info("File %s was deleted during processing; results discarded", file_id)
