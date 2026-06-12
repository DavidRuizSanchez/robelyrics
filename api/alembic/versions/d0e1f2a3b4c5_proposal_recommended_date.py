"""ContentProposal: columna recommended_date (fecha sugerida para efemérides).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-12 17:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_proposals",
        sa.Column("recommended_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_proposals", "recommended_date")
