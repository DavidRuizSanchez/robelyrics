"""Tabla `content_proposals`: banco de ideas editoriales.

El flujo editorial nuevo:
  GENERAR  → cron crea propuestas ligeras (sin body) de todo el catálogo
  EMAIL    → email semanal al admin con todas las propuestas nuevas
  PROGRAMAR→ el admin asigna fecha a las que quiere (máx 2/semana) desde
             la pestaña /biblioteca/admin/calendario
  PUBLICAR → al llegar la fecha, el materializador genera el body (si
             falta) y crea el Post publicado

Una propuesta `kind='news'` ya trae `body_md` (el scraper lo genera). El
resto (spotlight/evergreen/anniversary/album-anniversary) tienen body NULL
hasta que se materializan.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-20 09:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d6e7f8a9b0"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        # tipo de pieza editorial
        sa.Column("kind", sa.String(length=20), nullable=False),
        # entidad de origen (canción, taxonomía, disco) para regenerar body
        sa.Column("source_type", sa.String(length=16), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        # textos
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("angle", sa.Text(), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("meta_title", sa.String(length=256), nullable=True),
        sa.Column("meta_description", sa.String(length=512), nullable=True),
        sa.Column("hero_image_url", sa.String(length=500), nullable=True),
        sa.Column("hero_image_attribution", sa.Text(), nullable=True),
        sa.Column("hero_image_license", sa.String(length=64), nullable=True),
        sa.Column("hero_image_source_url", sa.String(length=500), nullable=True),
        # solo news
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column(
            "entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # workflow
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("scheduled_for", sa.Date(), nullable=True),
        sa.Column(
            "post_id",
            sa.Integer(),
            sa.ForeignKey("posts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'scheduled', 'used', 'discarded')",
            name="ck_content_proposals_status",
        ),
        sa.CheckConstraint(
            "kind IN ('news', 'spotlight', 'evergreen', 'anniversary', "
            "'album-anniversary')",
            name="ck_content_proposals_kind",
        ),
        # Evita proponer dos veces la misma pieza para la misma entidad
        # mientras la anterior siga viva (proposed/scheduled). Para news,
        # source_url es la clave de dedup (índice parcial aparte).
        sa.UniqueConstraint(
            "kind", "source_type", "source_id",
            name="uq_content_proposals_kind_source",
        ),
    )
    op.create_index(
        "ix_content_proposals_status", "content_proposals", ["status"]
    )
    op.create_index(
        "ix_content_proposals_scheduled_for",
        "content_proposals",
        ["scheduled_for"],
        postgresql_where=sa.text("scheduled_for IS NOT NULL"),
    )
    # Dedup de noticias por URL de fuente
    op.create_index(
        "uq_content_proposals_source_url",
        "content_proposals",
        ["source_url"],
        unique=True,
        postgresql_where=sa.text("source_url IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_content_proposals_source_url", table_name="content_proposals")
    op.drop_index("ix_content_proposals_scheduled_for", table_name="content_proposals")
    op.drop_index("ix_content_proposals_status", table_name="content_proposals")
    op.drop_table("content_proposals")
