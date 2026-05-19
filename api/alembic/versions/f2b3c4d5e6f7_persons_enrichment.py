"""Enriquecimiento de `persons` con datos Wikidata sin tablas nuevas.

Añade 3 columnas JSONB que se rellenan desde claims de Wikidata en
`scripts/seed_persons.py`:

  - `other_bands`: bandas/proyectos donde la persona es/fue miembro pero
    que NO están en nuestro Artist corpus (Extremoduro/Robe). Estructura:
      [
        {"name": str, "wikidata_id": str, "wikidata_url": str,
         "wikipedia_url": str | None}
      ]
  - `notable_works`: obras notables (canciones, discos, libros, programas)
    asociadas a la persona en Wikidata. Estructura: misma forma.
  - `occupations`: roles/profesiones (vocalista, guitarrista, compositor…)

Estos campos enriquecen el schema.org Person.memberOf con @id externos
(Wikidata) sin necesitar Artists adicionales en nuestro corpus.

Revision ID: f2b3c4d5e6f7
Revises: e1a2b3c4d5e6
Create Date: 2026-05-20 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2b3c4d5e6f7"
down_revision: str | None = "e1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "persons",
        sa.Column(
            "other_bands",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "persons",
        sa.Column(
            "notable_works",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "persons",
        sa.Column(
            "occupations",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("persons", "occupations")
    op.drop_column("persons", "notable_works")
    op.drop_column("persons", "other_bands")
