"""Band.relation_type (family|friend|None): clasifica el vínculo del grupo
con el universo Robe-Extremoduro (familia nacida de Extremoduro vs. amigos
de la escena). Lo usa el generador SEO para ramificar el H2 del "lazo".

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-06-03 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bands", sa.Column("relation_type", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("bands", "relation_type")
