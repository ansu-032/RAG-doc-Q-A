import asyncio
import datetime
import time
import uuid

from sqlalchemy.orm.exc import StaleDataError

from src.db.models import DocumentChunk, UploadedFile
from src.db.session import SessionLocal
from src.logging_config import logger
from src.services import scheduler, storage
from src.services.chunking import split_pages
from src.services.embeddings import embed_passages
from src.services.extraction import extract_text



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
            logger.info("Processing skipped: file %s no longer exists", file_id)
            return

        start = time.perf_counter()
        marks: dict[str, int] = {}
        step = "start"

        def finish_step(name: str) -> None:
            marks[name] = int((time.perf_counter() - start) * 1000) - sum(marks.values())

        logger.info("Processing file %s: %d bytes, type=%s", file_id, record.size_bytes, record.mime_type)
        try:
            step = "set status"
            record.status = "processing"
            await db.commit()

            step = "download from storage"
            data = await asyncio.to_thread(storage.get_file, record.minio_object_key)
            finish_step("download_ms")
            step = "extract text"
            pages = await asyncio.to_thread(extract_text, data, record.mime_type)
            finish_step("extract_ms")
            step = "split into chunks"
            chunks = await asyncio.to_thread(split_pages, pages)
            finish_step("chunk_ms")
            if not chunks:
                logger.warning("File %s has no extractable text (a scanned PDF?): no chunks to search", file_id)
            step = "create embeddings"
            vectors = await asyncio.to_thread(embed_passages, [c.content for c in chunks])
            finish_step("embed_ms")

            step = "save chunks"
            db.add_all(
                DocumentChunk(
                    file_id=file_id,
                    chunk_index=c.chunk_index,
                    page_number=c.page_number,
                    content=c.content,
                    embedding=v,
                )
                for c, v in zip(chunks, vectors)
            )
            record.page_count = max((p.page_number for p in pages if p.page_number), default=None)
            record.chunk_count = len(chunks)
            record.status = "ready"
            record.processed_at = datetime.datetime.now(datetime.timezone.utc)
            await db.commit()
            finish_step("save_ms")
            logger.info(
                "Processed file %s: %d pages, %d chunks, total=%d ms, %s",
                file_id,
                len(pages),
                len(chunks),
                sum(marks.values()),
                " ".join(f"{name}={ms}" for name, ms in marks.items()),
            )
        except Exception as e:
            await db.rollback()
            # The file may have been deleted while it was processing: nothing left to mark as failed.
            if await db.get(UploadedFile, file_id, populate_existing=True) is None:
                logger.info("File %s was deleted during processing; results discarded", file_id)
                return
            logger.exception("Processing failed for file %s at step '%s'", file_id, step)
            try:
                record.status = "failed"
                record.error_message = str(e)
                await db.commit()
            except StaleDataError:
                # Deleted in the moment between that check and this commit.
                await db.rollback()
                logger.info("File %s was deleted during processing; results discarded", file_id)
