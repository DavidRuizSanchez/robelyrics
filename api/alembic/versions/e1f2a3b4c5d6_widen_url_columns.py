"""Ampliar columnas de URL a 1000 chars (las URLs de Google News superan 500).

Afecta a posts y content_proposals: source_url, hero_image_url,
hero_image_source_url.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-12 17:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLS = [
    ("posts", "source_url"),
    ("posts", "hero_image_url"),
    ("posts", "hero_image_source_url"),
    ("content_proposals", "source_url"),
    ("content_proposals", "hero_image_url"),
    ("content_proposals", "hero_image_source_url"),
]


def upgrade() -> None:
    for table, col in _COLS:
        op.alter_column(
            table, col,
            existing_type=sa.String(length=500),
            type_=sa.String(length=1000),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Trunca a 500 para poder revertir sin desbordar.
    for table, col in _COLS:
        op.execute(f"UPDATE {table} SET {col} = left({col}, 500) WHERE length({col}) > 500")
        op.alter_column(
            table, col,
            existing_type=sa.String(length=1000),
            type_=sa.String(length=500),
            existing_nullable=True,
        )
