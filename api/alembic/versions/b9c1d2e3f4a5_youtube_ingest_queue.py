"""Tabla youtube_ingest_queue.

Cola de ingesta de vídeos de YouTube (Juancares + entrevistas de Robe) con la
arquitectura "1 click → autónomo": el server DETECTA uploads nuevos y encola en
`detected`; el admin aprueba el batch con un click (email firmado) → `approved`;
un daemon local en la Mac transcribe (IP residencial) y empuja a prod → `done`.

Revision ID: b9c1d2e3f4a5
Revises: e1f2a3b4c5d6
Create Date: 2026-06-24 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9c1d2e3f4a5"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "youtube_ingest_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("channel", sa.String(length=120), nullable=True),
        sa.Column(
            "target", sa.String(length=16), nullable=False, server_default="corpus"
        ),
        sa.Column(
            "kind",
            sa.String(length=24),
            nullable=False,
            server_default="youtube_transcript",
        ),
        sa.Column("author", sa.String(length=120), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="detected"
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('detected', 'approved', 'processing', 'done', 'failed')",
            name="ck_youtube_ingest_status",
        ),
        sa.CheckConstraint(
            "target IN ('corpus', 'robe_voice')",
            name="ck_youtube_ingest_target",
        ),
        sa.CheckConstraint(
            "kind IN ('youtube_transcript', 'robe_interview', 'about_robe')",
            name="ck_youtube_ingest_kind",
        ),
        sa.UniqueConstraint(
            "video_id", "target", name="uq_youtube_ingest_video_target"
        ),
    )
    op.create_index(
        "ix_youtube_ingest_queue_video_id", "youtube_ingest_queue", ["video_id"]
    )
    op.create_index(
        "ix_youtube_ingest_queue_status", "youtube_ingest_queue", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_youtube_ingest_queue_status", table_name="youtube_ingest_queue")
    op.drop_index(
        "ix_youtube_ingest_queue_video_id", table_name="youtube_ingest_queue"
    )
    op.drop_table("youtube_ingest_queue")
