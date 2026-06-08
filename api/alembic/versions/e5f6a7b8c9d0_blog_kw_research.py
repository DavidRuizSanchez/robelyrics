"""KW research del blog: keyword objetivo en Post (anti-canibalización) y
metadatos de long-tail/volumen/señal en ContentProposal.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-08 21:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Post: keyword objetivo (anti-canibalización).
    op.add_column("posts", sa.Column("target_keyword", sa.String(length=160), nullable=True))
    op.add_column("posts", sa.Column("target_keyword_slug", sa.String(length=160), nullable=True))
    op.create_index("ix_posts_target_keyword_slug", "posts", ["target_keyword_slug"])

    # ContentProposal: metadatos del research.
    op.add_column("content_proposals", sa.Column("target_keyword", sa.String(length=160), nullable=True))
    op.add_column("content_proposals", sa.Column("target_keyword_slug", sa.String(length=160), nullable=True))
    op.add_column("content_proposals", sa.Column("search_volume", sa.Integer(), nullable=True))
    op.add_column(
        "content_proposals",
        sa.Column("is_longtail", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("content_proposals", sa.Column("signal_source", sa.String(length=16), nullable=True))
    op.create_index(
        "ix_content_proposals_target_keyword_slug", "content_proposals", ["target_keyword_slug"]
    )


def downgrade() -> None:
    op.drop_index("ix_content_proposals_target_keyword_slug", table_name="content_proposals")
    op.drop_column("content_proposals", "signal_source")
    op.drop_column("content_proposals", "is_longtail")
    op.drop_column("content_proposals", "search_volume")
    op.drop_column("content_proposals", "target_keyword_slug")
    op.drop_column("content_proposals", "target_keyword")

    op.drop_index("ix_posts_target_keyword_slug", table_name="posts")
    op.drop_column("posts", "target_keyword_slug")
    op.drop_column("posts", "target_keyword")
