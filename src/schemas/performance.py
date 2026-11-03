import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class PerformanceRunOut(BaseModel):
    """One row of the model_performance table: an ingestion run or a question."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_id: uuid.UUID | None
    operation: str
    success: bool
    error_message: str | None
    embedding_model: str
    llm_model: str | None
    chunk_size: int | None
    chunk_overlap: int | None
    top_k: int | None
    question: str | None
    extraction_ms: int | None
    chunking_ms: int | None
    embedding_ms: int | None
    retrieval_ms: int | None
    generation_ms: int | None
    total_ms: int
    chunks_processed: int | None
    chunks_retrieved: int | None
    top_similarity: float | None
    avg_similarity: float | None
    answer_found: bool | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    llm_queue_ms: int | None
    llm_prompt_ms: int | None
    llm_completion_ms: int | None
    finish_reason: str | None
    created_at: datetime.datetime


class QuerySummary(BaseModel):
    """Averages over questions; rates are 0..1 and null when there are no runs."""

    runs: int
    success_rate: float | None
    answer_found_rate: float | None
    avg_total_ms: float | None
    p50_total_ms: float | None
    p95_total_ms: float | None
    avg_embedding_ms: float | None
    avg_retrieval_ms: float | None
    avg_generation_ms: float | None
    avg_llm_queue_ms: float | None
    avg_input_tokens: float | None
    avg_output_tokens: float | None
    avg_reasoning_tokens: float | None
    avg_chunks_retrieved: float | None
    avg_top_similarity: float | None
    truncated_answers: int


class IngestionSummary(BaseModel):
    """Averages over file processing runs."""

    runs: int
    success_rate: float | None
    avg_total_ms: float | None
    p50_total_ms: float | None
    p95_total_ms: float | None
    avg_extraction_ms: float | None
    avg_chunking_ms: float | None
    avg_embedding_ms: float | None
    avg_chunks_processed: float | None


class PerformanceSummary(BaseModel):
    query: QuerySummary
    ingestion: IngestionSummary
