"""ContentProposal + Post: columna event_date (fecha real del evento de la noticia).

Permite gestionar contenido ligado a una fecha (conciertos, festivales,
homenajes): antelación de publicación si es futura, caducidad (crónica o
cancelación) si llega pasada. NULL = pieza atemporal.

Revision ID: c2d3e4f5a6b7
Revises: b9c1d2e3f4a5
Create Date: 2026-06-25 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b9c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_proposals",
        sa.Column("event_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("event_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("posts", "event_date")
    op.drop_column("content_proposals", "event_date")
