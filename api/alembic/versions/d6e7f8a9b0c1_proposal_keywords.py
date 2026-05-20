"""Añade `keywords` JSONB a content_proposals.

Cada propuesta SEO-driven guarda las keywords objetivo con su volumen de
búsqueda (de DataForSEO), para mostrarlas en el calendario y el email y
para que el generador del artículo las use al redactar.

Estructura: [{"keyword": str, "volume": int, "cpc": float|null,
              "competition": float|null}]

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-20 10:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_proposals",
        sa.Column(
            "keywords",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("content_proposals", "keywords")
