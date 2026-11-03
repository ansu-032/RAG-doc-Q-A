import datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    REAL,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Must match the output size of the embedding model (BAAI/bge-small-en-v1.5).
EMBEDDING_DIM = 384

FILE_STATUSES = ("pending", "processing", "ready", "failed")


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class UploadedFile(Base):
    """An uploaded file: its details and where it lives in MinIO."""

    __tablename__ = "uploaded_files"
    __table_args__ = (
        UniqueConstraint("minio_bucket", "minio_object_key"),
        Index("uploaded_files_checksum_idx", "sha256_checksum"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    original_filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    file_extension: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256_checksum: Mapped[str] = mapped_column(String(64))
    minio_bucket: Mapped[str] = mapped_column(Text)
    minio_object_key: Mapped[str] = mapped_column(Text)
    minio_etag: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        Enum(*FILE_STATUSES, name="file_status"),
        default="pending",
        server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(Base):
    """A piece of a file's text plus its embedding; deleted together with the file."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("file_id", "chunk_index"),
        Index("document_chunks_file_id_idx", "file_id"),
        Index(
            "document_chunks_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # NULL until the embedding step fills it in.
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    file: Mapped[UploadedFile] = relationship(back_populates="chunks")


class ModelPerformance(Base):
    """One row per ingestion run or question: timings, counts and scores."""

    __tablename__ = "model_performance"
    __table_args__ = (
        CheckConstraint("operation IN ('ingestion', 'query')", name="model_performance_operation_check"),
        Index("model_performance_file_id_idx", "file_id"),
        Index("model_performance_created_at_idx", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # SET NULL keeps the history after a file is deleted (and allows cross-file questions).
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="SET NULL")
    )
    operation: Mapped[str] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)

    embedding_model: Mapped[str] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    chunk_overlap: Mapped[int | None] = mapped_column(Integer)
    top_k: Mapped[int | None] = mapped_column(Integer)
    question: Mapped[str | None] = mapped_column(Text)

    # time taken, in milliseconds
    extraction_ms: Mapped[int | None] = mapped_column(Integer)
    chunking_ms: Mapped[int | None] = mapped_column(Integer)
    embedding_ms: Mapped[int | None] = mapped_column(Integer)
    retrieval_ms: Mapped[int | None] = mapped_column(Integer)
    generation_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int] = mapped_column(Integer)

    chunks_processed: Mapped[int | None] = mapped_column(Integer)
    chunks_retrieved: Mapped[int | None] = mapped_column(Integer)
    top_similarity: Mapped[float | None] = mapped_column(REAL)
    avg_similarity: Mapped[float | None] = mapped_column(REAL)
    answer_found: Mapped[bool | None] = mapped_column(Boolean)

    # From the LLM reply; the *_ms timings are measured on Groq's servers.
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_queue_ms: Mapped[int | None] = mapped_column(Integer)
    llm_prompt_ms: Mapped[int | None] = mapped_column(Integer)
    llm_completion_ms: Mapped[int | None] = mapped_column(Integer)
    # "length" means the answer was cut off.
    finish_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
