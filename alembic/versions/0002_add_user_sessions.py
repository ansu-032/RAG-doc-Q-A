"""add user_sessions and tie each uploaded file to a session

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("user_sessions_last_activity_idx", "user_sessions", ["last_activity_at"])

    op.add_column("uploaded_files", sa.Column("session_id", postgresql.UUID(as_uuid=True)))
    # Files from before sessions have no owner: put them in one session nobody holds a cookie
    # for. The scheduler then deletes them once idle, including their objects in MinIO, which
    # deleting the rows here would leave behind.
    op.execute(
        """
        WITH legacy AS (
            INSERT INTO user_sessions (id)
            SELECT gen_random_uuid() WHERE EXISTS (SELECT 1 FROM uploaded_files)
            RETURNING id
        )
        UPDATE uploaded_files SET session_id = (SELECT id FROM legacy)
        """
    )
    op.alter_column("uploaded_files", "session_id", nullable=False)
    op.create_foreign_key(
        "uploaded_files_session_id_fkey", "uploaded_files", "user_sessions", ["session_id"], ["id"]
    )
    op.create_index("uploaded_files_session_id_idx", "uploaded_files", ["session_id"])


def downgrade() -> None:
    op.drop_index("uploaded_files_session_id_idx", table_name="uploaded_files")
    op.drop_constraint("uploaded_files_session_id_fkey", "uploaded_files", type_="foreignkey")
    op.drop_column("uploaded_files", "session_id")
    op.drop_table("user_sessions")
