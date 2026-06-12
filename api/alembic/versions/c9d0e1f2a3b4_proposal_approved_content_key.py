"""ContentProposal: estado 'approved' + columna content_key (dedup transversal).

Añade el estado intermedio `approved` al ciclo de vida de las propuestas
(proposed → approved → scheduled → used/discarded) y una huella estable
`content_key` para deduplicar entre tipos y semanas, en content_proposals y
posts.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-12 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Estado 'approved' en el CheckConstraint de content_proposals.
    op.drop_constraint(
        "ck_content_proposals_status", "content_proposals", type_="check"
    )
    op.create_check_constraint(
        "ck_content_proposals_status",
        "content_proposals",
        "status IN ('proposed', 'approved', 'scheduled', 'used', 'discarded')",
    )

    # 2. Huella de contenido para dedup transversal.
    op.add_column(
        "content_proposals",
        sa.Column("content_key", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ix_content_proposals_content_key", "content_proposals", ["content_key"]
    )
    op.add_column(
        "posts",
        sa.Column("content_key", sa.String(length=160), nullable=True),
    )
    op.create_index("ix_posts_content_key", "posts", ["content_key"])


def downgrade() -> None:
    op.drop_index("ix_posts_content_key", table_name="posts")
    op.drop_column("posts", "content_key")
    op.drop_index(
        "ix_content_proposals_content_key", table_name="content_proposals"
    )
    op.drop_column("content_proposals", "content_key")

    # Las filas 'approved' deben volver a un estado válido del constraint viejo.
    op.execute(
        "UPDATE content_proposals SET status='proposed' WHERE status='approved'"
    )
    op.drop_constraint(
        "ck_content_proposals_status", "content_proposals", type_="check"
    )
    op.create_check_constraint(
        "ck_content_proposals_status",
        "content_proposals",
        "status IN ('proposed', 'scheduled', 'used', 'discarded')",
    )
