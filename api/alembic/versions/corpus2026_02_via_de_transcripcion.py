"""La cola de ingesta apunta cómo se transcribió cada vídeo.

Fase 3 del corpus: subtítulos de YouTube (gratis) antes que Whisper, y un tope
de 15 $ al mes. El gasto se deduce de la cola —lo que está en `done` con
`via='whisper'` este mes, por su `duration_s`—, así que hace falta saber por
dónde fue cada uno. NULL en lo anterior: todo aquello iba por Whisper, pero no
se cuenta para el mes porque su duración tampoco se guardaba.

Revision ID: corpus2026_02
Revises: corpus2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "corpus2026_02"
down_revision: str | None = "corpus2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("youtube_ingest_queue", sa.Column("via", sa.String(16)))
    op.execute("UPDATE youtube_ingest_queue SET via = 'whisper' WHERE status = 'done'")


def downgrade() -> None:
    op.drop_column("youtube_ingest_queue", "via")
