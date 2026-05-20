"""Taxonomías Fase 2: themes, places, concepts + tablas pivot song_*.

Estas taxonomías habilitan hubs SEO long-tail (/temas/{slug}, /lugares/{slug},
/conceptos/{slug}) y enlazado horizontal entre canciones por motivos
compartidos. Las relaciones son N:M con metadata opcional (peso, contexto).

Revision ID: d21b9eb53034
Revises: d4f8c9b3e7a1
Create Date: 2026-05-17 22:17:59.305344
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d21b9eb53034"
down_revision: str | None = "d4f8c9b3e7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # themes
    op.create_table(
        "themes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_themes_slug", "themes", ["slug"])

    op.create_table(
        "song_themes",
        sa.Column(
            "song_id",
            sa.Integer(),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "theme_id",
            sa.Integer(),
            sa.ForeignKey("themes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("weight", sa.Numeric(4, 2), nullable=False, server_default="1.00"),
    )
    op.create_index("ix_song_themes_theme", "song_themes", ["theme_id"])

    # places
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=True),  # city, country, bar, region…
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("geo_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("geo_lng", sa.Numeric(9, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_places_slug", "places", ["slug"])

    op.create_table(
        "song_places",
        sa.Column(
            "song_id",
            sa.Integer(),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "place_id",
            sa.Integer(),
            sa.ForeignKey("places.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("context", sa.Text(), nullable=True),
    )
    op.create_index("ix_song_places_place", "song_places", ["place_id"])

    # concepts (motivos recurrentes: muerte, libertad, lucha, etc.)
    op.create_table(
        "concepts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_concepts_slug", "concepts", ["slug"])

    op.create_table(
        "song_concepts",
        sa.Column(
            "song_id",
            sa.Integer(),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "concept_id",
            sa.Integer(),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_song_concepts_concept", "song_concepts", ["concept_id"])


def downgrade() -> None:
    op.drop_table("song_concepts")
    op.drop_table("concepts")
    op.drop_table("song_places")
    op.drop_table("places")
    op.drop_table("song_themes")
    op.drop_table("themes")
