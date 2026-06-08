"""Motor de contenido RAG profundo: KW objetivo + secundarias + outline +
cobertura de fuentes en SeoContent.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-08 22:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("seo_content", sa.Column("target_keyword", sa.String(length=160), nullable=True))
    op.add_column(
        "seo_content",
        sa.Column("secondary_keywords", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "seo_content",
        sa.Column("outline", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("seo_content", sa.Column("sources_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("seo_content", "sources_count")
    op.drop_column("seo_content", "outline")
    op.drop_column("seo_content", "secondary_keywords")
    op.drop_column("seo_content", "target_keyword")
