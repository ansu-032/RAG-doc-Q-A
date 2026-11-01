import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import DocumentChunk
from src.services.embeddings import embed_query


async def search(
    db: AsyncSession, file_id: uuid.UUID, question: str
) -> list[tuple[DocumentChunk, float]]:
    """The file's chunks closest to the question, best first, with cosine similarity (0..1)."""
    vector = await asyncio.to_thread(embed_query, question)
    distance = DocumentChunk.embedding.cosine_distance(vector)
    stmt = (
        select(DocumentChunk, (1 - distance).label("score"))
        .where(DocumentChunk.file_id == file_id, DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(settings.top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [(chunk, score) for chunk, score in rows if score >= settings.min_score]
