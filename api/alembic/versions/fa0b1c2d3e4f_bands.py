"""Tabla bands (grupos/sellos afines al universo Robe-Extremoduro).

Espejo de persons para grupos. Su seo_content usa entity_type='band'
(SeoContent.entity_type no tiene CHECK en BD, así que no hay que alterarlo).

Revision ID: fa0b1c2d3e4f
Revises: f9b0c1d2e3f4
Create Date: 2026-06-02 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fa0b1c2d3e4f"
down_revision: str | None = "f9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="band"),
        sa.Column("founded_year", sa.Integer(), nullable=True),
        sa.Column("dissolved_year", sa.Integer(), nullable=True),
        sa.Column("bio_short", sa.Text(), nullable=True),
        sa.Column("wikipedia_url", sa.String(length=500), nullable=True),
        sa.Column("wikidata_id", sa.String(length=20), nullable=True),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("image_attribution", sa.Text(), nullable=True),
        sa.Column("image_license", sa.String(length=64), nullable=True),
        sa.Column("image_source_url", sa.String(length=1024), nullable=True),
        sa.Column("members", postgresql.JSONB(), nullable=True),
        sa.Column("related_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bands_wikidata_id", "bands", ["wikidata_id"])


def downgrade() -> None:
    op.drop_index("ix_bands_wikidata_id", table_name="bands")
    op.drop_table("bands")
