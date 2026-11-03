import asyncio
import logging
import time
import uuid

from langchain_core.messages import AIMessage
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import ModelPerformance
from src.db.session import SessionLocal

logger = logging.getLogger("uvicorn.error")

# The event loop only keeps weak references to tasks; hold them here until they finish.
_pending: set[asyncio.Task] = set()


class Timer:
    """`with Timer() as t: ...` then t.ms is the time taken, in milliseconds."""

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = elapsed_ms(self.start)


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def llm_usage(message: AIMessage) -> dict:
    """Token counts, Groq's own timings and the finish reason, as ModelPerformance fields."""
    usage = message.usage_metadata or {}
    raw = message.response_metadata.get("token_usage") or {}

    def ms(key: str) -> int | None:
        seconds = raw.get(key)
        return None if seconds is None else int(seconds * 1000)

    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": usage.get("output_token_details", {}).get("reasoning"),
        "llm_queue_ms": ms("queue_time"),
        "llm_prompt_ms": ms("prompt_time"),
        "llm_completion_ms": ms("completion_time"),
        "finish_reason": message.response_metadata.get("finish_reason"),
    }


def record(**fields) -> None:
    """Save one ModelPerformance row in the background.

    Returns at once and never raises: metrics must not slow down or break the work they measure.
    """
    task = asyncio.create_task(_save(fields))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _save(fields: dict) -> None:
    try:
        async with SessionLocal() as db:
            db.add(ModelPerformance(embedding_model=settings.embedding_model, **fields))
            await db.commit()
    except Exception:
        logger.exception("Could not save performance metrics")


async def recent_runs(
    db: AsyncSession, operation: str | None, file_id: uuid.UUID | None, limit: int
) -> list[ModelPerformance]:
    stmt = select(ModelPerformance).order_by(ModelPerformance.created_at.desc()).limit(limit)
    if operation:
        stmt = stmt.where(ModelPerformance.operation == operation)
    if file_id:
        stmt = stmt.where(ModelPerformance.file_id == file_id)
    return list((await db.scalars(stmt)).all())


def _rate(condition):
    """Share of rows where condition is true; rows where it is NULL are left out."""
    return func.avg(case((condition, 1.0), (~condition, 0.0)))


async def _aggregate(db: AsyncSession, operation: str, file_id: uuid.UUID | None, columns: dict) -> dict:
    m = ModelPerformance
    columns = {
        "runs": func.count(),
        "success_rate": _rate(m.success),
        "avg_total_ms": func.avg(m.total_ms),
        "p50_total_ms": func.percentile_cont(0.5).within_group(m.total_ms),
        "p95_total_ms": func.percentile_cont(0.95).within_group(m.total_ms),
    } | columns
    stmt = select(*(c.label(name) for name, c in columns.items())).where(m.operation == operation)
    if file_id:
        stmt = stmt.where(m.file_id == file_id)
    return dict((await db.execute(stmt)).one()._mapping)


async def query_summary(db: AsyncSession, file_id: uuid.UUID | None) -> dict:
    m = ModelPerformance
    return await _aggregate(db, "query", file_id, {
        "answer_found_rate": _rate(m.answer_found),
        "avg_embedding_ms": func.avg(m.embedding_ms),
        "avg_retrieval_ms": func.avg(m.retrieval_ms),
        "avg_generation_ms": func.avg(m.generation_ms),
        "avg_llm_queue_ms": func.avg(m.llm_queue_ms),
        "avg_input_tokens": func.avg(m.input_tokens),
        "avg_output_tokens": func.avg(m.output_tokens),
        "avg_reasoning_tokens": func.avg(m.reasoning_tokens),
        "avg_chunks_retrieved": func.avg(m.chunks_retrieved),
        "avg_top_similarity": func.avg(m.top_similarity),
        "truncated_answers": func.count().filter(m.finish_reason == "length"),
    })


async def ingestion_summary(db: AsyncSession, file_id: uuid.UUID | None) -> dict:
    m = ModelPerformance
    return await _aggregate(db, "ingestion", file_id, {
        "avg_extraction_ms": func.avg(m.extraction_ms),
        "avg_chunking_ms": func.avg(m.chunking_ms),
        "avg_embedding_ms": func.avg(m.embedding_ms),
        "avg_chunks_processed": func.avg(m.chunks_processed),
    })
