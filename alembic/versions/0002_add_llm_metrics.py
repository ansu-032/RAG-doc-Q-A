"""add LLM token counts, Groq timings and finish reason to model_performance

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = [
    ("input_tokens", sa.Integer()),
    ("output_tokens", sa.Integer()),
    ("reasoning_tokens", sa.Integer()),
    ("llm_queue_ms", sa.Integer()),
    ("llm_prompt_ms", sa.Integer()),
    ("llm_completion_ms", sa.Integer()),
    ("finish_reason", sa.Text()),
]


def upgrade() -> None:
    for name, type_ in NEW_COLUMNS:
        op.add_column("model_performance", sa.Column(name, type_))


def downgrade() -> None:
    for name, _ in reversed(NEW_COLUMNS):
        op.drop_column("model_performance", name)
