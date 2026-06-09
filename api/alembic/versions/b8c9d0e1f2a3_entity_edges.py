"""Grafo de conocimiento unificado: tabla entity_edges.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-10 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("src_type", sa.String(length=16), nullable=False),
        sa.Column("src_id", sa.Integer(), nullable=False),
        sa.Column("src_slug", sa.String(length=180), nullable=False),
        sa.Column("edge_type", sa.String(length=32), nullable=False),
        sa.Column("dst_type", sa.String(length=16), nullable=False),
        sa.Column("dst_id", sa.Integer(), nullable=False),
        sa.Column("dst_slug", sa.String(length=180), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "src_type", "src_id", "edge_type", "dst_type", "dst_id",
            name="uq_entity_edges",
        ),
    )
    op.create_index("ix_entity_edges_src", "entity_edges", ["src_type", "src_id"])
    op.create_index("ix_entity_edges_dst", "entity_edges", ["dst_type", "dst_id"])
    op.create_index("ix_entity_edges_type", "entity_edges", ["edge_type"])


def downgrade() -> None:
    op.drop_index("ix_entity_edges_type", table_name="entity_edges")
    op.drop_index("ix_entity_edges_dst", table_name="entity_edges")
    op.drop_index("ix_entity_edges_src", table_name="entity_edges")
    op.drop_table("entity_edges")
