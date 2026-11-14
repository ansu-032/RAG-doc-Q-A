"""create uploaded_files, document_chunks and model_performance

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 384
UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    # SQLAlchemy has no construct for extensions; this is the one raw statement.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "uploaded_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_DEFAULT, primary_key=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("file_extension", sa.Text()),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("minio_bucket", sa.Text(), nullable=False),
        sa.Column("minio_object_key", sa.Text(), nullable=False),
        sa.Column("minio_etag", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "ready", "failed", name="file_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("minio_bucket", "minio_object_key"),
    )
    op.create_index("uploaded_files_checksum_idx", "uploaded_files", ["sha256_checksum"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_DEFAULT, primary_key=True),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("file_id", "chunk_index"),
    )
    op.create_index("document_chunks_file_id_idx", "document_chunks", ["file_id"])
    op.create_index(
        "document_chunks_embedding_idx",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "model_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_DEFAULT, primary_key=True),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        ),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text()),
        sa.Column("chunk_size", sa.Integer()),
        sa.Column("chunk_overlap", sa.Integer()),
        sa.Column("top_k", sa.Integer()),
        sa.Column("question", sa.Text()),
        sa.Column("extraction_ms", sa.Integer()),
        sa.Column("chunking_ms", sa.Integer()),
        sa.Column("embedding_ms", sa.Integer()),
        sa.Column("retrieval_ms", sa.Integer()),
        sa.Column("generation_ms", sa.Integer()),
        sa.Column("total_ms", sa.Integer(), nullable=False),
        sa.Column("chunks_processed", sa.Integer()),
        sa.Column("chunks_retrieved", sa.Integer()),
        sa.Column("top_similarity", sa.REAL()),
        sa.Column("avg_similarity", sa.REAL()),
        sa.Column("answer_found", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("operation IN ('ingestion', 'query')", name="model_performance_operation_check"),
    )
    op.create_index("model_performance_file_id_idx", "model_performance", ["file_id"])
    op.create_index("model_performance_created_at_idx", "model_performance", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_table("model_performance")
    op.drop_table("document_chunks")
    op.drop_table("uploaded_files")
    sa.Enum(name="file_status").drop(op.get_bind(), checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS vector")
