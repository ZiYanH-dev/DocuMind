"""修改 embedding 向量维度：1536 → 768

Revision ID: 0002_alter_embedding_dim
Revises: 0001_initial_migration
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_alter_embedding_dim"
down_revision: str = "0001_initial_migration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """将 document_chunks.embedding 从 Vector(1536) 改为 Vector(768)。"""
    # pgvector 不支持 ALTER COLUMN 修改维度，需要重建列
    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(768) "
        "USING embedding::vector(768)"
    )


def downgrade() -> None:
    """回滚：将维度改回 1536。"""
    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
