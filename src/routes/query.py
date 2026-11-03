import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db
from src.schemas.query import QueryIn, QueryOut, Source, WebSource
from src.services import file_service, general, generation, retrieval

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryOut)
async def ask_question(file_id: uuid.UUID, query: QueryIn, db: AsyncSession = Depends(get_db)):
    record = await file_service.get_file_or_404(db, file_id)
    if record.status != "ready":
        raise HTTPException(409, f"File is not ready to query (status: {record.status})")

    hits = await retrieval.search(db, record.id, query.question)
    # With no relevant chunks, answer() returns "not found" without calling the LLM.
    answer = await generation.answer(query.question, [chunk.content for chunk, _ in hits])

    if answer != generation.NOT_FOUND:
        return QueryOut(
            file_id=record.id,
            filename=record.original_filename,
            question=query.question,
            answer_source="document",
            answer=answer,
            sources=[
                Source(number=i, chunk_index=chunk.chunk_index, score=round(score, 4), content=chunk.content)
                for i, (chunk, score) in enumerate(hits, start=1)
            ],
            web_sources=[],
        )

    # The document has no answer: the general model answers, searching the web only if it decides to.
    fallback = await general.answer(query.question)
    return QueryOut(
        file_id=record.id,
        filename=record.original_filename,
        question=query.question,
        answer_source=fallback.source,
        answer=fallback.text,
        sources=[],
        web_sources=[WebSource(title=title, url=url) for title, url in fallback.web_sources],
    )
