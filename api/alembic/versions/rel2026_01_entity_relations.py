"""`entity_relations`: las relaciones del JSON-LD, cada una con su fuente.

Plan de datos estructurados, fase 1 (13-11-2026). Tabla nueva y vacía: con ella vacía
el JSON-LD servido no cambia (lo vigila `test_relations.py`).

Revision ID: rel2026_01
Revises: iggate2026_02
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "rel2026_01"
down_revision: str | None = "iggate2026_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(600), nullable=False, unique=True),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("predicate", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(16), nullable=True),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("object_literal", postgresql.JSONB(), nullable=True),
        sa.Column("role_name", sa.String(120), nullable=True),
        sa.Column("start_date", sa.String(10), nullable=True),
        sa.Column("end_date", sa.String(10), nullable=True),
        sa.Column("fuentes", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(12), nullable=False, server_default="pendiente"),
        sa.Column("verified_by", sa.String(64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('verificada', 'pendiente', 'rechazada')",
                           name="ck_entity_relations_status"),
        sa.CheckConstraint("(object_id IS NOT NULL) <> (object_literal IS NOT NULL)",
                           name="ck_entity_relations_objeto"),
    )
    op.create_index("ix_entity_relations_subject", "entity_relations",
                    ["subject_type", "subject_id"])
    op.create_index("ix_entity_relations_object", "entity_relations",
                    ["object_type", "object_id"])


def downgrade() -> None:
    op.drop_index("ix_entity_relations_object", table_name="entity_relations")
    op.drop_index("ix_entity_relations_subject", table_name="entity_relations")
    op.drop_table("entity_relations")
