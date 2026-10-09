"""Qué gate retuvo la pieza, para retirarla si la vuelve a frenar.

Una pieza que un gate frena volvía a la cola de revisión, se reprogramaba, la
volvía a frenar el mismo gate a las 08:15 y llegaba otra vez en el correo, en
bucle (09-10-2026: cuatro posts, uno desde el 3 de septiembre). Criterio de
David: si se puede publicar, que se publique; si no, que desaparezca. Con el
nombre del gate guardado, el segundo frenazo del MISMO gate sin que nadie haya
tocado el cuerpo la retira (`rejected`), sin borrar nada.

Revision ID: revblockby2026_01
Revises: revblock2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "revblockby2026_01"
down_revision: str | None = "revblock2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("review_blocked_by", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "review_blocked_by")
