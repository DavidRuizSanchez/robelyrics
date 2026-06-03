"""Listas de reproducción manuales (playlists, playlist_items) en la zona
privada. Las listas por estado de ánimo se generan al vuelo (embeddings) y no
se persisten.

Revision ID: a1b2c3d4e5f6
Revises: f4a6b8c0d2e1
Create Date: 2026-06-03 18:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f4a6b8c0d2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "playlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "playlist_id",
            sa.Integer(),
            sa.ForeignKey("playlists.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "song_id",
            sa.Integer(),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),
    )


def downgrade() -> None:
    op.drop_table("playlist_items")
    op.drop_table("playlists")
