import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.deps import get_db
from src.schemas.query import QueryIn, QueryOut, Source
from src.services import file_service, generation, metrics, retrieval
from src.services.embeddings import embed_query

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryOut)
async def ask_question(file_id: uuid.UUID, query: QueryIn, db: AsyncSession = Depends(get_db)):
    record = await file_service.get_file_or_404(db, file_id)
    if record.status != "ready":
        raise HTTPException(409, f"File is not ready to query (status: {record.status})")

    start = time.perf_counter()
    stats = {
        "file_id": record.id,
        "operation": "query",
        "question": query.question,
        "llm_model": settings.llm_model,
        "top_k": settings.top_k,
    }
    try:
        with metrics.Timer() as t:
            vector = await asyncio.to_thread(embed_query, query.question)
        stats["embedding_ms"] = t.ms

        with metrics.Timer() as t:
            hits = await retrieval.search(db, record.id, vector)
        stats["retrieval_ms"] = t.ms

        # With no relevant chunks, answer() returns "not found" without calling the LLM.
        with metrics.Timer() as t:
            answer, message = await generation.answer(query.question, [chunk.content for chunk, _ in hits])
        stats["generation_ms"] = t.ms
    except Exception as e:
        metrics.record(**stats, success=False, error_message=str(e), total_ms=metrics.elapsed_ms(start))
        raise

    scores = [score for _, score in hits]
    metrics.record(
        **stats,
        **(metrics.llm_usage(message) if message else {}),
        success=True,
        total_ms=metrics.elapsed_ms(start),
        chunks_retrieved=len(hits),
        top_similarity=max(scores, default=None),
        avg_similarity=sum(scores) / len(scores) if scores else None,
        answer_found=answer != generation.NOT_FOUND,
    )

    return QueryOut(
        file_id=record.id,
        filename=record.original_filename,
        question=query.question,
        answer=answer,
        sources=[
            Source(number=i, chunk_index=chunk.chunk_index, score=round(score, 4), content=chunk.content)
            for i, (chunk, score) in enumerate(hits, start=1)
        ],
    )
