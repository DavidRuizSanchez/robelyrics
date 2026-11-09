"""`instagram_queue.notas_internas`: lo interno sale del texto publicable.

En los clips, `summary` era entero notas del selector («Tramo 45-57s…»,
«Motivos:…», «Corte:…», la transcripción del tramo, «Verificado:…», «AVISO:…»),
y cuatro caminos de respaldo lo publicaban. Se mueve tal cual a su columna y el
`summary` de los clips queda vacío.

Revision ID: iggate2026_01
Revises: corpus2026_03
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "iggate2026_01"
down_revision: str | None = "corpus2026_03"
branch_labels = None
depends_on = None

T = "instagram_queue"


def upgrade() -> None:
    op.add_column(T, sa.Column("notas_internas", sa.Text(), nullable=True))
    op.execute(
        f"UPDATE {T} SET notas_internas = summary, summary = NULL "
        "WHERE content_type = 'clip' AND summary IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE {T} SET summary = notas_internas "
        "WHERE content_type = 'clip' AND notas_internas IS NOT NULL"
    )
    op.drop_column(T, "notas_internas")
