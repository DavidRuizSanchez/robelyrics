"""Entidades mencionadas por post/seo_content para enriquecer schema.org.

Cada pieza editorial (post de blog, seo_content de artist/album/song/person)
guarda en `entities` la lista de personas, lugares, bandas, discos, ciudades
que se mencionan. El frontend las usa para emitir schema.org `mentions`
con @id locales (cuando la entidad está en nuestro corpus) o @id Wikidata.

Estructura por item:
  {
    "type": str,           # Person | MusicGroup | MusicAlbum |
                           # MusicComposition | Place | TVSeries |
                           # Organization | CreativeWork | ...
    "name": str,           # nombre visible
    "wikidata_id": str | None,
    "slug_hint": str | None,  # pista para el lookup local (slug si
                                el LLM lo conoce; sino el backend
                                normaliza el name)
  }

El backend (publishing.resolve_entities) lo enriquece con `local_url` y
`canonical_id` si encuentra match en el corpus.

Revision ID: a3b4c5d6e7f8
Revises: f2b3c4d5e6f7
Create Date: 2026-05-20 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column(
            "entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "seo_content",
        sa.Column(
            "entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("seo_content", "entities")
    op.drop_column("posts", "entities")
