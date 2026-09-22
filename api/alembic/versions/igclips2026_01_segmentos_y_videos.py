"""Segmentos con tiempo de las transcripciones + catálogo de vídeo elegible.

Las dos tablas que hacían falta para que el sistema elija solo el vídeo y el
tramo de un clip, que es lo único que seguía haciéndose a mano:

  · `source_segments`: los `start`/`end` que Whisper ya devolvía y que se
    tiraban al aplanar la transcripción a texto corrido.
  · `video_assets`: de qué vídeos se puede sacar un clip, con el canal real ya
    resuelto y el veto aplicado ANTES de descargar nada.

Revision ID: igclips2026_01
Revises: igtrust2026_01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "igclips2026_01"
down_revision: str | None = "igtrust2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("start_s", sa.Float(), nullable=False),
        sa.Column("end_s", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["interpretation_sources.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "idx", name="uq_source_segments_source_idx"),
        sa.CheckConstraint("end_s >= start_s", name="ck_source_segments_tramo"),
    )
    op.create_index(
        "ix_source_segments_source_id", "source_segments", ["source_id"]
    )

    op.create_table(
        "video_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("youtube_id", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("channel_title", sa.String(length=200), nullable=True),
        sa.Column("channel_url", sa.String(length=500), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False,
                  server_default="interview"),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("vetado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("motivo_veto", sa.String(length=200), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["interpretation_sources.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("youtube_id", name="uq_video_assets_youtube_id"),
        sa.CheckConstraint("kind IN ('interview','live_fan')",
                           name="ck_video_assets_kind"),
    )
    op.create_index("ix_video_assets_youtube_id", "video_assets", ["youtube_id"])


def downgrade() -> None:
    op.drop_index("ix_video_assets_youtube_id", table_name="video_assets")
    op.drop_table("video_assets")
    op.drop_index("ix_source_segments_source_id", table_name="source_segments")
    op.drop_table("source_segments")
