"""Tabla `subscribers` para newsletter + columna `posts.newsletter_sent_at`.

Doble opt-in (RGPD): pending → confirmed por email; unsubscribe siempre con
token único en cada email. Conserva filas tras unsubscribe (compliance).

Revision ID: 5ee24c23d924
Revises: ab9335b47dbf
Create Date: 2026-05-18 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5ee24c23d924"
down_revision: str | None = "ab9335b47dbf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=256), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("confirm_token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "subscribed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'unsubscribed', 'bounced')",
            name="ck_subscribers_status",
        ),
    )
    op.create_index("ix_subscribers_status", "subscribers", ["status"])

    op.add_column(
        "posts",
        sa.Column("newsletter_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_posts_newsletter_sent_at",
        "posts",
        ["newsletter_sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_posts_newsletter_sent_at", table_name="posts")
    op.drop_column("posts", "newsletter_sent_at")
    op.drop_index("ix_subscribers_status", table_name="subscribers")
    op.drop_table("subscribers")
