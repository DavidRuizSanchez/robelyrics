"""Tabla `posts` para la sección blog/noticias.

Modelo unificado para 3 tipos de entrada:
- editorial: artículo manual del admin.
- news:      noticia raspada de fuente externa (whitelist), requiere review.
- anniversary: entrada automática generada por cron (cumple/aniversario).

Revision ID: ab9335b47dbf
Revises: d21b9eb53034
Create Date: 2026-05-17 22:35:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ab9335b47dbf"
down_revision: str | None = "d21b9eb53034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=200), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("hero_image_url", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column("meta_title", sa.String(length=256), nullable=True),
        sa.Column("meta_description", sa.String(length=512), nullable=True),
        sa.Column("anniversary_year", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "kind IN ('editorial', 'news', 'anniversary')",
            name="ck_posts_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'published', 'rejected')",
            name="ck_posts_status",
        ),
    )
    op.create_index("ix_posts_slug", "posts", ["slug"])
    op.create_index("ix_posts_status_published_at", "posts", ["status", "published_at"])
    op.create_index("ix_posts_kind", "posts", ["kind"])


def downgrade() -> None:
    op.drop_table("posts")
