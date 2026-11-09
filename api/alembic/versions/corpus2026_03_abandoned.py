"""La cola de ingesta admite `abandoned`: lo que no se puede transcribir.

Un vídeo con restricción de edad, sin habla, privado o borrado agotaba sus tres
intentos y se quedaba para siempre en «Fallidos», mezclado con lo que sí se
arregla reintentando. `abandoned` lo saca de ahí con su motivo; «Reintentar» lo
devuelve a la cola si algo cambia.

Revision ID: corpus2026_03
Revises: monitor2026_01
"""
from __future__ import annotations

from alembic import op

revision: str = "corpus2026_03"
down_revision: str | None = "monitor2026_01"
branch_labels = None
depends_on = None

T = "youtube_ingest_queue"


def upgrade() -> None:
    op.drop_constraint("ck_youtube_ingest_status", T, type_="check")
    op.create_check_constraint(
        "ck_youtube_ingest_status", T,
        "status IN ('detected', 'approved', 'processing', 'done', 'failed', 'retired', "
        "'abandoned')",
    )


def downgrade() -> None:
    op.execute(f"UPDATE {T} SET status = 'failed' WHERE status = 'abandoned'")
    op.drop_constraint("ck_youtube_ingest_status", T, type_="check")
    op.create_check_constraint(
        "ck_youtube_ingest_status", T,
        "status IN ('detected', 'approved', 'processing', 'done', 'failed', 'retired')",
    )
