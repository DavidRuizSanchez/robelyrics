"""Tablas news_items e instagram_queue.

Fase 1 de la unificación de Entre Noticias dentro de entreinteriores.com.

`news_items` es el almacén único de noticias agregadas del universo Robe /
Extremoduro. El agregador lo alimenta y de él beben dos consumidores: el blog
(filtra `policy` con 'blog') y el pipeline de Instagram (usa todas).

`instagram_queue` es la cola de publicaciones para @entreinterioresrobe.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-05-21 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("url", sa.String(length=700), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_medium", sa.String(length=200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("policy", sa.String(length=16), nullable=False),
        sa.Column(
            "relevance_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "consumed_blog",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.CheckConstraint(
            "policy IN ('blog+ig', 'ig-only')",
            name="ck_news_items_policy",
        ),
        sa.UniqueConstraint("url", name="uq_news_items_url"),
    )
    op.create_index("ix_news_items_fetched_at", "news_items", ["fetched_at"])
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])

    op.create_table(
        "instagram_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("news_item_id", sa.Integer(), nullable=True),
        sa.Column("blog_post_id", sa.Integer(), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column("source_url", sa.String(length=700), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=700), nullable=True),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("ig_media_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'prepared', 'published', 'failed', "
            "'discarded')",
            name="ck_instagram_queue_status",
        ),
        sa.ForeignKeyConstraint(
            ["news_item_id"], ["news_items.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["blog_post_id"], ["posts.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_instagram_queue_day", "instagram_queue", ["day"])


def downgrade() -> None:
    op.drop_index("ix_instagram_queue_day", table_name="instagram_queue")
    op.drop_table("instagram_queue")
    op.drop_index("ix_news_items_published_at", table_name="news_items")
    op.drop_index("ix_news_items_fetched_at", table_name="news_items")
    op.drop_table("news_items")
