"""Por qué está retenida una pieza, escrito donde se pueda leer.

El correo de revisión trae un botón «aprobar» que llama al tronco de publicación.
Si un gate retiene la pieza, ese botón no puede funcionar NUNCA: vuelve a dar con
el mismo gate. Y hasta ahora el motivo solo existía en el log del contenedor, así
que ni el correo ni el panel podían decir qué corregir — la pantalla de error
culpaba siempre al guard de citas, que el 24-09-2026 resultó no tener nada que ver.

Con estas dos columnas el correo marca la pieza retenida, enseña el motivo y
cambia «aprobar» por «corregir». Se limpian al editar el cuerpo.

Revision ID: revblock2026_01
Revises: igrotulo2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "revblock2026_01"
down_revision: str | None = "igrotulo2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ambas NULL y sin server_default: ADD COLUMN instantáneo, sin reescribir la
    # tabla ni bloquearla.
    op.add_column(
        "posts",
        sa.Column("review_blocked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "posts", sa.Column("review_blocked_reason", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("posts", "review_blocked_reason")
    op.drop_column("posts", "review_blocked_at")
