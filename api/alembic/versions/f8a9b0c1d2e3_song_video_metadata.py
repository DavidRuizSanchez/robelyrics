"""Metadatos de vídeo en songs (para VideoObject schema.org).

Añade `youtube_title` y `youtube_published_at`. La duración ya existe
(`duration_sec`). Los rellena `match_youtube --enrich` vía YouTube Data API.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-01 15:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("songs", sa.Column("youtube_title", sa.String(length=300), nullable=True))
    op.add_column(
        "songs",
        sa.Column("youtube_published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("songs", sa.Column("youtube_duration_sec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("songs", "youtube_duration_sec")
    op.drop_column("songs", "youtube_published_at")
    op.drop_column("songs", "youtube_title")
