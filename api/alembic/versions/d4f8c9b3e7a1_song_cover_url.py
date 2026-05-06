"""songs.cover_url for singles/EPs/clips with own artwork

Revision ID: d4f8c9b3e7a1
Revises: c8e3f4a5d1b9
Create Date: 2026-05-06 17:50:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f8c9b3e7a1"
down_revision: str | None = "c8e3f4a5d1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "songs",
        sa.Column("cover_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("songs", "cover_url")
