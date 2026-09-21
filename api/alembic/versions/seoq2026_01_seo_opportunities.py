"""Cola de oportunidades SEO con aprobación en dos fases.

Hasta ahora el correo de los lunes («N URLs con oportunidad SEO») era solo un
informe: `gsc_optimize` corría sin `--apply` y el único CTA era un texto pidiendo
ejecutar un comando a mano. No había cola, ni endpoint, ni pantalla, así que
ninguna oportunidad llegaba nunca a aplicarse.

Esta tabla sostiene el circuito acordado: el primer clic aprueba el diagnóstico y
el motor prepara un borrador SIN publicar; un segundo correo enseña el antes/después
y solo entonces se aplica.

El índice único es PARCIAL: impide duplicar una oportunidad VIVA para la misma URL
y acción, pero deja pasar las históricas (`applied`, `discarded`, `noop`), que son
el registro de lo que ya se decidió.

Revision ID: seoq2026_01
Revises: igblock2026_01
Create Date: 2026-09-21 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "seoq2026_01"
down_revision: str | None = "igblock2026_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seo_opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False,
                  server_default="detected"),
        sa.Column("entity_type", sa.String(length=24), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("seo_content_id", sa.Integer(), nullable=True),
        sa.Column("queries", sa.JSON(), nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period", sa.String(length=32), nullable=True),
        sa.Column("gap_hint", sa.Text(), nullable=True),
        sa.Column("before_title", sa.Text(), nullable=True),
        sa.Column("before_description", sa.Text(), nullable=True),
        sa.Column("before_body", sa.Text(), nullable=True),
        sa.Column("draft_title", sa.Text(), nullable=True),
        sa.Column("draft_description", sa.Text(), nullable=True),
        sa.Column("draft_body", sa.Text(), nullable=True),
        sa.Column("draft_notes", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drafted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_drafted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('detected', 'approved', 'drafted', 'applied', "
            "'discarded', 'noop', 'failed')",
            name="ck_seo_opportunities_status",
        ),
        sa.CheckConstraint(
            "action IN ('meta', 'body')", name="ck_seo_opportunities_action"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seo_opportunities_path", "seo_opportunities", ["path"])
    op.create_index("ix_seo_opportunities_status", "seo_opportunities", ["status"])
    op.create_index(
        "uq_seo_opportunities_abierta",
        "seo_opportunities",
        ["path", "action"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('detected', 'approved', 'drafted', 'failed')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_seo_opportunities_abierta", table_name="seo_opportunities")
    op.drop_index("ix_seo_opportunities_status", table_name="seo_opportunities")
    op.drop_index("ix_seo_opportunities_path", table_name="seo_opportunities")
    op.drop_table("seo_opportunities")
