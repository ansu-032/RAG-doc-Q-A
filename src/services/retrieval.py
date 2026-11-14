import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import DocumentChunk, UploadedFile
from src.services.embeddings import embed_query


async def search(
    db: AsyncSession,
    question: str,
    file_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    file_ids: list[uuid.UUID] | None = None,
) -> list[tuple[DocumentChunk, float, str]]:
    """Chunks closest to the question, best first, with cosine similarity (0..1) and source filename."""
    vector = await asyncio.to_thread(embed_query, question)
    distance = DocumentChunk.embedding.cosine_distance(vector)
    stmt = (
        select(DocumentChunk, (1 - distance).label("score"), UploadedFile.original_filename)
        .join(UploadedFile, DocumentChunk.file_id == UploadedFile.id)
        .where(DocumentChunk.embedding.is_not(None), UploadedFile.status == "ready")
    )
    if file_id is not None:
        stmt = stmt.where(DocumentChunk.file_id == file_id).order_by(distance).limit(settings.top_k)
        rows = (await db.execute(stmt)).all()
        return [
            (chunk, float(score), filename)
            for chunk, score, filename in rows
            if score >= settings.min_score
        ]

    if file_ids:
        stmt = stmt.where(DocumentChunk.file_id.in_(file_ids))
    elif session_id is not None:
        stmt = stmt.where(UploadedFile.session_id == session_id)
    else:
        return []

    # For multi-document search:
    # Retrieve top candidates with an expanded limit and ensure balanced representation
    # across documents so relational queries capture evidence from all uploaded files.
    expanded_limit = max(settings.top_k * 3, 15)
    stmt = stmt.order_by(distance).limit(expanded_limit)
    rows = (await db.execute(stmt)).all()

    valid_hits = [
        (chunk, float(score), filename)
        for chunk, score, filename in rows
        if score >= settings.min_score
    ]
    if not valid_hits:
        return []

    # Balance hits across documents so relational concepts from both files are present
    by_file: dict[str, list[tuple[DocumentChunk, float, str]]] = {}
    for hit in valid_hits:
        by_file.setdefault(hit[2], []).append(hit)

    balanced_hits: list[tuple[DocumentChunk, float, str]] = []
    max_total = max(settings.top_k * 2, 8)

    # Take top chunks from each file to guarantee multi-document coverage
    for _fn, f_hits in by_file.items():
        balanced_hits.extend(f_hits[:3])

    # Fill remainder with highest scoring chunks
    included_ids = {h[0].id for h in balanced_hits}
    for hit in valid_hits:
        if hit[0].id not in included_ids and len(balanced_hits) < max_total:
            balanced_hits.append(hit)
            included_ids.add(hit[0].id)

    balanced_hits.sort(key=lambda x: x[1], reverse=True)
    return balanced_hits[:max_total]
