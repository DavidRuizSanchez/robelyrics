"""`content_proposals`: el veredicto del juez de rigor y el motivo de cada descarte.

Plan del blog (18-11-2026). El post del 10.º aniversario de «Destrozares» se escribió
a las 08:00 del día de publicar y el juez lo descartó en ese momento, sin reintento y
sin dejar rastro en la BD: el motivo solo iba en un correo. Medido ese día: 419 de
514 propuestas descartadas y ninguna con su porqué.

- `review_*`: el juicio se hace al preparar el borrador, días antes, y queda guardado.
- `discard_reason` / `discarded_by`: quién descarta (el sistema o una persona) y por qué.

Revision ID: blogjuez2026_01
Revises: ent2026_01
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "blogjuez2026_01"
down_revision: str | None = "ent2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_proposals", sa.Column("review_verdict", sa.String(16), nullable=True))
    op.add_column("content_proposals", sa.Column("review_score", sa.Integer(), nullable=True))
    op.add_column("content_proposals", sa.Column("review_reasons", postgresql.JSONB(),
                                                 nullable=True))
    op.add_column("content_proposals", sa.Column("reviewed_at", sa.DateTime(timezone=True),
                                                 nullable=True))
    op.add_column("content_proposals", sa.Column("review_attempts", sa.Integer(),
                                                 nullable=False, server_default="0"))
    op.add_column("content_proposals", sa.Column("discard_reason", sa.Text(), nullable=True))
    op.add_column("content_proposals", sa.Column("discarded_by", sa.String(32), nullable=True))
    op.add_column("content_proposals", sa.Column("discarded_at", sa.DateTime(timezone=True),
                                                 nullable=True))


def downgrade() -> None:
    for col in ("discarded_at", "discarded_by", "discard_reason", "review_attempts",
                "reviewed_at", "review_reasons", "review_score", "review_verdict"):
        op.drop_column("content_proposals", col)
