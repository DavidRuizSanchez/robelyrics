"""La cola de ingesta de YouTube guarda el nivel de confianza de cada vídeo.

El detector ya no solo vigila dos canales: busca en YouTube y clasifica cada
resultado con `corpus_trust` (A voz, B medio, C fan). La fila guarda POR QUÉ:
nivel, voces nombradas, motivos, canal real y duración, y cómo se encontró. Sin
eso, el correo y el panel no podrían enseñar el motivo de una entrada automática
ni se podría medir si el criterio acierta.

- `kind` admite `entorno_interview` (habla un miembro o un amigo: fuente propia
  que NO se cita) y `media_report` (reportaje de un medio: fondo).
- `status` admite `retired`: lo que se retira no se vuelve a detectar.

Revision ID: corpus2026_01
Revises: ampliar2026_01
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "corpus2026_01"
down_revision: str | None = "ampliar2026_01"
branch_labels = None
depends_on = None

T = "youtube_ingest_queue"


def upgrade() -> None:
    op.add_column(T, sa.Column("channel_id", sa.String(64)))
    op.add_column(T, sa.Column("nivel", sa.String(16)))
    op.add_column(T, sa.Column("voces", postgresql.ARRAY(sa.String(120))))
    op.add_column(T, sa.Column("motivos", postgresql.JSONB))
    op.add_column(T, sa.Column("descubierto_por", sa.String(16)))
    op.add_column(T, sa.Column("duration_s", sa.Float))
    op.drop_constraint("ck_youtube_ingest_kind", T, type_="check")
    op.create_check_constraint(
        "ck_youtube_ingest_kind", T,
        "kind IN ('youtube_transcript', 'robe_interview', 'about_robe', "
        "'entorno_interview', 'media_report')",
    )
    op.drop_constraint("ck_youtube_ingest_status", T, type_="check")
    op.create_check_constraint(
        "ck_youtube_ingest_status", T,
        "status IN ('detected', 'approved', 'processing', 'done', 'failed', 'retired')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_youtube_ingest_status", T, type_="check")
    op.create_check_constraint(
        "ck_youtube_ingest_status", T,
        "status IN ('detected', 'approved', 'processing', 'done', 'failed')",
    )
    op.drop_constraint("ck_youtube_ingest_kind", T, type_="check")
    op.create_check_constraint(
        "ck_youtube_ingest_kind", T,
        "kind IN ('youtube_transcript', 'robe_interview', 'about_robe')",
    )
    for col in ("duration_s", "descubierto_por", "motivos", "voces", "nivel", "channel_id"):
        op.drop_column(T, col)
