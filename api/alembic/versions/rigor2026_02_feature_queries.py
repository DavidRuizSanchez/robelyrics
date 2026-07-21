"""Analítica de uso (F2.4): tabla feature_queries.

Registra qué buscan los usuarios en el buscador semántico, "completar" y listas por
mood (el consultorio ya se registra en consult_questions).

Revision ID: rigor2026_02
Revises: rigor2026_01
Create Date: 2026-07-22 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "rigor2026_02"
down_revision: str | None = "rigor2026_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feature", sa.String(length=24), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("n_results", sa.Integer(), nullable=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feature_queries_feature_created", "feature_queries", ["feature", "created_at"])
    op.create_index("ix_feature_queries_user_id", "feature_queries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feature_queries_user_id", table_name="feature_queries")
    op.drop_index("ix_feature_queries_feature_created", table_name="feature_queries")
    op.drop_table("feature_queries")
