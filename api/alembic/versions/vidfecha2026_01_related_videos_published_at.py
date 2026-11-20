"""`related_videos.published_at`: la fecha de subida con su hora y su zona.

GSC (20-11-2026): «Falta el campo uploadDate» en 2 vídeos y «falta la zona horaria» /
«valor no válido» en 18. `upload_date` es `Date` y se servía «2018-11-15». La hora
real sale de `snippet.publishedAt` de la YouTube Data API
(`scripts.seo.backfill_video_dates`); no se completa con una medianoche inventada, así
que `upload_date` se queda como estaba y la columna nueva es aparte.

Revision ID: vidfecha2026_01
Revises: blogjuez2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "vidfecha2026_01"
down_revision: str | None = "blogjuez2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("related_videos", sa.Column("published_at", sa.DateTime(timezone=True),
                                              nullable=True))


def downgrade() -> None:
    op.drop_column("related_videos", "published_at")
