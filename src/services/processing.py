import asyncio
import datetime
import logging
import time
import uuid

from src.config import settings
from src.db.models import DocumentChunk, UploadedFile
from src.db.session import SessionLocal
from src.services import metrics, storage
from src.services.chunking import split_pages
from src.services.embeddings import embed_passages
from src.services.extraction import extract_text

logger = logging.getLogger("uvicorn.error")


async def process_file(file_id: uuid.UUID) -> None:
    """Background task run after upload: file in MinIO -> text -> chunks -> embeddings.

    Uses its own DB session, because the request's session is closed by the time this runs.
    """
    async with SessionLocal() as db:
        record = await db.get(UploadedFile, file_id)
        if record is None:
            return
        start = time.perf_counter()
        stats = {
            "file_id": file_id,
            "operation": "ingestion",
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
        }
        try:
            record.status = "processing"
            await db.commit()

            data = await asyncio.to_thread(storage.get_file, record.minio_object_key)
            with metrics.Timer() as t:
                pages = await asyncio.to_thread(extract_text, data, record.mime_type)
            stats["extraction_ms"] = t.ms
            with metrics.Timer() as t:
                chunks = await asyncio.to_thread(split_pages, pages)
            stats["chunking_ms"] = t.ms
            with metrics.Timer() as t:
                vectors = await asyncio.to_thread(embed_passages, [c.content for c in chunks])
            stats["embedding_ms"] = t.ms

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
            metrics.record(
                **stats, success=True, total_ms=metrics.elapsed_ms(start), chunks_processed=len(chunks)
            )
        except Exception as e:
            await db.rollback()
            record.status = "failed"
            record.error_message = str(e)
            await db.commit()
            logger.exception("Processing failed for %s", file_id)
            metrics.record(**stats, success=False, error_message=str(e), total_ms=metrics.elapsed_ms(start))
