"""Lo que hace falta para clips de CONCIERTO: de qué bolo es, y dónde hay música.

La descripción de YouTube se descargaba y se tiraba, y es donde los canales de
archivo escriben cuándo y dónde fue el bolo. Sin ella no hay forma de que un
post diga «La Cubierta, Leganés, 22/06/2002» sin inventárselo.

Revision ID: igdirecto2026_01
Revises: igclips2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "igdirecto2026_01"
down_revision: str | None = "igclips2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_assets", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("video_assets", sa.Column("event_date", sa.Date(), nullable=True))
    op.add_column("video_assets", sa.Column("event_place", sa.String(length=200), nullable=True))
    op.add_column("video_assets", sa.Column("event_source", sa.String(length=16), nullable=True))

    # Whisper las devuelve en cada segmento y se tiraban. `no_speech_prob` alto
    # es un tramo sin voz: en un concierto, eso es el solo o el instrumental.
    op.add_column("source_segments", sa.Column("no_speech_prob", sa.Float(), nullable=True))
    op.add_column("source_segments", sa.Column("avg_logprob", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_segments", "avg_logprob")
    op.drop_column("source_segments", "no_speech_prob")
    op.drop_column("video_assets", "event_source")
    op.drop_column("video_assets", "event_place")
    op.drop_column("video_assets", "event_date")
    op.drop_column("video_assets", "description")
