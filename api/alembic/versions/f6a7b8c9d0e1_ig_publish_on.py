"""Fecha fija de publicación para contenido de efeméride en la cola de Instagram.

`publish_on`: si está, el item (aniversario de disco, cumpleaños) SOLO se publica
ese día y NO entra en el goteo del cuentagotas.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-08 21:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("instagram_queue", sa.Column("publish_on", sa.Date(), nullable=True))
    op.create_index("ix_instagram_queue_publish_on", "instagram_queue", ["publish_on"])


def downgrade() -> None:
    op.drop_index("ix_instagram_queue_publish_on", table_name="instagram_queue")
    op.drop_column("instagram_queue", "publish_on")
