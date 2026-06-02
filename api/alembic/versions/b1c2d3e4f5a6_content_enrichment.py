"""Enriquecimiento de contenido: bio_long, instruments, trgm en fuentes.

- persons.bio_long / bands.bio_long: artículo completo de Wikipedia (contexto
  para generar contenido específico, no genérico).
- persons.instruments: Wikidata P1303.
- pg_trgm + índice GIN trigram en interpretation_sources.content_clean: para
  buscar fan-content por nombre de persona/grupo.

Revision ID: b1c2d3e4f5a6
Revises: fa0b1c2d3e4f
Create Date: 2026-06-02 13:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "fa0b1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("persons", sa.Column("bio_long", sa.Text(), nullable=True))
    op.add_column(
        "persons",
        sa.Column("instruments", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("bands", sa.Column("bio_long", sa.Text(), nullable=True))
    # pg_trgm para buscar fan-content por nombre. IF NOT EXISTS por si no hay
    # superuser / ya está; el índice es best-effort (búsqueda cae a ILIKE igual).
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_interp_sources_content_trgm "
            "ON interpretation_sources USING gin (content_clean gin_trgm_ops)"
        )
    except Exception:  # noqa: BLE001 — sin superuser: seguimos sin índice
        pass


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_interp_sources_content_trgm")
    op.drop_column("bands", "bio_long")
    op.drop_column("persons", "instruments")
    op.drop_column("persons", "bio_long")
