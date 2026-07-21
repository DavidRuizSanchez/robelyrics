"""blog_media_alt_videos_engagement

Revision ID: bc546b48786d
Revises: a9f1b2c3d4e5
Create Date: 2026-07-21 13:18:34.271726

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bc546b48786d'
down_revision: str | None = 'a9f1b2c3d4e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Multimedia (WS A): ALT descriptivo del hero + lista de vídeos (varios en
    # posts premium). Se conserva `video` (un objeto) por compatibilidad.
    # Engagement (WS B): score 0-100 y tier que modula profundidad/extensión.
    for table in ("posts", "content_proposals"):
        op.add_column(table, sa.Column("hero_image_alt", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("videos", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        op.add_column(table, sa.Column("engagement_score", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("quality_tier", sa.String(length=16), nullable=True))


def downgrade() -> None:
    for table in ("posts", "content_proposals"):
        for col in ("quality_tier", "engagement_score", "videos", "hero_image_alt"):
            op.drop_column(table, col)
