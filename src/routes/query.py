import time
import uuid
from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db, get_session_id
from src.logging_config import logger
from src.schemas.query import QueryIn, QueryOut, Source, WebSource
from src.services import (
    file_service,
    general,
    generation,
    rate_limit,
    retrieval,
    router as question_router,
    scheduler,
)
from src.services.sessions import short_id

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryOut, dependencies=[Depends(rate_limit.limit_queries)])
async def ask_question(
    query: QueryIn,
    file_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    session_id: uuid.UUID | None = Depends(get_session_id),
):
    start = time.perf_counter()
    elapsed_ms = lambda: int((time.perf_counter() - start) * 1000)
    await scheduler.touch(session_id)

    record = None
    files_searched: list[str] = []
    if file_id is not None:
        record = await file_service.get_file_or_404(db, file_id, session_id)
        if record.status != "ready":
            logger.warning("Question rejected: file %s is %s", file_id, record.status)
            raise HTTPException(409, f"File is not ready to query (status: {record.status})")
        context_name = record.original_filename
        files_searched = [record.original_filename]
        logger.info(
            "Question on file %s (%s): session=%s chars=%d history=%d",
            file_id,
            record.original_filename,
            short_id(session_id),
            len(query.question),
            len(query.history),
        )
    else:
        # Cross-document query across all ready files in this session
        all_files = await file_service.list_files(db, session_id) if session_id else []
        ready_files = [f for f in all_files if f.status == "ready"]
        if not ready_files:
            if all_files:
                raise HTTPException(409, "Documents are still being processed. Please wait.")
            raise HTTPException(400, "No documents available in this session to query.")
        files_searched = [f.original_filename for f in ready_files]
        context_name = ", ".join(files_searched)
        logger.info(
            "Question across %d file(s) in session %s: chars=%d history=%d",
            len(ready_files),
            short_id(session_id),
            len(query.question),
            len(query.history),
        )

    logger.debug("Question text: %r", query.question)

    # An LLM reads the question first: where it should go, and what it really asks.
    decision = await question_router.route(query.question, context_name, query.history)
    question = decision.rewritten_question
    logger.info("Routed: route=%s needs_web=%s (%d ms)", decision.route, decision.needs_web, elapsed_ms())
    logger.debug("Rewritten question: %r", question)
    respond = partial(
        QueryOut,
        file_id=record.id if record else None,
        filename=record.original_filename if record else "All Documents",
        files_searched=files_searched,
        question=query.question,
        route=decision.route,
        rewritten_question=question,
    )

    # Specific and broad questions: search the document(s) with the rewritten question.
    if decision.route != "general":
        hits = await retrieval.search(
            db, question, file_id=record.id if record else None, session_id=session_id
        )
        logger.info(
            "Retrieved %d relevant chunk(s), top_score=%s (%d ms)",
            len(hits),
            round(hits[0][1], 3) if hits else None,
            elapsed_ms(),
        )
        # Formulate grounded context passages with document name and page number
        passages = [
            f"(Document: {filename}, Page: {chunk.page_number or 'N/A'})\n{chunk.content}"
            for chunk, _score, filename in hits
        ]
        # With no relevant chunks, answer() returns "not found" without calling the LLM.
        answer = await generation.answer(question, passages)
        if answer != generation.NOT_FOUND:
            logger.info("Answered from document(s), %d source(s) (total %d ms)", len(hits), elapsed_ms())
            return respond(
                answer_source="document",
                answer=answer,
                sources=[
                    Source(
                        number=i,
                        chunk_index=chunk.chunk_index,
                        score=round(score, 4),
                        content=chunk.content,
                        file_id=chunk.file_id,
                        filename=filename,
                        page_number=chunk.page_number,
                    )
                    for i, (chunk, score, filename) in enumerate(hits, start=1)
                ],
                web_sources=[],
            )
        logger.info("Documents have no answer: falling back to the general model")

    # Not about the documents, or the documents have no answer: the general model answers,
    # with a web search first only if the router said the question needs recent data.
    fallback = await general.answer(question, decision.needs_web)
    logger.info(
        "Answered by general model: source=%s web_sources=%d (total %d ms)",
        fallback.source,
        len(fallback.web_sources),
        elapsed_ms(),
    )
    return respond(
        answer_source=fallback.source,
        answer=fallback.text,
        sources=[],
        web_sources=[WebSource(title=title, url=url) for title, url in fallback.web_sources],
    )
