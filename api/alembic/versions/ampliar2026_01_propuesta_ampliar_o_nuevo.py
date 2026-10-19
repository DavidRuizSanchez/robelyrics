"""Una propuesta del blog puede AMPLIAR una página que ya existe.

Criterio de David (19-10-2026): antes de escribir un post por una keyword hay que
mirar si ya hay una página que la responde o que Google ya asocia a ella. Medido
ese día: «integrantes de extremoduro» la posiciona `/personas` (pos 7,5–11) y un
post nuevo la habría canibalizado.

- `content_proposals.placement` guarda el análisis (decisión + candidatos con su
  evidencia), `merge_target` el destino elegido y `merge_opportunity_id` el
  borrador. Estado nuevo `merged`.
- `seo_opportunities` gana la acción `merge` y `proposal_id`.
- `content_revisions`: la copia de la página justo antes de aplicar, que es lo
  que permite revertir de verdad (`before_body` se re-sella y no sirve).
- `/personas` pasa a tener ficha (`entity_type='page'`) para que el motor pueda
  ampliarla. Se siembra con EXACTAMENTE el title, la description, el H1 y la
  intro que tiene hoy en código: es la página que posiciona y no se toca nada.

Revision ID: ampliar2026_01
Revises: clipcancion2026_01
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ampliar2026_01"
down_revision: str | None = "clipcancion2026_01"
branch_labels = None
depends_on = None

PERSONAS_TITLE = "Integrantes de Extremoduro y los colegas de Robe · Entre Interiores"
PERSONAS_DESCRIPTION = (
    "Los integrantes de Extremoduro a lo largo de su historia, la banda solista de "
    "Robe y las voces amigas del universo: quién es quién y qué tocó cada uno."
)
PERSONAS_H1 = "Los colegas de Robe"
PERSONAS_INTRO = (
    "Los miembros que pasaron por Extremoduro y la banda solista, las voces amigas "
    "que el escenario y los discos cruzaron con la suya."
)


def upgrade() -> None:
    op.drop_constraint("ck_content_proposals_status", "content_proposals", type_="check")
    op.create_check_constraint(
        "ck_content_proposals_status", "content_proposals",
        "status IN ('proposed', 'approved', 'scheduled', 'used', 'discarded', 'merged')",
    )
    op.add_column("content_proposals", sa.Column(
        "placement", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("content_proposals", sa.Column("merge_target", sa.String(80), nullable=True))
    op.add_column("content_proposals", sa.Column(
        "merge_opportunity_id", sa.Integer(), nullable=True))

    op.drop_constraint("ck_seo_opportunities_action", "seo_opportunities", type_="check")
    op.create_check_constraint(
        "ck_seo_opportunities_action", "seo_opportunities",
        "action IN ('meta', 'body', 'merge')",
    )
    op.add_column("seo_opportunities", sa.Column("proposal_id", sa.Integer(), nullable=True))

    op.create_table(
        "content_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("meta_title", sa.Text()),
        sa.Column("meta_description", sa.Text()),
        sa.Column("h1", sa.Text()),
        sa.Column("opportunity_id", sa.Integer()),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_content_revisions_target_id", "content_revisions", ["target_id"])
    op.create_index("ix_content_revisions_opportunity_id", "content_revisions",
                    ["opportunity_id"])

    seo = sa.table(
        "seo_content",
        sa.column("entity_type", sa.String), sa.column("entity_id", sa.Integer),
        sa.column("slug", sa.String), sa.column("body_md", sa.Text),
        sa.column("meta_title", sa.String), sa.column("meta_description", sa.String),
        sa.column("h1", sa.String), sa.column("published", sa.Boolean),
        sa.column("generated_by", sa.String),
    )
    conn = op.get_bind()
    existe = conn.execute(sa.text(
        "SELECT 1 FROM seo_content WHERE entity_type = 'page' AND entity_id = 1"
    )).first()
    if not existe:
        op.bulk_insert(seo, [{
            "entity_type": "page", "entity_id": 1, "slug": "personas",
            "body_md": PERSONAS_INTRO, "meta_title": PERSONAS_TITLE,
            "meta_description": PERSONAS_DESCRIPTION, "h1": PERSONAS_H1,
            "published": True, "generated_by": "manual",
        }])


def downgrade() -> None:
    op.execute("DELETE FROM seo_content WHERE entity_type = 'page' AND entity_id = 1")
    op.drop_index("ix_content_revisions_opportunity_id", "content_revisions")
    op.drop_index("ix_content_revisions_target_id", "content_revisions")
    op.drop_table("content_revisions")
    op.drop_column("seo_opportunities", "proposal_id")
    op.drop_constraint("ck_seo_opportunities_action", "seo_opportunities", type_="check")
    op.create_check_constraint(
        "ck_seo_opportunities_action", "seo_opportunities", "action IN ('meta', 'body')")
    op.drop_column("content_proposals", "merge_opportunity_id")
    op.drop_column("content_proposals", "merge_target")
    op.drop_column("content_proposals", "placement")
    op.drop_constraint("ck_content_proposals_status", "content_proposals", type_="check")
    op.create_check_constraint(
        "ck_content_proposals_status", "content_proposals",
        "status IN ('proposed', 'approved', 'scheduled', 'used', 'discarded')",
    )
