import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db
from src.schemas.query import QueryIn, QueryOut, Source
from src.services import file_service, generation, retrieval

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryOut)
async def ask_question(file_id: uuid.UUID, query: QueryIn, db: AsyncSession = Depends(get_db)):
    record = await file_service.get_file_or_404(db, file_id)
    if record.status != "ready":
        raise HTTPException(409, f"File is not ready to query (status: {record.status})")

    hits = await retrieval.search(db, record.id, query.question)
    # With no relevant chunks, answer() returns "not found" without calling the LLM.
    answer = await generation.answer(query.question, [chunk.content for chunk, _ in hits])

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
