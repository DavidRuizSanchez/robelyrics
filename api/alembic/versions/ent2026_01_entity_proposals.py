"""`entity_proposals`: entidades nuevas que salen de las relaciones, para que se decida.

Plan de relaciones (18-11-2026), PR D. Cuando una relación verificada apunta a algo que
no tiene página (la universidad donde estudió Sabina, Úbeda, un miembro de Marea), esa
otra punta se PROPONE aquí con su identificador, las relaciones que la traen y lo que
hay para escribir su ficha. No se crea nada sola: la decide una persona en el panel.

Revision ID: ent2026_01
Revises: rel2026_01
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ent2026_01"
down_revision: str | None = "rel2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(200), nullable=False, unique=True),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("qid", sa.String(20), nullable=True),
        sa.Column("relaciones", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("material", sa.Integer(), nullable=True),
        sa.Column("demanda", postgresql.JSONB(), nullable=True),
        sa.Column("estado", sa.String(12), nullable=False, server_default="propuesta"),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("decidida_por", sa.String(64), nullable=True),
        sa.Column("decidida_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("estado IN ('propuesta', 'aprobada', 'publicada', 'descartada')",
                           name="ck_entity_proposals_estado"),
    )
    op.create_index("ix_entity_proposals_estado", "entity_proposals", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_entity_proposals_estado", table_name="entity_proposals")
    op.drop_table("entity_proposals")
