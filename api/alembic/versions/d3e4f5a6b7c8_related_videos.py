"""Vídeos relacionados anclados a entidades (colaboraciones, entrevistas,
vídeos oficiales). Distinto del vídeo canónico de canción (Song.youtube_id):
estos cuelgan de personas, artistas, grupos o canciones vía una tabla join.

Tablas:
  - related_videos: el vídeo en sí (youtube_id único, título, tipo, fecha).
  - related_video_entities: relación N:M vídeo ↔ entidad (por type+slug, sin FK
    a las tablas de entidad para no acoplar y poder anclar a cualquier tipo).

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2026-06-03 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "related_videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("youtube_id", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),  # collaboration|interview|official|live
        sa.Column("upload_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "related_video_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "video_id",
            sa.Integer(),
            sa.ForeignKey("related_videos.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity_type", sa.String(16), nullable=False),  # person|artist|band|song
        sa.Column("entity_slug", sa.String(160), nullable=False),
    )
    op.create_index(
        "ix_related_video_entities_type_slug",
        "related_video_entities",
        ["entity_type", "entity_slug"],
    )
    op.create_unique_constraint(
        "uq_related_video_entity",
        "related_video_entities",
        ["video_id", "entity_type", "entity_slug"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_related_video_entity", "related_video_entities", type_="unique"
    )
    op.drop_index(
        "ix_related_video_entities_type_slug", table_name="related_video_entities"
    )
    op.drop_table("related_video_entities")
    op.drop_table("related_videos")
