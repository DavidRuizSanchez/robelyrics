"""Libros del universo Extremoduro/Robe (sección /libros): biografías,
ensayos, monográficos y la única novela de Robe. Metadatos bibliográficos
verificables, sembrados desde data/books.yaml (NO generados por LLM). Los
enlaces de compra/afiliado quedan preparados (columna buy_links) pero no se
renderizan todavía.

Revision ID: e3f5a7b9c1d2
Revises: d3e4f5a6b7c8
Create Date: 2026-06-03 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "e3f5a7b9c1d2"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("subtitle", sa.String(300), nullable=True),
        sa.Column("authors", JSONB(), nullable=True),  # ["Javier Menéndez Flores"]
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("publisher", sa.String(200), nullable=True),
        sa.Column("isbn", sa.String(20), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(8), nullable=False, server_default="es"),
        sa.Column("kind", sa.String(20), nullable=False, server_default="biografia"),
        # biografia|ensayo|novela|monografico|poesia
        sa.Column("availability", sa.String(16), nullable=False, server_default="new"),
        # new|secondhand|out_of_print
        sa.Column("cover_url", sa.String(1024), nullable=True),
        sa.Column("cover_attribution", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=True),
        sa.Column("buy_links", JSONB(), nullable=True),  # [{store,url,label}] — afiliados (futuro)
        sa.Column("about", JSONB(), nullable=True),  # ["extremoduro","robe"] → @graph
        sa.Column("meta_title", sa.String(300), nullable=True),
        sa.Column("meta_description", sa.String(400), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("books")
